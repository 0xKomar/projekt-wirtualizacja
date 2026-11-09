import hashlib
import hmac
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import ApiSettings, Settings
from app.database import check_database, create_database_engine


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


@dataclass
class StoredDevice:
    id: int
    name: str
    location_id: int
    key_hash: str
    last_seen_at: datetime | None = None
    last_reading: ReadingResponse | None = None


def create_app(
    *, engine: Engine | None = None, api_settings: ApiSettings | None = None
) -> FastAPI:
    api_settings = api_settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.engine = (
            engine if engine is not None else create_database_engine(Settings())
        )
        try:
            yield
        finally:
            application.state.engine.dispose()

    application = FastAPI(title="IoT Noise Monitoring API", lifespan=lifespan)
    application.state.locations = {}
    application.state.devices = {}
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
        payload: LocationCreate, request: Request
    ) -> LocationResponse:
        location_id = max(request.app.state.locations, default=0) + 1
        location = LocationResponse(id=location_id, **payload.model_dump())
        request.app.state.locations[location_id] = location
        return location

    def device_response(request: Request, device: StoredDevice) -> DeviceResponse:
        last_seen_at = device.last_seen_at
        online = (
            last_seen_at is not None
            and (datetime.now(timezone.utc) - last_seen_at).total_seconds()
            <= request.app.state.device_offline_after_seconds
        )
        return DeviceResponse(
            id=device.id,
            name=device.name,
            location=request.app.state.locations[device.location_id],
            online=online,
            last_seen_at=last_seen_at,
            last_reading=device.last_reading,
        )

    @application.get("/api/devices", response_model=list[DeviceResponse])
    def list_devices(request: Request) -> list[DeviceResponse]:
        return [
            device_response(request, device)
            for device in request.app.state.devices.values()
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
        device_id: Annotated[int, Path(gt=0)], request: Request
    ) -> DeviceResponse:
        device = request.app.state.devices.get(device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return device_response(request, device)

    @application.post(
        "/api/devices",
        status_code=201,
        response_model=DeviceCreated,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request data"},
            404: {"model": ErrorResponse, "description": "Location not found"},
        },
    )
    def create_device(payload: DeviceCreate, request: Request) -> DeviceCreated:
        if payload.location_id not in request.app.state.locations:
            raise HTTPException(status_code=404, detail="Location not found")
        device_id = max(request.app.state.devices, default=0) + 1
        key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        device = StoredDevice(
            id=device_id,
            name=payload.name,
            location_id=payload.location_id,
            key_hash=key_hash,
        )
        request.app.state.devices[device_id] = device
        return DeviceCreated(
            id=device_id,
            name=payload.name,
            location_id=payload.location_id,
            key=key,
        )

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
        device_key: str = Header(..., alias="X-Device-Key"),
    ) -> ReadingResponse:
        if not device_key:
            raise HTTPException(
                status_code=401, detail="Invalid or missing device key"
            )
        candidate_hash = hashlib.sha256(device_key.encode("utf-8")).hexdigest()
        device = next(
            (
                stored
                for stored in request.app.state.devices.values()
                if hmac.compare_digest(candidate_hash, stored.key_hash)
            ),
            None,
        )
        if device is None:
            raise HTTPException(
                status_code=401, detail="Invalid or missing device key"
            )

        received_at = datetime.now(timezone.utc)
        measured_at = payload.measured_at or received_at
        if measured_at > received_at + timedelta(minutes=5):
            raise HTTPException(status_code=400, detail="Invalid request data")

        reading = ReadingResponse(
            measured_at=measured_at,
            db_avg=payload.db_avg,
            db_min=payload.db_min,
            db_max=payload.db_max,
        )
        device.last_seen_at = received_at
        device.last_reading = reading
        return reading

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
