"""Application orchestration for deterministic and judged scheme matching."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.dss.application.matching import scheme_relevance
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.matching import MatchSchemes
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import SchemeMatch

logger = logging.getLogger(__name__)


@dataclass
class MatchingResult:
    """Matching output plus the session changes made by the use case."""

    session: Session
    state: ConversationState
    text: str
    schemes: list[SchemeMatch] = field(default_factory=list)
    inline_keyboard: list[list[dict[str, str]]] | None = None


class MatchingUseCase:
    """Run matching, relevance judging, and matching outcome preparation."""

    def __init__(
        self,
        ai: AITasks,
        *,
        match_schemes: MatchSchemes,
        is_low_context: Callable[[Session, str], bool],
        build_focus: Callable[[UserProfile, str], str],
        get_history: Callable[[Session], list[dict[str, str]]],
        build_scheme_list: Callable[[list[SchemeMatch], UserProfile, str], str],
        generate_no_schemes: Callable[[str], str],
        collection_state: Callable[[UserProfile], ConversationState],
        format_keyboard: Callable[[list[SchemeMatch], str], list[list[dict[str, str]]] | None],
        store_presented: Callable[[Session, list[SchemeMatch]], Session],
        set_awaiting_profile_change: Callable[[Session, bool], Session],
        clear_selection: Callable[[Session], Session],
        set_presented_schemes: Callable[[Session, list[dict[str, str]]], Session],
        set_currently_asking: Callable[[Session, str | None], Session],
    ) -> None:
        self.ai = ai
        self.match_schemes = match_schemes
        self.is_low_context = is_low_context
        self.build_focus = build_focus
        self.get_history = get_history
        self.build_scheme_list = build_scheme_list
        self.generate_no_schemes = generate_no_schemes
        self.collection_state = collection_state
        self.format_keyboard = format_keyboard
        self.store_presented = store_presented
        self.set_awaiting_profile_change = set_awaiting_profile_change
        self.clear_selection = clear_selection
        self.set_presented_schemes = set_presented_schemes
        self.set_currently_asking = set_currently_asking

    async def run(
        self,
        profile: UserProfile,
        user_message: str,
        session: Session,
        lang: str,
    ) -> MatchingResult:
        """Retrieve candidates, judge relevance, and prepare the response."""
        logger.info(
            "Running scheme matching for user=%s state=%s profile.life_event=%s age=%s category=%s income=%s",
            session.user_id,
            session.state.value,
            profile.life_event,
            profile.age,
            profile.category,
            profile.annual_income,
        )
        low_context_turn = self.is_low_context(session, user_message)
        matching_query_text = (
            self.build_focus(profile, user_message) if low_context_turn else user_message
        )
        schemes = await self.match_schemes(
            profile=profile,
            query_text=matching_query_text,
        )

        if not schemes:
            return self.no_match(session, profile, lang)

        relevance = await self._judge_relevance(
            session, profile, schemes, user_message, lang, low_context_turn
        )
        schemes = relevance["matches"]
        if relevance["should_clarify"]:
            session = self.set_awaiting_profile_change(session, False)
            session = self.clear_selection(session)
            session = self.set_presented_schemes(session, [])
            session = self.set_currently_asking(session, "life_event")
            return MatchingResult(
                session,
                ConversationState.SITUATION_UNDERSTANDING,
                relevance["clarification_question"],
            )

        session = self.set_awaiting_profile_change(session, False)
        session = self.store_presented(session, schemes)
        return MatchingResult(
            session,
            ConversationState.SCHEME_PRESENTATION,
            self.build_scheme_list(schemes, profile, lang),
            schemes,
            self.format_keyboard(schemes, lang),
        )

    async def _judge_relevance(
        self,
        session: Session,
        profile: UserProfile,
        schemes: list[SchemeMatch],
        user_message: str,
        lang: str,
        low_context_turn: bool,
    ) -> dict[str, Any]:
        """Run the AI relevance gate over deterministic candidates."""
        judgement = None
        if self.ai.should_run_relevance_judge(schemes):
            try:
                judgement = await self.ai.judge_scheme_relevance(
                    session=session,
                    user_message=self.build_focus(profile, user_message),
                    conversation_history=self.get_history(session),
                    candidate_schemes=scheme_relevance.build_candidate_payload(schemes),
                    session_language=lang,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Scheme relevance judging failed for user=%s: %s",
                    session.user_id,
                    exc,
                )
        else:
            logger.info(
                "Skipping AI relevance judge for user=%s top_score=%.3f",
                session.user_id,
                schemes[0].deterministic_score,
            )

        relevance = scheme_relevance.apply_relevance_judgement(
            schemes,
            judgement,
            lang,
            profile.life_event,
        )
        if low_context_turn and relevance["should_clarify"]:
            logger.info(
                "Ignoring low-context relevance clarification for user=%s currently_asking=%s",
                session.user_id,
                session.currently_asking,
            )
            relevance["should_clarify"] = False
            relevance["clarification_question"] = None

        logger.info(
            "Scheme relevance gate: should_clarify=%s overall_confidence=%s top_ids=%s",
            relevance["should_clarify"],
            relevance["overall_confidence"],
            [match.scheme.id for match in relevance["matches"][:3]],
        )
        return relevance

    def no_match(self, session: Session, profile: UserProfile, lang: str) -> MatchingResult:
        """Return to profile collection instead of ending the conversation."""
        session = self.set_awaiting_profile_change(session, True)
        session = self.clear_selection(session)
        session = self.set_presented_schemes(session, [])
        return MatchingResult(
            session,
            self.collection_state(profile),
            self.generate_no_schemes(lang),
        )
