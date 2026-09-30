"""Expanded catalog loading path before legacy callers migrate."""

from src.utils.scheme_catalog import _load_catalog as _load_catalog
from src.utils.scheme_catalog import get_canonical_life_events as get_canonical_life_events
from src.utils.scheme_catalog import (
    get_canonical_scheme_ids_for_life_event as get_canonical_scheme_ids_for_life_event,
)
from src.utils.scheme_catalog import get_canonical_scheme_record as get_canonical_scheme_record
from src.utils.scheme_catalog import get_canonical_tags as get_canonical_tags
from src.utils.scheme_catalog import (
    get_required_profile_fields_for_life_event as get_required_profile_fields_for_life_event,
)
