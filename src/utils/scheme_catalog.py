"""Legacy catalog exports, retained until Phase 6."""

from src.dss.infrastructure.database.catalog import _CATALOG_PATH as _CATALOG_PATH
from src.dss.infrastructure.database.catalog import _load_catalog as _load_catalog
from src.dss.infrastructure.database.catalog import (
    get_canonical_life_events as get_canonical_life_events,
)
from src.dss.infrastructure.database.catalog import (
    get_canonical_scheme_ids_for_life_event as get_canonical_scheme_ids_for_life_event,
)
from src.dss.infrastructure.database.catalog import (
    get_canonical_scheme_record as get_canonical_scheme_record,
)
from src.dss.infrastructure.database.catalog import get_canonical_tags as get_canonical_tags
from src.dss.infrastructure.database.catalog import (
    get_required_profile_fields_for_life_event as get_required_profile_fields_for_life_event,
)
