"""Builder Agent Input/Output 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.order import NormalizedOrder


class ScheduleBlock(BaseModel):
    order_id: str | None
    location: str
    arrival_time: str  # "HH:MM"
    action: str  # "상차" | "하차"
    is_fixed: bool = False  # 차주 고정 편도 구간 여부


class PackageCandidate(BaseModel):
    package_id: str
    label: str  # "최대수익형" | "균형형" | "조기복귀형"
    blocks: list[ScheduleBlock]
    order_ids: list[str]
    empty_km: float  # 공차거리
    nominal_profit: int  # 명목 순수익
    return_time: str  # 복귀 시각 "HH:MM"
    is_recommended: bool = False
    excluded_reason: str | None = None  # HARD 위반 시 사유
    hard_violations: list[str] = Field(default_factory=list)


class BuilderRunResult(BaseModel):
    generated_combination_count: int
    passed_constraint_count: int
    final_candidates: list[PackageCandidate]


class BuildRequest(BaseModel):
    driver_id: str
    candidate_orders: list[NormalizedOrder]
