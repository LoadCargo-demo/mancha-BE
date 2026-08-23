"""Gemini API 공통 래퍼. 키 없으면 더미 응답, 모든 프롬프트에 가드레일 프리픽스 삽입."""
from __future__ import annotations

import json
import re
import httpx

from app.core.config import settings
from app.core.constants import BANNED_PHRASES, CLOSED_QUESTION_RULE

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


ANSWER_TAG_RULE = (
    "부연설명이나 인사말 없이, 최종 답변 문장만 <answer></answer> 태그 안에 넣어 출력하세요."
)

_ANSWER_TAG_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL)


def _extract_answer(text: str) -> str:
    match = _ANSWER_TAG_RE.search(text)
    return (match.group(1) if match else text).strip()


NO_RECALCULATION_RULE = (
    "제공된 수치나 사실을 변경하거나 새로 계산하지 말 것. 주어진 결과만 설명할 것."
)


def _guardrail_prefix(closed_question: bool = False) -> str:
    rules = [
        f"다음 표현은 사용하지 마세요: {', '.join(BANNED_PHRASES)}.",
        ANSWER_TAG_RULE,
        NO_RECALCULATION_RULE,
    ]
    if closed_question:
        rules.append(CLOSED_QUESTION_RULE)
    return "<guardrails>\n" + "\n".join(rules) + "\n</guardrails>\n\n"


def _default_fallback(closed_question: bool) -> str:
    if closed_question:
        return "지금 조건을 기준으로 준비한 안입니다. 이대로 진행할까요?"
    return "실수익과 안정성을 함께 고려했을 때 이 안이 더 유리합니다."


async def generate_text(
    prompt: str, closed_question: bool = False, fallback: str | None = None
) -> str:
    """fallback: LLM 호출이 실패(키 없음/429/타임아웃)했을 때 대신 쓸 문장.
    호출부가 이미 계산해둔 실제 수치를 담아 넘기면, 문구가 통째로 비지 않는다.
    안 넘기면 범용 문구로 대체한다.
    """
    full_prompt = _guardrail_prefix(closed_question) + prompt
    fallback_text = fallback or _default_fallback(closed_question)

    if not settings.gemini_api_key:
        return fallback_text

    url = GEMINI_ENDPOINT.format(model=settings.gemini_model)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": full_prompt}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_answer(raw_text)
    except (httpx.HTTPError, KeyError, IndexError):
        return fallback_text


async def generate_structured(prompt: str, schema_hint: str) -> dict:
    """schema_hint는 원하는 JSON 형태를 설명하는 문자열."""
    full_prompt = (
        "<guardrails>\n"
        f"다음 표현은 사용하지 마세요: {', '.join(BANNED_PHRASES)}.\n"
        f"{NO_RECALCULATION_RULE}\n"
        "</guardrails>\n\n"
        f"{prompt}\n\n"
        f"<output_schema>\n{schema_hint}\n</output_schema>\n\n"
        "<final_check>\n"
        "출력하기 전에: 스키마의 모든 필드를 채웠는지, 원문에 없는 값을 지어내지 "
        "않았는지 확인하세요. 설명이나 코드블록 없이 JSON 객체만 출력하세요.\n"
        "</final_check>"
    )

    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY가 설정되지 않았습니다. .env를 확인하거나 "
            "테스트에서는 agents 모듈의 mock 경로를 사용하세요."
        )

    url = GEMINI_ENDPOINT.format(model=settings.gemini_model)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
