import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import ApiSettings, Settings
from app.database import (
    DatabaseSession,
    check_database,
    create_database_engine,
    create_schema,
)
from app.models import Device, Location, Reading


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["ok", "unreachable"]


class ErrorResponse(BaseModel):
    detail: str


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class LocationUpdate(LocationCreate):
    pass


class LocationResponse(BaseModel):
    id: int
    name: str
    lat: float
    lon: float


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class DeviceUpdate(DeviceCreate):
    pass


class DeviceCreated(BaseModel):
    id: int
    name: str
    location_id: int
    key: str


class ReadingResponse(BaseModel):
    measured_at: datetime
    db_avg: float
    db_min: float
    db_max: float


class DeviceResponse(BaseModel):
    id: int
    name: str
    location: LocationResponse
    online: bool
    last_seen_at: datetime | None
    last_reading: ReadingResponse | None


class ReadingCreate(BaseModel):
    measured_at: datetime | None = None
    db_avg: float = Field(ge=0, le=150)
    db_min: float = Field(ge=0, le=150)
    db_max: float = Field(ge=0, le=150)

    @field_validator("measured_at")
    @classmethod
    def measured_at_must_include_offset(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at must include a UTC offset")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def levels_must_be_ordered(self) -> "ReadingCreate":
        if not self.db_min <= self.db_avg <= self.db_max:
            raise ValueError("db_min must be <= db_avg <= db_max")
        return self


def create_app(
    *, engine: Engine | None = None, api_settings: ApiSettings | None = None
) -> FastAPI:
    api_settings = api_settings or ApiSettings()
    initialize_schema = engine is None

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.engine = (
            engine if engine is not None else create_database_engine(Settings())
        )
        try:
            if initialize_schema:
                create_schema(application.state.engine)
            yield
        finally:
            application.state.engine.dispose()

    application = FastAPI(title="IoT Noise Monitoring API", lifespan=lifespan)
    application.state.device_offline_after_seconds = (
        api_settings.device_offline_after_seconds
    )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        missing_device_key = any(
            error.get("type") == "missing"
            and len(error.get("loc", ())) >= 2
            and str(error["loc"][0]).casefold() == "header"
            and str(error["loc"][-1]).casefold() == "x-device-key"
            for error in exception.errors()
        )
        if missing_device_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing device key"},
            )
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid request data"},
        )

    @application.get(
        "/health",
        response_model=HealthResponse,
        include_in_schema=False,
        responses={
            503: {"model": HealthResponse, "description": "Database unavailable"}
        },
    )
    @application.get(
        "/api/health",
        response_model=HealthResponse,
        responses={
            503: {"model": HealthResponse, "description": "Database unavailable"}
        },
    )
    def health(request: Request, response: Response) -> HealthResponse | JSONResponse:
        try:
            check_database(request.app.state.engine)
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "database": "unreachable"},
                headers={"Cache-Control": "no-store"},
            )
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(status="ok", database="ok")

    @application.post(
        "/api/locations",
        status_code=201,
        response_model=LocationResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"}
        },
    )
    def create_location(
        payload: LocationCreate, session: DatabaseSession
    ) -> LocationResponse:
        location = Location(**payload.model_dump())
        session.add(location)
        session.flush()
        return LocationResponse(
            id=location.id,
            name=location.name,
            lat=location.lat,
            lon=location.lon,
        )

    @application.get("/api/locations", response_model=list[LocationResponse])
    def list_locations(session: DatabaseSession) -> list[LocationResponse]:
        locations = session.scalars(select(Location).order_by(Location.id)).all()
        return [
            LocationResponse(
                id=location.id,
                name=location.name,
                lat=location.lat,
                lon=location.lon,
            )
            for location in locations
        ]

    @application.get(
        "/api/locations/{location_id}",
        response_model=LocationResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Location not found"},
        },
    )
    def get_location(
        location_id: Annotated[int, Path(gt=0)], session: DatabaseSession
    ) -> LocationResponse:
        location = session.get(Location, location_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        return LocationResponse(
            id=location.id,
            name=location.name,
            lat=location.lat,
            lon=location.lon,
        )

    @application.put(
        "/api/locations/{location_id}",
        response_model=LocationResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Location not found"},
        },
    )
    def update_location(
        location_id: Annotated[int, Path(gt=0)],
        payload: LocationUpdate,
        session: DatabaseSession,
    ) -> LocationResponse:
        location = session.get(Location, location_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        for field, value in payload.model_dump().items():
            setattr(location, field, value)
        session.flush()
        return LocationResponse(
            id=location.id,
            name=location.name,
            lat=location.lat,
            lon=location.lon,
        )

    @application.delete(
        "/api/locations/{location_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Location not found"},
            409: {"model": ErrorResponse, "description": "Location has devices"},
        },
    )
    def delete_location(
        location_id: Annotated[int, Path(gt=0)], session: DatabaseSession
    ) -> Response:
        location = session.get(Location, location_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        has_devices = session.scalar(
            select(Device.id).where(Device.location_id == location_id).limit(1)
        )
        if has_devices is not None:
            raise HTTPException(status_code=409, detail="Location has devices")
        try:
            session.delete(location)
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409, detail="Location has devices"
            ) from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def reading_response(reading: Reading) -> ReadingResponse:
        measured_at = as_utc(reading.measured_at)
        assert measured_at is not None
        return ReadingResponse(
            measured_at=measured_at,
            db_avg=reading.db_avg,
            db_min=reading.db_min,
            db_max=reading.db_max,
        )

    def device_response(
        session: Session, device: Device, offline_after_seconds: int
    ) -> DeviceResponse:
        last_seen_at = as_utc(device.last_seen_at)
        online = (
            last_seen_at is not None
            and (datetime.now(timezone.utc) - last_seen_at).total_seconds()
            <= offline_after_seconds
        )
        last_reading = session.scalar(
            select(Reading)
            .where(Reading.device_id == device.id)
            .order_by(Reading.received_at.desc(), Reading.id.desc())
            .limit(1)
        )
        location = device.location
        return DeviceResponse(
            id=device.id,
            name=device.name,
            location=LocationResponse(
                id=location.id,
                name=location.name,
                lat=location.lat,
                lon=location.lon,
            ),
            online=online,
            last_seen_at=last_seen_at,
            last_reading=(
                reading_response(last_reading) if last_reading is not None else None
            ),
        )

    @application.get("/api/devices", response_model=list[DeviceResponse])
    def list_devices(
        request: Request, session: DatabaseSession
    ) -> list[DeviceResponse]:
        devices = session.scalars(select(Device).order_by(Device.id)).all()
        return [
            device_response(
                session, device, request.app.state.device_offline_after_seconds
            )
            for device in devices
        ]

    @application.get(
        "/api/devices/{device_id}",
        response_model=DeviceResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Device not found"},
        },
    )
    def get_device(
        device_id: Annotated[int, Path(gt=0)],
        request: Request,
        session: DatabaseSession,
    ) -> DeviceResponse:
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return device_response(
            session, device, request.app.state.device_offline_after_seconds
        )

    @application.put(
        "/api/devices/{device_id}",
        response_model=DeviceResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Device or location not found"},
        },
    )
    def update_device(
        device_id: Annotated[int, Path(gt=0)],
        payload: DeviceUpdate,
        request: Request,
        session: DatabaseSession,
    ) -> DeviceResponse:
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        location = session.get(Location, payload.location_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        device.name = payload.name
        device.location = location
        session.flush()
        return device_response(
            session, device, request.app.state.device_offline_after_seconds
        )

    @application.delete(
        "/api/devices/{device_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Device not found"},
            409: {"model": ErrorResponse, "description": "Device has readings"},
        },
    )
    def delete_device(
        device_id: Annotated[int, Path(gt=0)], session: DatabaseSession
    ) -> Response:
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        has_readings = session.scalar(
            select(Reading.id).where(Reading.device_id == device_id).limit(1)
        )
        if has_readings is not None:
            raise HTTPException(status_code=409, detail="Device has readings")
        try:
            session.delete(device)
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409, detail="Device has readings"
            ) from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.post(
        "/api/devices",
        status_code=201,
        response_model=DeviceCreated,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Location not found"},
        },
    )
    def create_device(
        payload: DeviceCreate, session: DatabaseSession
    ) -> DeviceCreated:
        if session.get(Location, payload.location_id) is None:
            raise HTTPException(status_code=404, detail="Location not found")
        key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        device = Device(
            name=payload.name,
            location_id=payload.location_id,
            key_hash=key_hash,
        )
        session.add(device)
        session.flush()
        return DeviceCreated(
            id=device.id,
            name=payload.name,
            location_id=payload.location_id,
            key=key,
        )

    @application.get(
        "/api/devices/{device_id}/readings",
        response_model=list[ReadingResponse],
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Device not found"},
        },
    )
    def list_device_readings(
        device_id: Annotated[int, Path(gt=0)],
        session: DatabaseSession,
        from_time: datetime | None = Query(
            default=None,
            alias="from",
            description="Inclusive ISO 8601 timestamp with a UTC offset.",
        ),
        to_time: datetime | None = Query(
            default=None,
            alias="to",
            description="Inclusive ISO 8601 timestamp with a UTC offset.",
        ),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[ReadingResponse]:
        if session.get(Device, device_id) is None:
            raise HTTPException(status_code=404, detail="Device not found")
        if any(
            value is not None and (value.tzinfo is None or value.utcoffset() is None)
            for value in (from_time, to_time)
        ):
            raise HTTPException(status_code=400, detail="Invalid request data")

        start = as_utc(from_time)
        end = as_utc(to_time)
        if start is not None and end is not None and start > end:
            raise HTTPException(status_code=400, detail="Invalid request data")

        statement = select(Reading).where(Reading.device_id == device_id)
        if start is not None:
            statement = statement.where(Reading.measured_at >= start)
        if end is not None:
            statement = statement.where(Reading.measured_at <= end)
        readings = session.scalars(
            statement.order_by(Reading.measured_at.desc(), Reading.id.desc()).limit(
                limit
            )
        ).all()
        return [reading_response(reading) for reading in readings]

    @application.post(
        "/api/readings",
        status_code=201,
        response_model=ReadingResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            401: {"model": ErrorResponse, "description": "Invalid device key"},
        },
    )
    def create_reading(
        payload: ReadingCreate,
        request: Request,
        session: DatabaseSession,
        device_key: str = Header(..., alias="X-Device-Key"),
    ) -> ReadingResponse:
        if not device_key:
            raise HTTPException(
                status_code=401, detail="Invalid or missing device key"
            )
        candidate_hash = hashlib.sha256(device_key.encode("utf-8")).hexdigest()
        device = session.scalar(
            select(Device).where(Device.key_hash == candidate_hash).limit(1)
        )
        if device is None:
            raise HTTPException(
                status_code=401, detail="Invalid or missing device key"
            )

        received_at = datetime.now(timezone.utc)
        measured_at = payload.measured_at or received_at
        if measured_at > received_at + timedelta(minutes=5):
            raise HTTPException(status_code=400, detail="Invalid request data")

        reading = Reading(
            device_id=device.id,
            measured_at=measured_at,
            received_at=received_at,
            db_avg=payload.db_avg,
            db_min=payload.db_min,
            db_max=payload.db_max,
        )
        device.last_seen_at = received_at
        session.add(reading)
        session.flush()
        return reading_response(reading)

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            routes=application.routes,
        )
        for path_item in schema["paths"].values():
            for operation in path_item.values():
                if isinstance(operation, dict) and "responses" in operation:
                    operation["responses"].pop("422", None)
        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi
    return application


app = create_app()
