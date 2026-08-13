# Mancha Backend / AI

만차(Mancha)의 **백엔드 및 AI Agent 파이프라인 서버**

차주의 하루 운행 조건과 화물 오더를 바탕으로 수행 가능한 하루 패키지를 생성하고,  
오더 리스크와 실수익을 평가해 추천안을 제공합니다.  
운행 중 지연·취소 이벤트가 발생하면 완료된 일정은 유지한 채 남은 일정을 재조립합니다.

---

## Tech Stack

- Python 3.12
- FastAPI
- Pydantic / pydantic-settings
- Gemini API
  - Text / Structured Output: `gemini-3.5-flash`
  - TTS: `gemini-3.1-flash-tts-preview`
- Docker
- AWS ECR / EC2 ASG / SSM


## Core Architecture

```text
Scout
  ↓
Builder
  ↓
Risk Predictor
  ↓
Appraiser
  ↓
Confirm
  ↓
Monitor
  ↓
Rebuilder
  ↓
Retrospective
```

## 주요 기능

- **Scout**: 비정형 오더를 Gemini Structured Output으로 정규화
- **Builder**: DFS/Backtracking 기반 하루 패키지 후보 생성 및 HARD 제약 검증
- **Risk Predictor**: 화주 이력·시간대 패턴을 기반으로 취소·지연 위험 및 성사 확률 계산
- **Appraiser**: 공차·대기 비용과 AI 현장 영향도를 반영한 실수익·Balanced Score 계산 및 추천
- **Q&A**: 암묵지 데이터 검색 + Gemini 기반 RAG 질의응답 및 후속 질문 생성
- **Monitor**: Mock 운행 이벤트 수신 및 재조립 트리거
- **Rebuilder**: 지연·취소 발생 시 완료 일정은 유지하고 잔여 일정 재조합
- **Retrospective**: 운행 종료 후 예측값과 실제값 비교 및 복기


## 프로젝트 구조

```text
app/
├── main.py                     # FastAPI 앱 엔트리포인트
├── api/
│   └── routes/                 # 기능별 API 라우터
├── agents/
│   ├── scout.py                # 자연어 오더 정규화
│   ├── builder.py              # 하루 패키지 조합 생성 및 제약 검증
│   ├── risk_predictor.py       # 오더 리스크·성사 확률·Backup 계산
│   ├── appraiser.py            # 실수익·Balanced Score·추천 계산
│   ├── qna.py                  # RAG 기반 질의응답
│   ├── monitor.py              # 운행 이벤트 처리(Mock)
│   └── rebuilder.py            # 잔여 일정 재조합
├── core/
│   ├── config.py               # 환경변수 및 애플리케이션 설정
│   └── constants.py            # 가중치·임계값·Guardrail 상수
├── models/                     # Pydantic 요청/응답 및 Agent 스키마
├── services/
│   ├── llm_client.py           # Gemini API 공통 클라이언트
│   ├── rag.py                  # 암묵지 검색 / pseudo-RAG
│   ├── mock_data.py            # 시연용
│   └── session_store.py        # MVP In-Memory Session 저장소
└── db/
    ├── models.py               # SQLAlchemy 모델 
    └── session.py              # DB 세션 팩토리
```

## 참고

- 현재 코드는 해커톤/MVP 데모를 기준으로 구성되어 있습니다.
- 일부 오더·거래이력·현장 데이터는 Mock입니다.
- `session_store.py`는 프로세스 재시작 시 초기화됩니다.