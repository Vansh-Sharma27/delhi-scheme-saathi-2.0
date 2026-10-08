"""Catalog values belong to the constructed profile collaborator, not a global."""

from unittest.mock import Mock

from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.domain.profiles.profile import UserProfile


def test_profile_catalogs_are_isolated_and_no_topic_is_lazy() -> None:
    catalog = Mock(return_value=[{
        "life_events": ["SYNTHETIC"],
        "eligibility": {"genders": ["female"], "categories": ["SC"]},
    }])
    restricted = ProfileFields(catalog)
    unrestricted = ProfileFields(lambda: [])
    assert restricted.get_next_missing_field(UserProfile()) == "life_event"
    catalog.assert_not_called()
    profile = UserProfile(life_event="SYNTHETIC", age=30, annual_income=100000)
    assert unrestricted.is_complete_for_matching(profile)
    assert not restricted.is_complete_for_matching(profile)
    assert restricted.get_next_missing_field(profile) == "gender"
    assert restricted.get_next_missing_field(profile, ["gender"]) == "category"
    assert restricted.get_next_question(profile, "en") == "Are you male or female?"
