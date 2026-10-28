"""The contract every mini-app implements.

A minimal app looks like this::

    from core.base_app import AppMeta, BaseApp
    from core.registry import register_app

    @register_app
    class HelloApp(BaseApp):
        meta = AppMeta(id="hello", name="Hello", description="Says hi",
                       category="tool", accent=(120, 200, 255))

        def handle_event(self, event): ...
        def update(self, dt): ...
        def draw(self, surface): ...

The framework (see :mod:`core.app_host`) owns the pause menu, restarting,
returning to the launcher and crash recovery, so apps only deal with their own
gameplay. Apps draw onto a :class:`~core.canvas.Canvas` of ``ctx.screen_rect``
size (1280×720 logical pixels) using ``core.gfx`` instead of ``pygame.draw``;
the canvas renders at the display's real resolution, so drawings stay sharp at
any window size and on high-DPI screens.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Literal

import pygame

from core import draw
from core.achievements import Achievement, AchievementService
from core.canvas import Canvas
from core.daily import DailyChallenge
from core.input import InputMap
from core.settings import Settings
from core.storage import DEFAULT_VARIANT, AppData, ScoreEntry, ScoreOrder, Storage
from core.theme import Color, Theme, readable_on
from core.toasts import ToastService

Category = Literal["game", "tool"]
ScoreFormat = Literal["points", "time"]


@dataclass(frozen=True)
class AppMeta:
    """Static description of an app, shown in the launcher and high scores screen.

    Attributes:
        id: Unique, stable identifier. Also used as the storage key, so don't rename it.
        name: Display name.
        description: One short line for the launcher card.
        category: ``"game"`` or ``"tool"`` (drives the launcher filter tabs).
        accent: Brand color for the card and in-app highlights.
        tracks_scores: Whether the app appears on the High Scores screen.
        score_order: ``"higher"`` if bigger is better (points), ``"lower"`` for times.
        score_format: How scores are displayed: plain ``"points"`` or ``"time"`` (m:ss).
        variants: Ordered score variants (e.g. difficulties). ``()`` means a single
            ``"default"`` variant.
        version: The app's own version.
        author: Who made it.
        min_framework: Oldest framework version (``core.manifest.FRAMEWORK_VERSION``)
            the app supports.
        achievements: Achievements the app can unlock with ``self.unlock(id)``.

    Discovered apps get their ``AppMeta`` from ``app.toml`` (see :mod:`core.manifest`).
    """

    id: str
    name: str
    description: str
    category: Category
    accent: Color
    tracks_scores: bool = False
    score_order: ScoreOrder = "higher"
    score_format: ScoreFormat = "points"
    variants: tuple[str, ...] = ()
    version: str = "1.0.0"
    author: str = ""
    min_framework: str = "1.0"
    achievements: tuple[Achievement, ...] = ()

    def score_variants(self) -> tuple[str, ...]:
        """Variants to display on the High Scores screen."""
        return self.variants or (DEFAULT_VARIANT,)


@dataclass
class AppContext:
    """Shared services handed to every app. Apps never import launcher/screen code."""

    theme: Theme
    storage: Storage
    settings: Settings
    screen_rect: pygame.Rect
    request_exit: Callable[[], None]
    request_pause: Callable[[], None]
    input: InputMap
    achievements: AchievementService
    toasts: ToastService


class BaseApp(ABC):
    """Base class for every mini-app. Subclass it, set ``meta`` and register it."""

    meta: ClassVar[AppMeta]

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._data: AppData | None = None

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        """Called when the app is launched and again after every Restart.

        Put (re)initialisation of game state here rather than in ``__init__``.
        """

    def on_exit(self) -> None:
        """Called before leaving the app or restarting it. Save anything here."""

    def on_pause(self) -> None:
        """Called when the pause menu opens (Esc, or the window losing focus)."""

    def on_resume(self) -> None:
        """Called when the pause menu closes and gameplay continues."""

    def restart(self) -> None:
        """Start over. The default runs :meth:`on_exit` then :meth:`on_enter`."""
        self.on_exit()
        self.on_enter()

    @abstractmethod
    def handle_event(self, event: pygame.event.Event) -> None:
        """React to one pygame event (mouse positions are already in canvas space).

        Besides raw pygame events this receives ``core.input.ACTIONDOWN`` /
        ``ACTIONUP`` for the shared, remappable controls; use
        ``core.input.is_action(event, "left")`` rather than checking arrow keys.
        """

    @abstractmethod
    def update(self, dt: float) -> None:
        """Advance the simulation by ``dt`` seconds. Not called while paused."""

    @abstractmethod
    def draw(self, surface: Canvas) -> None:
        """Render the current frame onto ``surface``."""

    # ------------------------------------------------------------------ hooks
    def captures_pause(self) -> bool:
        """Return ``True`` to receive the ``pause`` action yourself (e.g. to close an
        in-app dialog). By default it opens the framework's pause menu.
        """
        return False

    def wants_text(self) -> bool:
        """Same as :meth:`uses_text_input` (mirrors ``Scene.wants_text``)."""
        return self.uses_text_input()

    def uses_text_input(self) -> bool:
        """Return ``True`` if the app takes typed text.

        Printable keys then produce no actions (typing "w" must not also mean "up").
        """
        return False

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        """Draw the app's launcher icon inside ``rect``. Override for a custom icon.

        The default shows the first letter of the app's name on its accent color.
        """
        draw.rounded_rect(surface, rect, cls.meta.accent, theme.radius.md)
        font = theme.font(int(rect.height * 0.5), "bold")
        draw.text(
            surface, cls.meta.name[:1], font, readable_on(cls.meta.accent), rect.center, "center"
        )

    # ------------------------------------------------------------------ helpers
    @property
    def theme(self) -> Theme:
        return self.ctx.theme

    @property
    def input(self) -> InputMap:
        """Shared controls: ``self.input.held("left")`` for continuous movement."""
        return self.ctx.input

    @property
    def data(self) -> AppData:
        """Persistent, app-private key/value storage. Call ``self.data.save()``."""
        if self._data is None:
            self._data = self.ctx.storage.app_data(self.meta.id)
        return self._data

    @property
    def daily(self) -> DailyChallenge:
        """Today's date-seeded challenge (same for everyone) and its saved results."""
        return DailyChallenge(self.meta.id, self.data)

    def submit_score(self, score: float, variant: str = DEFAULT_VARIANT) -> bool:
        """Record ``score`` and return ``True`` if it is a new personal best."""
        return self.ctx.storage.record_score(self.meta.id, score, variant, self.meta.score_order)

    def best_score(self, variant: str = DEFAULT_VARIANT) -> ScoreEntry | None:
        """Return the stored best score for ``variant``, if any."""
        return self.ctx.storage.best_score(self.meta.id, variant)

    def unlock(self, achievement_id: str) -> bool:
        """Unlock one of this app's achievements (declared in ``app.toml``).

        Returns ``True`` the first time; later calls are cheap no-ops.
        """
        return self.ctx.achievements.unlock(self.meta.id, achievement_id)

    def unlock_milestones(self, value: float, milestones: Mapping[str, float]) -> None:
        """Unlock every achievement whose threshold ``value`` has reached.

        ``self.unlock_milestones(score, {"score_25": 25, "score_50": 50})``
        """
        for achievement_id, needed in milestones.items():
            if value >= needed:
                self.unlock(achievement_id)

    def exit_to_launcher(self) -> None:
        """Leave the app and return to the launcher."""
        self.ctx.request_exit()

    def pause(self) -> None:
        """Open the framework pause menu programmatically (e.g. from a pause button)."""
        self.ctx.request_pause()


def format_score(value: float, fmt: ScoreFormat) -> str:
    """Format a score for display: ``1234`` → ``"1,234"``; times → ``"m:ss"``."""
    if fmt == "time":
        total = round(value)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
    return f"{int(value):,}"
