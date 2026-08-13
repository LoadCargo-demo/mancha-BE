"""Builder Agent"""

from __future__ import annotations

import hashlib

from app.core.time_utils import to_hhmm as _to_hhmm, to_min as _to_min
from app.models.order import DriverConstraints, NormalizedOrder
from app.models.package import PackageCandidate, ScheduleBlock

BEAM_WIDTH = 20
BUFFER_MIN = 10


def _estimate_travel_min(from_loc: str, to_loc: str) -> int:
    """결정론적 mock 이동시간."""
    if from_loc == to_loc:
        return 5
    key = f"{from_loc}:{to_loc}".encode()
    seed = int(hashlib.sha256(key).hexdigest()[:8], 16) % 60
    return 20 + seed


def _estimate_distance_km(from_loc: str, to_loc: str) -> float:
    return round(_estimate_travel_min(from_loc, to_loc) * 0.8, 1)


class _Node:
    __slots__ = (
        "actions",
        "onboard_ids",
        "completed_ids",
        "current_loc",
        "current_time",
        "empty_km",
        "profit",
        "hard_violations",
        "total_drive_min",
        "continuous_drive_min",
    )

    def __init__(
        self,
        actions,
        onboard_ids,
        completed_ids,
        current_loc,
        current_time,
        empty_km,
        profit,
        hard_violations=frozenset(),
        total_drive_min=0,
        continuous_drive_min=0,
    ):
        self.actions = actions
        self.onboard_ids = onboard_ids
        self.completed_ids = completed_ids
        self.current_loc = current_loc
        self.current_time = current_time
        self.empty_km = empty_km
        self.profit = profit
        self.hard_violations = hard_violations
        self.total_drive_min = total_drive_min
        self.continuous_drive_min = continuous_drive_min


def _connect_feasible(
    current_time: int, to_pickup_min: int, order: NormalizedOrder
) -> bool:
    arrival = current_time + to_pickup_min + BUFFER_MIN
    return arrival <= _to_min(order.pickup_end)


def _policy_violation_code(
    order: NormalizedOrder, constraints: DriverConstraints
) -> str | None:
    if constraints.exclude_manual_loading and order.loading_type.value == "manual":
        return "manual_handling"
    return None


def _current_load(
    onboard_ids: frozenset[str], order_lookup: dict[str, NormalizedOrder]
) -> int:
    return sum(order_lookup[oid].pallet_count for oid in onboard_ids)


def _drive_time_after(
    total_drive_min: int,
    continuous_drive_min: int,
    delta_min: int,
    constraints: DriverConstraints,
) -> tuple[int, int] | None:
    new_total = total_drive_min + delta_min
    new_continuous = continuous_drive_min + delta_min
    if new_total > constraints.max_daily_drive_min:
        return None
    if new_continuous > constraints.max_continuous_drive_min:
        return None
    return new_total, new_continuous


def _search(
    node: _Node,
    remaining: list[NormalizedOrder],
    order_lookup: dict[str, NormalizedOrder],
    constraints: DriverConstraints,
    results: list[_Node],
):
    if not node.onboard_ids:
        results.append(node)

    branches: list[_Node] = []

    load_now = _current_load(node.onboard_ids, order_lookup)
    for order in remaining:
        if load_now + order.pallet_count > constraints.vehicle_capacity_pallets:
            continue
        to_pickup_min = _estimate_travel_min(node.current_loc, order.pickup)
        if not _connect_feasible(node.current_time, to_pickup_min, order):
            continue

        # PICKUP은 휴식에 포함 x
        drive_state = _drive_time_after(
            node.total_drive_min, node.continuous_drive_min, to_pickup_min, constraints
        )
        if drive_state is None:
            continue
        new_total_drive_min, new_continuous_drive_min = drive_state

        pickup_time = max(
            node.current_time + to_pickup_min, _to_min(order.pickup_start)
        )
        empty_km_add = _estimate_distance_km(node.current_loc, order.pickup)
        violation = _policy_violation_code(order, constraints)

        if violation and constraints.compliance_level == "strict":
            continue

        branches.append(
            _Node(
                actions=node.actions + [("PICKUP", order, pickup_time)],
                onboard_ids=node.onboard_ids | {order.order_id},
                completed_ids=node.completed_ids,
                current_loc=order.pickup,
                current_time=pickup_time,
                empty_km=node.empty_km + empty_km_add,
                profit=node.profit + (order.price or 0),
                hard_violations=node.hard_violations
                | ({violation} if violation else set()),
                total_drive_min=new_total_drive_min,
                continuous_drive_min=new_continuous_drive_min,
            )
        )

    for order_id in sorted(node.onboard_ids):
        order = order_lookup[order_id]
        travel_min = _estimate_travel_min(node.current_loc, order.dropoff)
        dropoff_time = node.current_time + travel_min

        drive_state = _drive_time_after(
            node.total_drive_min, node.continuous_drive_min, travel_min, constraints
        )
        if drive_state is None:
            continue
        new_total_drive_min, _ = drive_state

        branches.append(
            _Node(
                actions=node.actions + [("DROPOFF", order, dropoff_time)],
                onboard_ids=node.onboard_ids - {order_id},
                completed_ids=node.completed_ids | {order_id},
                current_loc=order.dropoff,
                current_time=dropoff_time,
                empty_km=node.empty_km,
                profit=node.profit,
                hard_violations=node.hard_violations,
                total_drive_min=new_total_drive_min,
                # 데모 규칙: 하차(DROPOFF)를 최소 휴식 지점으로 간주해 연속 운행시간을 리셋한다.
                continuous_drive_min=0,
            )
        )

    if not branches:
        return

    branches.sort(key=lambda n: n.profit, reverse=True)
    branches = branches[:BEAM_WIDTH]

    for next_node in branches:
        last_kind, last_order, _ = next_node.actions[-1]
        if last_kind == "PICKUP":
            rest = [o for o in remaining if o.order_id != last_order.order_id]
        else:
            rest = remaining
        _search(next_node, rest, order_lookup, constraints, results)


