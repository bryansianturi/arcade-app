"""Scene stack with animated transitions.

A *scene* is one full-screen state: the launcher, settings, high scores, or an
app (wrapped in :class:`core.app_host.AppHost`). Scenes are kept on a stack so
"Back" simply pops to whatever was underneath.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pygame

if TYPE_CHECKING:
    from core.services import Services

TransitionKind = Literal["slide", "fade", "none"]

TRANSITION_SECONDS = 0.22
SLIDE_DISTANCE = 48


class Scene:
    """Base class for screens managed by :class:`SceneManager`."""

    def __init__(self, services: Services) -> None:
        self.services = services

    @property
    def manager(self) -> SceneManager:
        return self.services.scenes

    def on_enter(self) -> None:
        """Called when the scene is pushed onto the stack."""

    def on_exit(self) -> None:
        """Called when the scene is removed from the stack."""

    def on_reveal(self) -> None:
        """Called when the scene above this one is popped and this one is visible again."""

    def handle_event(self, event: pygame.event.Event) -> None:
        """React to an input event."""

    def update(self, dt: float) -> None:
        """Advance animations/state by ``dt`` seconds."""

    def draw(self, surface: pygame.Surface) -> None:
        """Render the scene."""


@dataclass
class _Transition:
    snapshot: pygame.Surface  # frozen image of the outgoing scene
    forward: bool  # True for push/replace, False for pop
    kind: TransitionKind
    elapsed: float = 0.0

    @property
    def progress(self) -> float:
        return min(1.0, self.elapsed / TRANSITION_SECONDS)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class SceneManager:
    """Owns the scene stack and draws transitions between scenes."""

    def __init__(self, size: tuple[int, int], animations: bool = True) -> None:
        self.size = size
        self.animations = animations
        self._stack: list[Scene] = []
        self._transition: _Transition | None = None
        self._buffer = pygame.Surface(size)

    # ------------------------------------------------------------------ stack
    @property
    def current(self) -> Scene | None:
        return self._stack[-1] if self._stack else None

    @property
    def depth(self) -> int:
        return len(self._stack)

    def push(self, scene: Scene, transition: TransitionKind = "slide") -> None:
        """Show ``scene`` on top of the current one."""
        self._begin(forward=True, kind=transition)
        self._stack.append(scene)
        scene.on_enter()

    def pop(self, transition: TransitionKind = "slide") -> None:
        """Close the current scene and return to the one underneath."""
        if len(self._stack) <= 1:
            return
        self._begin(forward=False, kind=transition)
        self._stack.pop().on_exit()
        self._stack[-1].on_reveal()

    def replace(self, scene: Scene, transition: TransitionKind = "fade") -> None:
        """Swap the current scene for ``scene``."""
        self._begin(forward=True, kind=transition)
        if self._stack:
            self._stack.pop().on_exit()
        self._stack.append(scene)
        scene.on_enter()

    def pop_to_root(self, transition: TransitionKind = "fade") -> None:
        """Return to the bottom scene (the launcher)."""
        if len(self._stack) <= 1:
            return
        self._begin(forward=False, kind=transition)
        while len(self._stack) > 1:
            self._stack.pop().on_exit()
        self._stack[-1].on_reveal()

    def shutdown(self) -> None:
        """Exit every scene, top first (called when the program closes)."""
        while self._stack:
            self._stack.pop().on_exit()

    # ------------------------------------------------------------------ loop
    @property
    def transitioning(self) -> bool:
        return self._transition is not None

    def handle_event(self, event: pygame.event.Event) -> None:
        # Input is ignored mid-transition so a double click can't hit two screens.
        if self.current is not None and not self.transitioning:
            self.current.handle_event(event)

    def update(self, dt: float) -> None:
        if self._transition is not None:
            self._transition.elapsed += dt
            if self._transition.progress >= 1.0:
                self._transition = None
        if self.current is not None:
            self.current.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        scene = self.current
        if scene is None:
            return
        tr = self._transition
        if tr is None:
            scene.draw(surface)
            return

        t = ease_out_cubic(tr.progress)
        slide = SLIDE_DISTANCE if tr.kind == "slide" else 0
        self._buffer.fill((0, 0, 0))
        scene.draw(self._buffer)
        if tr.forward:
            # Old screen stays put; new screen fades/slides in on top.
            surface.blit(tr.snapshot, (0, 0))
            self._buffer.set_alpha(round(255 * t))
            surface.blit(self._buffer, (round(slide * (1 - t)), 0))
        else:
            # Revealed screen is underneath; old screen fades/slides out.
            surface.blit(self._buffer, (0, 0))
            tr.snapshot.set_alpha(round(255 * (1 - t)))
            surface.blit(tr.snapshot, (round(slide * t), 0))
        self._buffer.set_alpha(None)

    # ------------------------------------------------------------------ internals
    def _begin(self, forward: bool, kind: TransitionKind) -> None:
        if not self.animations or kind == "none" or self.current is None:
            self._transition = None
            return
        snapshot = pygame.Surface(self.size)
        self.current.draw(snapshot)
        self._transition = _Transition(snapshot=snapshot, forward=forward, kind=kind)
