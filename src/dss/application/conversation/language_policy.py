"""Application policy for settling a turn's response language."""

from src.dss.application.conversation import language
from src.dss.application.conversation import sessions as session_manager
from src.dss.application.conversation.models import TurnAnalysis
from src.dss.application.ports.responses import Responses
from src.dss.domain.conversations.session import Session


class LanguagePolicy:
    """Apply explicit locks and unlocked language observations to a session."""

    @staticmethod
    async def enforce(session: Session, text: str, language: str, *, responses: Responses) -> str:
        """Apply the shared localization path before a reply is persisted."""
        return await responses.ensure_response_language(session, text, language)

    @staticmethod
    def resolve(
        session: Session, analysis: TurnAnalysis
    ) -> tuple[Session, str, bool]:
        if analysis.explicit_language:
            language_changed = session.language_preference != analysis.explicit_language
            session = session_manager.set_language(session, analysis.explicit_language, locked=True)
            return session, analysis.explicit_language, language_changed

        if session.language_locked and session.language_preference != "auto":
            return session, session.language_preference, False

        preferred = (
            session.language_preference
            if analysis.preserve_unlocked_language and session.language_preference != "auto"
            else language.preferred_turn_language(
                analysis.inferred_turn_language, analysis.detected_language
            )
        )
        previous_language = session.language_preference
        language_changed = False
        if preferred != previous_language or previous_language == "auto":
            session = session_manager.set_language(session, preferred, locked=False)
            language_changed = previous_language != preferred

        return (
            session,
            session.language_preference if session.language_preference != "auto" else preferred,
            language_changed,
        )
