"""암묵지 RAG 파이프라인"""

from __future__ import annotations

import hashlib

import numpy as np

from app.core.config import settings

VECTOR_DIM = 64


class TacitKnowledgeDoc:
    def __init__(
        self,
        doc_id: str,
        text: str,
        source: str,
        sample_count: int | None = None,
        source_type: str | None = None,
    ):
        self.doc_id = doc_id
        self.text = text
        self.source = source
        self.sample_count = sample_count
        self.source_type = source_type


# 암묵지 DB Mock
TACIT_KNOWLEDGE_DB: list[TacitKnowledgeDoc] = [
    TacitKnowledgeDoc(
        "tk_busan_sasang_wait",
        "부산 사상 하역장은 오후 평균 대기 90분이다. 최근 38건 기록 기준.",
        "암묵지 DB · 부산신항 기록 38건",
        sample_count=38,
        source_type="tacit_knowledge",
    ),
    TacitKnowledgeDoc(
        "tk_gimhae_a_wait",
        "김해 A물류는 평균 대기 40분이며 오후 상차가 밀리는 경향이 있다.",
        "암묵지 DB · 김해A 기록 21건",
        sample_count=21,
        source_type="tacit_knowledge",
    ),
    TacitKnowledgeDoc(
        "tk_okcheon_forklift",
        "옥천 B물류는 오후에 지게차가 한 대뿐이라 상차가 밀린다.",
        "암묵지 DB · 옥천 기록 14건",
        sample_count=14,
        source_type="tacit_knowledge",
    ),
]


def _embed(text: str) -> np.ndarray:
    h = hashlib.sha256(text.encode()).digest()
    arr = np.frombuffer((h * (VECTOR_DIM // len(h) + 1))[:VECTOR_DIM], dtype=np.uint8)
    vec = arr.astype(np.float32)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _keyword_overlap(query: str, text: str) -> float:
    q_tokens = set(query.replace("?", "").split())
    t_tokens = set(text.split())
    if not q_tokens or not t_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / len(q_tokens)


def search(query: str, top_k: int = 3) -> list[tuple[TacitKnowledgeDoc, float]]:
    """질문과 유사한 암묵지 문서를 검색한다 (임베딩 코사인유사도 + 키워드 overlap 혼합)."""
    q_vec = _embed(query)
    scored = []
    for doc in TACIT_KNOWLEDGE_DB:
        cos = _cosine_sim(q_vec, _embed(doc.text))
        overlap = _keyword_overlap(query, doc.text)
        score = 0.3 * max(cos, 0) + 0.7 * overlap
        scored.append((doc, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def retrieve_with_threshold(query: str) -> list[tuple[TacitKnowledgeDoc, float]]:
    """환각 방지: 임계치 미만 결과는 제외."""
    results = search(query)
    return [r for r in results if r[1] >= settings.rag_similarity_threshold]
