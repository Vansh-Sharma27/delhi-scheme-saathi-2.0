"""Scheme row hydration with infrastructure-supplied catalog metadata."""

import json
from typing import Any, TypeVar

from src.dss.domain.schemes.scheme import EligibilityCriteria, HelplineInfo, Scheme
from src.dss.infrastructure.database.catalog import get_canonical_life_events, get_canonical_tags

SchemeType = TypeVar("SchemeType", bound=Scheme)


def scheme_from_row(cls: type[SchemeType], row: Any) -> SchemeType:
    """Preserve row decoding and canonical metadata precedence."""
    eligibility_data = row.get("eligibility") or {}
    if isinstance(eligibility_data, str):
        eligibility_data = json.loads(eligibility_data)
    helpline_data = row.get("helpline")
    helpline = None
    if helpline_data:
        if isinstance(helpline_data, str):
            helpline_data = json.loads(helpline_data)
        if helpline_data:
            # Normalize list fields to comma-separated strings
            for field in ["phone", "email", "website", "whatsapp"]:
                if isinstance(helpline_data.get(field), list):
                    helpline_data[field] = ", ".join(helpline_data[field])
            helpline = HelplineInfo(**helpline_data)
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    canonical_life_events = get_canonical_life_events(row["id"])
    canonical_tags = get_canonical_tags(row["id"])
    return cls(
        id=row["id"], name=row["name"], name_hindi=row["name_hindi"],
        department=row["department"], department_hindi=row["department_hindi"],
        level=row["level"], description=row["description"], description_hindi=row["description_hindi"],
        benefits_summary=row.get("benefits_summary"), benefits_amount=row.get("benefits_amount"),
        benefits_frequency=row.get("benefits_frequency"),
        eligibility=EligibilityCriteria.from_db(eligibility_data),
        documents_required=list(row.get("documents_required") or []),
        rejection_rules=list(row.get("rejection_rules") or []),
        application_url=row.get("application_url"), application_steps=list(row.get("application_steps") or []),
        offline_process=row.get("offline_process"), processing_time=row.get("processing_time"), helpline=helpline,
        life_events=canonical_life_events or list(row.get("life_events") or []),
        tags=canonical_tags or list(row.get("tags") or []), official_url=row.get("official_url"),
        metadata=metadata, last_verified=row.get("last_verified"), is_active=row.get("is_active", True),
    )