def _check_return_hard(node: _Node, constraints: DriverConstraints) -> bool:
    travel_to_return = _estimate_travel_min(
        node.current_loc, constraints.return_location
    )
    arrival = node.current_time + travel_to_return
    deadline = _to_min(constraints.return_deadline)
    return arrival <= deadline


def _node_to_package(
    node: _Node, constraints: DriverConstraints, label: str, package_id: str
) -> PackageCandidate:
    blocks = [
        ScheduleBlock(
            order_id=None,
            location=constraints.fixed_pickup,
            arrival_time=constraints.fixed_pickup_time,
            action="상차",
            is_fixed=True,
        ),
        ScheduleBlock(
            order_id=None,
            location=constraints.fixed_dropoff,
            arrival_time=constraints.fixed_dropoff_time,
            action="하차",
            is_fixed=True,
        ),
    ]

    for kind, order, minutes in node.actions:
        blocks.append(
            ScheduleBlock(
                order_id=order.order_id,
                location=order.pickup if kind == "PICKUP" else order.dropoff,
                arrival_time=_to_hhmm(minutes),
                action="상차" if kind == "PICKUP" else "하차",
                is_fixed=False,
            )
        )

    travel_to_return = _estimate_travel_min(
        node.current_loc, constraints.return_location
    )
    return_time = node.current_time + travel_to_return
    blocks.append(
        ScheduleBlock(
            order_id=None,
            location=constraints.return_location,
            arrival_time=_to_hhmm(return_time),
            action="귀가",
            is_fixed=True,
        )
    )

    order_ids: list[str] = []
    for kind, order, _ in node.actions:
        if kind == "PICKUP" and order.order_id not in order_ids:
            order_ids.append(order.order_id)

    violations = sorted(node.hard_violations)
    excluded_reason = (
        "정책상 HARD 위반(" + ", ".join(violations) + ") 포함 — 추천 대상에서 제외"
        if violations
        else None
    )

    return PackageCandidate(
        package_id=package_id,
        label=label,
        blocks=blocks,
        order_ids=order_ids,
        empty_km=round(node.empty_km, 1),
        nominal_profit=node.profit,
        return_time=_to_hhmm(return_time),
        hard_violations=violations,
        excluded_reason=excluded_reason,
    )


def build_packages(
    candidate_orders: list[NormalizedOrder], constraints: DriverConstraints
) -> tuple[list[PackageCandidate], int, int]:
    """3안(최대수익/균형/조기복귀)을 선별한다. Risk 반영은 pipeline.py에서 처리."""
    sorted_orders = sorted(candidate_orders, key=lambda o: _to_min(o.pickup_start))
    order_lookup = {o.order_id: o for o in candidate_orders}

    root = _Node(
        actions=[],
        onboard_ids=frozenset(),
        completed_ids=frozenset(),
        current_loc=constraints.fixed_dropoff,
        current_time=_to_min(constraints.fixed_dropoff_time),
        empty_km=0.0,
        profit=0,
    )
    all_nodes: list[_Node] = []
    _search(root, sorted_orders, order_lookup, constraints, all_nodes)

    generated_count = len(all_nodes)

    valid_nodes = [
        n for n in all_nodes if n.completed_ids and _check_return_hard(n, constraints)
    ]
    passed_count = len(valid_nodes)

    if not valid_nodes:
        return [], generated_count, 0

    max_profit_node = max(valid_nodes, key=lambda n: n.profit)
    non_violating_nodes = [n for n in valid_nodes if not n.hard_violations]
    selection_pool = non_violating_nodes or valid_nodes

    earliest_return_node = min(
        selection_pool,
        key=lambda n: n.current_time
        + _estimate_travel_min(n.current_loc, constraints.return_location),
    )

    def _balance_key(n: _Node) -> float:
        return n.profit - n.empty_km * 1840  # cost_per_km 근사치, Appraiser가 정밀 계산

    balanced_node = max(selection_pool, key=_balance_key)

    packages: list[PackageCandidate] = []
    seen_ids = set()
    for label, node in [
        ("균형형", balanced_node),
        ("최대수익형", max_profit_node),
        ("조기복귀형", earliest_return_node),
    ]:
        key = tuple(sorted(node.completed_ids))
        if key in seen_ids:
            continue
        seen_ids.add(key)
        pkg = _node_to_package(node, constraints, label, package_id=f"pkg_{label}")
        packages.append(pkg)

    return packages, generated_count, passed_count
