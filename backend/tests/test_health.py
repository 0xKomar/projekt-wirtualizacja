from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.main import create_app


def test_health_executes_database_query(engine):
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with TestClient(create_app(engine=engine)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert statements == ["SELECT 1"]


def test_health_returns_503_when_connection_fails(engine, monkeypatch):
    def unavailable():
        raise OperationalError("connect", {}, OSError("connection refused"))

    monkeypatch.setattr(engine, "connect", unavailable)
    with TestClient(create_app(engine=engine)) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unreachable"}
    assert response.headers["cache-control"] == "no-store"


def test_health_returns_503_when_query_fails(engine):
    @event.listens_for(engine, "before_cursor_execute")
    def fail_query(connection, cursor, statement, parameters, context, executemany):
        raise OperationalError(statement, parameters, OSError("query failed"))

    with TestClient(create_app(engine=engine)) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unreachable"}


def test_health_recovers_without_restarting_application(engine, monkeypatch):
    connect = engine.connect

    def unavailable():
        raise OperationalError("connect", {}, OSError("connection refused"))

    with TestClient(create_app(engine=engine)) as client:
        monkeypatch.setattr(engine, "connect", unavailable)
        assert client.get("/api/health").status_code == 503

        monkeypatch.setattr(engine, "connect", connect)
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
