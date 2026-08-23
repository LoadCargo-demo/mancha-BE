"""밤 설계 파이프라인 — 단계별 엔드포인트. 순서를 지키지 않고 호출하면 409."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.agents.appraiser import run_appraiser
from app.agents.builder import build_packages
from app.agents.risk_predictor import run_risk_predictor
from app.agents.scout import apply_basic_filter
from app.models.appraisal import DriverCostProfile
from app.models.order import DriverConstraints
from app.services.mock_data import (
    DRIVER_CONSTRAINTS,
    DRIVER_COST_PROFILE,
    MOCK_NORMALIZED_ORDERS,
    MOCK_TRADE_HISTORY,
)
from app.services import session_store
from app.services.session_store import get, resolve_session_key, set_value

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _require(session: dict, key: str, step_name: str):
    value = session.get(key)
    if not value:
        raise HTTPException(
            status_code=409, detail=f"{step_name} 단계를 먼저 실행하세요."
        )
    return value


# --- 1) Scout ----------------------------------------------------------------
@router.post("/scout", summary="스카우트 실행 (오더 수집·정규화·기본 필터)")
def run_scout_step(driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    constraints: DriverConstraints = session.get("constraints") or DRIVER_CONSTRAINTS

    scout_passed = apply_basic_filter(MOCK_NORMALIZED_ORDERS, constraints)
    result = {
        "collected_count": len(MOCK_NORMALIZED_ORDERS),
        "passed_count": len(scout_passed),
        "passed_orders": scout_passed,
        "completed_at": datetime.now().isoformat(),
    }
    set_value(driver_id, "scout_result", result)
    set_value(driver_id, "pipeline_status", "scout_done")
    return result


# --- 2) Builder ----------------------------------------------------------------
@router.post("/builder", summary="빌더 실행 (하루 패키지 3안 생성)")
def run_builder_step(driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    scout_result = _require(session, "scout_result", "스카우트")
    constraints: DriverConstraints = session.get("constraints") or DRIVER_CONSTRAINTS

    packages, generated_count, passed_count = build_packages(
        scout_result["passed_orders"], constraints
    )
    if not packages:
        raise HTTPException(
            status_code=422, detail="조건을 만족하는 패키지를 찾지 못했습니다."
        )

    result = {
        "generated_combination_count": generated_count,
        "passed_constraint_count": passed_count,
        "packages": packages,
        "completed_at": datetime.now().isoformat(),
    }
    set_value(driver_id, "builder_result", result)
    set_value(driver_id, "pipeline_status", "builder_done")
    return result


# --- 3) Risk Predictor ---------------------------------------------------------
@router.post("/risk", summary="리스크 예측기 실행 (성사 확률·자동 탈락·백업)")
async def run_risk_step(driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    _require(session, "scout_result", "스카우트")

    risk_result = await run_risk_predictor(MOCK_NORMALIZED_ORDERS, MOCK_TRADE_HISTORY)
    set_value(driver_id, "risk_result", risk_result)
    set_value(driver_id, "pipeline_status", "risk_done")
    return risk_result


# --- 4) Appraiser ----------------------------------------------------------------
@router.post("/appraiser", summary="감정사 실행 (실수익 계산·3안 추천·근거 생성)")
async def run_appraiser_step(driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    builder_result = _require(session, "builder_result", "빌더")
    risk_result = _require(session, "risk_result", "리스크 예측기")
    cost_profile: DriverCostProfile = session.get("cost_profile") or DRIVER_COST_PROFILE

    excluded_order_ids = {
        r.order_id for r in risk_result.order_risks if r.is_auto_excluded
    }
    valid_packages = [
        p
        for p in builder_result["packages"]
        if not (excluded_order_ids & set(p.order_ids))
    ]
    if not valid_packages:
        raise HTTPException(
            status_code=422,
            detail="리스크 탈락 오더를 제외하고 나니 유효한 패키지가 남지 않았습니다. "
            "빌더를 다시 실행하거나 오더 조건을 조정하세요.",
        )

    appraisal = await run_appraiser(
        valid_packages,
        cost_profile,
        risk_result.order_risks,
        field_wait_data=session_store.get_field_wait_data(driver_id),
    )
    set_value(driver_id, "appraisal_result", appraisal)
    set_value(driver_id, "pipeline_status", "briefing_ready")
    return appraisal


@router.post("/run-all", summary="Scout→Builder→Risk→Appraiser 순차 실행 (테스트용)")
async def run_all(driver_id: str = Depends(resolve_session_key)):
    run_scout_step(driver_id)
    run_builder_step(driver_id)
    await run_risk_step(driver_id)
    appraisal = await run_appraiser_step(driver_id)
    session = get(driver_id)
    return {
        "driver_id": driver_id,
        "status": session["pipeline_status"],
        "scout": session["scout_result"],
        "builder": session["builder_result"],
        "risk": session["risk_result"],
        "appraisal": appraisal,
    }


@router.get("/status", summary="에이전트 단계별 진행 상황 조회")
def get_pipeline_status(driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    return {
        "status": session.get("pipeline_status", "not_started"),
        "scout": session.get("scout_result"),
        "builder": session.get("builder_result"),
        "risk_excluded_count": (
            session["risk_result"].excluded_count
            if session.get("risk_result")
            else None
        ),
    }
