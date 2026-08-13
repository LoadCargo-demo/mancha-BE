"""Scout Agent"""

from __future__ import annotations

from datetime import datetime

from app.models.order import (
    DriverConstraints,
    LoadingType,
    NormalizedOrder,
    RawOrderInput,
)
from app.models.order import ScoutRunResult
from app.services.llm_client import generate_structured

ORDER_SCHEMA_HINT = """
{
  "pickup": "string",
  "dropoff": "string",
  "pickup_start": "HH:MM",
  "pickup_end": "HH:MM",
  "cargo_type": "string",
  "pallet_count": number,
  "loading_type": "forklift" | "manual",
  "price": number | null
}
"""


async def normalize_order(raw: RawOrderInput, order_id: str) -> NormalizedOrder:
    prompt = (
        "<role>물류 오더를 구조화된 스키마로 정규화하는 어시스턴트입니다.</role>\n\n"
        f"<raw_order>{raw.raw_text}</raw_order>\n\n"
        "<instructions>\n"
        "- loading_type(forklift/manual)은 화물 품목과 수량으로 추론하세요.\n"
        "- 문장에 가격이 없으면 price는 null로 두고, 값을 지어내지 마세요.\n"
        "</instructions>"
    )
    data = await generate_structured(prompt, ORDER_SCHEMA_HINT)
    return NormalizedOrder(
        order_id=order_id,
        pickup=data["pickup"],
        dropoff=data["dropoff"],
        pickup_start=data["pickup_start"],
        pickup_end=data["pickup_end"],
        cargo_type=data["cargo_type"],
        pallet_count=data["pallet_count"],
        loading_type=LoadingType(data["loading_type"]),
        price=data.get("price"),
        shipper_name=raw.shipper_name,
        raw_text=raw.raw_text,
    )


def _matches_region(order: NormalizedOrder, constraints: DriverConstraints) -> bool:
    origin_ok = (
        constraints.preferred_origin_region is None
        or constraints.preferred_origin_region in order.pickup
    )
    dest_ok = (
        constraints.preferred_destination_region is None
        or constraints.preferred_destination_region in order.dropoff
    )
    return origin_ok and dest_ok


def apply_basic_filter(
    orders: list[NormalizedOrder], constraints: DriverConstraints
) -> list[NormalizedOrder]:
    """물리적으로 불가능한 오더만 거른다. 수작업 상하차는 정책상 HARD로 여기서 빼지 않고 Builder가 hard_violations로 annotate한다"""
    if (
        constraints.preferred_origin_region is None
        and constraints.preferred_destination_region is None
    ):
        return list(orders)
    return sorted(orders, key=lambda o: not _matches_region(o, constraints))


def run_scout(
    collected_orders: list[NormalizedOrder], constraints: DriverConstraints
) -> ScoutRunResult:
    passed = apply_basic_filter(collected_orders, constraints)
    return ScoutRunResult(
        collected_count=len(collected_orders),
        passed_count=len(passed),
        normalized_orders=passed,
        completed_at=datetime.now(),
    )
