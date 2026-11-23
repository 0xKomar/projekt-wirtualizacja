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
| `DEVICE_OFFLINE_AFTER_SECONDS` | Provisional offline threshold; defaults to `60` seconds until ESP trials |

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
and only their SHA-256 hashes are stored. B1.3 will add the remaining location and
device CRUD operations plus filtered reading history.

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
