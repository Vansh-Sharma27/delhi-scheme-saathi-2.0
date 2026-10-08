"""Temporary pool adaptation for the port-driven document resolver."""

import asyncpg

from src.dss.application.guidance import documents
from src.dss.application.guidance.documents import MAX_CHAIN_DEPTH as MAX_CHAIN_DEPTH
from src.dss.application.guidance.documents import format_document_guide as format_document_guide
from src.dss.application.guidance.documents import generate_document_card as generate_document_card
from src.dss.application.guidance.documents import get_procurement_order as get_procurement_order
from src.dss.domain.schemes.document import DocumentChain
from src.dss.infrastructure.database.adapters import PostgresDocumentRepository


async def resolve_document_chain(
    pool: asyncpg.Pool, document_id: str,
    visited: set[str] | None = None, depth: int = 0,
) -> DocumentChain | None:
    return await documents.resolve_document_chain(
        PostgresDocumentRepository(pool), document_id, visited, depth,
    )


async def resolve_documents_for_scheme(
    pool: asyncpg.Pool, document_ids: list[str],
) -> list[DocumentChain]:
    return await documents.resolve_documents_for_scheme(PostgresDocumentRepository(pool), document_ids)
