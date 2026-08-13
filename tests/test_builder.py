from app.agents import builder
from app.models.order import DriverConstraints, LoadingType, NormalizedOrder

BASE_CONSTRAINTS = DriverConstraints(
    fixed_pickup="depot",
    fixed_pickup_time="08:00",
    fixed_dropoff="depot",
    fixed_dropoff_time="08:00",
    return_location="depot",
    return_deadline="23:59",
    exclude_manual_loading=True,
)


def _order(
    order_id, pickup, dropoff, pallet_count=5, price=100000, start="08:00", end="20:00"
):
    return NormalizedOrder(
        order_id=order_id,
        pickup=pickup,
        dropoff=dropoff,
        pickup_start=start,
        pickup_end=end,
        cargo_type="화물",
        pallet_count=pallet_count,
        loading_type=LoadingType.FORKLIFT,
        price=price,
    )


def _run_search(orders, constraints=BASE_CONSTRAINTS):
    order_lookup = {o.order_id: o for o in orders}
    root = builder._Node(
        actions=[],
        onboard_ids=frozenset(),
        completed_ids=frozenset(),
        current_loc=constraints.fixed_dropoff,
        current_time=builder._to_min(constraints.fixed_dropoff_time),
        empty_km=0.0,
        profit=0,
    )
    results: list[builder._Node] = []
    builder._search(root, orders, order_lookup, constraints, results)
    return results


def test_single_order_pickup_then_dropoff_still_works():
    order_a = _order("A", "P1", "D1")
    results = _run_search([order_a])

    closed_with_a = [n for n in results if n.completed_ids == {"A"}]
    assert closed_with_a
    kinds = [kind for kind, _, _ in closed_with_a[0].actions]
    assert kinds == ["PICKUP", "DROPOFF"]


def test_multi_load_route_is_reachable():
    """순서 후보가 실제로 나와야 한다."""
    order_a = _order("A", "P1", "D1")
    order_b = _order("B", "P2", "D2")
    results = _run_search([order_a, order_b])

    multi_load = [
        n
        for n in results
        if n.completed_ids == {"A", "B"}
        and [kind for kind, _, _ in n.actions]
        == ["PICKUP", "PICKUP", "DROPOFF", "DROPOFF"]
    ]
    assert (
        multi_load
    ), "동시 적재 경로(PICKUP A → PICKUP B → DROPOFF B → DROPOFF A)가 탐색되지 않았습니다."

    assert any(
        n.actions[1][1].order_id == "B" and n.actions[2][1].order_id == "B"
        for n in multi_load
    )


def test_cannot_dropoff_order_not_picked_up_yet():
    """구조상 onboard가 아닌 오더는 DROPOFF 후보 자체가 생성되지 않는다."""
    order_a = _order("A", "P1", "D1")
    order_b = _order("B", "P2", "D2")
    results = _run_search([order_a, order_b])

    for node in results:
        picked_so_far: set[str] = set()
        for kind, order, _ in node.actions:
            if kind == "DROPOFF":
                assert (
                    order.order_id in picked_so_far
                ), "픽업 전에 드롭오프가 발생했습니다."
                picked_so_far.discard(order.order_id)
            else:
                picked_so_far.add(order.order_id)


def test_no_duplicate_pickup_or_dropoff_for_same_order():
    order_a = _order("A", "P1", "D1")
    order_b = _order("B", "P2", "D2")
    results = _run_search([order_a, order_b])

    for node in results:
        pickups = [o.order_id for kind, o, _ in node.actions if kind == "PICKUP"]
        dropoffs = [o.order_id for kind, o, _ in node.actions if kind == "DROPOFF"]
        assert len(pickups) == len(set(pickups))
        assert len(dropoffs) == len(set(dropoffs))


def test_vehicle_capacity_blocks_simultaneous_overload():
    """A(15)+B(10) 동시 적재는 capacity(20) 초과라 동시 onboard 상태가 나오면 안 된다."""
    order_a = _order("A", "P1", "D1", pallet_count=15)
    order_b = _order("B", "P2", "D2", pallet_count=10)
    results = _run_search([order_a, order_b])

    assert not any(n.onboard_ids == {"A", "B"} for n in results)


def test_capacity_frees_up_after_dropoff():
    """A를 내리고 나면 다시 용량이 확보돼 B를 실을 수 있어야 한다."""
    order_a = _order("A", "P1", "D1", pallet_count=15)
    order_b = _order("B", "P2", "D2", pallet_count=10)
    results = _run_search([order_a, order_b])

    assert any(n.completed_ids == {"A", "B"} for n in results)


def test_pickup_time_window_violation_excludes_order():
    order_a = _order("A", "P1", "D1")
    unreachable = _order("B", "P2", "D2", start="00:00", end="00:05")
    results = _run_search([order_a, unreachable])

    assert not any(
        any(order.order_id == "B" for _, order, _ in n.actions) for n in results
    )


def test_figma_shape_pickup_pickup_dropoff_dropoff():
    yangsan = _order("order_yangsan", "양산 대한부품", "군포", pallet_count=6)
    gimhae = _order("order_gimhae", "김해 A물류", "대전", pallet_count=8)
    results = _run_search([yangsan, gimhae])

    shaped = [
        n
        for n in results
        if [(kind, o.order_id) for kind, o, _ in n.actions]
        == [
            ("PICKUP", "order_yangsan"),
            ("PICKUP", "order_gimhae"),
            ("DROPOFF", "order_gimhae"),
            ("DROPOFF", "order_yangsan"),
        ]
    ]
    assert (
        shaped
    ), "Figma 형태(양산 적재 → 김해 적재 → 대전 하차 → 군포 하차)가 탐색되지 않았습니다."


def test_build_packages_still_returns_valid_candidates_for_existing_mock_orders():
    """멀티 적재 확장 후에도 기존 단일 오더 흐름(build_packages 전체)이 정상 동작해야 한다."""
    from app.services.mock_data import DRIVER_CONSTRAINTS, MOCK_NORMALIZED_ORDERS

    packages, generated_count, passed_count = builder.build_packages(
        MOCK_NORMALIZED_ORDERS, DRIVER_CONSTRAINTS
    )

    assert packages
    assert generated_count >= passed_count > 0
    for pkg in packages:
        assert pkg.nominal_profit > 0
        block_order_ids = {b.order_id for b in pkg.blocks if b.order_id}
        assert block_order_ids <= set(pkg.order_ids)
