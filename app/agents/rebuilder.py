"""Rebuilder Agent"""

from __future__ import annotations

from app.core.config import settings
from app.core.time_utils import to_hhmm as _to_hhmm, to_min as _to_min
from app.models.event import PlanSummary, RebuildDiff, RebuildRequest, RebuildResult
from app.models.order import DriverConstraints, NormalizedOrder
from app.models.package import PackageCandidate, ScheduleBlock
from app.services.llm_client import generate_text
from app.services.mock_data import MOCK_NORMALIZED_ORDERS


def _to_plan_summary(package: PackageCandidate) -> PlanSummary:
    return PlanSummary(
        return_time=package.return_time,
        profit=package.nominal_profit,
        empty_km=package.empty_km,
    )


def _apply_event(
    remaining_orders: list[NormalizedOrder],
    request: RebuildRequest,
    old_package: PackageCandidate,
) -> list[NormalizedOrder]:
    event = request.event
    orders = [o.model_copy(deep=True) for o in remaining_orders]
    backup_pairs = request.backup_pairs

    def _swap_in_backups(without_order_id: str, candidate_backup_ids: set[str]) -> None:
        nonlocal orders
        orders = [o for o in orders if o.order_id != without_order_id]
        backup_orders = [
            o.model_copy(deep=True)
            for o in MOCK_NORMALIZED_ORDERS
            if o.order_id in candidate_backup_ids
        ]
        orders.extend(
            [o for o in backup_orders if o.order_id not in [x.order_id for x in orders]]
        )

    if event.event_type.value == "CANCEL" and event.order_id:
        _swap_in_backups(event.order_id, set(backup_pairs.values()))

    elif event.event_type.value == "DELAY" and event.order_id and event.delay_min:
        backup_id = backup_pairs.get(event.order_id)
        if backup_id:
            _swap_in_backups(event.order_id, {backup_id})
        else:
            original_pickup_block = next(
                (
                    b
                    for b in old_package.blocks
                    if b.order_id == event.order_id and b.action == "상차"
                ),
                None,
            )
            for o in orders:
                if o.order_id == event.order_id:
                    window_width = _to_min(o.pickup_end) - _to_min(o.pickup_start)
                    baseline_min = (
                        _to_min(original_pickup_block.arrival_time)
                        if original_pickup_block is not None
                        else _to_min(o.pickup_start)
                    )
                    delayed_start = baseline_min + event.delay_min
                    delayed_end = delayed_start + window_width
                    o.pickup_start = _to_hhmm(delayed_start)
                    o.pickup_end = _to_hhmm(delayed_end)

    return orders


