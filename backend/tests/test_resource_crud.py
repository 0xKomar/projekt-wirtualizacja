import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Device, Location


def test_locations_can_be_listed_in_id_order(engine):
    with TestClient(create_app(engine=engine)) as client:
        first = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        second = client.post(
            "/api/locations",
            json={"name": "Malta", "lat": 52.4095, "lon": 16.9643},
        ).json()
        response = client.get("/api/locations")

    assert response.status_code == 200
    assert response.json() == [first, second]


def test_location_detail_returns_existing_location(engine):
    with TestClient(create_app(engine=engine)) as client:
        created = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        response = client.get(f"/api/locations/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_location_can_be_updated(engine):
    with TestClient(create_app(engine=engine)) as client:
        created = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        response = client.put(
            f"/api/locations/{created['id']}",
            json={"name": "Malta", "lat": 52.4095, "lon": 16.9643},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "name": "Malta",
        "lat": 52.4095,
        "lon": 16.9643,
    }


def test_unused_location_can_be_deleted(engine):
    with TestClient(create_app(engine=engine)) as client:
        created = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        response = client.delete(f"/api/locations/{created['id']}")
        missing = client.get(f"/api/locations/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert missing.status_code == 404


def test_location_with_devices_cannot_be_deleted(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location["id"]},
        )
        response = client.delete(f"/api/locations/{location['id']}")
        retained = client.get(f"/api/locations/{location['id']}")

    assert response.status_code == 409
    assert response.json() == {"detail": "Location has devices"}
    assert retained.status_code == 200


def test_device_can_be_updated_without_rotating_or_leaking_key(engine):
    with TestClient(create_app(engine=engine)) as client:
        old_location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        new_location = client.post(
            "/api/locations",
            json={"name": "Malta", "lat": 52.4095, "lon": 16.9643},
        ).json()
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": old_location["id"]},
        ).json()
        reading_before_update = client.post(
            "/api/readings",
            json={
                "measured_at": "2026-11-20T10:00:00Z",
                "db_avg": 54,
                "db_min": 48,
                "db_max": 72,
            },
            headers={"X-Device-Key": device["key"]},
        )
        response = client.put(
            f"/api/devices/{device['id']}",
            json={"name": "sensor-2", "location_id": new_location["id"]},
        )
        reading_after_update = client.post(
            "/api/readings",
            json={
                "measured_at": "2026-11-20T10:01:00Z",
                "db_avg": 56,
                "db_min": 49,
                "db_max": 73,
            },
            headers={"X-Device-Key": device["key"]},
        )
        history = client.get(f"/api/devices/{device['id']}/readings")

    assert response.status_code == 200
    assert response.json()["name"] == "sensor-2"
    assert response.json()["location"] == new_location
    assert "key" not in response.json()
    assert reading_before_update.status_code == 201
    assert reading_after_update.status_code == 201
    assert [reading["db_avg"] for reading in history.json()] == [56.0, 54.0]


def test_unused_device_can_be_deleted(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location["id"]},
        ).json()
        response = client.delete(f"/api/devices/{device['id']}")
        missing = client.get(f"/api/devices/{device['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert missing.status_code == 404


def test_device_with_readings_cannot_be_deleted(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location["id"]},
        ).json()
        reading = client.post(
            "/api/readings",
            json={"db_avg": 54, "db_min": 48, "db_max": 72},
            headers={"X-Device-Key": device["key"]},
        )
        response = client.delete(f"/api/devices/{device['id']}")
        retained_history = client.get(f"/api/devices/{device['id']}/readings")

    assert reading.status_code == 201
    assert response.status_code == 409
    assert response.json() == {"detail": "Device has dependent records"}
    assert len(retained_history.json()) == 1


