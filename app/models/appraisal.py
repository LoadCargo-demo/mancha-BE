"""Appraiser Agent Input/Output 스키마."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.package import PackageCandidate


class DriverCostProfile(BaseModel):
    cost_per_km: int
    value_per_hour: int
    min_fare_per_km: int | None = None  # 손익분기
    daily_min_revenue: int | None = None  # 일 최소 매출


class DeductionItem(BaseModel):
    label: str
    amount: int
    source: str
    source_id: str | None = None
    source_type: str | None = None


class AppraisedPackage(BaseModel):
    package: PackageCandidate
    expected_wait_min: int
    success_probability: float
    empty_cost: int
    wait_cost: int
    adjusted_profit: int
    deductions: list[DeductionItem]
    balanced_score: float | None = None
    recommendable: bool = True
    negotiation_gain: int | None = None


class AppraisalResult(BaseModel):
    ranked_packages: list[AppraisedPackage]
    recommended_package_id: str | None
    recommendation_reason: str
    briefing_text: str
