"""Port: rejection rule repository.

Defines the read surface over rejection rules so the application guidance
layer and the scheme-detail endpoint can depend on the port instead of the
`src.db.rejection_rule_repo` function module. The functions there are
module-level and take a pool as the first argument, so they do not
structurally satisfy a class-shaped protocol; Phase 3 wraps them in an
adapter class that holds the pool and implements this port.

`RejectionRule` already lives in `src.dss.domain.schemes.rejection_rule`
after the Phase 1 facade proof, so this port imports it directly from the
domain layer rather than through a TYPE_CHECKING reference.

The four methods mirror the four read functions in the legacy repo. Only
`get_rules_by_scheme` has live callers today; the other three are kept
because the legacy module documents them as the complete read surface for
rules and Phase 3 should not lose them.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.dss.domain.schemes.rejection_rule import RejectionRule


@runtime_checkable
class RejectionRuleRepository(Protocol):
    """Read access to rejection rules keyed by scheme."""

    async def get_rules_by_scheme(self, scheme_id: str) -> list[RejectionRule]: ...
    async def get_rules_by_ids(self, rule_ids: list[str]) -> list[RejectionRule]: ...
    async def get_critical_rules(self, scheme_id: str) -> list[RejectionRule]: ...
    async def get_all_rules(self) -> list[RejectionRule]: ...
