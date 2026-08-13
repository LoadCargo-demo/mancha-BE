"""오더 신뢰도/리스크 리포트 화면."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.mock_data import DRIVER_ID
from app.services.session_store import get

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/report", summary="오더별 성사 확률 / 자동 탈락 / 백업 오더")
def get_risk_report(driver_id: str = DRIVER_ID):
    session = get(driver_id)
    risk_result = session.get("risk_result")
    if not risk_result:
        raise HTTPException(
            status_code=404, detail="파이프라인을 먼저 실행하세요 (/pipeline/run)"
        )
    return risk_result
