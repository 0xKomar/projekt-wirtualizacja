import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def create_device(client: TestClient) -> dict:
    location = client.post(
        "/api/locations",
        json={"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
    ).json()
    return client.post(
        "/api/devices",
        json={"name": "sensor-1", "location_id": location["id"]},
    ).json()


def test_reading_history_filters_by_time_and_limit(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        for minute, level in ((0, 50), (1, 52), (2, 54)):
            response = client.post(
                "/api/readings",
                json={
                    "measured_at": f"2026-11-20T10:0{minute}:00+00:00",
                    "db_avg": level,
                    "db_min": level - 1,
                    "db_max": level + 1,
                },
                headers={"X-Device-Key": device["key"]},
            )
            assert response.status_code == 201

        response = client.get(
            f"/api/devices/{device['id']}/readings",
            params={
                "from": "2026-11-20T10:01:00+00:00",
                "to": "2026-11-20T10:02:00+00:00",
                "limit": 1,
            },
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "measured_at": "2026-11-20T10:02:00Z",
            "db_avg": 54.0,
            "db_min": 53.0,
            "db_max": 55.0,
        }
    ]


def test_reading_history_rejects_reversed_time_range(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        response = client.get(
            f"/api/devices/{device['id']}/readings",
            params={
                "from": "2026-11-20T10:02:00+00:00",
                "to": "2026-11-20T10:01:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_reading_history_requires_existing_device(engine):
    with TestClient(create_app(engine=engine)) as client:
        response = client.get("/api/devices/999/readings")

    assert response.status_code == 404
    assert response.json() == {"detail": "Device not found"}


def test_reading_history_rejects_nonpositive_limit(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        response = client.get(
            f"/api/devices/{device['id']}/readings", params={"limit": 0}
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_reading_history_openapi_documents_filters_and_errors(engine):
    with TestClient(create_app(engine=engine)) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/devices/{device_id}/readings"]["get"]
    assert "400" in operation["responses"]
    assert "404" in operation["responses"]
    assert "422" not in operation["responses"]
    parameters = {
        parameter["name"]: parameter for parameter in operation["parameters"]
    }
    assert set(parameters) == {"device_id", "from", "to", "limit"}
    assert "UTC offset" in parameters["from"]["description"]
    assert "UTC offset" in parameters["to"]["description"]
    assert parameters["limit"]["schema"]["minimum"] == 1
    assert parameters["limit"]["schema"]["maximum"] == 1000


def test_reading_history_includes_boundaries_and_normalizes_offsets(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        for minute, level in ((0, 50), (1, 52), (2, 54)):
            response = client.post(
                "/api/readings",
                json={
                    "measured_at": f"2026-11-20T10:0{minute}:00Z",
                    "db_avg": level,
                    "db_min": level - 1,
                    "db_max": level + 1,
                },
                headers={"X-Device-Key": device["key"]},
            )
            assert response.status_code == 201

        response = client.get(
            f"/api/devices/{device['id']}/readings",
            params={
                "from": "2026-11-20T12:01:00+02:00",
                "to": "2026-11-20T10:01:00Z",
            },
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "measured_at": "2026-11-20T10:01:00Z",
            "db_avg": 52.0,
            "db_min": 51.0,
            "db_max": 53.0,
        }
    ]


def test_reading_history_orders_equal_timestamps_by_latest_id(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        for level in (52, 54):
            response = client.post(
                "/api/readings",
                json={
                    "measured_at": "2026-11-20T10:01:00Z",
                    "db_avg": level,
                    "db_min": level - 1,
                    "db_max": level + 1,
                },
                headers={"X-Device-Key": device["key"]},
            )
            assert response.status_code == 201

        response = client.get(f"/api/devices/{device['id']}/readings")

    assert response.status_code == 200
    assert [reading["db_avg"] for reading in response.json()] == [54.0, 52.0]


@pytest.mark.parametrize("parameter", ["from", "to"])
def test_reading_history_requires_offset_on_filter_timestamps(engine, parameter):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        response = client.get(
            f"/api/devices/{device['id']}/readings",
            params={parameter: "2026-11-20T10:01:00"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


@pytest.mark.parametrize("parameter", ["from", "to"])
def test_reading_history_rejects_malformed_filter_timestamps(engine, parameter):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        response = client.get(
            f"/api/devices/{device['id']}/readings",
            params={parameter: "not-a-timestamp"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request data"}


def test_reading_history_returns_newest_timestamp_first_without_filters(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        for second in (0, 2, 1):
            level = 50 + second
            response = client.post(
                "/api/readings",
                json={
                    "measured_at": f"2026-11-20T10:00:{second:02d}Z",
                    "db_avg": level,
                    "db_min": level - 1,
                    "db_max": level + 1,
                },
                headers={"X-Device-Key": device["key"]},
            )
            assert response.status_code == 201
        response = client.get(f"/api/devices/{device['id']}/readings")

    assert [reading["measured_at"] for reading in response.json()] == [
        "2026-11-20T10:00:02Z",
        "2026-11-20T10:00:01Z",
        "2026-11-20T10:00:00Z",
    ]


def test_reading_history_defaults_to_100_rows(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        for index in range(101):
            minute, second = divmod(index, 60)
            response = client.post(
                "/api/readings",
                json={
                    "measured_at": f"2026-11-20T10:{minute:02d}:{second:02d}Z",
                    "db_avg": 50,
                    "db_min": 49,
                    "db_max": 51,
                },
                headers={"X-Device-Key": device["key"]},
            )
            assert response.status_code == 201
        response = client.get(f"/api/devices/{device['id']}/readings")

    assert response.status_code == 200
    assert len(response.json()) == 100
    assert response.json()[0]["measured_at"] == "2026-11-20T10:01:40Z"
    assert response.json()[-1]["measured_at"] == "2026-11-20T10:00:01Z"


@pytest.mark.parametrize(("limit", "expected_status"), [(1000, 200), (1001, 400)])
def test_reading_history_limit_upper_bound(engine, limit, expected_status):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        response = client.get(
            f"/api/devices/{device['id']}/readings", params={"limit": limit}
        )

    assert response.status_code == expected_status
