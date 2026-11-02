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

The stack currently contains `db` and `backend`. The frontend will add its own
service, reverse proxy and published port to the `frontend` network.

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

If `BACKEND_PORT` changes, update the port in `BACKEND_URL` for the frontend too.
Database connection and statement timeouts are three seconds. The connection
pool checks existing connections before reuse, allowing recovery after a database
restart without restarting the API.

## Health contract

`GET /api/health` does not require authentication. Responses have
`Cache-Control: no-store`.

| HTTP status | JSON body |
| --- | --- |
| `200` | `{"status": "ok", "database": "ok"}` |
| `503` | `{"status": "error", "database": "unreachable"}` |

A database connection or query failure returns 503 without exposing connection
details. The application creates its connection pool without connecting during
startup; Compose waits for a healthy database before starting the backend.

## Networks

- `frontend`: the API and, when added, the frontend service.
- `backend`: the API and PostgreSQL.

The frontend service should join only `frontend`, so it has no direct connection
to the database network. The API joins both networks.

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
