"""Generated equivalence against an independent pre-extraction evaluator."""

import ast
import subprocess
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from src.dss.domain.eligibility.evaluator import calculate_eligibility_match
from src.models.scheme import EligibilityCriteria, Scheme
from src.models.session import UserProfile
from tests import eligibility_reference

labels = st.sampled_from(["all", "ALL", "All", "SC", "sc", "ST", "OBC", "General", "EWS", "ews", "LIG", "MIG", "HIG", "other", ""])
numbers = st.one_of(st.none(), st.integers(-10, 2000000))
criteria = st.builds(
    EligibilityCriteria,
    min_age=numbers,
    max_age=numbers,
    genders=st.lists(st.sampled_from(["all", "ALL", "male", "Male", "female", "other", ""]), max_size=4),
    categories=st.lists(labels, max_size=5),
    caste_categories=st.lists(labels, max_size=5),
    income_segments=st.lists(labels, max_size=5),
    max_income=numbers,
    income_by_category=st.dictionaries(labels, st.integers(-10, 2000000), max_size=6),
    domicile_required=st.booleans(),
    bpl_required=st.one_of(st.none(), st.booleans()),
    disability_required=st.one_of(st.none(), st.booleans()),
    disability_min_percentage=numbers,
    employment_statuses=st.lists(labels, max_size=3),
    education_levels=st.lists(labels, max_size=3),
    other_conditions=st.lists(labels, max_size=3),
    special_focus_groups=st.lists(labels, max_size=3),
)
profiles = st.builds(
    UserProfile,
    age=numbers,
    gender=st.one_of(st.none(), st.sampled_from(["all", "ALL", "male", "Male", "female", "other", ""])),
    category=st.one_of(st.none(), labels),
    annual_income=numbers,
    has_bpl_card=st.one_of(st.none(), st.booleans()),
    disability_percentage=numbers,
    employment_status=st.one_of(st.none(), labels),
)


def test_reference_is_original_source() -> None:
    """The oracle's helpers and evaluator remain the exact original AST."""
    original = subprocess.check_output(
        ["git", "show", "e7f8ae0:src/dss/infrastructure/database/scheme_repo.py"],
        text=True,
    )
    reference = Path(eligibility_reference.__file__).read_text(encoding="utf-8")
    names = {"_lookup_case_insensitive", "_infer_income_segment", "calculate_eligibility_match"}
    def functions(source: str) -> dict[str, str]:
        return {
            node.name: ast.dump(node)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in names
        }
    assert functions(original) == functions(reference)


@settings(max_examples=1000, derandomize=True, deadline=None, database=None)
@given(eligibility=criteria, profile=profiles)
def test_evaluator_equivalence(eligibility: EligibilityCriteria, profile: UserProfile) -> None:
    scheme = Scheme(
        id="synthetic", name="Synthetic", name_hindi="Synthetic", department="Synthetic",
        department_hindi="Synthetic", level="state", description="Synthetic",
        description_hindi="Synthetic", eligibility=eligibility,
    )
    expected = eligibility_reference.calculate_eligibility_match(scheme, profile)
    actual = calculate_eligibility_match(scheme, profile)
    assert list(actual.items()) == list(expected.items())
