"""Phase 3 expand: scheme repository's infrastructure import surface."""

from src.db.scheme_repo import INCOME_SEGMENT_ORDER as INCOME_SEGMENT_ORDER
from src.db.scheme_repo import _calculate_eligibility_match as _calculate_eligibility_match
from src.db.scheme_repo import calculate_eligibility_match as calculate_eligibility_match
from src.db.scheme_repo import get_all_schemes as get_all_schemes
from src.db.scheme_repo import get_scheme_by_id as get_scheme_by_id
from src.db.scheme_repo import get_scheme_debug_rows as get_scheme_debug_rows
from src.db.scheme_repo import get_schemes_by_life_event as get_schemes_by_life_event
from src.db.scheme_repo import hybrid_search as hybrid_search
from src.db.scheme_repo import search_schemes_by_text as search_schemes_by_text
