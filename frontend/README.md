# Frontend

Static page served by nginx. For now it only shows whether the backend and the database are up.

## Files

- `public/` - the page (HTML, CSS, JS), no build step.
- `nginx/default.conf.template` - serves the page and forwards `/api/` to the backend.
  The official nginx image fills in `${BACKEND_URL}` when the container starts.

## Environment

| Variable | Example | Purpose |
|---|---|---|
| `BACKEND_URL` | `http://backend:8000` | where nginx sends `/api/` requests |

The browser only talks to this container. It never calls the backend or the database directly.

## Run

Started together with the rest by `docker compose up --build` (see the main README).
