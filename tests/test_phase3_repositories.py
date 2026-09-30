"""Repository adapters preserve pool binding, arguments, and return identity."""

import inspect
from unittest.mock import AsyncMock, Mock

import asyncpg
import pytest

from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.infrastructure.database import adapters


@pytest.mark.asyncio
async def test_postgres_adapters_forward_every_port_method(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = Mock(spec=asyncpg.Pool)
    for adapter_type, port, module in (
        (adapters.PostgresSchemeRepository, SchemeRepository, adapters.scheme_repo),
        (adapters.PostgresDocumentRepository, DocumentRepository, adapters.document_repo),
        (adapters.PostgresOfficeRepository, OfficeRepository, adapters.office_repo),
        (adapters.PostgresRejectionRuleRepository, RejectionRuleRepository, adapters.rejection_rule_repo),
    ):
        adapter = adapter_type(pool)
        assert isinstance(adapter, port)
        for name, method in vars(port).items():
            if name.startswith("_") or not inspect.iscoroutinefunction(method):
                continue
            parameters = list(inspect.signature(method).parameters.values())[1:]
            actual = list(inspect.signature(getattr(adapter, name)).parameters.values())
            assert [(p.name, p.kind, p.default) for p in actual] == [
                (p.name, p.kind, p.default) for p in parameters
            ]
            args = [object() for _ in parameters]
            result = object()
            function = AsyncMock(return_value=result)
            monkeypatch.setattr(module, name, function)
            assert await getattr(adapter, name)(*args) is result
            function.assert_awaited_once_with(pool, *args)
            required = [p for p in parameters if p.default is inspect.Parameter.empty]
            defaults = [p.default for p in parameters if p.default is not inspect.Parameter.empty]
            function.reset_mock()
            await getattr(adapter, name)(*args[:len(required)])
            function.assert_awaited_once_with(pool, *args[:len(required)], *defaults)
