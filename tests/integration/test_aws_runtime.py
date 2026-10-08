"""Opt-in boto3 tests against a disposable Docker moto server (no moto package).

Run the test container on dss-phase6-test with
DSS_INTEGRATION_AWS_ENDPOINT_URL=http://phase6-aws:5000 and the existing app/dev
dependencies installed. The server must be ready before pytest starts. Each
test creates and deletes its own table and queue; TTL expiry is not enabled.
Only synthetic data and dummy AWS credentials are used; no LLM is called.
"""

import asyncio
import json
import os
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
import pytest

from src.dss.application.ports.work_queue import AIWorkItem, AIWorkType
from src.dss.bootstrap import memory_worker, runtime
from src.dss.domain.conversations.session import ConversationMemory, Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.infrastructure.queues.work_queue import SQSAIWorkQueue
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore
from src.dss.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DSS_INTEGRATION_AWS_ENDPOINT_URL"),
    reason="Set DSS_INTEGRATION_AWS_ENDPOINT_URL to a disposable moto server",
)

REGION = "ap-south-1"
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class FixedClock:
    def now(self):
        return NOW


@pytest.fixture
def endpoint_url(monkeypatch):
    endpoint = os.environ["DSS_INTEGRATION_AWS_ENDPOINT_URL"]
    parsed = urlsplit(endpoint)
    assert parsed.scheme in {"http", "https"} and parsed.hostname
    for name, value in {
        "AWS_ENDPOINT_URL": endpoint,
        "AWS_ENDPOINT_URL_DYNAMODB": endpoint,
        "AWS_ENDPOINT_URL_SQS": endpoint,
        "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "false",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": REGION,
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    # Discard cached credentials from earlier tests while retaining real boto3.
    monkeypatch.setattr(boto3, "DEFAULT_SESSION", None)
    return endpoint


@pytest.fixture
def aws_resources(endpoint_url):
    name = f"dss-integration-{uuid4().hex}"
    # ExitStack runs every cleanup even if setup or another cleanup raises.
    with ExitStack() as cleanup:
        dynamodb = boto3.resource("dynamodb", region_name=REGION, endpoint_url=endpoint_url)
        cleanup.callback(dynamodb.meta.client.close)
        table = dynamodb.create_table(
            TableName=name,
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        cleanup.callback(table.delete)
        table.wait_until_exists(WaiterConfig={"Delay": 1, "MaxAttempts": 10})
        sqs = boto3.client("sqs", region_name=REGION, endpoint_url=endpoint_url)
        cleanup.callback(sqs.close)
        queue_url = sqs.create_queue(QueueName=name)["QueueUrl"]
        cleanup.callback(sqs.delete_queue, QueueUrl=queue_url)
        store = DynamoDBSessionStore(name, REGION, clock=FixedClock())
        cleanup.callback(store.close)
        queue = SQSAIWorkQueue(queue_url, REGION)
        cleanup.callback(lambda: asyncio.run(queue.close()))
        yield table, sqs, queue_url, store, queue


async def test_dynamodb_roundtrip_clocks_serialization_and_legacy_states(aws_resources):
    table, _, _, store, _ = aws_resources
    session = Session(
        user_id="synthetic-session",
        state=ConversationState.DETAILS,
        user_profile=UserProfile(age=30, annual_income=50000, life_event="HOUSING"),
        working_memory=ConversationMemory(summary="synthetic summary", profile_facts=["test fact"]),
        discussed_schemes=["DSS-TEST-001"],
        selected_scheme_id="DSS-TEST-001",
        language_preference="hi",
        language_locked=True,
        currently_asking="district",
        skipped_fields=["category"],
        awaiting_profile_change=True,
        presented_schemes=[{"id": "DSS-TEST-001", "name": "Synthetic scheme"}],
        completed_turn_count=8,
        last_memory_refresh_turn=4,
        pending_memory_job=True,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(hours=1),
        metadata={"synthetic": True, "nested": {"count": 2}},
    ).with_clock(store._clock)
    session = session.add_message("user", "synthetic नमस्ते")
    # An explicit older timestamp must survive save; the store must not restamp it.
    session = session.copy_with(updated_at=NOW - timedelta(minutes=1))
    assert await store.get(session.user_id) is None
    await store.save(session)
    raw = table.get_item(Key={"user_id": session.user_id}, ConsistentRead=True)["Item"]
    assert raw["state"] == "SCHEME_DETAILS"
    assert raw["created_at"] == session.created_at.isoformat()
    assert raw["updated_at"] == session.updated_at.isoformat()
    assert raw["messages"][0]["timestamp"] == NOW.isoformat()
    assert raw["ttl"] == int(session.updated_at.timestamp()) + 7 * 86400
    assert "clock" not in raw and "_clock" not in raw
    loaded = await store.get(session.user_id)
    assert loaded is not None
    assert loaded.model_dump() == session.model_dump()
    assert loaded.clock is store._clock
    changed = loaded.add_message("assistant", "synthetic reply")
    assert changed.updated_at == changed.messages[-1].timestamp == NOW
    assert len(loaded.messages) == 1
    await store.save(changed)
    assert (await store.get(session.user_id)).model_dump() == changed.model_dump()

    for state, profile, expected in (
        ("MATCHING", {}, ConversationState.SCHEME_MATCHING),
        ("PRESENTING", {}, ConversationState.SCHEME_PRESENTATION),
        ("DETAILS", {}, ConversationState.SCHEME_DETAILS),
        ("APPLICATION", {}, ConversationState.APPLICATION_HELP),
        ("HANDOFF", {}, ConversationState.CSC_HANDOFF),
        ("UNDERSTANDING", {}, ConversationState.SITUATION_UNDERSTANDING),
        ("UNDERSTANDING", {"life_event": "HOUSING"}, ConversationState.PROFILE_COLLECTION),
    ):
        table.put_item(Item={"user_id": "synthetic-legacy", "state": state, "user_profile": profile})
        legacy = await store.get("synthetic-legacy")
        assert legacy.state is expected
        assert legacy.created_at == legacy.updated_at == NOW
        assert legacy.clock is store._clock
        await store.save(legacy)
        assert table.get_item(Key={"user_id": legacy.user_id}, ConsistentRead=True)["Item"]["state"] == expected.value
    await store.delete(session.user_id)
    await store.delete("synthetic-legacy")
    assert await store.get(session.user_id) is None
    assert await store.get("synthetic-legacy") is None


async def test_sqs_enqueue_dequeue_and_ack(aws_resources):
    _, sqs, queue_url, _, queue = aws_resources
    item = AIWorkItem(AIWorkType.REFRESH_WORKING_MEMORY, "synthetic-queue", 8, NOW)
    await queue.enqueue(item)
    received = await queue.dequeue()  # Already queued: do not long-poll an empty queue.
    assert received is not None and received.receipt_handle
    assert received.work_type is item.work_type
    assert received.user_id == item.user_id
    assert received.turn_count == item.turn_count
    assert received.enqueued_at == item.enqueued_at
    await queue.ack(received)
    counts = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    assert counts["ApproximateNumberOfMessages"] == "0"
    assert counts["ApproximateNumberOfMessagesNotVisible"] == "0"
    assert not sqs.receive_message(QueueUrl=queue_url, WaitTimeSeconds=0).get("Messages")


def test_worker_two_warm_invocations_persist_and_report_partial_errors(aws_resources, monkeypatch):
    table, sqs, queue_url, store, queue = aws_resources
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    settings = Settings(
        _env_file=None, session_table_name=table.name, aws_region=REGION,
        use_bedrock=False, xai_api_key="", ai_memory_queue_backend="sqs",
        ai_memory_queue_url=queue_url,
    )
    monkeypatch.setattr(memory_worker, "get_settings", lambda: settings)
    calls = []
    builds = []

    class FakeAI:
        async def refresh_working_memory(self, session, *, queue_lag_ms):
            assert queue_lag_ms >= 0
            calls.append((session.completed_turn_count, session.working_memory.summary))
            return ConversationMemory(summary=f"synthetic refresh {session.completed_turn_count}")

    def build_ai(actual_settings, client):
        assert actual_settings is settings
        builds.append(client)
        return FakeAI()

    monkeypatch.setattr(runtime, "build_ai", build_ai)
    session = Session(user_id="synthetic-worker", created_at=NOW, updated_at=NOW)
    for turn in (8, 9):
        session = session.copy_with(completed_turn_count=turn, pending_memory_job=True)
        asyncio.run(store.save(session))
        asyncio.run(queue.enqueue(AIWorkItem(
            AIWorkType.REFRESH_WORKING_MEMORY, session.user_id, turn, NOW,
        )))
        messages = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=0,
        ).get("Messages", [])
        assert len(messages) == 1
        message = messages[0]
        event = {"Records": [
            {"messageId": "synthetic-bad-json", "body": "{"},
            {"messageId": message["MessageId"], "body": message["Body"]},
            {"messageId": "synthetic-bad-type", "body": json.dumps({
                "work_type": "synthetic-invalid", "user_id": "synthetic-invalid",
            })},
            # A duplicate valid record must not refresh memory twice.
            {"messageId": "synthetic-duplicate", "body": message["Body"]},
        ]}
        assert memory_worker.handler(event, None) == {"batchItemFailures": [
            {"itemIdentifier": "synthetic-bad-json"},
            {"itemIdentifier": "synthetic-bad-type"},
        ]}
        session = asyncio.run(store.get(session.user_id))
        assert session is not None
        assert session.working_memory.summary == f"synthetic refresh {turn}"
        assert session.last_memory_refresh_turn == session.completed_turn_count == turn
        assert session.pending_memory_job is False
        assert session.created_at == NOW and session.updated_at > NOW
        raw = table.get_item(Key={"user_id": session.user_id}, ConsistentRead=True)["Item"]
        assert raw["working_memory"]["summary"] == f"synthetic refresh {turn}"
        assert raw["pending_memory_job"] is False
        # Lambda's event source normally deletes successful SQS records.
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
    assert calls == [(8, None), (9, "synthetic refresh 8")]
    assert len(builds) == 2 and builds[0] is not builds[1]
