from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import check_database, create_database_engine


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["ok", "unreachable"]


def create_app(*, engine: Engine | None = None) -> FastAPI:
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

    @application.get(
        "/api/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
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

    @application.get("/api/devices", status_code=501)
    def list_devices() -> Response:
        return Response(status_code=501)

    @application.get("/api/devices/{device_id}", status_code=501)
    def get_device(device_id: str) -> Response:
        return Response(status_code=501)

    @application.post("/api/devices", status_code=501)
    def create_device() -> Response:
        return Response(status_code=501)

    @application.put("/api/devices/{device_id}", status_code=501)
    def update_device(device_id: str) -> Response:
        return Response(status_code=501)

    return application


app = create_app()
