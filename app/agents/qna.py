"""음성 질의응답 (RAG) — 검색 결과가 임계치 미만이면 지어내지 않고 고정 응답."""

from __future__ import annotations

from pydantic import BaseModel

from app.services.llm_client import generate_structured, generate_text
from app.services.rag import TacitKnowledgeDoc, retrieve_with_threshold

NO_DATA_RESPONSE = "관련 데이터가 없습니다."

FALLBACK_FOLLOW_UP_QUESTIONS = [
    "1안은 왜 수작업이야?",
    "대기 시간은 어디서 나온 거야?",
    "다른 안은 몇 시 복귀야?",
]

FOLLOW_UP_SCHEMA_HINT = """
{
  "follow_up_questions": ["string", "string", "string"]
}
"""


class QnaAnswer(BaseModel):
    answer: str
    sources: list[dict]  # [{"source": str, "text": str}]
    follow_up_questions: list[str]


async def _generate_follow_up_questions(
    question: str,
    answer: str,
    package_context: str,
    hits: list[tuple[TacitKnowledgeDoc, float]],
) -> list[str]:
    context_text = "\n".join(f"- {doc.text} (출처: {doc.source})" for doc, _ in hits)
    prompt = (
        "<role>기사가 방금 받은 답변을 보고 이어서 물어볼 법한 질문을 제안하는 물류 어시스턴트입니다.</role>\n\n"
        f"<package_context>{package_context}</package_context>\n\n"
        f"<retrieved_knowledge>\n{context_text}\n</retrieved_knowledge>\n\n"
        f"<question>{question}</question>\n\n"
        f"<answer>{answer}</answer>\n\n"
        "<task>기사가 이어서 물어볼 법한 후속 질문을 정확히 3개 생성하세요. "
        "각 질문은 package_context/retrieved_knowledge/answer 안에서 실제로 확인 가능한 내용에 대해서만 물어야 합니다.</task>\n\n"
        "<constraints>새로운 수치나 사실을 지어내지 말고, 질문 문장만 만드세요.</constraints>"
    )
    try:
        data = await generate_structured(prompt, FOLLOW_UP_SCHEMA_HINT)
        questions = data.get("follow_up_questions")
        if (
            isinstance(questions, list)
            and len(questions) == 3
            and all(isinstance(q, str) and q.strip() for q in questions)
        ):
            return questions
    except Exception:
        pass
    return list(FALLBACK_FOLLOW_UP_QUESTIONS)


def _build_answer_fallback(hits: list[tuple[TacitKnowledgeDoc, float]]) -> str:
    facts = " ".join(doc.text for doc, _ in hits[:2])
    return f"관련 현장 기록에 따르면 {facts}"


async def answer_question(question: str, package_context: str) -> QnaAnswer:
    hits = retrieve_with_threshold(question)

    if not hits:
        return QnaAnswer(answer=NO_DATA_RESPONSE, sources=[], follow_up_questions=[])

    context_text = "\n".join(f"- {doc.text} (출처: {doc.source})" for doc, _ in hits)
    prompt = (
        "<role>기사의 질문에 암묵지 데이터를 근거로 답하는 물류 어시스턴트입니다.</role>\n\n"
        f"<package_context>{package_context}</package_context>\n\n"
        f"<retrieved_knowledge>\n{context_text}\n</retrieved_knowledge>\n\n"
        f"<question>{question}</question>\n\n"
        "<instructions>\n"
        "- retrieved_knowledge에 있는 내용만 근거로 답변하세요.\n"
        "- 구체적인 수치와 산출 과정을 포함하세요.\n"
        "- retrieved_knowledge에 없는 내용은 지어내지 마세요.\n"
        "</instructions>\n\n"
        "<final_check>답변의 모든 근거가 retrieved_knowledge 안에 실제로 있는지 "
        "확인한 뒤 출력하세요.</final_check>"
    )
    answer = await generate_text(prompt, fallback=_build_answer_fallback(hits))
    follow_ups = await _generate_follow_up_questions(
        question, answer, package_context, hits
    )

    return QnaAnswer(
        answer=answer,
        sources=[
            {
                "source": doc.source,
                "text": doc.text,
                "source_type": doc.source_type,
                "sample_count": doc.sample_count,
            }
            for doc, _ in hits
        ],
        follow_up_questions=follow_ups,
    )
