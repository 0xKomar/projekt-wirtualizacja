from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def create_device(client: TestClient) -> dict[str, Any]:
    location = client.post(
        "/api/locations",
        json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
    ).json()
    return client.post(
        "/api/devices",
        json={"name": "sensor-1", "location_id": location["id"]},
    ).json()


def test_health_alias_matches_api_health(engine):
    with TestClient(create_app(engine=engine)) as client:
        api_response = client.get("/api/health")
        alias_response = client.get("/health")

    assert alias_response.status_code == api_response.status_code == 200
    assert alias_response.json() == api_response.json()
    assert alias_response.headers["cache-control"] == "no-store"


def test_create_location_returns_contract_shape(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "name": "Stary Rynek",
        "lat": 52.4083,
        "lon": 16.9335,
    }


def test_invalid_location_body_returns_contract_400(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.post(
            "/api/locations",
            json={"name": " ", "lat": 100, "lon": 200},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_device_routes_return_created_and_missing_resources(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        created = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location["id"]},
        )
        devices = client.get("/api/devices")
        device = client.get("/api/devices/1")
        missing = client.get("/api/devices/999")
        invalid_id = client.get("/api/devices/0")
        unknown_location = client.post(
            "/api/devices", json={"name": "orphan", "location_id": 999}
        )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["id"] == 1
    assert created_body["name"] == "sensor-1"
    assert created_body["location_id"] == location["id"]
    assert isinstance(created_body["key"], str) and len(created_body["key"]) >= 32
    assert devices.status_code == 200
    assert devices.json() == [
        {
            "id": 1,
            "name": "sensor-1",
            "location": location,
            "online": False,
            "last_seen_at": None,
            "last_reading": None,
        }
    ]
    assert "key" not in devices.json()[0]
    assert device.status_code == 200
    assert device.json() == devices.json()[0]
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Device not found"}
    assert invalid_id.status_code == 400
    assert invalid_id.json() == {"detail": "Invalid request data"}
    assert unknown_location.status_code == 404
    assert unknown_location.json() == {"detail": "Location not found"}


def test_invalid_device_body_returns_contract_400(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.post("/api/devices", json={"name": "sensor-1"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_reading_requires_key_and_updates_device_status(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        payload = {
            "measured_at": "2026-11-09T16:00:00+02:00",
            "db_avg": 54.2,
            "db_min": 48.1,
            "db_max": 71.9,
        }
        missing_key = client.post("/api/readings", json=payload)
        invalid_key = client.post(
            "/api/readings", json=payload, headers={"X-Device-Key": "wrong"}
        )
        created = client.post(
            "/api/readings",
            json=payload,
            headers={"X-Device-Key": device["key"]},
        )
        devices = client.get("/api/devices").json()

    assert missing_key.status_code == 401
    assert missing_key.json() == {"detail": "Invalid or missing device key"}
    assert invalid_key.status_code == 401
    assert invalid_key.json() == {"detail": "Invalid or missing device key"}
    assert created.status_code == 201
    reading = created.json()
    measured_at = datetime.fromisoformat(reading["measured_at"].replace("Z", "+00:00"))
    assert measured_at == datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)
    assert {key: reading[key] for key in ("db_avg", "db_min", "db_max")} == {
        "db_avg": 54.2,
        "db_min": 48.1,
        "db_max": 71.9,
    }
    assert devices[0]["online"] is True
    assert devices[0]["last_seen_at"] is not None
    assert devices[0]["last_reading"] == reading


@pytest.mark.parametrize(
    "payload",
    [
        {"db_avg": 151, "db_min": 48, "db_max": 152},
        {"db_avg": 50, "db_min": 51, "db_max": 60},
        {
            "measured_at": "2026-11-09T16:00:00",
            "db_avg": 54,
            "db_min": 48,
            "db_max": 72,
        },
        {
            "measured_at": "future",
            "db_avg": 54,
            "db_min": 48,
            "db_max": 72,
        },
    ],
)
def test_invalid_reading_returns_contract_400(engine, payload):
    payload = dict(payload)
    if payload.get("measured_at") == "future":
        payload["measured_at"] = (
            datetime.now(timezone.utc) + timedelta(minutes=6)
        ).isoformat()
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        response = client.post(
            "/api/readings",
            json=payload,
            headers={"X-Device-Key": device["key"]},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_device_offline_threshold_is_configurable(engine, monkeypatch):
    monkeypatch.setenv("DEVICE_OFFLINE_AFTER_SECONDS", "90")
    app = create_app(engine=engine)
    with TestClient(app) as client:
        device = create_device(client)
        response = client.post(
            "/api/readings",
            json={"db_avg": 54, "db_min": 48, "db_max": 72},
            headers={"X-Device-Key": device["key"]},
        )
        assert response.status_code == 201
        app.state.devices[1].last_seen_at = datetime.now(timezone.utc) - timedelta(
            seconds=75
        )
        device_response = client.get("/api/devices/1")

    assert device_response.json()["online"] is True


def test_invalid_offline_threshold_fails_configuration(engine, monkeypatch):
    monkeypatch.setenv("DEVICE_OFFLINE_AFTER_SECONDS", "0")

    with pytest.raises(ValueError):
        create_app(engine=engine)


def test_openapi_documents_contract_errors_as_400_not_422(engine):
    with TestClient(create_app(engine=engine)) as client:
        schema = client.get("/openapi.json").json()

    for path, method in (
        ("/api/locations", "post"),
        ("/api/devices", "post"),
        ("/api/devices/{device_id}", "get"),
        ("/api/readings", "post"),
    ):
        responses = schema["paths"][path][method]["responses"]
        assert "400" in responses
        assert "422" not in responses
        assert "ErrorResponse" in str(responses["400"])

    reading_parameters = schema["paths"]["/api/readings"]["post"]["parameters"]
    device_key_header = next(
        parameter
        for parameter in reading_parameters
        if parameter["name"].lower() == "x-device-key"
    )
    assert device_key_header["required"] is True


def test_reading_without_measured_at_uses_receipt_time(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        before = datetime.now(timezone.utc)
        response = client.post(
            "/api/readings",
            json={"db_avg": 54, "db_min": 48, "db_max": 72},
            headers={"X-Device-Key": device["key"]},
        )
        after = datetime.now(timezone.utc)

    assert response.status_code == 201
    measured_at = datetime.fromisoformat(
        response.json()["measured_at"].replace("Z", "+00:00")
    )
    assert before <= measured_at <= after


@pytest.mark.parametrize("field", ["db_avg", "db_min", "db_max"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_reading_is_rejected_without_mutating_device(
    engine, field, value
):
    app = create_app(engine=engine)
    with TestClient(app) as client:
        device = create_device(client)
        valid = client.post(
            "/api/readings",
            json={"db_avg": 54, "db_min": 48, "db_max": 72},
            headers={"X-Device-Key": device["key"]},
        )
        assert valid.status_code == 201
        stored = app.state.devices[1]
        last_seen_before = stored.last_seen_at
        last_reading_before = stored.last_reading
        payload = {"db_avg": "54", "db_min": "48", "db_max": "72"}
        payload[field] = value
        raw_body = (
            f'{{"db_avg":{payload["db_avg"]},'
            f'"db_min":{payload["db_min"]},'
            f'"db_max":{payload["db_max"]}}}'
        )
        response = client.post(
            "/api/readings",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Device-Key": device["key"],
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}
    assert stored.last_seen_at == last_seen_before
    assert stored.last_reading == last_reading_before
