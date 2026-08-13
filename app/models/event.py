"""Monitor / Rebuilder Agent Input/Output 스키마."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.package import PackageCandidate, ScheduleBlock


class EventType(str, Enum):
    NEW_ORDER = "NEW_ORDER"
    DELAY = "DELAY"
    CANCEL = "CANCEL"
    CONGESTION = "CONGESTION"
    ORDER_COMPLETE = "ORDER_COMPLETE"


class MockEvent(BaseModel):
    event_type: EventType
    order_id: str | None = None
    delay_min: int | None = None
    detail: str | None = None


class RebuildRequest(BaseModel):
    driver_id: str
    current_location: str
    completed_blocks: list[ScheduleBlock]
    remaining_blocks: list[ScheduleBlock]
    event: MockEvent
    backup_order_ids: list[str] = Field(default_factory=list)


class RebuildDiff(BaseModel):
    profit_diff: int
    return_time_diff_min: int
    empty_km_diff: float


class PlanSummary(BaseModel):
    return_time: str
    profit: int
    empty_km: float


class RebuildResult(BaseModel):
    should_notify: bool
    new_package: PackageCandidate | None
    diff: RebuildDiff | None
    tradeoff_text: str | None
    event_summary: str | None = None
    detected_automatically: bool = True
    keep_plan: PlanSummary | None = None
    replace_plan: PlanSummary | None = None
