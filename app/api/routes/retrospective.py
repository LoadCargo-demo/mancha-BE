"""하루 복기 화면"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.mock_data import DRIVER_COST_PROFILE
from app.services.session_store import (
    get,
    get_field_wait_data,
    resolve_session_key,
    set_value,
    update_field_wait_data,
)

router = APIRouter(prefix="/retrospective", tags=["retrospective"])

STRUCTURAL_WAIT_DEVIATION_MIN = 15


class VoiceNote(BaseModel):
    text: str


def _find_appraised(appraisal, package_id: str):
    return next(
        (ap for ap in appraisal.ranked_packages if ap.package.package_id == package_id),
        None,
    )


@router.get("/summary", summary="공차 비교, 예측 대비 실제")
def get_summary(driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    package = session.get("confirmed_package")
    appraisal = session.get("appraisal_result")
    rebuild_result = session.get("last_rebuild_result")

    predicted_wait = None
    predicted_profit = None
    matched = None
    if appraisal:
        matched = (
            _find_appraised(appraisal, package.package_id) if package else None
        ) or next(
            (
                ap
                for ap in appraisal.ranked_packages
                if ap.package.package_id == appraisal.recommended_package_id
            ),
            None,
        )
        if matched:
            predicted_wait = matched.expected_wait_min
            predicted_profit = matched.adjusted_profit

    actual_wait = predicted_wait
    structural_cause = None
    affected_location = None
    field_wait_data = get_field_wait_data(driver_id)

    if rebuild_result and package:
        for block in package.blocks:
            if block.is_fixed:
                continue
            if field_wait_data.get(block.location):
                affected_location = block.location
                break

        if affected_location is not None and predicted_wait is not None:
            actual_wait = predicted_wait + STRUCTURAL_WAIT_DEVIATION_MIN
            structural_cause = (
                f"{affected_location} 하역장은 최근 운행에서도 평균보다 대기가 길게 "
                "반복 관측돼 구조적 특성으로 판단됩니다."
            )

    wait_diff = (
        actual_wait - predicted_wait
        if actual_wait is not None and predicted_wait is not None
        else None
    )
    cost_per_min = DRIVER_COST_PROFILE.value_per_hour / 60
    actual_profit = (
        round(predicted_profit - wait_diff * cost_per_min)
        if predicted_profit is not None and wait_diff
        else predicted_profit
    )

    if affected_location is not None and wait_diff:
        field = field_wait_data[affected_location]
        update_field_wait_data(
            driver_id, affected_location, actual_wait, field["sample_count"] + 1
        )
        prefs = session.get("driver_preferences", {})
        prefs["on_time_return_weight"] = round(
            prefs.get("on_time_return_weight", 1.0) + 0.1, 2
        )
        set_value(driver_id, "driver_preferences", prefs)

    predicted_return = (
        matched.package.return_time
        if matched
        else (package.return_time if package else None)
    )
    actual_return = package.return_time if package else None

    return {
        "today_empty_km": package.empty_km if package else None,
        "last_week_empty_km": 412,
        "predicted_profit": predicted_profit,
        "actual_profit": actual_profit,
        "predicted_wait_min": predicted_wait,
        "actual_wait_min": actual_wait,
        "wait_diff_min": wait_diff,
        "predicted_return": predicted_return,
        "actual_return": actual_return,
        "structural_cause": structural_cause,
        "note": "오차 원인 판정은 규칙 기반이며, 실제 ML 모델은 사용하지 않습니다.",
    }


@router.post("/voice-note", summary="한 줄 남기기")
def submit_voice_note(note: VoiceNote, driver_id: str = Depends(resolve_session_key)):
    return {"received": True, "text": note.text, "structured": None}
