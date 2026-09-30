"""Scheme and eligibility data models."""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

INCOME_SEGMENT_KEYS = {"EWS", "LIG", "MIG", "HIG"}


class EligibilityCriteria(BaseModel, frozen=True):
    """Eligibility criteria for a scheme (immutable)."""

    min_age: int | None = None
    max_age: int | None = None
    genders: list[str] = Field(default_factory=lambda: ["all"])
    categories: list[str] = Field(default_factory=list)  # Raw source field; do not match directly.
    caste_categories: list[str] = Field(default_factory=list)
    income_segments: list[str] = Field(default_factory=list)
    max_income: int | None = None
    income_by_category: dict[str, int] = Field(default_factory=dict)
    domicile_required: bool = False
    domicile_states: list[str] = Field(default_factory=lambda: ["all"])
    employment_statuses: list[str] = Field(default_factory=lambda: ["all"])
    education_levels: list[str] = Field(default_factory=lambda: ["all"])
    bpl_required: bool | None = None
    disability_required: bool | None = None
    disability_min_percentage: int | None = None
    other_conditions: list[str] = Field(default_factory=list)
    special_focus_groups: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_category_dimensions(cls, data: Any) -> Any:
        """Split demographic categories from income-segment labels."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        raw_categories = [
            str(value).strip()
            for value in normalized.get("categories", [])
            if str(value).strip()
        ]
        caste_categories = [
            str(value).strip()
            for value in normalized.get("caste_categories", [])
            if str(value).strip()
        ]
        income_segments = [
            str(value).strip()
            for value in normalized.get("income_segments", [])
            if str(value).strip()
        ]

        if not caste_categories and not income_segments and raw_categories:
            upper_categories = {value.upper() for value in raw_categories}
            income_keys = {
                str(key).strip().upper()
                for key in (normalized.get("income_by_category") or {})
                if str(key).strip()
            }
            if upper_categories == {"ALL"}:
                caste_categories = []
            elif (upper_categories | income_keys) & (INCOME_SEGMENT_KEYS - {"EWS"}):
                income_segments = raw_categories
            else:
                caste_categories = raw_categories

        normalized["categories"] = raw_categories
        normalized["caste_categories"] = caste_categories
        normalized["income_segments"] = income_segments
        return normalized

    @property
    def has_caste_restrictions(self) -> bool:
        """Whether the scheme restricts by caste/social category."""
        return bool(self.caste_categories)

    @property
    def has_income_segment_restrictions(self) -> bool:
        """Whether the scheme uses income bands like EWS/LIG/MIG."""
        return bool(self.income_segments)

    @classmethod
    def from_db(cls, data: Any) -> "EligibilityCriteria":
        """Create from database JSONB field."""
        if not data:
            return cls()
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            return cls()
        # Filter out None values to use model defaults instead
        filtered_data = {k: v for k, v in data.items() if v is not None}
        return cls(**filtered_data)


class HelplineInfo(BaseModel, frozen=True):
    """Helpline contact information."""

    phone: str | None = None
    email: str | None = None
    website: str | None = None
    whatsapp: str | None = None


class Scheme(BaseModel, frozen=True):
    """Government welfare scheme (immutable)."""

    id: str
    name: str
    name_hindi: str
    department: str
    department_hindi: str
    level: str  # central, state, district
    description: str
    description_hindi: str
    benefits_summary: str | None = None
    benefits_amount: int | None = None
    benefits_frequency: str | None = None
    eligibility: EligibilityCriteria = Field(default_factory=EligibilityCriteria)
    documents_required: list[str] = Field(default_factory=list)
    rejection_rules: list[str] = Field(default_factory=list)
    application_url: str | None = None
    application_steps: list[str] = Field(default_factory=list)
    offline_process: str | None = None
    processing_time: str | None = None
    helpline: HelplineInfo | None = None
    life_events: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    official_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_verified: datetime | None = None
    is_active: bool = True

class SchemeCandidate(BaseModel, frozen=True):
    """Retrieved scheme and similarity, before eligibility evaluation."""

    scheme: Scheme
    similarity: float = 0.0


class SchemeMatch(BaseModel, frozen=True):
    """Scheme with similarity score from vector search."""

    scheme: Scheme
    similarity: float = 0.0
    eligibility_match: dict[str, bool] = Field(default_factory=dict)
    deterministic_score: float = 0.0
    ai_relevance_score: float | None = None
    ai_relevance_reason: str | None = None
    topic_match: bool | None = None
