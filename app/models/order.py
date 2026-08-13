"""Scout Agent Input/Output 스키마."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LoadingType(str, Enum):
    FORKLIFT = "forklift"  # 지게차 상하차
    MANUAL = "manual"  # 수작업 상하차


class ComplianceLevel(str, Enum):
    STRICT = "strict"
    PREFER = "prefer"
    FLEXIBLE = "flexible"


class RawOrderInput(BaseModel):
    raw_text: str = Field(
        ..., description='예: "내일 오전 양산에서 군포로 파렛트 6개 보낼게요"'
    )
    shipper_name: str | None = None


class NormalizedOrder(BaseModel):
    order_id: str
    pickup: str
    dropoff: str
    pickup_start: str  # "HH:MM"
    pickup_end: str
    cargo_type: str
    pallet_count: int
    loading_type: LoadingType
    price: int | None = None  # None이면 AI 시세 추정 필요
    shipper_name: str | None = None
    raw_text: str | None = None
    offered_price: int | None = None
    negotiated_price: int | None = None


class DriverConstraints(BaseModel):
    fixed_pickup: str
    fixed_pickup_time: str
    fixed_dropoff: str
    fixed_dropoff_time: str
    return_location: str
    return_deadline: str  # "HH:MM", HARD 제약
    exclude_manual_loading: bool = True  # HARD
    avoid_night_driving: bool = False  # SOFT
    max_continuous_drive_min: int = 240  # HARD
    max_daily_drive_min: int = 600  # HARD
    vehicle_type: str = "5톤 카고"
    vehicle_capacity_pallets: int = 20  # HARD, 동시 적재 가능 파렛트 수
    compliance_level: ComplianceLevel = ComplianceLevel.PREFER
    preferred_origin_region: str | None = None  # 주 활동 권역 (출발)
    preferred_destination_region: str | None = None  # 주 활동 권역 (도착)


class ScoutRunResult(BaseModel):
    collected_count: int
    passed_count: int
    normalized_orders: list[NormalizedOrder]
    completed_at: datetime
