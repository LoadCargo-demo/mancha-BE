"""Figma 데모 시나리오 E2E — 등록부터 복기까지 API 레벨로 전체 흐름을 검증한다."""
from fastapi.testclient import TestClient

from app.main import app


def _client():
    return TestClient(app)


def _run_pipeline(client):
    r = client.post("/api/pipeline/run-all")
    assert r.status_code == 200
    return r.json()


# --- A. Builder -------------------------------------------------------------

def test_builder_produces_three_distinct_packages_with_expected_roles():
    data = _run_pipeline(_client())
    packages = {p["label"]: p for p in [ap["package"] for ap in data["appraisal"]["ranked_packages"]]}

    assert set(packages) == {"최대수익형", "균형형", "조기복귀형"}

    max_profit = packages["최대수익형"]
    balanced = packages["균형형"]
    early_return = packages["조기복귀형"]

    assert "manual_handling" in max_profit["hard_violations"]
    assert max_profit["nominal_profit"] > balanced["nominal_profit"] > early_return["nominal_profit"]

    assert set(balanced["order_ids"]) == {"order_yangsan", "order_gimhae"}
    assert balanced["hard_violations"] == []

    assert early_return["hard_violations"] == []
    assert early_return["return_time"] < balanced["return_time"]

    sequences = {
        label: tuple((b["action"], b["order_id"]) for b in p["blocks"] if not b["is_fixed"])
        for label, p in packages.items()
    }
    assert len(set(sequences.values())) == 3  # 셋 다 서로 다른 action sequence


# --- B. Risk ------------------------------------------------------------

def test_risk_predictor_matches_target_relationships():
    data = _run_pipeline(_client())
    risk = data["risk"]
    by_id = {r["order_id"]: r for r in risk["order_risks"]}

    assert by_id["order_busan_c"]["is_auto_excluded"] is True
    assert by_id["order_gimhae"]["backup_order_id"] == "order_okcheon"
    assert risk["backup_pairs"] == {"order_gimhae": "order_okcheon"}


# --- C. Appraiser ---------------------------------------------------------

def test_final_recommendation_is_balanced_package():
    data = _run_pipeline(_client())
    appraisal = data["appraisal"]

    ranked = {ap["package"]["label"]: ap for ap in appraisal["ranked_packages"]}
    assert ranked["최대수익형"]["recommendable"] is False
    assert ranked["균형형"]["recommendable"] is True
    assert ranked["조기복귀형"]["recommendable"] is True

    recommended_label = next(
        ap["package"]["label"] for ap in appraisal["ranked_packages"]
        if ap["package"]["package_id"] == appraisal["recommended_package_id"]
    )
    assert recommended_label == "균형형"
    assert ranked["조기복귀형"]["package"]["return_time"] < ranked["균형형"]["package"]["return_time"]


# --- D. Confirm -------------------------------------------------------------

def test_confirm_balanced_package_stores_confirmed_package():
    client = _client()
    data = _run_pipeline(client)
    rec_id = data["appraisal"]["recommended_package_id"]

    r = client.post("/api/briefing/confirm", params={"package_id": rec_id})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["package"]["package_id"] == rec_id

    status = client.get("/api/driving/status")
    assert status.status_code == 200
    assert status.json()["package"]["package_id"] == rec_id


# --- E. Rebuild (김해 40분 지연 → 옥천 backup) ------------------------------

def test_gimhae_delay_triggers_okcheon_backup_rebuild():
    client = _client()
    data = _run_pipeline(client)
    rec_id = data["appraisal"]["recommended_package_id"]
    client.post("/api/briefing/confirm", params={"package_id": rec_id})

    r = client.post(
        "/api/driving/event",
        json={
            "event_type": "DELAY",
            "order_id": "order_gimhae",
            "delay_min": 40,
            "detail": "김해 상차 40분 지연",
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert result["should_notify"] is True

    new_package = result["new_package"]
    assert "order_gimhae" not in new_package["order_ids"]
    assert "order_okcheon" in new_package["order_ids"]
    non_fixed_locations = {b["location"] for b in new_package["blocks"] if not b["is_fixed"]}
    assert "대전" not in non_fixed_locations  # 김해 dropoff 지점이 남아있으면 안 됨

    # 완료된 구간(성남 상차/부산사상 하차/양산 상차)은 그대로 남아있어야 한다.
    fixed_and_completed = [b["location"] for b in new_package["blocks"]]
    assert "성남 물류센터" in fixed_and_completed
    assert "부산 사상" in fixed_and_completed
    assert any(b["order_id"] == "order_yangsan" and b["action"] == "상차" for b in new_package["blocks"])

    apply_r = client.post("/api/driving/rebuild/apply")
    assert apply_r.status_code == 200
    assert apply_r.json()["status"] == "applied"
    assert apply_r.json()["package"]["order_ids"] == new_package["order_ids"]


# --- F. Review --------------------------------------------------------------

def test_retrospective_reflects_rebuild_and_updates_wait_data():
    client = _client()
    data = _run_pipeline(client)
    rec_id = data["appraisal"]["recommended_package_id"]
    client.post("/api/briefing/confirm", params={"package_id": rec_id})
    client.post(
        "/api/driving/event",
        json={"event_type": "DELAY", "order_id": "order_gimhae", "delay_min": 40, "detail": "지연"},
    )
    client.post("/api/driving/rebuild/apply")

    r = client.get("/api/retrospective/summary")
    assert r.status_code == 200
    summary = r.json()

    assert summary["predicted_wait_min"] is not None
    assert summary["actual_wait_min"] >= summary["predicted_wait_min"]
    assert summary["wait_diff_min"] > 0
    assert summary["structural_cause"] is not None
    assert "옥천" in summary["structural_cause"]


# --- G. Determinism (핵심 파이프라인 + 재조립 제안) --------------------------

def test_core_pipeline_and_rebuild_proposal_are_deterministic():
    """Scout~Rebuild 제안까지는 반복 실행해도 항상 같은 결과가 나와야 한다.

    (복기 단계는 "다음 운행에 반영"하는 학습 루프가 의도적으로 전역 mock을
    갱신하므로 이 결정성 검사 범위에서 제외한다 — 그게 그 기능의 목적이다.)
    """
    def run_once():
        client = _client()
        data = _run_pipeline(client)
        rec_id = data["appraisal"]["recommended_package_id"]
        client.post("/api/briefing/confirm", params={"package_id": rec_id})
        r = client.post(
            "/api/driving/event",
            json={"event_type": "DELAY", "order_id": "order_gimhae", "delay_min": 40, "detail": "지연"},
        )
        rebuild = r.json()
        packages = [
            (ap["package"]["label"], tuple(ap["package"]["order_ids"]), ap["package"]["nominal_profit"])
            for ap in data["appraisal"]["ranked_packages"]
        ]
        return (
            rec_id,
            packages,
            data["risk"]["backup_pairs"],
            tuple(rebuild["new_package"]["order_ids"]),
            rebuild["diff"],
        )

    first = run_once()
    second = run_once()
    assert first == second
