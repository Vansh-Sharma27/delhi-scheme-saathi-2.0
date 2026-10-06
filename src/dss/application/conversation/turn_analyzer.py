"""Application use case for analyzing one conversation turn."""

from typing import Any, cast

from src.dss.application.conversation.models import TurnAnalysis
from src.dss.domain.conversations.session import Session
from src.dss.infrastructure.ai.prompts.loader import get_analysis_system_prompt


class TurnAnalyzer:
    """Run LLM analysis and apply deterministic conversation guardrails."""

    def __init__(self, ai: Any, *, policies: Any) -> None:
        self.ai = ai
        self.policies = policies

    async def analyze(self, session: Session, user_message: str) -> TurnAnalysis:
        language = self.policies.language
        intents = self.policies.intents
        explicit_language = language.detect_explicit_language_request(user_message)
        explicit_topic_switch = intents.is_explicit_topic_switch(user_message)
        inferred_turn_language = explicit_language or language.infer_text_language(user_message)
        preserve_unlocked_language = language.should_preserve_unlocked_session_language(
            session, user_message, inferred_turn_language
        )
        llm_session_language = (
            session.language_preference
            if (session.language_locked and session.language_preference != "auto")
            or preserve_unlocked_language
            else inferred_turn_language
        )
        analysis = await self.ai.analyze_message(
            session=session,
            user_message=user_message,
            conversation_history=self.policies.session_manager.get_conversation_history(
                session, include_assistant=bool(session.currently_asking)
            ),
            system_prompt=get_analysis_system_prompt(),
            session_language=llm_session_language,
        )
        extracted_fields = self._merge_extracted_fields(
            session, user_message, analysis.get("extracted_fields", {})
        )
        detected_life_event = self._resolve_life_event(
            analysis.get("life_event"),
            user_message,
            explicit_topic_switch=explicit_topic_switch,
            current_life_event=session.user_profile.life_event,
        )
        resolved_scheme_id = self._resolve_scheme_id(
            session,
            user_message,
            llm_scheme_id=analysis.get("selected_scheme_id"),
            explicit_topic_switch=explicit_topic_switch,
        )
        action = self._resolve_action(
            session,
            user_message,
            llm_action=analysis.get("action"),
            resolved_scheme_id=resolved_scheme_id,
            explicit_topic_switch=explicit_topic_switch,
        )
        return TurnAnalysis(
            intent=analysis.get("intent", "unknown"),
            action=action,
            detected_life_event=detected_life_event,
            extracted_fields=extracted_fields,
            llm_response_text=analysis.get("response_text"),
            resolved_scheme_id=resolved_scheme_id,
            explicit_language=explicit_language,
            explicit_topic_switch=explicit_topic_switch,
            detected_language=language.normalize_language(
                analysis.get("language", llm_session_language)
            ),
            inferred_turn_language=inferred_turn_language,
            preserve_unlocked_language=preserve_unlocked_language,
        )

    def _merge_extracted_fields(
        self, session: Session, user_message: str, llm_fields: dict[str, Any]
    ) -> dict[str, Any]:
        profile_extractor = self.policies.profile_extractor
        turn_policy = self.policies.turn_policy
        rule_based_fields = profile_extractor.extract_by_patterns(
            user_message, current_field=session.currently_asking
        )
        merged = turn_policy.sanitize_extracted_fields(
            user_message, {**llm_fields, **rule_based_fields}, rule_based_fields
        )
        if session.currently_asking and session.currently_asking not in merged:
            contextual = turn_policy.contextual_field_value(session.currently_asking, user_message)
            if contextual:
                field_name, value = contextual
                merged[field_name] = value
        return cast(dict[str, Any], merged)

    def _resolve_life_event(
        self,
        llm_life_event: str | None,
        user_message: str,
        *,
        explicit_topic_switch: bool,
        current_life_event: str | None,
    ) -> str | None:
        life_event_classifier = self.policies.life_event_classifier
        detected = llm_life_event
        if explicit_topic_switch:
            classified = life_event_classifier.classify_by_keywords(user_message)
            if classified and classified != current_life_event:
                return cast(str | None, classified)
        return cast(
            str | None, detected or life_event_classifier.classify_by_keywords(user_message)
        )

    def _resolve_scheme_id(
        self,
        session: Session,
        user_message: str,
        *,
        llm_scheme_id: str | None,
        explicit_topic_switch: bool,
    ) -> str | None:
        scheme_reference = self.policies.scheme_reference
        if explicit_topic_switch:
            return None
        validated = scheme_reference.validated_selected_scheme_id(session, llm_scheme_id)
        return cast(
            str | None,
            validated or scheme_reference.resolve_scheme_from_text(session, user_message),
        )

    def _resolve_action(
        self,
        session: Session,
        user_message: str,
        *,
        llm_action: str | None,
        resolved_scheme_id: str | None,
        explicit_topic_switch: bool,
    ) -> str | None:
        intents = self.policies.intents
        turn_policy = self.policies.turn_policy
        action = (
            intents.detect_action_override(
                user_message,
                session.state,
                session.currently_asking,
                resolved_scheme_id,
                session.selected_scheme_id,
            )
            or llm_action
        )
        if explicit_topic_switch and turn_policy.should_preserve_scheme_context_action(action):
            return None
        has_scheme_context = bool(
            resolved_scheme_id or session.selected_scheme_id or session.presented_schemes
        )
        if turn_policy.should_answer_scheme_question(
            user_message,
            session.state,
            action,
            resolved_scheme_id,
            session.selected_scheme_id,
            has_scheme_context,
        ):
            return "answer_scheme_question"
        return action
