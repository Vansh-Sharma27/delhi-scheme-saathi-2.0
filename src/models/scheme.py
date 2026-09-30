"""Legacy scheme hydration convenience, retained until Phase 6."""

from typing import Any, Self

from src.dss.domain.schemes.scheme import INCOME_SEGMENT_KEYS as INCOME_SEGMENT_KEYS
from src.dss.domain.schemes.scheme import EligibilityCriteria as EligibilityCriteria
from src.dss.domain.schemes.scheme import HelplineInfo as HelplineInfo
from src.dss.domain.schemes.scheme import Scheme as DomainScheme
from src.dss.domain.schemes.scheme import SchemeMatch as SchemeMatch
from src.dss.infrastructure.database.scheme_codec import scheme_from_row


class Scheme(DomainScheme, frozen=True):
    """Preserve standalone legacy row hydration."""

    @classmethod
    def from_db_row(cls, row: Any) -> Self:
        return scheme_from_row(cls, row)
