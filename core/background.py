"""Run work off the frame loop: on a thread where possible, else between frames.

Computer opponents search on a background thread so the UI keeps animating.
Browsers (WebAssembly) have no threads; there the work is queued and run by the
main loop right after a frame is drawn, so a "thinking" indicator still shows
before the search starts.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from core.web import IS_BROWSER

#: Whether :func:`run_in_background` uses threads. Tests may switch it off.
USE_THREADS = not IS_BROWSER

_pending: list[Callable[[], None]] = []


def run_in_background(work: Callable[[], None]) -> None:
    """Start ``work`` on a daemon thread, or queue it for :func:`run_pending`."""
    if USE_THREADS:
        threading.Thread(target=work, daemon=True).start()
    else:
        _pending.append(work)


def run_pending() -> None:
    """Run queued work. The main loop calls this once per frame, after drawing."""
    while _pending:
        _pending.pop(0)()
