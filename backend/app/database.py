from collections.abc import Iterator
from typing import Annotated, TypeAlias

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import Settings


class Base(DeclarativeBase):
    pass


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_timeout=3,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=3000",
        },
    )


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


DatabaseSession: TypeAlias = Annotated[Session, Depends(get_session)]
