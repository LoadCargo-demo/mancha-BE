"""아침 음성 브리핑 / 패키지 비교 / 보정 내역"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.services.session_store import get, resolve_session_key, set_value

router = APIRouter(prefix="/briefing", tags=["briefing"])


def _get_appraisal(driver_id: str):
    session = get(driver_id)
    appraisal = session.get("appraisal_result")
    if not appraisal:
        raise HTTPException(
            status_code=404, detail="파이프라인을 먼저 실행하세요 (/pipeline/run)"
        )
    return appraisal


@router.get("/voice", summary="30초 음성 브리핑 텍스트 (TTS 입력용)")
def get_voice_briefing(driver_id: str = Depends(resolve_session_key)):
    appraisal = _get_appraisal(driver_id)
    recommended = next(
        (
            ap
            for ap in appraisal.ranked_packages
            if ap.package.package_id == appraisal.recommended_package_id
        ),
        None,
    )
    return {
        "briefing_text": appraisal.briefing_text,
        "recommended_package_id": appraisal.recommended_package_id,
        "expected_wait_min": recommended.expected_wait_min if recommended else None,
        "success_probability": recommended.success_probability if recommended else None,
    }


@router.get("/compare", summary="패키지 3안 비교")
def compare_packages(driver_id: str = Depends(resolve_session_key)):
    appraisal = _get_appraisal(driver_id)
    return {
        "packages": appraisal.ranked_packages,
        "recommendation_reason": appraisal.recommendation_reason,
    }


@router.get("/adjustment", summary="보정 내역 (명목 vs 실수익)")
def get_adjustment_detail(driver_id: str = Depends(resolve_session_key)):
    appraisal = _get_appraisal(driver_id)
    return {"packages": appraisal.ranked_packages}


@router.post("/confirm", summary="확정 실행 -> 확정된 하루 화면 데이터 반환")
def confirm_package(package_id: str, driver_id: str = Depends(resolve_session_key)):
    appraisal = _get_appraisal(driver_id)
    chosen = next(
        (p for p in appraisal.ranked_packages if p.package.package_id == package_id),
        None,
    )
    if not chosen:
        raise HTTPException(status_code=404, detail="해당 패키지를 찾을 수 없습니다.")
    set_value(driver_id, "confirmed_package", chosen.package)
    set_value(driver_id, "pipeline_status", "confirmed")
    return {
        "status": "confirmed",
        "package": chosen.package,
        "adjusted_profit": chosen.adjusted_profit,
    }
