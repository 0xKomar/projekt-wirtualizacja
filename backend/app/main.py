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

    return application


app = create_app()
