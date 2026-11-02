from sqlalchemy import Engine, create_engine, text

from app.config import Settings


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


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
