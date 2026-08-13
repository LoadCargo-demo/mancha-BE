"""Registration Agent"""

from __future__ import annotations

from app.services.llm_client import generate_text

WEATHER_FACT = {
    "rain_probability_pct": 70,
    "suggested_constraint": "방수 포장 화물만 수락",
}
WEATHER_MESSAGE_FALLBACK = "내일은 강수 확률 70%입니다. 방수 포장 화물만 받을까요?"


async def generate_weather_suggestion_message() -> str:
    prompt = (
        "<role>내일 등록 화면에서 기상 조건을 안내하는 물류 어시스턴트입니다.</role>\n\n"
        "<facts>\n"
        f"강수 확률: {WEATHER_FACT['rain_probability_pct']}%\n"
        f"제안: {WEATHER_FACT['suggested_constraint']}\n"
        "</facts>\n\n"
        "<task>facts에 있는 내용만 근거로 기사에게 보여줄 한 문장 제안 메시지를 작성하세요.</task>\n\n"
        "<constraints>facts의 수치나 제안 내용을 바꾸거나 새로 판단하지 마세요. 그대로 문장으로만 옮기세요.</constraints>"
    )
    return await generate_text(
        prompt, closed_question=True, fallback=WEATHER_MESSAGE_FALLBACK
    )
