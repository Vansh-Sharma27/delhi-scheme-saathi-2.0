"""Compatibility exports for application profile extraction."""

from typing import Any as Any

from src.dss.application.conversation import profile_extractor as _implementation
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
    get_missing_fields as get_missing_fields,
)
from src.dss.application.conversation.profile_extractor import (
    get_next_missing_field as get_next_missing_field,
)
from src.dss.application.conversation.profile_extractor import (
    get_next_question as get_next_question,
)
from src.dss.application.conversation.profile_extractor import (
    get_required_matching_fields as get_required_matching_fields,
)
from src.dss.application.conversation.profile_extractor import (
    get_validation_re_prompt as get_validation_re_prompt,
)
from src.dss.application.conversation.profile_extractor import (
    is_complete_for_matching as is_complete_for_matching,
)
from src.dss.application.conversation.profile_extractor import (
    validate_field_response as validate_field_response,
)
from src.dss.domain.profiles.profile import UserProfile as UserProfile
from src.dss.infrastructure.database.catalog import _load_catalog as _load_catalog

_implementation._load_catalog = _load_catalog
