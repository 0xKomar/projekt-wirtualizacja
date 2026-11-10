import os
import signal
import sys
import time
from datetime import datetime

from noise import SENSORS, make_reading

INTERVAL = float(os.environ.get("SIM_INTERVAL", "10"))


def main():
    # Stop right away on "docker compose stop" (SIGTERM).
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    print(f"Simulating {len(SENSORS)} sensors every {INTERVAL:g} s")

    while True:
        now = datetime.now().astimezone()
        for name, lat, lon, base in SENSORS:
            reading = make_reading(base, now)
            print(f"{now:%H:%M:%S} {name}: {reading}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
