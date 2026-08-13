import asyncio

from app.agents import builder
from app.agents.rebuilder import _apply_event, rebuild
from app.models.event import EventType, MockEvent, RebuildRequest
from app.services.mock_data import DRIVER_CONSTRAINTS, MOCK_NORMALIZED_ORDERS


def _gimhae_order():
    return [o for o in MOCK_NORMALIZED_ORDERS if o.order_id == "order_gimhae"]


def _build_gimhae_package():
    packages, _, _ = builder.build_packages(_gimhae_order(), DRIVER_CONSTRAINTS)
    return packages[0]


def test_apply_event_does_not_mutate_global_mock_data():
    before = _gimhae_order()[0].pickup_start
    event = MockEvent(event_type=EventType.DELAY, order_id="order_gimhae", delay_min=40)
    request = RebuildRequest(
        driver_id="d",
        current_location="x",
        completed_blocks=[],
        remaining_blocks=[],
        event=event,
    )

    updated = _apply_event(_gimhae_order(), request)

    assert updated[0].pickup_start != before
    assert _gimhae_order()[0].pickup_start == before


def test_rebuild_preserves_completed_blocks_and_profit():
    package = _build_gimhae_package()
    completed = [b for b in package.blocks if b.arrival_time <= "10:30"]
    remaining = [b for b in package.blocks if b.arrival_time > "10:30"]

    event = MockEvent(event_type=EventType.DELAY, order_id="order_gimhae", delay_min=40)
    request = RebuildRequest(
        driver_id="d",
        current_location=completed[-1].location,
        completed_blocks=completed,
        remaining_blocks=remaining,
        event=event,
    )

    result = asyncio.run(rebuild(request, DRIVER_CONSTRAINTS, package))

    assert result.new_package is not None
    completed_locations = {b.location for b in completed}
    new_locations = {b.location for b in result.new_package.blocks}
    assert completed_locations.issubset(new_locations)
    # 지연만 발생했고 오더는 그대로라 명목수익은 원래 패키지와 같아야 한다 (0으로 초기화 버그 확인용).
    assert result.new_package.nominal_profit == package.nominal_profit
    assert result.new_package.nominal_profit > 0


def test_rebuild_uses_settings_threshold_for_notification():
    package = _build_gimhae_package()
    completed = [b for b in package.blocks if b.arrival_time <= "10:30"]
    remaining = [b for b in package.blocks if b.arrival_time > "10:30"]

    # 40분 지연이면 settings.rebuild_return_threshold_min(기본 30분) 초과라 알림이 떠야 한다.
    event = MockEvent(event_type=EventType.DELAY, order_id="order_gimhae", delay_min=40)
    request = RebuildRequest(
        driver_id="d",
        current_location=completed[-1].location,
        completed_blocks=completed,
        remaining_blocks=remaining,
        event=event,
    )

    result = asyncio.run(rebuild(request, DRIVER_CONSTRAINTS, package))

    assert result.should_notify is True
    assert abs(result.diff.return_time_diff_min) >= 30


def test_rebuild_starts_from_last_completed_time_not_midnight():
    package = _build_gimhae_package()
    completed = [b for b in package.blocks if b.arrival_time <= "10:30"]
    remaining = [b for b in package.blocks if b.arrival_time > "10:30"]

    event = MockEvent(event_type=EventType.DELAY, order_id="order_gimhae", delay_min=40)
    request = RebuildRequest(
        driver_id="d",
        current_location=completed[-1].location,
        completed_blocks=completed,
        remaining_blocks=remaining,
        event=event,
    )

    result = asyncio.run(rebuild(request, DRIVER_CONSTRAINTS, package))

    # 재조립된 상차 시각은 이벤트 지연(40분)이 반영된 시각이어야 한다.
    rebuilt_pickup = next(
        b
        for b in result.new_package.blocks
        if b.location == "김해 A물류" and b.action == "상차"
    )
    assert rebuilt_pickup.arrival_time == "12:40"
