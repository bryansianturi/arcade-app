"""App registration and auto-discovery.

Each app package calls :func:`register_app` (usually as a class decorator) when
it is imported. :func:`discover_apps` imports every sub-package of ``apps/``
so that registration happens without the launcher knowing any app by name.

Packages whose name starts with an underscore (such as ``apps/_template``) are
skipped unless the ``ARCADE_SHOW_TEMPLATE`` environment variable is set.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from dataclasses import dataclass, field
from typing import TypeVar

from core.base_app import BaseApp

log = logging.getLogger(__name__)

AppT = TypeVar("AppT", bound=type[BaseApp])

SHOW_PRIVATE_ENV = "ARCADE_SHOW_TEMPLATE"


class RegistrationError(Exception):
    """Raised when an app class is invalid or its id is already taken."""


@dataclass
class DiscoveryFailure:
    """An app package that could not be imported."""

    package: str
    error: str


@dataclass
class AppRegistry:
    """Holds the registered app classes, keyed by ``meta.id``."""

    _apps: dict[str, type[BaseApp]] = field(default_factory=dict)
    failures: list[DiscoveryFailure] = field(default_factory=list)

    def register(self, cls: AppT) -> AppT:
        """Register an app class. Returns the class so it works as a decorator."""
        if not (isinstance(cls, type) and issubclass(cls, BaseApp)):
            raise RegistrationError(f"{cls!r} is not a BaseApp subclass")
        meta = getattr(cls, "meta", None)
        if meta is None:
            raise RegistrationError(f"{cls.__name__} must define a 'meta' AppMeta")
        existing = self._apps.get(meta.id)
        if existing is not None and existing is not cls:
            raise RegistrationError(
                f"App id {meta.id!r} is used by both {existing.__qualname__} and {cls.__qualname__}"
            )
        self._apps[meta.id] = cls
        return cls

    def discover(self, package: str = "apps", include_private: bool | None = None) -> None:
        """Import every sub-package of ``package`` so that apps can register themselves.

        Import errors are logged and recorded in :attr:`failures`; they never stop
        the other apps (or the launcher) from loading.
        """
        if include_private is None:
            include_private = bool(os.environ.get(SHOW_PRIVATE_ENV))
        root = importlib.import_module(package)
        for info in sorted(pkgutil.iter_modules(root.__path__), key=lambda m: m.name):
            if not info.ispkg or (info.name.startswith("_") and not include_private):
                continue
            name = f"{package}.{info.name}"
            try:
                importlib.import_module(name)
            except Exception as exc:
                log.exception("Failed to load app package %s", name)
                self.failures.append(DiscoveryFailure(name, f"{type(exc).__name__}: {exc}"))

    def get(self, app_id: str) -> type[BaseApp] | None:
        return self._apps.get(app_id)

    def all(self) -> list[type[BaseApp]]:
        """Registered apps sorted by display name."""
        return sorted(self._apps.values(), key=lambda cls: cls.meta.name.lower())

    def __len__(self) -> int:
        return len(self._apps)


#: The process-wide registry used by the real application.
registry = AppRegistry()


def register_app(cls: AppT) -> AppT:
    """Class decorator that adds an app to the global registry."""
    return registry.register(cls)


def discover_apps(package: str = "apps") -> list[type[BaseApp]]:
    """Discover apps in ``package`` and return every registered app, sorted by name."""
    registry.discover(package)
    return registry.all()
