"""Port: idempotency store for Telegram update deduplication.

Telegram retries webhook deliveries, so an update can arrive twice and be
processed twice. `update_id` is declared on `TelegramUpdate` but never read
today (spec 11.4), so there is no existing implementation to relocate. This
port is the seam for the post-migration dedup fix: the webhook handler will
claim each `update_id` before processing, and reject retries that were
already claimed.

The contract is a single atomic claim rather than a check-then-mark pair,
because a separate check and mark races under concurrent retries: two
deliveries can both pass the check before either marks. A claim that
returns whether this caller was first closes that window. An in-memory
adapter is a set; a durable adapter would be DynamoDB conditional write or
Redis SETNX. The fix itself is out of migration scope (spec 11.4, not fixed
during the migration); this port exists because spec 6.1 requires it.
"""

from __future__ import annotations

from typing import Protocol


class IdempotencyStore(Protocol):
    """Atomic first-seen claim keyed by an integer update id."""

    async def claim(self, update_id: int) -> bool:
        """Return True the first time `update_id` is seen, False after.

        Must be atomic: two concurrent claims for the same id must not both
        return True. The contract does not guarantee durability; an adapter
        that survives restarts picks a durable backing store.
        """
        ...
