"""SQLAlchemy 모델."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String)
    vehicle_capacity_pallets: Mapped[int] = mapped_column(Integer, default=20)
    cost_per_km: Mapped[int] = mapped_column(Integer)
    value_per_hour: Mapped[int] = mapped_column(Integer)
    min_fare_per_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fixed_pickup: Mapped[str] = mapped_column(String)
    fixed_pickup_time: Mapped[str] = mapped_column(String)
    fixed_dropoff: Mapped[str] = mapped_column(String)
    fixed_dropoff_time: Mapped[str] = mapped_column(String)
    return_location: Mapped[str] = mapped_column(String)
    return_deadline: Mapped[str] = mapped_column(String)


class Shipper(Base):
    __tablename__ = "shippers"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    cancel_count: Mapped[int] = mapped_column(Integer, default=0)
    delay_count: Mapped[int] = mapped_column(Integer, default=0)
    time_risk: Mapped[float] = mapped_column(Float, default=0.0)


class FieldWaitData(Base):
    __tablename__ = "field_wait_data"

    location: Mapped[str] = mapped_column(String, primary_key=True)
    avg_wait_min: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shipper_name: Mapped[str | None] = mapped_column(
        ForeignKey("shippers.name"), nullable=True
    )
    pickup: Mapped[str] = mapped_column(String)
    dropoff: Mapped[str] = mapped_column(String)
    pickup_start: Mapped[str] = mapped_column(String)
    pickup_end: Mapped[str] = mapped_column(String)
    cargo_type: Mapped[str] = mapped_column(String)
    pallet_count: Mapped[int] = mapped_column(Integer)
    loading_type: Mapped[str] = mapped_column(String)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OrderRiskAssessment(Base):
    __tablename__ = "order_risk_assessments"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), primary_key=True)
    cancel_probability: Mapped[float] = mapped_column(Float)
    delay_probability: Mapped[float] = mapped_column(Float)
    success_probability: Mapped[float] = mapped_column(Float)
    is_auto_excluded: Mapped[bool] = mapped_column(default=False)
    backup_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True
    )


class DailyRegistration(Base):
    __tablename__ = "daily_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    date: Mapped[datetime] = mapped_column(DateTime)
    constraints_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="registered")


class PackageRecord(Base):
    __tablename__ = "packages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("daily_registrations.id"))
    label: Mapped[str] = mapped_column(String)
    nominal_profit: Mapped[int] = mapped_column(Integer)
    adjusted_profit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    empty_km: Mapped[float] = mapped_column(Float)
    return_time: Mapped[str] = mapped_column(String)
    blocks_json: Mapped[dict] = mapped_column(JSON)
    hard_violations_json: Mapped[dict] = mapped_column(JSON, default=list)
    is_confirmed: Mapped[bool] = mapped_column(default=False)


class PackageOrder(Base):
    __tablename__ = "package_orders"

    package_id: Mapped[str] = mapped_column(ForeignKey("packages.id"), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), primary_key=True)


class RebuildEvent(Base):
    __tablename__ = "rebuild_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[str] = mapped_column(ForeignKey("packages.id"))
    event_type: Mapped[str] = mapped_column(String)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    delay_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    profit_diff: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_diff_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
