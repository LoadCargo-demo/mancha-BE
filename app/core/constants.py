"""전역 상수. 하드코딩 대신 여기에 모아 관리한다."""
# --- Risk Predictor ---
RISK_WEIGHT_CANCEL = 0.5      # w1
RISK_WEIGHT_DELAY = 0.3       # w2
RISK_WEIGHT_TIME = 0.2        # w3

# --- 백업 오더 매칭 (Risk Predictor) ---
BACKUP_PICKUP_WINDOW_MIN = 240  # 4시간 이내

# --- 균형형 패키지 스코어 ---
BALANCE_WEIGHT_PROFIT = 0.35     # w1
BALANCE_WEIGHT_SUCCESS = 0.25    # w2
BALANCE_WEIGHT_EMPTY_KM = 0.15   # w3
BALANCE_WEIGHT_WAIT = 0.15       # w4
BALANCE_WEIGHT_RETURN_DELAY = 0.10  # w5
BALANCE_WEIGHT_FIELD_IMPACT = 5  # w6

BANNED_PHRASES = ["최적", "완벽", "실시간"]
CLOSED_QUESTION_RULE = (
    "모든 발화는 예/아니오 또는 번호로 답할 수 있는 닫힌 질문으로 끝나야 한다. "
    "열린 질문 형태('어떻게 할까요?' 등)는 사용하지 않는다."
)
