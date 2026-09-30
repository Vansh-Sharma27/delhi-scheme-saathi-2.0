"""Re-export facade for the document repository moved in Phase 3.

Canonical home: ``src.dss.infrastructure.database.document_repo``. This
module forwards the public names so existing imports keep working; it is
deleted in Phase 6 (spec 2.1, 2.3 contract step). The pool-holding adapter
implementing the ``DocumentRepository`` port is
``src.dss.infrastructure.database.adapters.PostgresDocumentRepository``.
"""

from src.dss.infrastructure.database.document_repo import (
    get_all_documents as get_all_documents,
)
from src.dss.infrastructure.database.document_repo import (
    get_document_by_id as get_document_by_id,
)
from src.dss.infrastructure.database.document_repo import (
    get_documents_by_ids as get_documents_by_ids,
)
from src.dss.infrastructure.database.document_repo import (
    get_documents_for_scheme as get_documents_for_scheme,
)
from src.dss.infrastructure.database.document_repo import (
    search_documents as search_documents,
)
