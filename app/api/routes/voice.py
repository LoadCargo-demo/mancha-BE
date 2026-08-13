"""Gemini TTS/STT 프록시. 프론트가 API 키 없이 이 엔드포인트로 텍스트/오디오를
보내면 서버가 대신 Gemini를 호출해 결과를 돌려준다.

llm_client.py와 동일한 철학: 키가 없거나 Gemini 호출이 실패해도(요청 한도
초과, 타임아웃 등) 500으로 전체 요청을 죽이지 않고 None으로 조용히 응답한다.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])

TTS_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1alpha/models/{model}:generateContent"
)
# STT는 별도 TTS 전용 모델이 아니라, 텍스트 생성에도 쓰는 일반 멀티모달 모델을 그대로 사용
# (Gemini는 오디오를 멀티모달 입력으로 받아 generateContent 하나로 처리 가능)
STT_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


# ── TTS ──────────────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str
    voice_name: str = "Aoede"


class TTSResponse(BaseModel):
    audio_base64: str | None  # 실패 시 None — 프론트는 이 경우 TTS만 생략


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest) -> TTSResponse:
    if not req.text.strip():
        return TTSResponse(audio_base64=None)

    if not settings.gemini_api_key:
        return TTSResponse(audio_base64=None)

    url = TTS_ENDPOINT.format(model=settings.gemini_tts_model)
    payload = {
        "contents": [{"parts": [{"text": req.text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": req.voice_name}}
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()
            audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            return TTSResponse(audio_base64=audio_b64)
    except (httpx.HTTPError, KeyError, IndexError):
        return TTSResponse(audio_base64=None)


# ── STT ──────────────────────────────────────────────────────────
class STTRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"


class STTResponse(BaseModel):
    text: str | None  # 실패 시 None — 프론트는 "(인식 실패)" 등으로 처리


@router.post("/stt", response_model=STTResponse)
async def speech_to_text(req: STTRequest) -> STTResponse:
    if not req.audio_base64:
        return STTResponse(text=None)

    if not settings.gemini_api_key:
        return STTResponse(text=None)

    url = STT_ENDPOINT.format(model=settings.gemini_model)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "다음 음성을 있는 그대로 받아써줘. 텍스트만 출력하고 다른 말은 붙이지 마."},
                    {"inline_data": {"mime_type": req.mime_type, "data": req.audio_base64}},
                ],
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return STTResponse(text=text)
    except (httpx.HTTPError, KeyError, IndexError):
        return STTResponse(text=None)