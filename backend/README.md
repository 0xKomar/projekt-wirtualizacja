# Backend

FastAPI and SQLAlchemy with PostgreSQL. The API uses the psycopg driver and checks
the database with a real `SELECT 1` query on every health request.

## Start the backend and database

From the repository root, with Docker and Docker Compose installed:

```sh
cp .env.example .env
# Set POSTGRES_PASSWORD in .env before using a shared or deployed environment.
docker compose up --build -d --wait db backend
curl -i http://localhost:8000/api/health
```

The backend's development port is published on loopback only. The database has no
host port. Swagger UI is available at `http://localhost:8000/docs`.

The stack contains `db`, `backend` and `frontend`. The frontend joins only the
`frontend` network; the API joins both networks so it can reach PostgreSQL.

Stop the stack with `docker compose down`. Database files remain in the named
`postgres_data` volume. Existing PostgreSQL volumes retain their original
credentials; changing `.env` does not change the database password automatically.

## Configuration

Compose reads `.env` and passes the relevant variables into each container.
The application does not load a local `.env` file itself.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password; required and never returned by the API |
| `DB_HOST` | Database hostname inside Compose; normally `db` |
| `DB_PORT` | PostgreSQL listening port; normally `5432` |
| `BACKEND_PORT` | API listening and loopback host port; normally `8000` |
| `DEVICE_OFFLINE_AFTER_SECONDS` | Provisional offline threshold for initial demo checks; defaults to `60` seconds |
| `EVENT_SCAN_INTERVAL_SECONDS` | Background offline-event scan interval; defaults to `5` seconds |

If `BACKEND_PORT` changes, update the port in `BACKEND_URL` for the frontend too.
Database connection and statement timeouts are three seconds. The connection
pool checks existing connections before reuse, allowing recovery after a database
restart without restarting the API.

## Health contract

`GET /api/health` and its `/health` alias do not require authentication. Both
responses have `Cache-Control: no-store`.

| HTTP status | JSON body |
| --- | --- |
| `200` | `{"status": "ok", "database": "ok"}` |
| `503` | `{"status": "error", "database": "unreachable"}` |

A database connection or query failure returns 503 without exposing connection
details. At startup, the backend creates any missing model tables after Compose has waited
for the database healthcheck. Health requests then verify connectivity with a real
`SELECT 1` query.

## Device API contract (B1.2)

Locations, devices, key hashes and readings are stored in PostgreSQL through
SQLAlchemy models. The backend creates missing tables on startup; managed schema
migrations are planned for B2.2. Device keys are returned only at registration
and only their SHA-256 hashes are stored. B1.3 CRUD and filtered reading history
are implemented on this branch; deleting a resource with dependents returns 409
instead of deleting its associated records.

### Locations and devices

`POST /api/locations` accepts:

```json
{"name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335}
```

It returns `201` with an assigned `id` and those location fields. Latitude must
be between -90 and 90; longitude between -180 and 180.

`POST /api/devices` accepts `{"name": "Stary Rynek", "location_id": 1}` and
returns `201` with `id`, `name`, `location_id` and a cryptographically random
`key`. For example:

```json
{"id": 1, "name": "Stary Rynek", "location_id": 1, "key": "<returned-once>"}
```

The key is returned only in this creation response; PostgreSQL stores only its
SHA-256 hash. `location_id` must refer to an existing location.

`GET /api/locations` lists locations, and `GET /api/locations/{id}` returns one
or 404. `PUT /api/locations/{id}` replaces its name and coordinates.
`DELETE /api/locations/{id}` returns 204 when unused, or 409 while devices
reference it.

`PUT /api/devices/{id}` replaces the device name and location using the same
fields as device creation. It does not rotate the key, and the key is not returned
again. `DELETE /api/devices/{id}` returns 204 only when unused; otherwise it
returns 409 to preserve measurement history.

### Readings

`POST /api/readings` requires the `X-Device-Key` header and accepts:

```json
{"measured_at": "2026-01-01T12:00:00Z", "db_avg": 54.2, "db_min": 48.1, "db_max": 71.9}
```

