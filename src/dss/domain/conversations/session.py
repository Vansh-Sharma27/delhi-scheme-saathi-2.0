"""Conversation session values and timestamp-preserving mutations."""

from datetime import UTC, datetime
from typing import Any, Self

from pydantic import BaseModel, Field, PrivateAttr

from src.dss.domain.conversations.clock import Clock
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile


class Message(BaseModel, frozen=True):
    """Single conversation message."""

    role: str  # user, assistant, system
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationMemory(BaseModel):
    """Compact working memory for long-running conversations."""

    summary: str | None = None
    profile_facts: list[str] = Field(default_factory=list)
    active_scheme_ids: list[str] = Field(default_factory=list)
    pending_action: str | None = None
    last_user_goal: str | None = None

    def is_meaningful(self) -> bool:
        """Return True when working memory contains useful context."""
        return any([
            bool(self.summary), bool(self.profile_facts), bool(self.active_scheme_ids),
            bool(self.pending_action), bool(self.last_user_goal),
        ])


class Session(BaseModel):
    """Conversation session (mutable for state updates)."""

    user_id: str
    state: ConversationState = ConversationState.GREETING
    user_profile: UserProfile = Field(default_factory=UserProfile)
    messages: list[Message] = Field(default_factory=list)
    working_memory: ConversationMemory = Field(default_factory=ConversationMemory)
    discussed_schemes: list[str] = Field(default_factory=list)  # Scheme IDs
    selected_scheme_id: str | None = None
    language_preference: str = "auto"  # auto, hi, en
    language_locked: bool = False
    currently_asking: str | None = None
    skipped_fields: list[str] = Field(default_factory=list)
    awaiting_profile_change: bool = False
    presented_schemes: list[dict[str, str]] = Field(default_factory=list)
    completed_turn_count: int = 0
    last_memory_refresh_turn: int = 0
    pending_memory_job: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
    _clock: Clock | None = PrivateAttr(default=None)

    @property
    def clock(self) -> Clock | None:
        """Time source shared by session copies and resets."""
        return self._clock

    def with_clock(self, clock: Clock | None) -> Self:
        """Bind a time source without adding it to the persisted session."""
        self._clock = clock
        return self

    def now(self) -> datetime:
        """Read the injected clock, or UTC wall time for legacy callers."""
        return self._clock.now() if self._clock is not None else datetime.now(UTC)

    def copy_with(self, **updates: Any) -> Self:
        """Return a deep-copied session with updated fields."""
        data = self.model_dump(round_trip=True)
        data.update(updates)
        # Always update timestamp unless caller explicitly provides one
        if "updated_at" not in updates:
            data["updated_at"] = self.now()
        return type(self)(**data).with_clock(self._clock)

    def add_message(self, role: str, content: str) -> Self:
        """Add message and return new session (keeping sliding window of 12)."""
        new_message = Message(role=role, content=content, timestamp=self.now())
        messages = list(self.messages)
        messages.append(new_message)
        # Keep the last 6 completed turns (12 messages) in raw history.
        if len(messages) > 12:
            messages = messages[-12:]
        return self.copy_with(messages=messages, updated_at=self.now())

    def with_state(self, new_state: ConversationState) -> Self:
        """Return new session with updated state."""
        return self.copy_with(state=new_state, updated_at=self.now())

    def with_profile(self, profile: UserProfile) -> Self:
        """Return new session with updated profile."""
        return self.copy_with(user_profile=profile, updated_at=self.now())

    def to_dynamodb_item(self) -> dict[str, Any]:
        """Serialize for DynamoDB storage."""
        return {
            "user_id": self.user_id, "state": self.state.value,
            "user_profile": self.user_profile.model_dump(),
            # DynamoDB serializer does not support datetime objects directly.
            "messages": [{"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in self.messages],
            "working_memory": self.working_memory.model_dump(),
            "discussed_schemes": self.discussed_schemes,
            "selected_scheme_id": self.selected_scheme_id,
            "language_preference": self.language_preference,
            "language_locked": self.language_locked,
            "currently_asking": self.currently_asking,
            "skipped_fields": self.skipped_fields,
            "awaiting_profile_change": self.awaiting_profile_change,
            "presented_schemes": self.presented_schemes,
            "completed_turn_count": self.completed_turn_count,
            "last_memory_refresh_turn": self.last_memory_refresh_turn,
            "pending_memory_job": self.pending_memory_job,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "ttl": int(self.updated_at.timestamp()) + 86400 * 7,  # 7 days TTL
        }
