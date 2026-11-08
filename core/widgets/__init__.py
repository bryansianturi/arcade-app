"""Reusable UI widgets. Import from here: ``from core.widgets import Button, Card``."""

from core.widgets.base import Widget, approach
from core.widgets.button import Button
from core.widgets.card import Card
from core.widgets.grid import Grid
from core.widgets.label import Label
from core.widgets.menu import ButtonMenu, draw_panel
from core.widgets.replay_banner import draw_replay_banner
from core.widgets.segmented import SegmentedControl
from core.widgets.slider import Slider
from core.widgets.text_input import TextInput
from core.widgets.toggle import Toggle

__all__ = [
    "Button",
    "ButtonMenu",
    "Card",
    "Grid",
    "Label",
    "SegmentedControl",
    "Slider",
    "TextInput",
    "Toggle",
    "Widget",
    "approach",
    "draw_panel",
    "draw_replay_banner",
]
