from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pygame
import pytest

import core.registry as registry_module
from core.base_app import AppContext, AppMeta, BaseApp
from core.registry import AppRegistry, RegistrationError

APP_SOURCE = """
from core.base_app import AppMeta, BaseApp
from core.registry import register_app

@register_app
class {cls}(BaseApp):
    meta = AppMeta(id="{id}", name="{name}", description="d", category="game", accent=(1, 2, 3))
    def handle_event(self, event): pass
    def update(self, dt): pass
    def draw(self, surface): pass
"""


@pytest.fixture
def fake_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Build a throwaway ``apps``-like package and return its import name."""
    name = f"fakeapps_{uuid.uuid4().hex[:8]}"
    root = tmp_path / name
    root.mkdir()
    (root / "__init__.py").write_text("")
    for pkg, cls, app_id, app_name in [
        ("beta", "Beta", "beta", "Beta"),
        ("alpha", "A", "a", "Alpha"),
        ("_hidden", "H", "hidden", "Hidden"),
    ]:
        (root / pkg).mkdir()
        (root / pkg / "__init__.py").write_text(
            APP_SOURCE.format(cls=cls, id=app_id, name=app_name)
        )
    (root / "broken").mkdir()
    (root / "broken" / "__init__.py").write_text("raise RuntimeError('boom')")
    (root / "loose_module.py").write_text("raise AssertionError('modules are not apps')")

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(registry_module, "registry", AppRegistry())
    monkeypatch.delenv(registry_module.SHOW_PRIVATE_ENV, raising=False)
    yield name
    for mod in [m for m in sys.modules if m.startswith(name)]:
        del sys.modules[mod]


def test_discovery_registers_apps_sorted_and_skips_private(fake_apps: str) -> None:
    apps = registry_module.discover_apps(fake_apps)
    assert [a.meta.name for a in apps] == ["Alpha", "Beta"]


def test_broken_package_is_recorded_not_raised(fake_apps: str) -> None:
    registry_module.discover_apps(fake_apps)
    failures = registry_module.registry.failures
    assert len(failures) == 1
    assert failures[0].package.endswith(".broken") and "boom" in failures[0].error


def test_private_packages_can_be_included(fake_apps: str) -> None:
    registry_module.registry.discover(fake_apps, include_private=True)
    assert registry_module.registry.get("hidden") is not None


class _Ok(BaseApp):
    meta = AppMeta(id="ok", name="Ok", description="", category="tool", accent=(0, 0, 0))

    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...


def test_duplicate_ids_are_rejected() -> None:
    reg = AppRegistry()
    reg.register(_Ok)
    reg.register(_Ok)  # re-registering the same class is harmless

    class Clash(_Ok):
        pass

    with pytest.raises(RegistrationError, match="ok"):
        reg.register(Clash)


def test_non_apps_are_rejected() -> None:
    reg = AppRegistry()
    with pytest.raises(RegistrationError):
        reg.register(int)  # type: ignore[type-var]

    class NoMeta(BaseApp):
        def handle_event(self, event: pygame.event.Event) -> None: ...
        def update(self, dt: float) -> None: ...
        def draw(self, surface: pygame.Surface) -> None: ...

    with pytest.raises(RegistrationError, match="meta"):
        reg.register(NoMeta)


def test_base_app_helpers(app_context: AppContext) -> None:
    app = _Ok(app_context)
    assert app.submit_score(5) is True
    assert app.submit_score(3) is False
    best = app.best_score()
    assert best is not None and best.score == 5
    app.data["k"] = 1
    app.data.save()
    assert app_context.storage.app_data("ok")["k"] == 1
