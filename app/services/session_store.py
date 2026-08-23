"""데모/MVP용 인메모리 세션 저장소"""

from __future__ import annotations

from typing import Any

from app.services.mock_data import MOCK_FIELD_WAIT_DATA

_STORE: dict[str, dict[str, Any]] = {}


def get(driver_id: str) -> dict[str, Any]:
    return _STORE.setdefault(driver_id, {})


def set_value(driver_id: str, key: str, value: Any) -> None:
    _STORE.setdefault(driver_id, {})[key] = value


def clear(driver_id: str) -> None:
    _STORE.pop(driver_id, None)


def get_field_wait_data(driver_id: str) -> dict[str, dict]:
    """MOCK_FIELD_WAIT_DATA 기본값 + 이 세션에서 학습으로 보정된 값(있으면 우선)."""
    overrides = get(driver_id).get("field_wait_overrides", {})
    return {**MOCK_FIELD_WAIT_DATA, **overrides}


def update_field_wait_data(driver_id: str, location: str, avg_wait_min: int, sample_count: int) -> None:
    """복기 단계의 학습 결과를 세션 범위로만 반영한다 (다른 세션에 새지 않도록)."""
    session = get(driver_id)
    overrides = session.setdefault("field_wait_overrides", {})
    overrides[location] = {"avg_wait_min": avg_wait_min, "sample_count": sample_count}
