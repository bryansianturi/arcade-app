"""Developer mode: hot reload and the debug overlay."""

from __future__ import annotations

import importlib
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

import core.registry as registry_module
from core import devtools
from core.app_host import AppHost, HostState
from core.canvas import Canvas
from core.registry import AppRegistry
from core.services import Services
from core.settings import Settings
from tests.conftest import host_app
from tests.test_registry import MANIFEST

SOURCE = """
from core.base_app import BaseApp
from core.registry import register_app

@register_app
class Counter(BaseApp):
    LABEL = "{label}"
    def on_enter(self):
        self.count = self.data.get("count", 0)
    def on_exit(self):
        self.data["count"] = self.count + 1
        self.data.save()
    def handle_event(self, event): pass
    def update(self, dt): pass
    def draw(self, surface): pass
"""


@pytest.fixture
def live_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    name = f"devapps_{uuid.uuid4().hex[:8]}"
    folder = tmp_path / name / "counter"
    folder.mkdir(parents=True)
    (tmp_path / name / "__init__.py").write_text("")
    (folder / "__init__.py").write_text(SOURCE.format(label="v1"))
    (folder / "app.toml").write_text(MANIFEST.format(id="counter", name="Counter", fw="1.0"))
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(registry_module, "registry", AppRegistry())
    registry_module.registry.discover(name)
    yield folder
    for mod in [m for m in sys.modules if m.startswith(name)]:
        del sys.modules[mod]


def write(path: Path, text: str) -> None:
    path.write_text(text)
    importlib.invalidate_caches()


def test_hot_reload_swaps_code_and_keeps_saved_state(services: Services, live_app: Path) -> None:
    old = registry_module.registry.get("counter")
    assert old is not None
    services.apps = [old]
    host = host_app(services, old)
    write(live_app / "__init__.py", SOURCE.format(label="v2-with-longer-text"))
    write(live_app / "app.toml", MANIFEST.format(id="counter", name="Counter Two", fw="1.0"))
    assert devtools.hot_reload(services)
    new = host.app_cls
    assert new is not old and new.LABEL == "v2-with-longer-text"  # type: ignore[attr-defined]
    assert new.meta.name == "Counter Two" and services.apps == [new]
    assert host.app is not None and host.app.count == 1  # type: ignore[attr-defined]
    assert host.state is HostState.RUNNING
    assert services.toasts.toasts[-1].title == "Reloaded Counter Two"


def test_failed_reload_keeps_the_old_app(services: Services, live_app: Path) -> None:
    old = registry_module.registry.get("counter")
    assert old is not None
    services.apps = [old]
    host = host_app(services, old)
    write(live_app / "__init__.py", "this is not python(")
    assert not devtools.hot_reload(services)
    assert host.app_cls is old and isinstance(host.app, old)
    assert registry_module.registry.get("counter") is old
    assert not registry_module.registry.failures
    assert "SyntaxError" in services.toasts.toasts[-1].message
    write(live_app / "app.toml", 'id = "counter"\n')  # broken manifest
    write(live_app / "__init__.py", SOURCE.format(label="ok"))
    assert not devtools.hot_reload(services)
    assert registry_module.registry.get("counter") is old


def test_reload_needs_an_open_app(services: Services) -> None:
    assert not devtools.hot_reload(services)
    assert services.toasts.toasts[-1].title == "Nothing to reload"


def test_overlay(services: Services, live_app: Path) -> None:
    app = registry_module.registry.get("counter")
    assert app is not None
    host = host_app(services, app)
    assert isinstance(host, AppHost)
    lines = devtools.overlay_lines(services, 59.9, 16.7)
    assert lines[0].startswith(" 59.9 FPS") and any("App: counter v1.0.0" in ln for ln in lines)
    devtools.draw_overlay(Canvas.new(services.scenes.size), services, 60, 16)


def test_old_show_fps_setting_becomes_developer_mode() -> None:
    s = Settings()
    s.update_from_dict({"show_fps": True})
    assert s.developer_mode
    s = Settings()
    s.update_from_dict({"show_fps": True, "developer_mode": False})
    assert not s.developer_mode
