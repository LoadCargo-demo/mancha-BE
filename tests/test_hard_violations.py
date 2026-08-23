import asyncio

from app.agents import appraiser, builder
from app.models.appraisal import DriverCostProfile
from app.models.order import DriverConstraints, LoadingType, NormalizedOrder
from app.models.package import PackageCandidate, ScheduleBlock

BASE_CONSTRAINTS = DriverConstraints(
    fixed_pickup="depot",
    fixed_pickup_time="08:00",
    fixed_dropoff="depot",
    fixed_dropoff_time="08:00",
    return_location="depot",
    return_deadline="23:59",
    exclude_manual_loading=True,
)

COST_PROFILE = DriverCostProfile(cost_per_km=1840, value_per_hour=41000)


def _order(
    order_id,
    pickup,
    dropoff,
    loading_type=LoadingType.FORKLIFT,
    pallet_count=5,
    price=100000,
):
    return NormalizedOrder(
        order_id=order_id,
        pickup=pickup,
        dropoff=dropoff,
        pickup_start="08:00",
        pickup_end="20:00",
        cargo_type="화물",
        pallet_count=pallet_count,
        loading_type=loading_type,
        price=price,
    )


def test_manual_handling_candidate_is_generated_and_annotated():
    manual_order = _order("M", "P1", "D1", loading_type=LoadingType.MANUAL)
    packages, _, _ = builder.build_packages([manual_order], BASE_CONSTRAINTS)

    assert packages, "수작업 상하차 오더도 후보 자체는 생성돼야 한다."
    pkg = packages[0]
    assert "manual_handling" in pkg.hard_violations
    assert pkg.excluded_reason is not None


def test_manual_handling_candidate_excluded_from_recommendation_but_stays_in_comparison():
    violating_package = PackageCandidate(
        package_id="pkg_violating",
        label="최대수익형",
        blocks=[],
        order_ids=["M"],
        empty_km=0.0,
        nominal_profit=999_000_000,
        return_time="12:00",
        hard_violations=["manual_handling"],
    )
    clean_package = PackageCandidate(
        package_id="pkg_clean",
        label="균형형",
        blocks=[],
        order_ids=["N"],
        empty_km=0.0,
        nominal_profit=100_000,
        return_time="12:00",
    )

    appraisal = asyncio.run(
        appraiser.run_appraiser([violating_package, clean_package], COST_PROFILE, [])
    )

    labels_with_violation = [
        ap for ap in appraisal.ranked_packages if ap.package.hard_violations
    ]
    labels_without_violation = [
        ap for ap in appraisal.ranked_packages if not ap.package.hard_violations
    ]
    assert labels_with_violation, "HARD 위반 후보가 비교 결과에서 사라지면 안 된다."
    assert labels_without_violation, "정상 후보도 비교 결과에 있어야 한다."

    for ap in labels_with_violation:
        assert ap.recommendable is False
    for ap in labels_without_violation:
        assert ap.recommendable is True

    recommended = next(
        ap
        for ap in appraisal.ranked_packages
        if ap.package.package_id == appraisal.recommended_package_id
    )
    assert recommended.recommendable is True
    assert not recommended.package.hard_violations


def test_capacity_overflow_still_pruned_from_search():
    """물리적 제약(적재 초과)은 여전히 branch 자체가 생성되지 않는다."""
    order_a = _order("A", "P1", "D1", pallet_count=15)
    order_b = _order("B", "P2", "D2", pallet_count=10)
    constraints = BASE_CONSTRAINTS.model_copy(update={"vehicle_capacity_pallets": 20})

    order_lookup = {"A": order_a, "B": order_b}
    root = builder._Node(
        actions=[],
        onboard_ids=frozenset(),
        completed_ids=frozenset(),
        current_loc="depot",
        current_time=builder._to_min("08:00"),
        empty_km=0.0,
        profit=0,
    )
    results: list = []
    builder._search(root, [order_a, order_b], order_lookup, constraints, results)

    assert not any(n.onboard_ids == {"A", "B"} for n in results)


def test_pickup_dropoff_precedence_still_enforced():
    order_a = _order("A", "P1", "D1")
    order_lookup = {"A": order_a}
    root = builder._Node(
        actions=[],
        onboard_ids=frozenset(),
        completed_ids=frozenset(),
        current_loc="depot",
        current_time=builder._to_min("08:00"),
        empty_km=0.0,
        profit=0,
    )
    results: list = []
    builder._search(root, [order_a], order_lookup, BASE_CONSTRAINTS, results)

    for node in results:
        picked: set[str] = set()
        for kind, order, _ in node.actions:
            if kind == "DROPOFF":
                assert order.order_id in picked
                picked.discard(order.order_id)
            else:
                picked.add(order.order_id)


def test_wait_time_excludes_fixed_blocks_but_includes_candidate_blocks():
    """고정 일정(성남/부산사상 등)의 대기시간이 후보마다 강제로 붙지 않아야 한다."""
    from app.services.mock_data import MOCK_FIELD_WAIT_DATA

    fixed_location = next(iter(MOCK_FIELD_WAIT_DATA))

    fixed_only_package = PackageCandidate(
        package_id="p1",
        label="테스트",
        blocks=[
            ScheduleBlock(
                order_id=None,
                location=fixed_location,
                arrival_time="10:30",
                action="하차",
                is_fixed=True,
            ),
        ],
        order_ids=[],
        empty_km=0.0,
        nominal_profit=0,
        return_time="10:30",
    )
    candidate_specific_package = PackageCandidate(
        package_id="p2",
        label="테스트2",
        blocks=[
            ScheduleBlock(
                order_id="X",
                location=fixed_location,
                arrival_time="14:00",
                action="하차",
                is_fixed=False,
            ),
        ],
        order_ids=["X"],
        empty_km=0.0,
        nominal_profit=0,
        return_time="14:00",
    )

    fixed_wait, _ = appraiser._estimate_wait_min(fixed_only_package)
    candidate_wait, _ = appraiser._estimate_wait_min(candidate_specific_package)

    assert fixed_wait == 0, "고정(is_fixed=True) 블록은 대기시간 집계에서 빠져야 한다."
    assert candidate_wait == MOCK_FIELD_WAIT_DATA[fixed_location]["avg_wait_min"]


def test_appraiser_recommends_none_when_all_candidates_violate():
    """위반 없는 후보가 하나도 없으면 정책 위반 후보를 억지로 추천하지 않고 None."""
    manual_order = _order("M", "P1", "D1", loading_type=LoadingType.MANUAL)
    packages, _, _ = builder.build_packages([manual_order], BASE_CONSTRAINTS)

    appraisal = asyncio.run(appraiser.run_appraiser(packages, COST_PROFILE, []))
    assert appraisal.recommended_package_id is None
    assert not any(p.is_recommended for p in packages)
