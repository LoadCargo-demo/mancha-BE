"""데모/MVP용 인메모리 세션 저장소"""

from __future__ import annotations

from typing import Any

_STORE: dict[str, dict[str, Any]] = {}


def get(driver_id: str) -> dict[str, Any]:
    return _STORE.setdefault(driver_id, {})


def set_value(driver_id: str, key: str, value: Any) -> None:
    _STORE.setdefault(driver_id, {})[key] = value


def clear(driver_id: str) -> None:
    _STORE.pop(driver_id, None)
