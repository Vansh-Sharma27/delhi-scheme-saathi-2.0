"""Load canonical scheme metadata and supply it to domain policy."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.dss.domain.profiles.required_fields import required_profile_fields

logger = logging.getLogger(__name__)
_CATALOG_PATH = Path(__file__).resolve().parents[4] / "data" / "all_schemes.json"


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, dict[str, Any]]:
    """Load bundled scheme metadata keyed by scheme id."""
    try:
        schemes = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Canonical scheme catalog not found at %s", _CATALOG_PATH)
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse canonical scheme catalog: %s", exc)
        return {}

    catalog: dict[str, dict[str, Any]] = {}
    for scheme in schemes:
        scheme_id = str(scheme.get("id", "")).strip()
        if scheme_id:
            catalog[scheme_id] = scheme
    return catalog


def get_canonical_scheme_record(scheme_id: str) -> dict[str, Any] | None:
    """Return bundled scheme metadata for a scheme id, if present."""
    return _load_catalog().get(scheme_id)


def get_canonical_scheme_ids_for_life_event(life_event: str | None) -> list[str]:
    """Return bundled scheme ids mapped to a life event."""
    if not life_event:
        return []
    matching_ids: list[str] = []
    for scheme_id, scheme in _load_catalog().items():
        if life_event in scheme.get("life_events", []):
            matching_ids.append(scheme_id)
    return matching_ids


def get_canonical_life_events(scheme_id: str) -> list[str]:
    """Return bundled life events for a scheme id."""
    record = get_canonical_scheme_record(scheme_id)
    if not record:
        return []
    return [str(value) for value in record.get("life_events", []) if str(value)]


def get_canonical_tags(scheme_id: str) -> list[str]:
    """Return bundled tags for a scheme id."""
    record = get_canonical_scheme_record(scheme_id)
    if not record:
        return []
    return [str(value) for value in record.get("tags", []) if str(value)]


@lru_cache(maxsize=32)
def get_required_profile_fields_for_life_event(life_event: str | None) -> tuple[str, ...]:
    """Supply catalog data to the unchanged required-field policy."""
    # Preserve the no-topic path without reading the catalog.
    return required_profile_fields(life_event, _load_catalog().values() if life_event else ())
