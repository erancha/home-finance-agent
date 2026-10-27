"""Port for named locks that every replica of the agent shares.

A lock is held for the duration of a context and released when the context exits or when the
process holding it dies, so a lock outlives no holder.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class Locks(Protocol):
    def hold(self, key: str) -> AbstractAsyncContextManager[None]:
        """Wait until no one holds the key's lock, then hold it for the context."""
        ...

    def try_hold(self, key: str) -> AbstractAsyncContextManager[bool]:
        """Hold the key's lock for the context and yield True when no one holds it; otherwise
        yield False at once, holding nothing."""
        ...
