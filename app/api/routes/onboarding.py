"""원가 입력 / 제약 조건 입력."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.constants import DEMO_DAILY_HOURS_ASSUMPTION, DEMO_DAILY_KM_ASSUMPTION
from app.models.appraisal import DriverCostProfile
from app.models.order import DriverConstraints
from app.services.session_store import resolve_session_key, set_value

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/cost-profile", summary="원가 입력 -> 손익분기 자동 계산")
def submit_cost_profile(profile: DriverCostProfile, driver_id: str = Depends(resolve_session_key)):
    if profile.min_fare_per_km is None:
        profile.min_fare_per_km = round(profile.cost_per_km * 1.15)

    if profile.daily_min_revenue is None:
        profile.daily_min_revenue = round(
            profile.cost_per_km * DEMO_DAILY_KM_ASSUMPTION
            + profile.value_per_hour * DEMO_DAILY_HOURS_ASSUMPTION
        )

    set_value(driver_id, "cost_profile", profile)
    return {
        "driver_id": driver_id,
        "cost_profile": profile,
        "break_even": {
            "min_fare_per_km": profile.min_fare_per_km,
            "daily_min_revenue": profile.daily_min_revenue,
        },
    }


@router.post("/constraints", summary="제약 조건 입력")
def submit_constraints(constraints: DriverConstraints, driver_id: str = Depends(resolve_session_key)):
    set_value(driver_id, "constraints", constraints)
    return {"driver_id": driver_id, "constraints": constraints}
