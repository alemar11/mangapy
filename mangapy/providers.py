from __future__ import annotations

from typing import Any, Dict, Type


_REGISTRY: Dict[str, Type[Any]] = {}
_LOADED = False


def register_provider(name: str, repo_cls: Type[Any]) -> None:
    _REGISTRY[name.lower()] = repo_cls


def load_providers() -> None:
    global _LOADED
    if _LOADED:
        return
    from mangapy.fanfox import FanFoxRepository

    register_provider("fanfox", FanFoxRepository)
    _LOADED = True


def get_repository(name: str):
    load_providers()
    key = name.lower()
    if key not in _REGISTRY:
        raise ValueError(f"Source {name} is missing")
    return _REGISTRY[key]()


def available_providers() -> list[str]:
    load_providers()
    return sorted(_REGISTRY.keys())
