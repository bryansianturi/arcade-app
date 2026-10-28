"""Running in a web browser: the arcade compiled to WebAssembly with pygbag.

The same code runs on the desktop and in the browser. The few places that
differ check :data:`IS_BROWSER`:

- saves go to the browser's ``localStorage`` (:class:`core.storage.BrowserStorage`);
- the page's canvas replaces the resizable OS window (:class:`core.display.BrowserDisplay`);
- there are no threads, so background work runs between frames
  (:mod:`core.background`), and computer opponents think for less time
  (:func:`think_limit`) so the page never freezes for long;
- window size, fullscreen and screenshots are left to the browser;
- the browser's ``decimal`` module is a placeholder, so :func:`patch_stdlib`
  swaps in CPython's pure-Python one (bundled by the build script).

Build the web version with ``python tools/build_web.py`` (see the README).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

IS_BROWSER = sys.platform == "emscripten"

#: Longest a computer opponent may think per move in the browser, in seconds.
BROWSER_THINK_LIMIT = 1.5


def think_limit(seconds: float) -> float:
    """A search time limit, capped in the browser where the search blocks the page."""
    return min(seconds, BROWSER_THINK_LIMIT) if IS_BROWSER else seconds


def patch_stdlib() -> None:
    """Replace standard-library modules that the browser build only stubs out.

    pygbag's ``decimal`` has a ``Decimal`` that takes no arguments, which breaks
    the Calculator and Unit Converter. ``tools/build_web.py`` bundles CPython's
    pure-Python implementation, ``_pydecimal``, and this makes ``import decimal``
    return it. Call before any app is imported.
    """
    import _pydecimal

    sys.modules["decimal"] = _pydecimal


class ConsoleHandler(logging.Handler):
    """Copies log records to the browser's developer console (F12 → Console).

    In the browser, Python's own output goes to pygbag's hidden terminal, so
    without this a crash would just leave a blank page.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            import platform

            platform.window.console.log(self.format(record))  # type: ignore[attr-defined]
        except Exception:  # never let logging itself break the game
            self.handleError(record)


def local_storage() -> Any:
    """The page's ``window.localStorage``. Only available in the browser."""
    import platform  # in pygbag this module is the bridge to the page's JavaScript

    return platform.window.localStorage  # type: ignore[attr-defined]
