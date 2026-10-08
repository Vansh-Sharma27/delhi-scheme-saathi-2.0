"""Typed HTTP dependencies supplied by an entrypoint-owned application graph."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.dss.application.conversation.contracts import ChatRequest, ChatResponse
from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.settings import Settings


@dataclass(frozen=True)
class APIDependencies:
    settings: Settings
    schemes: SchemeRepository | None
    documents: DocumentRepository | None
    offices: OfficeRepository | None
    rules: RejectionRuleRepository | None
    chat: Callable[[ChatRequest], Awaitable[ChatResponse]]
    telegram: Callable[[dict[str, Any]], Awaitable[dict[str, str]]]
