import asyncio

from app.agents import risk_predictor
from app.services.mock_data import MOCK_NORMALIZED_ORDERS, MOCK_TRADE_HISTORY


def _run():
    return asyncio.run(risk_predictor.run_risk_predictor(MOCK_NORMALIZED_ORDERS, MOCK_TRADE_HISTORY))


def _risk_by_id(result, order_id):
    return next(r for r in result.order_risks if r.order_id == order_id)


def test_yangsan_success_probability():
    r = _risk_by_id(_run(), "order_yangsan")
    assert r.success_probability == 0.96
    assert r.is_auto_excluded is False


def test_gimhae_success_probability_and_backup():
    result = _run()
    r = _risk_by_id(result, "order_gimhae")
    assert r.success_probability == 0.71
    assert r.is_auto_excluded is False
    assert r.backup_order_id == "order_okcheon"
    assert result.backup_pairs == {"order_gimhae": "order_okcheon"}


def test_busan_c_auto_excluded():
    r = _risk_by_id(_run(), "order_busan_c")
    assert r.success_probability == 0.42
    assert r.is_auto_excluded is True


def test_run_risk_predictor_is_deterministic_across_calls():
    first = _run()
    second = _run()
    assert [r.success_probability for r in first.order_risks] == [
        r.success_probability for r in second.order_risks
    ]
    assert first.backup_pairs == second.backup_pairs
    assert first.excluded_count == second.excluded_count == 1
