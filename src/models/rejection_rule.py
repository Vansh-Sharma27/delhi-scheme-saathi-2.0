"""Rejection rule data model.

Facade: the implementation moved to
``src.dss.domain.schemes.rejection_rule`` in Phase 1 as the facade-pattern
proof (spec 2.1, Phase 1). This module re-exports it so existing imports
``from src.models.rejection_rule import RejectionRule`` keep working while the
migration proceeds. The facade is removed in Phase 6 once every consumer
imports the new path.
"""

from src.dss.domain.schemes.rejection_rule import RejectionRule

__all__ = ["RejectionRule"]
