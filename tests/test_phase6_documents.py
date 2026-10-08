"""Document traversal keeps branch-local visited sets and the original depth guard."""

from unittest.mock import AsyncMock

from src.dss.application.guidance.documents import resolve_document_chain
from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.domain.schemes.document import Document


async def test_document_traversal_keeps_shared_prerequisites_and_stops_cycles() -> None:
    graph = {name: Document(
        id=name, name=name, name_hindi=name, issuing_authority="synthetic",
        prerequisites=prerequisites,
    ) for name, prerequisites in {
        "root": ["left", "right"], "left": ["shared"],
        "right": ["shared"], "shared": ["root"],
    }.items()}
    repository = AsyncMock(spec=DocumentRepository)
    repository.get_document_by_id.side_effect = graph.get
    chain = await resolve_document_chain(repository, "root")
    assert [child.document.id for child in chain.prerequisites] == ["left", "right"]
    for child in chain.prerequisites:
        assert child.prerequisites[0].document.id == "shared"
        assert child.prerequisites[0].prerequisites == []
    assert await resolve_document_chain(repository, "missing") is None
    before = repository.get_document_by_id.await_count
    assert await resolve_document_chain(repository, "root", depth=6) is None
    assert repository.get_document_by_id.await_count == before
