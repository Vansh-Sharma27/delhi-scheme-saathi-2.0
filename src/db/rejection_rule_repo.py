"""Re-export facade for the rejection rule repository moved in Phase 3.

Canonical home: ``src.dss.infrastructure.database.rejection_rule_repo``. This
module forwards the public names so existing imports keep working; it is
deleted in Phase 6 (spec 2.1, 2.3 contract step). The pool-holding adapter
implementing the ``RejectionRuleRepository`` port is
``src.dss.infrastructure.database.adapters.PostgresRejectionRuleRepository``.
"""

from src.dss.infrastructure.database.rejection_rule_repo import (
    get_all_rules as get_all_rules,
)
from src.dss.infrastructure.database.rejection_rule_repo import (
    get_critical_rules as get_critical_rules,
)
from src.dss.infrastructure.database.rejection_rule_repo import (
    get_rules_by_ids as get_rules_by_ids,
)
from src.dss.infrastructure.database.rejection_rule_repo import (
    get_rules_by_scheme as get_rules_by_scheme,
)
