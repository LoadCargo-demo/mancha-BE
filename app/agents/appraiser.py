"""Appraiser Agent"""

from __future__ import annotations

import asyncio

from app.core.constants import (
    BALANCE_WEIGHT_EMPTY_KM,
    BALANCE_WEIGHT_FIELD_IMPACT,
    BALANCE_WEIGHT_PROFIT,
    BALANCE_WEIGHT_RETURN_DELAY,
    BALANCE_WEIGHT_SUCCESS,
    BALANCE_WEIGHT_WAIT,
)
from app.models.appraisal import (
    AppraisalResult,
    AppraisedPackage,
    DeductionItem,
    DriverCostProfile,
)
from app.models.order import NormalizedOrder
from app.models.package import PackageCandidate
from app.models.risk import OrderRisk
from app.services.llm_client import generate_structured, generate_text
from app.services.mock_data import MOCK_FIELD_WAIT_DATA, MOCK_NORMALIZED_ORDERS

_ORDER_LOOKUP = {o.order_id: o for o in MOCK_NORMALIZED_ORDERS}

FIELD_IMPACT_SCHEMA_HINT = """
{
  "field_impact_level": "LOW" | "MEDIUM" | "HIGH"
}
"""

FIELD_IMPACT_VALUES: dict[str, float] = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.8}


def _location_slug(location: str) -> str:
    return "field_" + location.replace(" ", "_")


def _estimate_wait_min(package: PackageCandidate) -> tuple[int, list[tuple[str, int]]]:
    total_wait = 0
    breakdown: list[tuple[str, int]] = []
    for block in package.blocks:
        if block.is_fixed:
            continue
        field = MOCK_FIELD_WAIT_DATA.get(block.location)
        if field:
            total_wait += field["avg_wait_min"]
            breakdown.append((block.location, field["avg_wait_min"]))
    return total_wait, breakdown


def _field_impact_fallback(wait_min: int) -> str:
    if wait_min >= 60:
        return "HIGH"
    if wait_min >= 30:
        return "MEDIUM"
    return "LOW"


async def _classify_field_impact_level(
    wait_breakdown: list[tuple[str, int]], wait_min: int
) -> str:
    if not wait_breakdown:
        return "LOW"
    facts = "\n".join(f"- {loc}: 평균 대기 {mins}분" for loc, mins in wait_breakdown)
    prompt = (
        "<role>화물 패키지의 현장 암묵지(하역장 대기 기록)를 바탕으로 영향도를 분류하는 물류 분석가입니다.</role>\n\n"
        f"<field_data>\n{facts}\n</field_data>\n\n"
        "<task>field_data만 근거로 이 패키지가 받는 현장 영향도를 LOW, MEDIUM, HIGH 중 하나로 "
        "분류하세요. 이유를 설명하지 말고 분류만 하세요.</task>\n\n"
        "<constraints>field_data에 없는 사실을 지어내지 말고, 반드시 LOW/MEDIUM/HIGH 중 하나만 반환하세요.</constraints>"
    )
    try:
        data = await generate_structured(prompt, FIELD_IMPACT_SCHEMA_HINT)
        label = data.get("field_impact_level")
        if isinstance(label, str) and label.upper() in {"LOW", "MEDIUM", "HIGH"}:
            return label.upper()
    except Exception:
        pass
    return _field_impact_fallback(wait_min)


def _compute_negotiation_gain(
    package: PackageCandidate, order_lookup: dict[str, NormalizedOrder]
) -> int | None:
    total = 0
    any_set = False
    for order_id in package.order_ids:
        order = order_lookup.get(order_id)
        if (
            order
            and order.offered_price is not None
            and order.negotiated_price is not None
        ):
            total += order.negotiated_price - order.offered_price
            any_set = True
    return total if any_set else None


def _package_success_probability(
    package: PackageCandidate, order_risks: list[OrderRisk]
) -> float:
    risk_map = {r.order_id: r.success_probability for r in order_risks}
    if not package.order_ids:
        return 1.0
    probs = [risk_map.get(oid, 0.9) for oid in package.order_ids]
    result = 1.0
    for p in probs:
        result *= p
    return round(result, 3)


