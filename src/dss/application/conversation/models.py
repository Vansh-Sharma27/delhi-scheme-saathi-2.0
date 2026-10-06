"""Conversation application results shared by the extracted use cases."""

from dataclasses import dataclass, field
from typing import Any

from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import SchemeMatch


@dataclass(frozen=True)
class TurnAnalysis:
    """What the analysis phase concluded about one user message."""

    intent: str
    action: str | None
    detected_life_event: str | None
    extracted_fields: dict[str, Any]
    llm_response_text: str | None
    resolved_scheme_id: str | None
    explicit_language: str | None
    explicit_topic_switch: bool
    detected_language: str
    inferred_turn_language: str
    preserve_unlocked_language: bool


@dataclass(frozen=True)
class ProfileUpdate:
    """How a turn changed the stored profile."""

    before_profile: UserProfile
    changed_fields: set[str]

    @property
    def profile_changed(self) -> bool:
        return bool(self.changed_fields)

    @property
    def matching_inputs_changed(self) -> bool:
        return bool(
            self.changed_fields & {"life_event", "age", "category", "annual_income", "gender"}
        )


@dataclass
class RenderResult:
    """The reply produced for one FSM state, plus session edits."""

    session: Session
    state: ConversationState
    text: str
    schemes: list[SchemeMatch] = field(default_factory=list)
    inline_keyboard: list[list[dict[str, str]]] | None = None
