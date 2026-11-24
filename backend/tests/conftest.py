import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.database import create_schema
from app.models import Device, Location, Reading


@pytest.fixture
def engine():
    database = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema(database)
    yield database
    database.dispose()
