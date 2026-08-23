"""하루 등록 화면."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.registration import generate_weather_suggestion_message
from app.models.order import DriverConstraints
from app.services.mock_data import DRIVER_CONSTRAINTS
from app.services.session_store import get, resolve_session_key, set_value

router = APIRouter(prefix="/registration", tags=["registration"])


@router.get("/prefill", summary="조건 프리필 (과거 패턴 + 기상 연동)")
async def get_prefill(driver_id: str = Depends(resolve_session_key)):
    """실제로는 과거 등록 이력 요일 패턴 + 기상 API를 결합해야 하지만
    지금은 고정 mock 프리필을 반환한다. ai_suggestion.message만 Gemini가 문장으로 다듬고,
    type/applied 및 제안 내용 자체는 항상 Python(mock rule)이 결정한다.
    """
    stored = get(driver_id).get("constraints")
    base = stored or DRIVER_CONSTRAINTS
    message = await generate_weather_suggestion_message()
    return {
        "prefill": base,
        "prefill_source": "stored" if stored else "mock_pattern",
        "ai_suggestion": {
            "type": "weather",
            "message": message,
            "applied": False,
        },
    }


@router.post("/day", summary="등록 실행 → 밤 설계 파이프라인 트리거")
def register_day(constraints: DriverConstraints, driver_id: str = Depends(resolve_session_key)):
    set_value(driver_id, "constraints", constraints)
    set_value(driver_id, "pipeline_status", "registered")
    return {
        "driver_id": driver_id,
        "status": "registered",
        "message": "등록 완료. 브리핑은 내일 04:40에 도착합니다.",
    }
