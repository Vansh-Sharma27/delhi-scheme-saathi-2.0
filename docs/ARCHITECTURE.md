# Architecture

Delhi Scheme Saathi is a Python 3.11 FastAPI application for welfare-scheme guidance through Telegram and a direct chat API. It supports Hindi, English, and Hinglish. It provides recommendations and application guidance; it does not submit applications or transfer a conversation to a human operator.

## Migration state

Phase 4 domain extraction is implemented and locally verified. Remote review and merge remain pending. Canonical domain values and infrastructure adapters live under `src/dss`; conversation orchestration, rendering, HTTP routes, and composition wiring still live in their existing packages pending Phases 5 and 6.

| Area | Current implementation |
| --- | --- |
| Domain profiles and required-field policy | `src/dss/domain/profiles/` |
| Domain schemes, documents, offices, rejection rules | `src/dss/domain/schemes/` |
| Conversation state, session, memory, shared clock type | `src/dss/domain/conversations/` |
| Eligibility evaluation | `src/dss/domain/eligibility/evaluator.py` |
| Application ports | `src/dss/application/ports/` |
| SQL repositories, pool-holding adapters, catalog loading, scheme hydration | `src/dss/infrastructure/database/` |
| Session stores, clock adapter, persisted-state repair | `src/dss/infrastructure/sessions/` |
| Queue adapters and payload codec | `src/dss/infrastructure/queues/` |
| AI providers and unchanged prompt templates | `src/dss/infrastructure/ai/` |
| Embeddings and speech adapters | `src/dss/infrastructure/embeddings/`, `src/dss/infrastructure/speech/` |
| Conversation pipeline and rendering | `src/services/conversation/`, `src/services/response_generator.py` |
| Matching orchestration | `src/services/scheme_matcher.py` |
| FastAPI routes and Telegram handling | `src/main.py`, `src/webhook/handler.py` |
| Settings and credential redaction | `src/config.py`, `src/utils/logging_config.py` |

Import-linter enforces three contracts: the six-module conversation order, the modular-monolith layer direction, and the restriction on new `src.dss` imports of legacy wiring. The remaining legacy exception permits infrastructure to read `src.config`. Type-checking imports are visible to the contracts.

Domain code imports no application, infrastructure, or legacy project modules. Infrastructure supplies catalog values to the pure required-fields policy. The application clock import re-exports the domain `Clock` Protocol with the same type identity.

Legacy `src/db`, provider, model, prompt-loader, and catalog paths remain compatibility surfaces until Phase 6. Legacy `Session`, `UserProfile`, and `Scheme` subclasses retain standalone hydration and no-argument catalog helpers. Production services and ports use canonical domain types.

## Four consumer surfaces

| Surface | Entrypoint | Lifecycle |
| --- | --- | --- |
| Container API | `src/main.py`, started by `scripts/container_start.py` | FastAPI lifespan creates the database pool and starts the local background worker when configured |
| Lambda API | `src.lambda_handler.handler` | Mangum currently uses `lifespan="auto"`; final lifecycle separation is Phase 6 work |
| SQS worker | `src.memory_worker_handler.handler` | Processes working-memory messages and reports batch failures |
| Operational scripts | `scripts/fork_session.py` and other utilities | Use current import surfaces; session inspection requires a shared store |

The SAM template defines API Gateway, the API and worker Lambdas, DynamoDB sessions, SQS with a dead-letter queue, an audio bucket, logs, and an error alarm. PostgreSQL is supplied through `DatabaseUrl`; SAM does not provision RDS. Docker Compose provides PostgreSQL 16 with pgvector and the application for local use.

## Conversation handling

The LLM proposes and deterministic rules decide. Plain-language topic, action, and scheme references override conflicting LLM output. The conversation package dependency order is `service`, `views`, `turn_policy`, `intents`, `scheme_reference`, then `language`, from highest to lowest.

The ten states are `GREETING`, `SITUATION_UNDERSTANDING`, `PROFILE_COLLECTION`, `SCHEME_MATCHING`, `SCHEME_PRESENTATION`, `SCHEME_DETAILS`, `DOCUMENT_GUIDANCE`, `REJECTION_WARNINGS`, `APPLICATION_HELP`, and `CSC_HANDOFF`. The four scheme views can move between one another and back to the list. `src/services/fsm.py` owns the transition table.

`ConversationState(str, Enum)` retains six aliases: `UNDERSTANDING`, `MATCHING`, `PRESENTING`, `DETAILS`, `APPLICATION`, and `HANDOFF`. Infrastructure repairs older persisted string values on read. The enum remains a plain string-valued Enum rather than StrEnum.

Profile collection requires a topic first, then age and annual income. Gender and category are requested only when relevant catalog schemes use them. This policy does not add BPL, residency, employment, or disability checks. Deterministic extraction and validation merge with LLM-proposed profile fields.

## Matching and eligibility

The exact matching order is:

