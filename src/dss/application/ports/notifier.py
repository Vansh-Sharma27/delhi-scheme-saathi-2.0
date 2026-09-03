"""Port: Telegram notifier.

Defines the Telegram send surface the webhook handler consumes, so that
when Phase 5 moves the handler into `src.dss.interfaces.telegram` it can
depend on this port instead of the `TelegramClient` adapter directly. The
spec names only the send direction (spec 6.1: "Telegram send"), but the
handler also fetches inbound voice via `download_voice`, so the port
includes it to fully sever the interface-to-adapter edge. The legacy
`TelegramClient` satisfies this protocol structurally; Phase 3 can relocate
it behind the port.

Methods that the handler does not call (`get_file`, `send_message`,
`set_webhook`, `delete_webhook`, `get_me`, `set_my_commands`, `get_my_commands`,
`close`) are deliberately excluded. `send_message` is an internal helper of
`send_text` and `send_inline_keyboard` and stays on the adapter.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """Outbound Telegram surface consumed by the webhook handler."""

    async def send_text(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
    ) -> dict[str, Any]: ...

    async def send_inline_keyboard(
        self,
        chat_id: int | str,
        text: str,
        buttons: list[list[dict[str, str]]],
        parse_mode: str | None = None,
    ) -> dict[str, Any]: ...

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]: ...

    async def send_chat_action(
        self,
        chat_id: int | str,
        action: str = "typing",
    ) -> dict[str, Any]: ...

    async def send_voice(
        self,
        chat_id: int | str,
        voice_data: bytes | str,
        caption: str | None = None,
        filename: str = "response.ogg",
        content_type: str = "audio/ogg",
    ) -> dict[str, Any]: ...

    async def send_audio(
        self,
        chat_id: int | str,
        audio_bytes: bytes,
        filename: str = "response.ogg",
        caption: str | None = None,
        content_type: str = "audio/ogg",
    ) -> dict[str, Any]: ...

    async def download_voice(self, file_id: str) -> bytes: ...