`measured_at` is optional; when omitted, the backend uses receipt time. Supplied
timestamps must include an ISO 8601 UTC offset and are normalized to UTC. Past
times are allowed; times more than five minutes in the future are rejected. A
successful request returns `201` with the same four reading fields, including the
normalized `measured_at`. Each level must be in the inclusive 0–150 range and
satisfy `db_min <= db_avg <= db_max`. These are uncalibrated readings, not
calibrated dB SPL values.

### Device listing

`GET /api/devices` returns a list; `GET /api/devices/{id}` returns one device or
404. Each item has this shape:

```json
{
  "id": 1,
  "name": "Stary Rynek",
  "location": {"id": 1, "name": "Stary Rynek", "lat": 52.4083, "lon": 16.9335},
  "online": true,
  "last_seen_at": "2026-01-01T12:00:00Z",
  "last_reading": {"measured_at": "2026-01-01T12:00:00Z", "db_avg": 54.2, "db_min": 48.1, "db_max": 71.9}
}
```

Before the first reading, `online` is false and `last_seen_at` and
`last_reading` are null. `last_seen_at` records receipt time, not the sensor's
`measured_at`. `DEVICE_OFFLINE_AFTER_SECONDS` controls the online threshold; its
initial value is 60 seconds for testing only and will be reviewed after ESP
trials.

### Reading history (B1.3)

`GET /api/devices/{id}/readings?from=...&to=...&limit=...` returns a device's
readings ordered by `measured_at` descending, with newer inserted rows first when
timestamps match. The optional `from` and `to` filters are inclusive ISO 8601
timestamps and must include a UTC offset; they are normalized to UTC. `limit`
defaults to 100 and must be between 1 and 1000. A missing device returns 404;
invalid filters return 400.

## Alert rules and events (B1.5)

`/api/alert-rules` supports `GET`, `POST`, `PUT /{id}`, and `DELETE /{id}`. A
rule accepts `name`, optional `device_id` (null applies to all devices),
`threshold_db` (0–150), `min_duration_seconds` (1–86400), and `enabled`.
Deleting a rule that has generated events returns 409 so event history is kept.

`GET /api/events` supports `device_id`, `type`, inclusive offset-aware `from`
and `to`, and `limit` (default 100, maximum 1000). Event types are
`noise_threshold`, `device_offline`, and `device_online`. `PATCH
/api/events/{id}` accepts `{"acknowledged": true}`. Invalid filters or bodies
return 400; missing resources return 404.

Noise events are created after successive above-threshold `db_avg` readings
cover the configured minimum duration without a gap longer than the provisional
offline threshold. Threshold events are append-only records of alerts emitted
using readings available at evaluation time. A later-arriving reading with an
earlier `measured_at` is stored in history but does not revise or retract an
existing event; the event history is not a recomputed final chronology. A
background task emits one offline event per outage; the next reading emits the
matching online transition. Device deletion returns 409 when readings, rules, or
events depend on that device.

All readings in this project are uncalibrated. A threshold value is an
application rule in that uncalibrated scale, not a health or regulatory limit.
The ESP32 firmware sends synthetic readings from the board itself. The example
70-unit / 10-second alert rule is a demo trigger only—not a health, workplace, or
regulatory threshold. Project readings are uncalibrated and are not dB SPL or
dBA. See `../firmware/README.md` for the measurement and threshold rationale.

Invalid request data returns `400 {"detail":"Invalid request data"}`. Missing or
invalid device keys return `401 {"detail":"Invalid or missing device key"}`;
missing locations and devices return `404` with a `detail` string.

## Networks

- `frontend`: the API and frontend service.
- `backend`: the API and PostgreSQL.

The frontend service joins only `frontend`, so it has no direct connection to the
database network. The API joins both networks.


## Tests

From the repository root:

```sh
docker build --target test -t iot-noise-backend-test backend
docker run --rm iot-noise-backend-test
```

Or with Python 3.13 and a virtual environment:

```sh
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests execute SQL against an in-memory SQLite engine and simulate connection and
query errors to verify both response contracts and recovery. They do not require
running PostgreSQL or real credentials.

To check a real database outage locally, stop only `db` with
`docker compose stop db` and request `/api/health`: it must return 503. Start the
same database with `docker compose start db`, wait until it is ready, and repeat
the request: it must return 200 without restarting `backend`.
