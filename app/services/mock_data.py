"""고정 Mock 데이터셋. 페르소나: 김만수(52) · 5톤 카고 · 고정 편도 성남→부산 사상."""
from app.models.order import DriverConstraints, LoadingType, NormalizedOrder
from app.models.risk import TradeHistory
from app.models.appraisal import DriverCostProfile

DRIVER_ID = "driver_kimmansu"

DRIVER_CONSTRAINTS = DriverConstraints(
    fixed_pickup="성남 물류센터",
    fixed_pickup_time="05:30",
    fixed_dropoff="부산 사상",
    fixed_dropoff_time="10:30",
    return_location="경기 광주",
    return_deadline="23:00",
    exclude_manual_loading=True,
    avoid_night_driving=True,
    vehicle_type="5톤 카고",
)

DRIVER_COST_PROFILE = DriverCostProfile(
    cost_per_km=1840,
    value_per_hour=41000,
    min_fare_per_km=1500,
)

MOCK_NORMALIZED_ORDERS: list[NormalizedOrder] = [
    NormalizedOrder(
        order_id="order_yangsan",
        pickup="양산 대한부품",
        dropoff="군포",
        pickup_start="11:00",
        pickup_end="12:00",
        cargo_type="자동차 부품",
        pallet_count=6,
        loading_type=LoadingType.FORKLIFT,
        price=142000,
        shipper_name="양산 대한부품",
    ),
    NormalizedOrder(
        order_id="order_gimhae",
        pickup="김해 A물류",
        dropoff="대전",
        pickup_start="12:00",
        pickup_end="13:00",
        cargo_type="생활용품",
        pallet_count=8,
        loading_type=LoadingType.FORKLIFT,
        price=200000,
        shipper_name="김해 A물류",
    ),
    NormalizedOrder(
        order_id="order_busan_c",
        pickup="부산 C통운",
        dropoff="울산",
        pickup_start="11:30",
        pickup_end="12:30",
        cargo_type="철강 부자재",
        pallet_count=4,
        loading_type=LoadingType.MANUAL,
        price=95000,
        shipper_name="부산 C통운",
    ),
    NormalizedOrder(
        order_id="order_incheon",
        pickup="인천 신항",
        dropoff="평택",
        pickup_start="10:30",
        pickup_end="20:00",
        cargo_type="중량물",
        pallet_count=10,
        loading_type=LoadingType.MANUAL,
        price=400000,
        shipper_name="인천 신항물류",
    ),
    NormalizedOrder(
        order_id="order_okcheon",
        pickup="옥천",
        dropoff="군포",
        pickup_start="14:00",
        pickup_end="15:00",
        cargo_type="자동차 부품",
        pallet_count=5,
        loading_type=LoadingType.FORKLIFT,
        price=30000,
        shipper_name="옥천 B물류",
    ),
]

MOCK_TRADE_HISTORY: dict[str, TradeHistory] = {
    "양산 대한부품": TradeHistory(
        shipper_name="양산 대한부품", total_trades=12, cancel_count=0, delay_count=0, time_risk=0.2,
    ),
    "김해 A물류": TradeHistory(
        shipper_name="김해 A물류", total_trades=5, cancel_count=0, delay_count=3, time_risk=0.55,
    ),
    "부산 C통운": TradeHistory(
        shipper_name="부산 C통운", total_trades=8, cancel_count=6, delay_count=2, time_risk=0.65,
    ),
    "옥천 B물류": TradeHistory(
        shipper_name="옥천 B물류", total_trades=9, cancel_count=0, delay_count=1, time_risk=0.15,
    ),
    "인천 신항물류": TradeHistory(
        shipper_name="인천 신항물류", total_trades=10, cancel_count=0, delay_count=0, time_risk=0.1,
    ),
}

MOCK_FIELD_WAIT_DATA: dict[str, dict] = {
    "부산 사상": {"avg_wait_min": 90, "sample_count": 38},
    "김해 A물류": {"avg_wait_min": 40, "sample_count": 21},
    "옥천": {"avg_wait_min": 10, "sample_count": 14},
    "대전": {"avg_wait_min": 15, "sample_count": 17},
}

MOCK_EVENT_SCENARIOS = {
    "gimhae_delay_40min": {
        "event_type": "DELAY",
        "order_id": "order_gimhae",
        "delay_min": 40,
        "detail": "김해 상차 40분 지연",
    },
    "yangsan_delay_60min": {
        "event_type": "DELAY",
        "order_id": "order_yangsan",
        "delay_min": 60,
        "detail": "양산 대한부품 상차 60분 지연",
    },
}
