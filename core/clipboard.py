"""Copy text to the system clipboard (or the browser's), never raising.

``copy_text("hello")`` returns ``True`` on success so the caller can show a
"Copied" toast, and ``False`` if no clipboard is available (for example a
browser that refuses access).
"""

from __future__ import annotations

import logging

import pygame

from core.web import IS_BROWSER

log = logging.getLogger(__name__)


def copy_text(text: str) -> bool:
    """Put ``text`` on the clipboard. Returns whether it worked."""
    try:
        if IS_BROWSER:
            import platform

            platform.window.navigator.clipboard.writeText(text)  # type: ignore[attr-defined]
        else:
            pygame.scrap.put_text(text)
    except Exception as exc:  # no clipboard is never fatal
        log.warning("Couldn't copy to the clipboard: %s", exc)
        return False
    return True
