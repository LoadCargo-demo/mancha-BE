"""데모용 더미데이터 시드 스크립트"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.agents import appraiser, builder, risk_predictor
from app.db.models import (
    Base,
    DailyRegistration,
    Driver,
    FieldWaitData,
    Order,
    OrderRiskAssessment,
    PackageOrder,
    PackageRecord,
    RebuildEvent,
    Shipper,
)
from app.db.session import SessionLocal, engine
from app.models.event import EventType, MockEvent, RebuildRequest
from app.services.mock_data import (
    DRIVER_CONSTRAINTS,
    DRIVER_COST_PROFILE,
    DRIVER_ID,
    MOCK_FIELD_WAIT_DATA,
    MOCK_NORMALIZED_ORDERS,
    MOCK_TRADE_HISTORY,
)


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.merge(
            Driver(
                id=DRIVER_ID,
                vehicle_type=DRIVER_CONSTRAINTS.vehicle_type,
                vehicle_capacity_pallets=DRIVER_CONSTRAINTS.vehicle_capacity_pallets,
                cost_per_km=DRIVER_COST_PROFILE.cost_per_km,
                value_per_hour=DRIVER_COST_PROFILE.value_per_hour,
                min_fare_per_km=DRIVER_COST_PROFILE.min_fare_per_km,
                fixed_pickup=DRIVER_CONSTRAINTS.fixed_pickup,
                fixed_pickup_time=DRIVER_CONSTRAINTS.fixed_pickup_time,
                fixed_dropoff=DRIVER_CONSTRAINTS.fixed_dropoff,
                fixed_dropoff_time=DRIVER_CONSTRAINTS.fixed_dropoff_time,
                return_location=DRIVER_CONSTRAINTS.return_location,
                return_deadline=DRIVER_CONSTRAINTS.return_deadline,
            )
        )

        for name, h in MOCK_TRADE_HISTORY.items():
            db.merge(
                Shipper(
                    name=name,
                    total_trades=h.total_trades,
                    cancel_count=h.cancel_count,
                    delay_count=h.delay_count,
                    time_risk=h.time_risk,
                )
            )

        for location, field in MOCK_FIELD_WAIT_DATA.items():
            db.merge(
                FieldWaitData(
                    location=location,
                    avg_wait_min=field["avg_wait_min"],
                    sample_count=field["sample_count"],
                )
            )

        for o in MOCK_NORMALIZED_ORDERS:
            db.merge(
                Order(
                    id=o.order_id,
                    shipper_name=o.shipper_name,
                    pickup=o.pickup,
                    dropoff=o.dropoff,
                    pickup_start=o.pickup_start,
                    pickup_end=o.pickup_end,
                    cargo_type=o.cargo_type,
                    pallet_count=o.pallet_count,
                    loading_type=o.loading_type.value,
                    price=o.price,
                )
            )

        risk_result = asyncio.run(
            risk_predictor.run_risk_predictor(
                MOCK_NORMALIZED_ORDERS, MOCK_TRADE_HISTORY
            )
        )
        for r in risk_result.order_risks:
            db.merge(
                OrderRiskAssessment(
                    order_id=r.order_id,
                    cancel_probability=r.cancel_probability,
                    delay_probability=r.delay_probability,
                    success_probability=r.success_probability,
                    is_auto_excluded=r.is_auto_excluded,
                    backup_order_id=r.backup_order_id,
                )
            )

        registration = DailyRegistration(
            driver_id=DRIVER_ID,
            date=datetime.now(UTC),
            constraints_json=DRIVER_CONSTRAINTS.model_dump(),
            status="registered",
        )
        db.add(registration)
        db.flush()

        packages, _, _ = builder.build_packages(
            MOCK_NORMALIZED_ORDERS, DRIVER_CONSTRAINTS
        )
        excluded_ids = {
            r.order_id for r in risk_result.order_risks if r.is_auto_excluded
        }
        valid_packages = [p for p in packages if not (excluded_ids & set(p.order_ids))]
        appraisal = asyncio.run(
            appraiser.run_appraiser(
                valid_packages, DRIVER_COST_PROFILE, risk_result.order_risks
            )
        )
        adjusted_by_id = {
            ap.package.package_id: ap.adjusted_profit
            for ap in appraisal.ranked_packages
        }

        confirmed_package = None
        for p in packages:
            db.merge(
                PackageRecord(
                    id=p.package_id,
                    registration_id=registration.id,
                    label=p.label,
                    nominal_profit=p.nominal_profit,
                    adjusted_profit=adjusted_by_id.get(p.package_id),
                    empty_km=p.empty_km,
                    return_time=p.return_time,
                    blocks_json=[b.model_dump() for b in p.blocks],
                    hard_violations_json=p.hard_violations,
                    is_confirmed=(p.package_id == appraisal.recommended_package_id),
                )
            )
            for order_id in p.order_ids:
                db.merge(PackageOrder(package_id=p.package_id, order_id=order_id))
            if p.package_id == appraisal.recommended_package_id:
                confirmed_package = p

        if confirmed_package:
            from app.agents.rebuilder import rebuild

            split_idx = next(
                (
                    i
                    for i, b in enumerate(confirmed_package.blocks)
                    if b.order_id == "order_gimhae"
                ),
                len(confirmed_package.blocks),
            )
            completed = confirmed_package.blocks[:split_idx]
            remaining = confirmed_package.blocks[split_idx:]
            event = MockEvent(
                event_type=EventType.DELAY,
                order_id="order_gimhae",
                delay_min=40,
                detail="김해 상차 40분 지연",
            )
            request = RebuildRequest(
                driver_id=DRIVER_ID,
                current_location=(
                    completed[-1].location
                    if completed
                    else confirmed_package.blocks[0].location
                ),
                completed_blocks=completed,
                remaining_blocks=remaining,
                event=event,
                backup_order_ids=list(risk_result.backup_pairs.values()),
            )
            result = asyncio.run(
                rebuild(request, DRIVER_CONSTRAINTS, confirmed_package)
            )
            db.add(
                RebuildEvent(
                    package_id=confirmed_package.package_id,
                    event_type=event.event_type.value,
                    order_id=event.order_id,
                    delay_min=event.delay_min,
                    detail=event.detail,
                    profit_diff=result.diff.profit_diff if result.diff else None,
                    return_diff_min=(
                        result.diff.return_time_diff_min if result.diff else None
                    ),
                    applied=True,
                )
            )

        db.commit()
        print("시드 완료.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