def test_location_update_rejects_invalid_coordinates(engine):
    with TestClient(create_app(engine=engine)) as client:
        created = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        response = client.put(
            f"/api/locations/{created['id']}",
            json={"name": "Malta", "lat": 100, "lon": 16.9643},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_location_update_returns_404_for_missing_location(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.put(
            "/api/locations/999",
            json={"name": "Malta", "lat": 52.4095, "lon": 16.9643},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}


def test_device_update_returns_404_for_missing_location(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location["id"]},
        ).json()
        response = client.put(
            f"/api/devices/{device['id']}",
            json={"name": "sensor-1", "location_id": 999},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}


def test_location_delete_returns_404_for_missing_location(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.delete("/api/locations/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}


def test_device_update_returns_404_for_missing_device(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        response = client.put(
            "/api/devices/999",
            json={"name": "sensor-1", "location_id": location["id"]},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Device not found"}


def test_device_delete_returns_404_for_missing_device(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.delete("/api/devices/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Device not found"}


def test_location_and_device_crud_errors_are_documented(engine):
    with TestClient(create_app(engine=engine)) as client:
        schema = client.get("/openapi.json").json()

    expected = {
        ("/api/locations/{location_id}", "get"): {"400", "404"},
        ("/api/locations/{location_id}", "put"): {"400", "404"},
        ("/api/locations/{location_id}", "delete"): {"204", "400", "404", "409"},
        ("/api/devices/{device_id}", "put"): {"400", "404"},
        ("/api/devices/{device_id}", "delete"): {"204", "400", "404", "409"},
    }
    for (path, method), expected_codes in expected.items():
        responses = schema["paths"][path][method]["responses"]
        assert expected_codes <= set(responses)
        assert "422" not in responses
        for code in expected_codes - {"204"}:
            assert "ErrorResponse" in str(responses[code])


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/locations/not-an-id", None),
        ("get", "/api/locations/0", None),
        ("put", "/api/devices/not-an-id", {"name": "sensor-1", "location_id": 1}),
        ("delete", "/api/devices/0", None),
    ],
)
def test_resource_routes_reject_malformed_or_nonpositive_ids(
    engine, method, path, payload
):
    with TestClient(create_app(engine=engine)) as client:
        request = getattr(client, method)
        response = request(path) if payload is None else request(path, json=payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_device_update_rejects_invalid_fields(engine):
    with TestClient(create_app(engine=engine)) as client:
        location = client.post(
            "/api/locations",
            json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
        ).json()
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": location["id"]},
        ).json()
        response = client.put(
            f"/api/devices/{device['id']}",
            json={"name": " ", "location_id": location["id"]},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_delete_integrity_races_return_409_and_preserve_resources(engine):
    with TestClient(
        create_app(engine=engine), raise_server_exceptions=False
    ) as client:
        unused_location = client.post(
            "/api/locations",
            json={"name": "Cytadela", "lat": 52.4083, "lon": 16.9335},
        ).json()
        used_location = client.post(
            "/api/locations",
            json={"name": "Malta", "lat": 52.4095, "lon": 16.9643},
        ).json()
        device = client.post(
            "/api/devices",
            json={"name": "sensor-1", "location_id": used_location["id"]},
        ).json()

        def fail_dependent_delete(session, _flush_context, _instances):
            if any(isinstance(row, (Device, Location)) for row in session.deleted):
                raise IntegrityError(
                    "DELETE statement", {}, RuntimeError("concurrent reference")
                )

        event.listen(Session, "before_flush", fail_dependent_delete)
        try:
            location_delete = client.delete(
                f"/api/locations/{unused_location['id']}"
            )
            device_delete = client.delete(f"/api/devices/{device['id']}")
        finally:
            event.remove(Session, "before_flush", fail_dependent_delete)

        retained_location = client.get(f"/api/locations/{unused_location['id']}")
        retained_device = client.get(f"/api/devices/{device['id']}")

    assert location_delete.status_code == 409
    assert location_delete.json() == {"detail": "Location has devices"}
    assert device_delete.status_code == 409
    assert device_delete.json() == {"detail": "Device has dependent records"}
    assert retained_location.status_code == 200
    assert retained_device.status_code == 200
