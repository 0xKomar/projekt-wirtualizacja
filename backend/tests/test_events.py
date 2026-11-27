from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def create_device(client: TestClient) -> dict:
    location = client.post(
        "/api/locations",
        json={"name": "Demo site", "lat": 52.4, "lon": 16.9},
    ).json()
    return client.post(
        "/api/devices",
        json={"name": "ESP demo", "location_id": location["id"]},
    ).json()


def post_reading(client: TestClient, device: dict, measured_at: datetime, avg: float):
    return client.post(
        "/api/readings",
        json={
            "measured_at": measured_at.isoformat(),
            "db_avg": avg,
            "db_min": avg - 2,
            "db_max": avg + 2,
        },
        headers={"X-Device-Key": device["key"]},
    )


def test_late_low_reading_does_not_retract_emitted_threshold_event(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        rule = client.post(
            "/api/alert-rules",
            json={
                "name": "Demo sustained noise",
                "device_id": device["id"],
                "threshold_db": 70,
                "min_duration_seconds": 10,
                "enabled": True,
            },
        )
        assert rule.status_code == 201

        start = datetime.now(timezone.utc) - timedelta(seconds=60)
        first = post_reading(client, device, start, 72)
        qualifying = post_reading(client, device, start + timedelta(seconds=20), 74)
        emitted = client.get(
            "/api/events", params={"device_id": device["id"], "type": "noise_threshold"}
        ).json()
        late_low = post_reading(client, device, start + timedelta(seconds=5), 65)
        after_late_reading = client.get(
            "/api/events", params={"device_id": device["id"], "type": "noise_threshold"}
        ).json()
        readings = client.get(f"/api/devices/{device['id']}/readings").json()

    assert first.status_code == qualifying.status_code == late_low.status_code == 201
    assert len(emitted) == len(after_late_reading) == 1
    assert after_late_reading[0] == emitted[0]
    assert [reading["db_avg"] for reading in readings[:3]] == [74, 65, 72]


def test_sustained_threshold_creates_filterable_acknowledgeable_event(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        rule_response = client.post(
            "/api/alert-rules",
            json={
                "name": "Demo sustained noise",
                "device_id": device["id"],
                "threshold_db": 70,
                "min_duration_seconds": 10,
                "enabled": True,
            },
        )
        assert rule_response.status_code == 201
        rule = rule_response.json()

        start = datetime.now(timezone.utc) - timedelta(seconds=30)
        first = post_reading(client, device, start, 72)
        before_duration = client.get(
            "/api/events", params={"device_id": device["id"], "type": "noise_threshold"}
        )
        second = post_reading(client, device, start + timedelta(seconds=10), 74)
        third = post_reading(client, device, start + timedelta(seconds=20), 74)
        events = client.get(
            "/api/events",
            params={"device_id": device["id"], "type": "noise_threshold"},
        )
        assert events.status_code == 200
        assert len(events.json()) == 1
        event = events.json()[0]
        inclusive = client.get(
            "/api/events",
            params={"device_id": device["id"], "from": event["started_at"],
                    "to": event["started_at"], "type": "noise_threshold"},
        )
        acknowledged = client.patch(
            f"/api/events/{event['id']}", json={"acknowledged": True}
        )
        delete_rule_conflict = client.delete(f"/api/alert-rules/{rule['id']}")
        delete_device_conflict = client.delete(f"/api/devices/{device['id']}")

    assert rule["threshold_db"] == 70
    assert first.status_code == second.status_code == third.status_code == 201
    assert before_duration.status_code == 200 and before_duration.json() == []
    assert events.status_code == 200 and len(events.json()) == 1
    assert event["type"] == "noise_threshold"
    assert event["device_id"] == device["id"]
    assert event["alert_rule_id"] == rule["id"]
    assert event["acknowledged"] is False
    assert inclusive.status_code == 200 and inclusive.json() == [event]
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged"] is True
    assert delete_rule_conflict.status_code == delete_device_conflict.status_code == 409


def test_alert_rule_validation_crud_and_event_filters(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        invalid_rule = client.post(
            "/api/alert-rules",
            json={"name": "bad", "device_id": device["id"], "threshold_db": 151,
                  "min_duration_seconds": 10},
        )
        missing_device = client.post(
            "/api/alert-rules",
            json={"name": "bad", "device_id": 999, "threshold_db": 70,
                  "min_duration_seconds": 10},
        )
        rule = client.post(
            "/api/alert-rules",
            json={"name": "rule", "device_id": device["id"], "threshold_db": 70,
                  "min_duration_seconds": 10},
        ).json()
        listed = client.get("/api/alert-rules")
        updated = client.put(
            f"/api/alert-rules/{rule['id']}",
            json={"name": "updated", "device_id": device["id"],
                  "threshold_db": 75, "min_duration_seconds": 15, "enabled": False},
        )
        bad_type = client.get("/api/events", params={"type": "made_up"})
        bad_range = client.get(
            "/api/events", params={"from": "2026-11-20T12:00:00Z",
                                   "to": "2026-11-20T11:00:00Z"}
        )
        naive_time = client.get("/api/events", params={"from": "2026-11-20T12:00:00"})
        unknown_device = client.get("/api/events", params={"device_id": 999})
        deleted = client.delete(f"/api/alert-rules/{rule['id']}")
        missing_event = client.patch("/api/events/999", json={"acknowledged": True})
        schema = client.get("/openapi.json").json()
        event_responses = schema["paths"]["/api/events"]["get"]["responses"]
        patch_responses = schema["paths"]["/api/events/{event_id}"]["patch"]["responses"]

    assert invalid_rule.status_code == 400
    assert missing_device.status_code == 404
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert updated.status_code == 200 and updated.json()["threshold_db"] == 75
    assert bad_type.status_code == bad_range.status_code == naive_time.status_code == 400
    assert unknown_device.status_code == 404
    assert deleted.status_code == 204
    assert missing_event.status_code == 404
    assert {"400", "404"} <= event_responses.keys()
    assert {"400", "404"} <= patch_responses.keys()
    assert "422" not in event_responses and "422" not in patch_responses


def test_event_dedupe_key_is_enforced_by_database(engine):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.models import Event

    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        started_at = datetime.now(timezone.utc)
        key = f"offline:{device['id']}:{started_at.isoformat()}"
        with Session(engine) as session:
            first = Event(
                device_id=device["id"],
                type="device_offline",
                started_at=started_at,
                description="offline",
                dedupe_key=key,
            )
            session.add(first)
            session.flush()
            session.add(
                Event(
                    device_id=device["id"],
                    type="device_offline",
                    started_at=started_at,
                    description="offline duplicate",
                    dedupe_key=key,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()


def test_persist_event_once_ignores_duplicate_key(engine):
    from sqlalchemy.orm import Session

    from app.events import persist_event_once
    from app.models import Event

    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        started_at = datetime.now(timezone.utc)
        key = f"offline:{device['id']}:{started_at.isoformat()}"
        with Session(engine) as session:
            session.add(
                Event(
                    device_id=device["id"],
                    type="device_offline",
                    started_at=started_at,
                    description="offline",
                    dedupe_key=key,
                )
            )
            session.commit()
        with Session(engine) as session:
            duplicate = Event(
                device_id=device["id"],
                type="device_offline",
                started_at=started_at,
                description="duplicate offline",
                dedupe_key=key,
            )
            assert persist_event_once(session, duplicate) is False
            session.commit()


def test_device_row_lock_query_compiles_to_for_update():
    from sqlalchemy.dialects import postgresql

    from app.events import locked_device_query
    from app.models import Device

    query = locked_device_query(Device.id == 1)
    compiled = str(query.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE" in compiled


def test_alert_rule_row_lock_query_compiles_to_for_update():
    from sqlalchemy.dialects import postgresql

    from app.events import locked_alert_rule_query
    from app.models import AlertRule

    query = locked_alert_rule_query(AlertRule.id == 1)
    compiled = str(query.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE" in compiled


def test_same_timestamp_low_then_high_starts_sustained_run(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        client.post(
            "/api/alert-rules",
            json={"name": "rule", "device_id": device["id"],
                  "threshold_db": 70, "min_duration_seconds": 10},
        )
        start = datetime.now(timezone.utc) - timedelta(seconds=30)
        low = post_reading(client, device, start, 65)
        high_at_same_time = post_reading(client, device, start, 75)
        high_after_duration = post_reading(
            client, device, start + timedelta(seconds=10), 75
        )
        events = client.get("/api/events", params={"type": "noise_threshold"})

    assert low.status_code == high_at_same_time.status_code == 201
    assert high_after_duration.status_code == 201
    assert len(events.json()) == 1
    assert datetime.fromisoformat(events.json()[0]["started_at"]) == start


def test_sustained_noise_restarts_after_long_reading_gap(engine):
    with TestClient(create_app(engine=engine)) as client:
        device = create_device(client)
        client.post(
            "/api/alert-rules",
            json={"name": "rule", "device_id": device["id"],
                  "threshold_db": 70, "min_duration_seconds": 10},
        )
        start = datetime.now(timezone.utc) - timedelta(seconds=120)
        assert post_reading(client, device, start, 75).status_code == 201
        assert post_reading(
            client, device, start + timedelta(seconds=70), 75
        ).status_code == 201
        before_duration = client.get(
            "/api/events", params={"type": "noise_threshold"}
        )
        assert before_duration.status_code == 200
        assert before_duration.json() == []

        final_reading = post_reading(
            client, device, start + timedelta(seconds=80), 75
        )
        events = client.get("/api/events", params={"type": "noise_threshold"})

    assert final_reading.status_code == 201
    assert len(events.json()) == 1
    assert datetime.fromisoformat(events.json()[0]["started_at"]) == start + timedelta(
        seconds=70
    )


def test_offline_monitor_recovers_after_database_error(monkeypatch):
    import asyncio
    from sqlalchemy.exc import SQLAlchemyError

    import app.main as main_module

    calls = 0

    def scan(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SQLAlchemyError("temporary database failure")
        return 0

    monkeypatch.setattr(main_module, "scan_offline_devices", scan)
    application = main_module.FastAPI()
    application.state.event_scan_interval_seconds = 0.001
    application.state.engine = object()
    application.state.device_offline_after_seconds = 60

    async def run_monitor():
        task = asyncio.create_task(main_module.monitor_offline_events(application))
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_monitor())
    assert calls >= 2


def test_offline_monitor_creates_one_event_and_reading_marks_online(engine):
    import time

    from sqlalchemy.orm import Session

    from app.config import ApiSettings
    from app.models import Device

    settings = ApiSettings(
        device_offline_after_seconds=60,
        event_scan_interval_seconds=1,
    )
    with TestClient(create_app(engine=engine, api_settings=settings)) as client:
        device = create_device(client)
        posted = client.post(
            "/api/readings",
            json={"db_avg": 54, "db_min": 48, "db_max": 72},
            headers={"X-Device-Key": device["key"]},
        )
        assert posted.status_code == 201
        with Session(engine) as session:
            stored_device = session.get(Device, device["id"])
            assert stored_device is not None
            stored_device.last_seen_at = datetime.now(timezone.utc) - timedelta(
                seconds=70
            )
            session.commit()
        time.sleep(1.25)
        offline = client.get("/api/events", params={"type": "device_offline"})
        resumed = post_reading(client, device, datetime.now(timezone.utc), 54)
        online = client.get("/api/events", params={"type": "device_online"})

    assert offline.status_code == 200 and len(offline.json()) == 1
    assert resumed.status_code == 201
    assert online.status_code == 200 and len(online.json()) == 1
