"""The banner shown while a replay plays: what it is, its score and progress."""

from __future__ import annotations

import pygame

from core import draw, gfx
from core.canvas import Canvas
from core.replay import Player
from core.theme import Color, Theme, lerp_color
from core.widgets.menu import draw_panel


def draw_replay_banner(
    surface: Canvas,
    theme: Theme,
    area: pygame.Rect,
    player: Player,
    accent: Color,
    stop_key: str,
) -> None:
    """Draw the banner centered at the top of ``area`` (usually the playfield)."""
    t = theme
    p = t.palette
    replay = player.replay
    score = f"{replay.score:,.0f}"
    title = f"Best run · {score}"
    hint = f"{stop_key} to stop"
    title_font = t.font(t.size.label, "semibold")
    hint_font = t.font(t.size.caption)
    width = max(300, title_font.size(title)[0] + hint_font.size(hint)[0] + 96)
    rect = pygame.Rect(0, 0, width, 52)
    rect.midtop = (area.centerx, area.y + 14)
    draw_panel(surface, rect, t)
    # A "play" triangle in an accent circle.
    dot = (rect.x + 26, rect.y + 22)
    gfx.circle(surface, lerp_color(p.surface, accent, 0.25), dot, 13)
    gfx.polygon(
        surface, accent, [(dot[0] - 4, dot[1] - 6), (dot[0] - 4, dot[1] + 6), (dot[0] + 6, dot[1])]
    )
    draw.text(surface, title, title_font, p.text, (rect.x + 48, dot[1]), "midleft")
    draw.text(surface, hint, hint_font, p.text_muted, (rect.right - 16, dot[1]), "midright")
    bar = pygame.Rect(rect.x + 16, rect.bottom - 10, rect.width - 32, 4)
    gfx.rect(surface, p.surface_alt, bar, border_radius=2)
    done = bar.copy()
    done.width = max(4, round(bar.width * player.progress))
    gfx.rect(surface, accent, done, border_radius=2)
