"""Risk Predictor Agent."""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.constants import (
    BACKUP_PICKUP_WINDOW_MIN,
    RISK_WEIGHT_CANCEL,
    RISK_WEIGHT_DELAY,
    RISK_WEIGHT_TIME,
)
from app.core.time_utils import to_min as _to_min
from app.models.order import LoadingType, NormalizedOrder
from app.models.risk import (
    TIME_PATTERN_RISK_VALUES,
    OrderRisk,
    RiskRunResult,
    TimePatternRisk,
    TradeHistory,
)
from app.services.llm_client import generate_structured, generate_text

TIME_PATTERN_RISK_SCHEMA_HINT = """
{
  "time_pattern_risk": "LOW" | "MEDIUM" | "HIGH"
}
"""


def _base_rates(history: TradeHistory) -> tuple[float, float]:
    if history.total_trades == 0:
        return 0.0, 0.0
    return (
        history.cancel_count / history.total_trades,
        history.delay_count / history.total_trades,
    )


def compute_risk_score(
    history: TradeHistory, time_pattern_risk_value: float
) -> tuple[float, float, float]:
    """riskScore = cancelRate*w1 + delayRate*w2 + time_pattern_risk_value*w3, success = 1-riskScore.
    time_pattern_risk_value는 Gemini의 LOW/MEDIUM/HIGH
    """
    cancel_rate, delay_rate = _base_rates(history)
    risk_score = (
        cancel_rate * RISK_WEIGHT_CANCEL
        + delay_rate * RISK_WEIGHT_DELAY
        + time_pattern_risk_value * RISK_WEIGHT_TIME
    )
    success_probability = max(0.0, min(1.0, 1 - risk_score))
    return cancel_rate, delay_rate, success_probability


def find_backup(
    order: NormalizedOrder, candidates: list[NormalizedOrder]
) -> NormalizedOrder | None:
    order_pickup_min = _to_min(order.pickup_start)
    best: NormalizedOrder | None = None
    best_gap: int | None = None
    for c in candidates:
        if c.order_id == order.order_id:
            continue
        if c.loading_type == LoadingType.MANUAL:
            continue
        gap = _to_min(c.pickup_start) - order_pickup_min
        if 0 <= gap <= BACKUP_PICKUP_WINDOW_MIN and (
            best_gap is None or gap < best_gap
        ):
            best = c
            best_gap = gap
    return best


async def _classify_time_pattern_risk(
    order: NormalizedOrder, history: TradeHistory
) -> float:
    prompt = (
        "<role>화물 오더의 화주 이력에서 시간대/이력 패턴에 따른 위험도를 분류하는 물류 분석가입니다.</role>\n\n"
        "<data>\n"
        f"total_trades: {history.total_trades}\n"
        f"cancel_count: {history.cancel_count}\n"
        f"delay_count: {history.delay_count}\n"
        f"pickup_time: {order.pickup_start}\n"
        f"cargo_type: {order.cargo_type}\n"
        f"pallet_count: {order.pallet_count}\n"
        f"loading_type: {order.loading_type.value}\n"
        f"shipper_name: {order.shipper_name or '알 수 없음'}\n"
        "</data>\n\n"
        "<task>data만 근거로 이 오더의 시간대/이력 패턴 위험도를 LOW, MEDIUM, HIGH 중 하나로 "
        "분류하세요. 확률이나 점수를 직접 계산하지 말고 분류만 하세요.</task>\n\n"
        "<constraints>data에 없는 사실을 지어내지 말고, 반드시 LOW/MEDIUM/HIGH 중 하나만 반환하세요.</constraints>"
    )
    try:
        data = await generate_structured(prompt, TIME_PATTERN_RISK_SCHEMA_HINT)
        label = data.get("time_pattern_risk")
        if isinstance(label, str) and label.upper() in TimePatternRisk.__members__:
            return TIME_PATTERN_RISK_VALUES[TimePatternRisk[label.upper()]]
    except Exception:
        pass
    return history.time_risk


def _nearest_time_pattern_label(value: float) -> str:
    return min(TIME_PATTERN_RISK_VALUES.items(), key=lambda kv: abs(kv[1] - value))[
        0
    ].value


def _risk_explanation_fallback(
    history: TradeHistory,
    cancel_rate: float,
    delay_rate: float,
    time_pattern_label: str,
    success_prob: float,
    is_excluded: bool,
    backup_id: str | None,
) -> str:
    parts = [
        f"최근 거래 {history.total_trades}건 중 취소 {history.cancel_count}건({cancel_rate:.0%}), "
        f"지연 {history.delay_count}건({delay_rate:.0%}), 시간대/이력 패턴 위험도 {time_pattern_label}를 "
        f"종합해 성사 확률을 {success_prob:.0%}로 평가했습니다."
    ]
    if is_excluded:
        parts.append("취소 확률이 기준치를 초과해 자동 제외했습니다.")
    elif backup_id:
        parts.append(f"일정 안정성을 위해 {backup_id} 오더를 백업으로 확보했습니다.")
    return " ".join(parts)


