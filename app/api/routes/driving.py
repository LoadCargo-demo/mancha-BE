"""주행 중 화면 / 재조립 제안 / 재조립 완료."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.monitor import receive_event, should_trigger_rebuild
from app.agents.rebuilder import rebuild
from app.models.event import MockEvent, RebuildRequest
from app.services.mock_data import DRIVER_CONSTRAINTS, DRIVER_ID
from app.services.session_store import get, set_value

router = APIRouter(prefix="/driving", tags=["driving"])


@router.get("/status", summary="현재 진행 상태 (완료구간/다음행동/공차/복귀예정)")
def get_driving_status(driver_id: str = DRIVER_ID):
    session = get(driver_id)
    package = session.get("confirmed_package")
    if not package:
        raise HTTPException(status_code=404, detail="확정된 패키지가 없습니다.")
    return {"package": package}


@router.post("/event", summary="이벤트 주입(Mock) -> 재조립 제안")
async def submit_event(event: MockEvent, driver_id: str = DRIVER_ID):
    session = get(driver_id)
    package = session.get("confirmed_package")
    if not package:
        raise HTTPException(status_code=404, detail="확정된 패키지가 없습니다.")

    received = receive_event(event)
    if not should_trigger_rebuild(received):
        return {"should_notify": False, "message": "재조립이 필요한 이벤트가 아닙니다."}

    # 이벤트 대상 오더의 첫 블록 이전까지를 완료 구간으로 본다.
    if event.order_id:
        split_idx = next(
            (i for i, b in enumerate(package.blocks) if b.order_id == event.order_id),
            len(package.blocks),
        )
    else:
        split_idx = len(package.blocks)
    completed = package.blocks[:split_idx]
    remaining = package.blocks[split_idx:]
    backup_pairs = (
        session.get("risk_result").backup_pairs if session.get("risk_result") else {}
    )

    request = RebuildRequest(
        driver_id=driver_id,
        current_location=(
            completed[-1].location if completed else package.blocks[0].location
        ),
        completed_blocks=completed,
        remaining_blocks=remaining,
        event=received,
        backup_order_ids=list(backup_pairs.values()),
    )
    result = await rebuild(request, DRIVER_CONSTRAINTS, package)
    set_value(driver_id, "last_rebuild_result", result)
    return result


@router.post("/rebuild/apply", summary="재조립 반영 완료")
def apply_rebuild(driver_id: str = DRIVER_ID):
    session = get(driver_id)
    result = session.get("last_rebuild_result")
    if not result or not result.new_package:
        raise HTTPException(status_code=404, detail="적용할 재조립 결과가 없습니다.")
    set_value(driver_id, "confirmed_package", result.new_package)
    return {"status": "applied", "package": result.new_package, "diff": result.diff}
