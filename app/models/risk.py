"""Risk Predictor Agent Input/Output 스키마."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class TimePatternRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


TIME_PATTERN_RISK_VALUES: dict[TimePatternRisk, float] = {
    TimePatternRisk.LOW: 0.2,
    TimePatternRisk.MEDIUM: 0.5,
    TimePatternRisk.HIGH: 0.8,
}


class TradeHistory(BaseModel):
    shipper_name: str
    total_trades: int
    cancel_count: int
    delay_count: int
    time_risk: float = 0.0


class OrderRisk(BaseModel):
    order_id: str
    shipper_name: str
    cancel_probability: float
    delay_probability: float
    success_probability: float
    is_auto_excluded: bool
    exclude_reason: str | None = None
    backup_order_id: str | None = None
    explanation: str | None = None


class RiskRunResult(BaseModel):
    order_risks: list[OrderRisk]
    excluded_count: int
    backup_pairs: dict[str, str]
