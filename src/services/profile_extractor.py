"""Compatibility exports for application profile extraction."""

from typing import Any as Any

from src.dss.application.conversation.profile_extractor import (
    _INCOME_ATTEMPT_PATTERN as _INCOME_ATTEMPT_PATTERN,
)
from src.dss.application.conversation.profile_extractor import _INCOME_UNIT as _INCOME_UNIT
from src.dss.application.conversation.profile_extractor import (
    _SPOUSE_LOSS_EVENT_PATTERN as _SPOUSE_LOSS_EVENT_PATTERN,
)
from src.dss.application.conversation.profile_extractor import (
    _SPOUSE_LOSS_PATTERNS as _SPOUSE_LOSS_PATTERNS,
)
from src.dss.application.conversation.profile_extractor import (
    FIELD_QUESTION_ORDER as FIELD_QUESTION_ORDER,
)
from src.dss.application.conversation.profile_extractor import (
    _extract_spouse_loss_context as _extract_spouse_loss_context,
)
from src.dss.application.conversation.profile_extractor import (
    _has_income_context as _has_income_context,
)
from src.dss.application.conversation.profile_extractor import (
    extract_by_patterns as extract_by_patterns,
)
from src.dss.application.conversation.profile_extractor import (
    get_validation_re_prompt as get_validation_re_prompt,
)
from src.dss.application.conversation.profile_extractor import (
    validate_field_response as validate_field_response,
)
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.domain.profiles.profile import UserProfile as UserProfile
from src.dss.infrastructure.database.catalog import _load_catalog as _load_catalog

_fields = ProfileFields(lambda: _load_catalog().values())
get_missing_fields = _fields.get_missing_fields
get_next_missing_field = _fields.get_next_missing_field
get_next_question = _fields.get_next_question
get_required_matching_fields = _fields.get_required_matching_fields
is_complete_for_matching = _fields.is_complete_for_matching