async def rebuild(
    request: RebuildRequest,
    constraints: DriverConstraints,
    old_package: PackageCandidate,
) -> RebuildResult:
    from app.agents.builder import _estimate_travel_min, build_packages

    order_lookup = {o.order_id: o for o in MOCK_NORMALIZED_ORDERS}

    completed_order_ids = {b.order_id for b in request.completed_blocks if b.order_id}
    remaining_order_ids = {b.order_id for b in request.remaining_blocks if b.order_id}
    # 완료/잔여 양쪽에 다 있는 오더 = 상차만 끝나고 하차 전인 채로 실려있는 것.
    # 재탐색에서 다시 "픽업"시키면 수익이 두 번 잡히므로 후보에서 빼고 하차만 붙인다.
    still_onboard_ids = completed_order_ids & remaining_order_ids
    untouched_order_ids = remaining_order_ids - still_onboard_ids

    untouched_orders = [
        o for o in MOCK_NORMALIZED_ORDERS if o.order_id in untouched_order_ids
    ]
    updated_candidates = _apply_event(untouched_orders, request, old_package)

    now_time = (
        request.completed_blocks[-1].arrival_time
        if request.completed_blocks
        else constraints.fixed_dropoff_time
    )
    temp_constraints = constraints.model_copy(
        update={
            "fixed_pickup": request.current_location,
            "fixed_pickup_time": now_time,
            "fixed_dropoff": request.current_location,
            "fixed_dropoff_time": now_time,
        }
    )

    if updated_candidates:
        new_packages, _, _ = build_packages(updated_candidates, temp_constraints)
        if not new_packages:
            return RebuildResult(
                should_notify=False, new_package=None, diff=None, tradeoff_text=None
            )
        rebuilt = next(
            (p for p in new_packages if p.label == "균형형"), new_packages[0]
        )
        # 앞 2개는 temp_constraints가 만든 합성 시작 블록, 마지막은 귀가 블록이라 제외.
        body_blocks = list(rebuilt.blocks[2:-1])
        body_profit = rebuilt.nominal_profit
        body_empty_km = rebuilt.empty_km
        body_order_ids = list(rebuilt.order_ids)
        cursor_loc = (
            body_blocks[-1].location if body_blocks else request.current_location
        )
        cursor_time = body_blocks[-1].arrival_time if body_blocks else now_time
    else:
        body_blocks = []
        body_profit = 0
        body_empty_km = 0.0
        body_order_ids = []
        cursor_loc = request.current_location
        cursor_time = now_time

    for order_id in sorted(still_onboard_ids):
        order = order_lookup[order_id]
        travel_min = _estimate_travel_min(cursor_loc, order.dropoff)
        arrival = _to_min(cursor_time) + travel_min
        body_blocks.append(
            ScheduleBlock(
                order_id=order.order_id,
                location=order.dropoff,
                arrival_time=_to_hhmm(arrival),
                action="하차",
                is_fixed=False,
            )
        )
        cursor_loc = order.dropoff
        cursor_time = _to_hhmm(arrival)

    travel_home = _estimate_travel_min(cursor_loc, constraints.return_location)
    return_time_min = _to_min(cursor_time) + travel_home
    return_block = ScheduleBlock(
        order_id=None,
        location=constraints.return_location,
        arrival_time=_to_hhmm(return_time_min),
        action="귀가",
        is_fixed=True,
    )

    completed_profit = sum(order_lookup[oid].price or 0 for oid in completed_order_ids)

    new_package = PackageCandidate(
        package_id="pkg_rebuilt",
        label="재조립",
        blocks=request.completed_blocks + body_blocks + [return_block],
        order_ids=[
            b.order_id
            for b in request.completed_blocks
            if b.order_id and b.action == "상차"
        ]
        + body_order_ids,
        empty_km=body_empty_km,
        nominal_profit=completed_profit + body_profit,
        return_time=_to_hhmm(return_time_min),
        is_recommended=True,
    )

    profit_diff = new_package.nominal_profit - old_package.nominal_profit
    old_return_min = _to_min(old_package.return_time)
    new_return_min = _to_min(new_package.return_time)
    return_diff_min = old_return_min - new_return_min
    empty_km_diff = old_package.empty_km - new_package.empty_km

    diff = RebuildDiff(
        profit_diff=profit_diff,
        return_time_diff_min=return_diff_min,
        empty_km_diff=empty_km_diff,
    )

    should_notify = (
        abs(profit_diff) >= settings.rebuild_profit_threshold
        or abs(return_diff_min) >= settings.rebuild_return_threshold_min
    )

    tradeoff_text = None
    if should_notify:
        prompt = (
            "<role>주행 중 발생한 이벤트에 대한 재조립 제안을 안내하는 물류 어시스턴트입니다.</role>\n\n"
            "<context>\n"
            f"상황: {request.event.detail or request.event.event_type.value}\n"
            f"대안 적용 시 복귀시각 차이: {return_diff_min}분\n"
            f"대안 적용 시 수익 차이: {profit_diff:,}원\n"
            "</context>\n\n"
            "<task>무엇을 잃고 무엇을 지키는지 한 문장으로 요약하고, "
            "'바꿀까요?'로 끝나는 닫힌 질문형 제안 문장을 작성하세요.</task>\n\n"
            "<constraints>context에 없는 수치를 지어내지 마세요.</constraints>\n\n"
            "<final_check>문장이 '바꿀까요?'로 끝나는지, 수치가 context와 일치하는지 "
            "확인한 뒤 출력하세요.</final_check>"
        )
        gain_or_loss = "줄지만" if profit_diff < 0 else "늘고"
        time_word = "빨라집니다" if return_diff_min > 0 else "늦어집니다"
        tradeoff_fallback = (
            f"대안으로 바꾸면 수익이 {abs(profit_diff):,}원 {gain_or_loss}, "
            f"복귀는 {abs(return_diff_min)}분 {time_word}. 바꿀까요?"
        )
        tradeoff_text = await generate_text(
            prompt, closed_question=True, fallback=tradeoff_fallback
        )

    event_summary = (
        request.event.detail or f"{request.event.event_type.value} 이벤트 감지"
    )

    return RebuildResult(
        should_notify=should_notify,
        new_package=new_package,
        diff=diff,
        tradeoff_text=tradeoff_text,
        event_summary=event_summary,
        detected_automatically=True,
        keep_plan=_to_plan_summary(old_package),
        replace_plan=_to_plan_summary(new_package),
    )