async def _generate_risk_explanation(
    order: NormalizedOrder,
    history: TradeHistory,
    cancel_rate: float,
    delay_rate: float,
    time_pattern_label: str,
    success_prob: float,
    is_excluded: bool,
    backup_id: str | None,
) -> str:
    fallback = _risk_explanation_fallback(
        history,
        cancel_rate,
        delay_rate,
        time_pattern_label,
        success_prob,
        is_excluded,
        backup_id,
    )
    prompt = (
        "<role>화물 오더의 리스크 평가 최종 결과를 기사에게 설명하는 물류 어시스턴트입니다.</role>\n\n"
        "<computed_result>\n"
        f"화주: {order.shipper_name or '알 수 없음'}\n"
        f"total_trades: {history.total_trades}\n"
        f"cancel_count: {history.cancel_count}\n"
        f"cancel_rate: {cancel_rate}\n"
        f"delay_count: {history.delay_count}\n"
        f"delay_rate: {delay_rate}\n"
        f"time_pattern_risk: {time_pattern_label}\n"
        f"success_probability: {success_prob}\n"
        f"is_auto_excluded: {is_excluded}\n"
        f"backup_order_id: {backup_id}\n"
        "</computed_result>\n\n"
        "<task>computed_result의 최종 결과 전체를 근거로, 왜 이런 리스크 평가가 나왔는지 설명하세요. "
        "time_pattern_risk 같은 개별 보조지표의 판단 이유가 아니라, 종합 결과를 설명하세요.</task>\n\n"
        "<constraints>\n"
        "- computed_result에 없는 사실이나 수치를 지어내지 마세요.\n"
        "- 한 문장 또는 최대 두 문장으로 작성하세요.\n"
        "</constraints>\n\n"
        "<final_check>문장 수가 1~2개인지, computed_result의 수치와 정확히 일치하는지 확인한 뒤 출력하세요.</final_check>"
    )
    return await generate_text(prompt, fallback=fallback)


def _resolve_history(
    order: NormalizedOrder, histories: dict[str, TradeHistory]
) -> TradeHistory:
    return histories.get(order.shipper_name or "") or TradeHistory(
        shipper_name=order.shipper_name or "unknown",
        total_trades=0,
        cancel_count=0,
        delay_count=0,
    )


async def run_risk_predictor(
    orders: list[NormalizedOrder], histories: dict[str, TradeHistory]
) -> RiskRunResult:
    resolved_histories = [_resolve_history(order, histories) for order in orders]

    time_pattern_values = await asyncio.gather(
        *[
            _classify_time_pattern_risk(order, history)
            for order, history in zip(orders, resolved_histories)
        ]
    )

    scored: list[tuple[dict, tuple]] = []
    for order, history, time_pattern_value in zip(
        orders, resolved_histories, time_pattern_values
    ):
        cancel_rate, delay_rate, success_prob = compute_risk_score(
            history, time_pattern_value
        )

        is_excluded = cancel_rate > settings.cancel_threshold
        reason = None
        backup_id = None
        if is_excluded:
            reason = (
                f"최근 취소 {history.cancel_count}회 / {history.total_trades}건 — "
                f"취소 확률 {cancel_rate:.0%}로 기준({settings.cancel_threshold:.0%}) 초과"
            )
        elif 0.6 <= success_prob < 0.8:
            backup = find_backup(order, orders)
            if backup:
                backup_id = backup.order_id

        risk_kwargs = dict(
            order_id=order.order_id,
            shipper_name=order.shipper_name or "",
            cancel_probability=round(cancel_rate, 3),
            delay_probability=round(delay_rate, 3),
            success_probability=round(success_prob, 3),
            is_auto_excluded=is_excluded,
            exclude_reason=reason,
            backup_order_id=backup_id,
        )
        time_pattern_label = _nearest_time_pattern_label(time_pattern_value)
        explanation_args = (
            order,
            history,
            cancel_rate,
            delay_rate,
            time_pattern_label,
            success_prob,
            is_excluded,
            backup_id,
        )
        scored.append((risk_kwargs, explanation_args))

    explanations = await asyncio.gather(
        *[
            _generate_risk_explanation(*explanation_args)
            for _, explanation_args in scored
        ]
    )

    order_risks = [
        OrderRisk(**risk_kwargs, explanation=explanation)
        for (risk_kwargs, _), explanation in zip(scored, explanations)
    ]

    excluded_count = sum(1 for r in order_risks if r.is_auto_excluded)
    backup_pairs = {
        r.order_id: r.backup_order_id for r in order_risks if r.backup_order_id
    }

    return RiskRunResult(
        order_risks=order_risks,
        excluded_count=excluded_count,
        backup_pairs=backup_pairs,
    )
