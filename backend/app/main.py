from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine

from app.config import Settings
from app.database import create_database_engine


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

    return FastAPI(title="IoT Noise Monitoring API", lifespan=lifespan)


app = create_app()
