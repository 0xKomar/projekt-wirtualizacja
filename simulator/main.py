import json
import os
import signal
import sys
import time
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


def main():
    # Stop right away on "docker compose stop" (SIGTERM).
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    devices = load_devices()
    register(devices)
    print(f"Simulating {len(SENSORS)} sensors every {INTERVAL:g} s")

    while True:
        now = datetime.now().astimezone()
        for name, lat, lon, base in SENSORS:
            reading = make_reading(base, now)
            print(f"{now:%H:%M:%S} {name}: {reading}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
