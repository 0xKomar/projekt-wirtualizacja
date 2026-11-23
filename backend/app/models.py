from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90", name="ck_locations_lat_range"),
        CheckConstraint("lon >= -180 AND lon <= 180", name="ck_locations_lon_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)

    devices: Mapped[list["Device"]] = relationship(back_populates="location")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    location: Mapped[Location] = relationship(back_populates="devices")
    readings: Mapped[list["Reading"]] = relationship(back_populates="device")


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        CheckConstraint(
            "db_min >= 0 AND db_min <= db_avg AND db_avg <= db_max AND db_max <= 150",
            name="ck_readings_level_range_and_order",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), nullable=False, index=True
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    db_avg: Mapped[float] = mapped_column(Float, nullable=False)
    db_min: Mapped[float] = mapped_column(Float, nullable=False)
    db_max: Mapped[float] = mapped_column(Float, nullable=False)

    device: Mapped[Device] = relationship(back_populates="readings")
