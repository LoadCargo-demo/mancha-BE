"""전역 상수. 하드코딩 대신 여기에 모아 관리한다."""

# --- Risk Predictor ---
RISK_WEIGHT_CANCEL = 0.5  # w1
RISK_WEIGHT_DELAY = 0.3  # w2
RISK_WEIGHT_TIME = 0.2  # w3

# --- 백업 오더 매칭 (Risk Predictor) ---
BACKUP_PICKUP_WINDOW_MIN = 240  # 4시간 이내

# --- 균형형 패키지 스코어 ---
BALANCE_WEIGHT_PROFIT = 0.35  # w1
BALANCE_WEIGHT_SUCCESS = 0.25  # w2
BALANCE_WEIGHT_EMPTY_KM = 0.15  # w3
BALANCE_WEIGHT_WAIT = 0.15  # w4
BALANCE_WEIGHT_RETURN_DELAY = 0.10  # w5
BALANCE_WEIGHT_FIELD_IMPACT = 5  # w6

# --- 알림 억제 임계값 ---
ALERT_MIN_PROFIT_GAP = 30_000
ALERT_MIN_TIME_GAP_MIN = 30

# --- RAG 환각 방지 ---
RAG_MIN_HITS = 1
RAG_MIN_SIMILARITY = 0.5

# --- ONB-01-05 손익분기 데모 산식 (실제 통계 기반 아님, 설명 가능한 단순 가정치) ---
DEMO_DAILY_KM_ASSUMPTION = 300    # 하루 평균 주행 거리 가정 (km)
DEMO_DAILY_HOURS_ASSUMPTION = 10  # 하루 평균 가동 시간 가정 (h)

BANNED_PHRASES = ["최적", "완벽", "실시간"]
CLOSED_QUESTION_RULE = (
    "모든 발화는 예/아니오 또는 번호로 답할 수 있는 닫힌 질문으로 끝나야 한다. "
    "열린 질문 형태('어떻게 할까요?' 등)는 사용하지 않는다."
)
