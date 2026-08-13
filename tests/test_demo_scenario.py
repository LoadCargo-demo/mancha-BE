import asyncio

from app.agents import appraiser, builder, risk_predictor
from app.services.mock_data import (
    DRIVER_CONSTRAINTS,
    DRIVER_COST_PROFILE,
    MOCK_NORMALIZED_ORDERS,
    MOCK_TRADE_HISTORY,
)


def _build():
    return builder.build_packages(MOCK_NORMALIZED_ORDERS, DRIVER_CONSTRAINTS)


def _by_label(packages, label):
    return next(p for p in packages if p.label == label)


def test_balanced_package_active_orders_are_exactly_yangsan_and_gimhae():
    packages, _, _ = _build()
    balanced = _by_label(packages, "균형형")
    assert set(balanced.order_ids) == {"order_yangsan", "order_gimhae"}
    assert "order_okcheon" not in balanced.order_ids


def test_balanced_package_action_sequence_matches_figma_shape():
    packages, _, _ = _build()
    balanced = _by_label(packages, "균형형")
    pickups_dropoffs = [
        (b.action, b.order_id) for b in balanced.blocks if not b.is_fixed
    ]
    assert pickups_dropoffs == [
        ("상차", "order_yangsan"),
        ("상차", "order_gimhae"),
        ("하차", "order_gimhae"),
        ("하차", "order_yangsan"),
    ]


def test_max_profit_package_has_manual_violation_and_is_not_recommendable():
    packages, _, _ = _build()
    max_profit = _by_label(packages, "최대수익형")
    assert "manual_handling" in max_profit.hard_violations
    assert max_profit.excluded_reason is not None


def test_balanced_and_early_return_packages_have_no_violations():
    packages, _, _ = _build()
    balanced = _by_label(packages, "균형형")
    early_return = _by_label(packages, "조기복귀형")
    assert balanced.hard_violations == []
    assert early_return.hard_violations == []


def test_early_return_package_returns_earlier_than_balanced():
    packages, _, _ = _build()
    balanced = _by_label(packages, "균형형")
    early_return = _by_label(packages, "조기복귀형")
    assert early_return.return_time < balanced.return_time


def test_three_packages_have_distinct_action_sequences():
    packages, _, _ = _build()
    sequences = {
        p.label: tuple((b.action, b.order_id) for b in p.blocks if not b.is_fixed)
        for p in packages
    }
    assert len(set(sequences.values())) == len(packages)


def test_yangsan_gimhae_okcheon_combo_is_not_selected_as_any_final_candidate():
    """정상 상황에서 3건(양산+김해+옥천) 동시 조합이 최종 3안 중 하나로 선택되면 안 된다."""
    packages, _, _ = _build()
    triple = {"order_yangsan", "order_gimhae", "order_okcheon"}
    assert not any(set(p.order_ids) == triple for p in packages)


def test_yangsan_okcheon_is_feasible_when_gimhae_is_unavailable():
    """김해가 빠진(지연/취소) 상황을 가정하면 양산+옥천 조합은 후보로 생성 가능해야 한다."""
    orders_without_gimhae = [
        o for o in MOCK_NORMALIZED_ORDERS if o.order_id != "order_gimhae"
    ]
    order_lookup = {o.order_id: o for o in orders_without_gimhae}
    root = builder._Node(
        actions=[], onboard_ids=frozenset(), completed_ids=frozenset(),
        current_loc=DRIVER_CONSTRAINTS.fixed_dropoff,
        current_time=builder._to_min(DRIVER_CONSTRAINTS.fixed_dropoff_time),
        empty_km=0.0, profit=0,
    )
    results: list = []
    builder._search(
        root,
        sorted(orders_without_gimhae, key=lambda o: builder._to_min(o.pickup_start)),
        order_lookup,
        DRIVER_CONSTRAINTS,
        results,
    )
    feasible = [
        n for n in results
        if n.completed_ids == {"order_yangsan", "order_okcheon"}
        and builder._check_return_hard(n, DRIVER_CONSTRAINTS)
    ]
    assert feasible, "김해가 빠진 상황에서 양산+옥천 조합이 feasible해야 한다."


def test_backup_pair_is_gimhae_to_okcheon():
    result = asyncio.run(risk_predictor.run_risk_predictor(MOCK_NORMALIZED_ORDERS, MOCK_TRADE_HISTORY))
    assert result.backup_pairs == {"order_gimhae": "order_okcheon"}


def test_demo_pipeline_is_deterministic_across_repeated_calls():
    def run_once():
        packages, _, _ = _build()
        risk_result = asyncio.run(
            risk_predictor.run_risk_predictor(MOCK_NORMALIZED_ORDERS, MOCK_TRADE_HISTORY)
        )
        excluded = {r.order_id for r in risk_result.order_risks if r.is_auto_excluded}
        valid = [p for p in packages if not (excluded & set(p.order_ids))]
        appraisal = asyncio.run(appraiser.run_appraiser(valid, DRIVER_COST_PROFILE, risk_result.order_risks))
        return (
            [(p.label, tuple(p.order_ids), p.nominal_profit, p.empty_km, p.return_time) for p in packages],
            risk_result.backup_pairs,
            appraisal.recommended_package_id,
        )

    first = run_once()
    second = run_once()
    assert first == second
