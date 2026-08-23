"""음성 질의응답 (RAG). 프론트가 STT로 텍스트를 뽑아 이 엔드포인트로 보낸다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.qna import answer_question
from app.services.session_store import get, resolve_session_key

router = APIRouter(prefix="/qna", tags=["qna"])


class QuestionRequest(BaseModel):
    question: str


@router.post("/ask", summary="근거 기반 답변 생성 (RAG)")
async def ask(payload: QuestionRequest, driver_id: str = Depends(resolve_session_key)):
    session = get(driver_id)
    appraisal = session.get("appraisal_result")
    if not appraisal:
        raise HTTPException(
            status_code=404, detail="파이프라인을 먼저 실행하세요 (/pipeline/run)"
        )

    recommended = next(
        (
            ap
            for ap in appraisal.ranked_packages
            if ap.package.package_id == appraisal.recommended_package_id
        ),
        appraisal.ranked_packages[0],
    )
    context = (
        f"추천안 {recommended.package.label}, 실수익 {recommended.adjusted_profit:,}원, "
        f"복귀 {recommended.package.return_time}"
    )
    return await answer_question(payload.question, context)
