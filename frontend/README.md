# Frontend

Static page served by nginx: a full-screen map of Poznań with the noise sensors, and cards on top of it
with the backend status, the sensor list and the legend.

## Map

- Leaflet 1.9.4 from unpkg (pinned with an integrity hash) with OpenStreetMap tiles, shown in gray so the sensors stand out.
- Sensors come from `GET /api/devices`, refreshed every 10 seconds. Each marker shows the latest `db_avg` rounded.
- Color from the latest `db_avg`: below 55 green, 55-70 yellow, above 70 red,
  gray when the device is offline or has no readings yet.
- Hover shows the name, a click shows the latest reading (avg, min, max) and how long ago it was measured.
- The sensor list (loudest first) scrolls when there are many sensors; a click moves the map to that sensor.
- Light and dark theme: the button in the header switches it, the choice is kept in the browser.
  Without a saved choice the page follows the system setting.

The values are uncalibrated sensor readings, not dB SPL.

## Files

- `public/` - the page (HTML, CSS, JS), no build step.
  - `theme.js` - light or dark theme.
  - `app.js` - backend and database status, checked every 10 seconds.
  - `map.js` - the map, the markers and the sensor list.
  - `style.css` - layout and colors for both themes.
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
