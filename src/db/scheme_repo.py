"""Re-export facade for the scheme repository moved in Phase 3.

Canonical home: ``src.dss.infrastructure.database.scheme_repo``. This module
forwards the public names so existing imports keep working; it is deleted in
Phase 6 (spec 2.1, 2.3 contract step). The pool-holding adapter implementing
the ``SchemeRepository`` port is
``src.dss.infrastructure.database.adapters.PostgresSchemeRepository``.
"""

from src.dss.infrastructure.database.scheme_repo import (
    INCOME_SEGMENT_ORDER as INCOME_SEGMENT_ORDER,
)
from src.dss.infrastructure.database.scheme_repo import (
    _calculate_eligibility_match as _calculate_eligibility_match,
)
from src.dss.infrastructure.database.scheme_repo import (
    calculate_eligibility_match as calculate_eligibility_match,
)
from src.dss.infrastructure.database.scheme_repo import (
    get_all_schemes as get_all_schemes,
)
from src.dss.infrastructure.database.scheme_repo import (
    get_scheme_by_id as get_scheme_by_id,
)
from src.dss.infrastructure.database.scheme_repo import (
    get_scheme_debug_rows as get_scheme_debug_rows,
)
from src.dss.infrastructure.database.scheme_repo import (
    get_schemes_by_life_event as get_schemes_by_life_event,
)
from src.dss.infrastructure.database.scheme_repo import (
    hybrid_search as hybrid_search,
)
from src.dss.infrastructure.database.scheme_repo import (
    search_schemes_by_text as search_schemes_by_text,
)
