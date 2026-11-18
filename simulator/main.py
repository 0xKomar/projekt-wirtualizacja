import json
import math
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

from noise import SENSORS, make_reading

API_URL = os.environ.get("SIM_API_URL", "http://localhost:8000")
INTERVAL = float(os.environ.get("SIM_INTERVAL", "10"))
# Device ids and keys, so a restart reuses the same devices.
STATE_FILE = os.environ.get("SIM_STATE_FILE", "devices.json")


def post(path, data, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Device-Key"] = key
    request = urllib.request.Request(
        API_URL + path, json.dumps(data).encode(), headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def load_devices():
    try:
        with open(STATE_FILE) as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_devices(devices):
    with open(STATE_FILE, "w") as file:
        json.dump(devices, file, indent=2)


def register(devices):
    # A location and a device for every sensor that has no key yet.
    for name, lat, lon, base in SENSORS:
        if name in devices:
            continue
        location = post("/api/locations", {"name": name, "lat": lat, "lon": lon})
        device = post("/api/devices", {"name": name, "location_id": location["id"]})
        devices[name] = {"id": device["id"], "key": device["key"]}
        save_devices(devices)
        print(f"Registered {name} as device {device['id']}")


def send_readings(devices, stopped):
    now = datetime.now().astimezone()
    for name, lat, lon, base in SENSORS:
        if name in stopped:
            continue
        reading = make_reading(base, now)
        reading["measured_at"] = now.isoformat(timespec="seconds")
        try:
            post("/api/readings", reading, devices[name]["key"])
            print(f"{now:%H:%M:%S} {name}: {reading['db_avg']} dB")
        except urllib.error.HTTPError as error:
            if error.code == 401:
                # Don't register a new device, so a lost key is visible.
                print(f"{name}: key rejected (401), sensor stopped. "
                      f"Delete {STATE_FILE} to register again.")
                stopped.add(name)
            else:
                print(f"{name}: backend answered {error.code}")
        except OSError as error:
            # Backend down or too slow: try again next time.
            print(f"{name}: backend unreachable ({error})")


def main():
    # 0 would send readings in a loop without any pause.
    # Written this way so nan and inf are rejected too.
    if not 0 < INTERVAL < math.inf:
        sys.exit(f"SIM_INTERVAL must be a number greater than 0, got {INTERVAL:g}")
    # Stop right away on "docker compose stop" (SIGTERM).
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    devices = load_devices()
    register(devices)
    print(f"Sending {len(SENSORS)} sensors to {API_URL} every {INTERVAL:g} s")

    stopped = set()
    while len(stopped) < len(SENSORS):
        send_readings(devices, stopped)
        time.sleep(INTERVAL)
    print("All sensors stopped")
    sys.exit(1)


if __name__ == "__main__":
    main()