def appraise_package(
    package: PackageCandidate,
    cost_profile: DriverCostProfile,
    order_risks: list[OrderRisk],
    order_lookup: dict[str, NormalizedOrder] | None = None,
) -> AppraisedPackage:
    """실수익 = 명목수익 - 공차비(공차거리×km당원가) - 대기비(대기시간×시간가치)."""
    wait_min, wait_breakdown = _estimate_wait_min(package)
    empty_cost = round(package.empty_km * cost_profile.cost_per_km)
    wait_cost = round((wait_min / 60) * cost_profile.value_per_hour)
    adjusted_profit = package.nominal_profit - empty_cost - wait_cost

    deductions: list[DeductionItem] = []
    for location, loc_wait_min in wait_breakdown:
        loc_cost = round((loc_wait_min / 60) * cost_profile.value_per_hour)
        if loc_cost <= 0:
            continue
        deductions.append(
            DeductionItem(
                label="대기 비용",
                amount=loc_cost,
                source=f"{location} 예상 대기 {loc_wait_min}분 × 시간가치 {cost_profile.value_per_hour:,}원/h",
                source_id=_location_slug(location),
                source_type="tacit_knowledge",
            )
        )
    if empty_cost > 0:
        deductions.append(
            DeductionItem(
                label="공차 비용",
                amount=empty_cost,
                source=f"공차 {package.empty_km:.1f}km × {cost_profile.cost_per_km:,}원/km",
            )
        )

    success_prob = _package_success_probability(package, order_risks)

    return AppraisedPackage(
        package=package,
        expected_wait_min=wait_min,
        success_probability=success_prob,
        empty_cost=empty_cost,
        wait_cost=wait_cost,
        adjusted_profit=adjusted_profit,
        deductions=deductions,
        recommendable=not package.hard_violations,
        negotiation_gain=_compute_negotiation_gain(
            package, order_lookup if order_lookup is not None else _ORDER_LOOKUP
        ),
    )


def _return_delay_penalty(return_time: str) -> float:
    h, m = return_time.split(":")
    minutes = int(h) * 60 + int(m)
    baseline = 21 * 60
    return max(0, minutes - baseline)


def compute_balanced_score(
    ap: AppraisedPackage, field_impact_value: float = 0.0
) -> float:
    """수익*w1 + 성사확률*w2 - 공차*w3 - 대기*w4 - 복귀지연*w5 - 현장영향도*w6.

    field_impact_value(0.2/0.5/0.8, AI 보조지표)는 작은 penalty로
    """
    return (
        ap.adjusted_profit * BALANCE_WEIGHT_PROFIT / 1000
        + ap.success_probability * 100 * BALANCE_WEIGHT_SUCCESS
        - ap.package.empty_km * BALANCE_WEIGHT_EMPTY_KM
        - ap.expected_wait_min * BALANCE_WEIGHT_WAIT
        - _return_delay_penalty(ap.package.return_time) * BALANCE_WEIGHT_RETURN_DELAY
        - field_impact_value * BALANCE_WEIGHT_FIELD_IMPACT
    )