1. Retrieve SQL-filtered candidates. Canonical catalog IDs take precedence over database life-event tags. SQL checks age bounds and maximum income when profile values are present.
2. Evaluate every candidate in the domain.
3. Apply topic consistency, falling back to the scheme's runtime life events when canonical metadata is unavailable.
4. Drop candidates with any eligibility field equal to `False`.
5. Rank survivors.
6. Truncate to the requested limit.

Retrieval fetches `max(limit * 3, 10)` candidates. It orders by pgvector cosine distance when a valid embedding exists, otherwise by `benefits_amount DESC NULLS LAST`. The matcher accepts only 1024-dimensional embeddings. Embedding failure disables vector ranking rather than sending a malformed vector.

Ranking uses 0.4 times similarity, 0.4 times the evaluated-field match rate, and 0.2 times benefit amount normalized against ten lakh and capped at one. The domain evaluator checks age, gender, caste category, and income/income-segment rules. Residency, employment, education, BPL, disability, other conditions, and special-focus groups are stored but currently omitted from evaluation. Matching is not a final eligibility determination.

Optional AI relevance judging follows deterministic matching. Presentation and clarification thresholds remain 0.6 and 0.45. The judge-skip score and score-gap settings remain 0.85 and 0.15. Legacy evaluated `hybrid_search` and `_calculate_eligibility_match` remain compatibility paths.

## Providers and failure handling

- LLM: Bedrock is preferred when `USE_BEDROCK=true`; Grok is used when configured as the fallback or primary local provider. The default Bedrock identifier is `global.amazon.nova-2-lite-v1:0`; this does not establish India-only processing.
- Embeddings: Jina `jina-embeddings-v3` is primary, Voyage `voyage-multilingual-2` is fallback, then vector ranking is skipped.
- Speech: the webhook selects Sarvam when its key exists, otherwise Bhashini when configured. It does not retry Bhashini automatically after a selected Sarvam client fails. Unavailable or low-confidence speech requests fall back to text; the confidence threshold is 0.5.
- Telegram: text and inline keyboards are sent through the existing client. TTS audio is sent directly as bytes; the current response path does not upload audio to S3. Text above 900 characters skips TTS.

`AIOrchestrator` applies timeouts of 8 seconds for analysis, 3 seconds for relevance judging, 8 seconds for response generation, and 20 seconds for background memory refresh. It records task telemetry and returns task-specific safe outputs on failure. A missing API database pool produces `503`; `/health` reports database state in its JSON response, including disconnected or error states.

## Persistence and memory

Scheme, eligibility, document, office, rejection-rule, candidate, and match models are frozen Pydantic models. `UserProfile`, `Session`, and `ConversationMemory` are mutable values with copy/merge helpers.

Sessions retain the last 12 messages, or six completed turns, and working memory containing a summary, profile facts, active schemes, pending action, and last goal. Background refresh is triggered by the configured turn interval or the estimated context-size threshold. Defaults are eight turns and approximately 6000 tokens. Queue and worker policy remains in `src/services/ai_background.py`.

An injected clock is private session state and is excluded from serialization. Copies and resets preserve its identity. `Session.copy_with` supplies the default update timestamp. DynamoDB saves preserve `updated_at`; in-memory saves refresh it. DynamoDB TTL is an integer timestamp derived from `updated_at` plus seven days. Reads do not themselves reject an expired item, and DynamoDB deletion is asynchronous.

The database schema is `scripts/init-db/01-schema.sql`. It includes schemes, documents, offices, rejection rules, and life-event taxonomy; scheme vectors have 1024 dimensions with a cosine HNSW index. There is no schema migration framework. Bundled metadata can override scheme tags during hydration but is not a replacement database during an outage.

## Security boundaries and known limits

`POST /api/chat` prefixes caller-supplied IDs with `api:` before accessing the store. It cannot resume a Telegram user's session with the same numeric ID. `CHAT_API_KEY`, when configured, adds a constant-time header check. Telegram webhook verification depends on a non-empty `TELEGRAM_WEBHOOK_SECRET`. The current Compose and SAM definitions do not supply these two secrets.

Credential redaction attaches filters to logging handlers. It does not establish that all personal data is excluded from logs; existing paths still log session identifiers, profile details, or transcripts. Other retained limitations include whole-item session writes without concurrency protection, no Telegram update deduplication, no application rate limiter, and seed timestamps that do not preserve source verification dates.

## Verification

Tests live under `tests/`. The golden corpus covers 14 synthetic scenarios with exact response and session comparisons. It supplies synthetic evaluated facts at the evaluation seam; separate SQL, operation-order, and evaluator-equivalence tests exercise the extracted boundaries. Hypothesis compares the domain evaluator with an independent frozen original across generated profiles and schemes.

CI runs Python 3.11.16 with pinned dependencies, pytest, Ruff, import-linter, dependency synchronization, executable-bit checks, a mypy fingerprint delta, and a locked dependency audit. CodeQL runs in a separate workflow. CI does not deploy the application. Historical baseline counts are recorded in `docs/migration/BASELINE.md`; they are not the current suite size.
