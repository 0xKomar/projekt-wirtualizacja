from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import create_app


def test_device_and_readings_persist_across_application_restart(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'persistent-api.db'}")
    monkeypatch.setattr("app.main.Settings", lambda: None)
    monkeypatch.setattr("app.main.create_database_engine", lambda _settings: engine)
    location_payload = {
        "name": "Stary Rynek",
        "lat": 52.4083,
        "lon": 16.9335,
    }
    first_reading = {"db_avg": 54.2, "db_min": 48.1, "db_max": 71.9}

    with TestClient(create_app()) as client:
        location = client.post("/api/locations", json=location_payload)
        assert location.status_code == 201
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location.json()["id"]},
        )
        assert device.status_code == 201
        created_reading = client.post(
            "/api/readings",
            json=first_reading,
            headers={"X-Device-Key": device.json()["key"]},
        )
        assert created_reading.status_code == 201

    with TestClient(create_app()) as client:
        devices = client.get("/api/devices")
        assert devices.status_code == 200
        assert len(devices.json()) == 1
        assert devices.json()[0]["name"] == "sensor-1"
        assert devices.json()[0]["location"] == {
            "id": location.json()["id"],
            **location_payload,
        }
        assert devices.json()[0]["last_reading"] == created_reading.json()
        assert devices.json()[0]["last_seen_at"] is not None

        second_reading = {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "db_avg": 55.0,
            "db_min": 49.0,
            "db_max": 72.0,
        }
        accepted_after_restart = client.post(
            "/api/readings",
            json=second_reading,
            headers={"X-Device-Key": device.json()["key"]},
        )
        assert accepted_after_restart.status_code == 201

    with engine.connect() as connection:
        reading_count = connection.execute(
            text("SELECT COUNT(*) FROM readings")
        ).scalar_one()
    engine.dispose()

    assert reading_count == 2
