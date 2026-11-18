# Simulator

Six virtual noise sensors around Poznań. Each one talks to the backend like the ESP32 does:
a reading every `SIM_INTERVAL` seconds, `POST /api/readings` with its `X-Device-Key`.
Plain Python, no external libraries.

## How the noise is made

- Each place has its own typical daytime level, so Rondo Kaponiera is louder than Cytadela.
- An offset for every hour of the day: quiet at night, loudest around 8:00 and 16:00 (Polish time).
- A reading is 10 samples with random spread, sent as `db_avg`, `db_min` and `db_max`,
  like the 10 s window on the ESP.
- About 2% of readings get a short loud event (+20 dB for 3 samples, like a car horn).

The numbers are made up for testing. Like the sensor readings, they are uncalibrated, not dB SPL.

## Files

- `noise.py` - the sensor list and the noise generator.
- `main.py` - registers the sensors and sends the readings.
- `test_noise.py` - tests for the generator.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `SIM_API_URL` | `http://localhost:8000` | backend address, compose sets it from `BACKEND_URL` |
| `SIM_INTERVAL` | `10` | seconds between readings, greater than 0 |
| `SIM_STATE_FILE` | `devices.json` (`/data/devices.json` in the container) | where device ids and keys are kept |

## Run

```sh
docker compose --profile sim up --build
```

Without `--profile sim` the simulator doesn't start. It waits for a healthy backend.
On the first start it creates a location and a device for each sensor and saves the keys
in the `simulator_data` volume. Later starts reuse them.

If the backend rejects a key (401), for example after it lost its devices, that sensor stops
with a message in the log. The simulator doesn't create a new device on its own. To register again:

```sh
docker compose --profile sim run --rm simulator rm /data/devices.json
docker compose --profile sim up -d simulator
```

Tests: `cd simulator && python -m unittest`