async def run_appraiser(
    packages: list[PackageCandidate],
    cost_profile: DriverCostProfile,
    order_risks: list[OrderRisk],
    order_lookup: dict[str, NormalizedOrder] | None = None,
) -> AppraisalResult:
    appraised = [
        appraise_package(p, cost_profile, order_risks, order_lookup) for p in packages
    ]

    wait_infos = [_estimate_wait_min(ap.package) for ap in appraised]
    field_impact_levels = await asyncio.gather(
        *[
            _classify_field_impact_level(breakdown, wait_min)
            for wait_min, breakdown in wait_infos
        ]
    )
    field_impact_by_id = {
        ap.package.package_id: level
        for ap, level in zip(appraised, field_impact_levels)
    }

    for ap in appraised:
        field_impact_value = FIELD_IMPACT_VALUES[
            field_impact_by_id[ap.package.package_id]
        ]
        ap.balanced_score = compute_balanced_score(ap, field_impact_value)

    appraised.sort(key=lambda a: (a.balanced_score or 0), reverse=True)

    eligible = [a for a in appraised if a.recommendable]
    recommended = eligible[0] if eligible else None
    if recommended:
        recommended.package.is_recommended = True

    max_nominal = max(appraised, key=lambda a: a.package.nominal_profit)

    if recommended is None:
        reason = "정책상 조건을 위반하지 않는 추천 가능한 안이 없습니다."
        briefing = (
            "오늘은 추천할 수 있는 안이 없습니다. 조건을 조정해서 다시 시도할까요?"
        )
        return AppraisalResult(
            ranked_packages=appraised,
            recommended_package_id=None,
            recommendation_reason=reason,
            briefing_text=briefing,
        )

    context_lines = [
        f"- {ap.package.label}: 명목수익 {ap.package.nominal_profit:,}원, "
        f"실수익 {ap.adjusted_profit:,}원, 공차 {ap.package.empty_km:.1f}km, "
        f"예상대기 {ap.expected_wait_min}분, 성사확률 {ap.success_probability:.0%}, "
        f"현장영향도 {field_impact_by_id.get(ap.package.package_id, 'LOW')}, "
        f"정책위반 {'있음' if ap.package.hard_violations else '없음'}"
        for ap in appraised
    ]
    reason_prompt = (
        "<role>화물 배차 추천 근거를 설명하는 물류 어시스턴트입니다.</role>\n\n"
        "<context>\n" + "\n".join(context_lines) + "\n"
        f"최종 추천: {recommended.package.label}\n"
        "</context>\n\n"
        "<task>context의 최종 계산 결과 전체를 근거로, 왜 최종 추천을 선택했는지 설명하세요. "
        "field_impact_level 같은 개별 보조지표의 판단 이유가 아니라, 종합 평가 결과를 설명하세요.</task>\n\n"
        "<constraints>\n"
        "- context에 없는 숫자나 사실을 지어내지 마세요.\n"
        "- 한 문장 또는 최대 두 문장으로 작성하세요.\n"
        "</constraints>\n\n"
        "<final_check>문장 수가 1~2개인지, context의 숫자와 정확히 일치하는지 확인한 뒤 출력하세요.</final_check>"
    )
    reason_fallback = (
        f"{max_nominal.package.label}은 명목수익이 {max_nominal.package.nominal_profit:,}원으로 "
        f"더 높지만, 대기·공차 비용과 현장 데이터를 반영한 실수익은 {recommended.package.label}이 "
        f"{recommended.adjusted_profit:,}원으로 더 유리해 이 안을 추천합니다."
    )
    reason = await generate_text(reason_prompt, fallback=reason_fallback)

    briefing_prompt = (
        "<role>기사에게 아침 운행 계획을 음성으로 브리핑하는 어시스턴트입니다.</role>\n\n"
        "<context>\n"
        f"추천안: {recommended.package.label}\n"
        f"공차: {recommended.package.empty_km:.1f}km\n"
        f"예상 실수익: {recommended.adjusted_profit:,}원\n"
        f"복귀 시각: {recommended.package.return_time}\n"
        "</context>\n\n"
        "<task>위 내용을 30초 이내 분량으로 요약하는 아침 브리핑 문장을 작성하세요.</task>\n\n"
        "<constraints>\n"
        "- 마지막 문장은 반드시 '확정할까요?'로 끝나는 닫힌 질문이어야 합니다.\n"
        "- context에 없는 수치나 상황을 지어내지 마세요.\n"
        "</constraints>\n\n"
        "<final_check>길이가 30초 분량인지, '확정할까요?'로 끝나는지 확인한 뒤 출력하세요.</final_check>"
    )
    briefing_fallback = (
        f"오늘 추천은 {recommended.package.label}입니다. "
        f"공차 {recommended.package.empty_km:.1f}km, 예상 실수익 {recommended.adjusted_profit:,}원, "
        f"복귀 예정 시각은 {recommended.package.return_time}입니다. 확정할까요?"
    )
    briefing = await generate_text(
        briefing_prompt, closed_question=True, fallback=briefing_fallback
    )

    return AppraisalResult(
        ranked_packages=appraised,
        recommended_package_id=recommended.package.package_id,
        recommendation_reason=reason,
        briefing_text=briefing,
    )
