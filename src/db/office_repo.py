"""Re-export facade for the office repository moved in Phase 3.

Canonical home: ``src.dss.infrastructure.database.office_repo``. This module
forwards the public names so existing imports keep working; it is deleted in
Phase 6 (spec 2.1, 2.3 contract step). The pool-holding adapter implementing
the ``OfficeRepository`` port is
``src.dss.infrastructure.database.adapters.PostgresOfficeRepository``.
"""

from src.dss.infrastructure.database.office_repo import (
    get_all_offices as get_all_offices,
)
from src.dss.infrastructure.database.office_repo import (
    get_nearest_offices as get_nearest_offices,
)
from src.dss.infrastructure.database.office_repo import (
    get_office_by_id as get_office_by_id,
)
from src.dss.infrastructure.database.office_repo import (
    get_offices_by_district as get_offices_by_district,
)
from src.dss.infrastructure.database.office_repo import (
    get_offices_by_service as get_offices_by_service,
)
from src.dss.infrastructure.database.office_repo import (
    haversine_distance as haversine_distance,
)
