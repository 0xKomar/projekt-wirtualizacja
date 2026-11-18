# Frontend

Static page served by nginx: a map of Poznań with the noise sensors, plus the backend status at the top.

## Map

- Leaflet 1.9.4 from unpkg (pinned with an integrity hash) with OpenStreetMap tiles, shown in gray so the sensors stand out.
- Sensors come from `GET /api/devices`, one circle per device, refreshed every 10 seconds.
- Color from the latest `db_avg`: below 55 green, 55-70 yellow, above 70 red,
  gray when the device is offline or has no readings yet.
- Hover shows the name, a click shows the latest reading (avg, min, max) and when it was measured.

The values are uncalibrated sensor readings, not dB SPL.

## Files

- `public/` - the page (HTML, CSS, JS), no build step.
  - `app.js` - backend and database status, checked every 10 seconds.
  - `map.js` - the map, the sensors and the legend.
- `nginx/default.conf.template` - serves the page and forwards `/api/` to the backend.
  The official nginx image fills in `${BACKEND_URL}` when the container starts.

## Environment

| Variable | Example | Purpose |
|---|---|---|
| `BACKEND_URL` | `http://backend:8000` | where nginx sends `/api/` requests |

All data goes through this container. The browser never calls the backend or the database directly.
Only Leaflet and the map tiles come from the internet (unpkg, OpenStreetMap).

## Run

Started together with the rest by `docker compose up --build` (see the main README).
To see sensors on the map, start the simulator too: `docker compose --profile sim up --build`.
