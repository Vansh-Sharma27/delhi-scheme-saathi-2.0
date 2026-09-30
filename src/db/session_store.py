"""Re-export facade for the session stores moved in Phase 3.

Canonical home: ``src.dss.infrastructure.sessions.session_store``. This module forwards the public names so existing imports keep working; it is deleted in Phase 6 (spec 2.1, 2.3 contract step). The configured-store singleton lives in the canonical module; callers that reset it for tests import the canonical module directly.
"""

from src.dss.application.ports.session_repository import (
    SessionStore as SessionStore,
)
from src.dss.infrastructure.sessions.session_store import (
    DynamoDBSessionStore as DynamoDBSessionStore,
)
from src.dss.infrastructure.sessions.session_store import (
    InMemorySessionStore as InMemorySessionStore,
)
from src.dss.infrastructure.sessions.session_store import (
    configure_session_store as configure_session_store,
)
from src.dss.infrastructure.sessions.session_store import (
    get_session_store as get_session_store,
)
