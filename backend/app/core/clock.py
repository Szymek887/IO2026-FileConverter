"""Single source of "now" for the whole app, so expiry logic can be tested without sleeping.

Always call `clock.now()` instead of `time.time()`. Tests use `freeze()` / `unfreeze()`.
"""

import time

_frozen_at: int | None = None


def now() -> int:
    """Current Unix time in whole seconds."""
    return _frozen_at if _frozen_at is not None else int(time.time())


def freeze(timestamp: int) -> None:
    """Make `now()` return `timestamp` until `unfreeze()` is called (tests only)."""
    global _frozen_at
    _frozen_at = timestamp


def unfreeze() -> None:
    global _frozen_at
    _frozen_at = None
