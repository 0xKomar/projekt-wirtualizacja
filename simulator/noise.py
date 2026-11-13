import random

# Virtual sensors: name, latitude, longitude, typical daytime level in dB.
SENSORS = [
    ("Stary Rynek", 52.4083, 16.9335, 58),
    ("Rondo Kaponiera", 52.4066, 16.9121, 67),
    ("Dworzec", 52.4016, 16.9110, 63),
    ("Malta", 52.4012, 16.9830, 49),
    ("Kampus Piotrowo", 52.4025, 16.9503, 53),
    ("Cytadela", 52.4204, 16.9348, 45),
]

# Offset in dB for each hour 0-23: quiet at night, rush hours around 8:00 and 16:00.
HOURLY_OFFSET = [
    -12, -13, -14, -14, -13, -10, -5, 2, 4, 2, 0, 0,
    1, 1, 1, 3, 4, 4, 2, 0, -2, -4, -7, -10,
]

SAMPLES = 10  # one sample per second of a 10 s window, like the ESP
SPREAD = 3.0  # random spread of a single sample in dB
SPIKE_CHANCE = 0.02  # chance of a loud event (horn, motorbike) in one window
SPIKE = 20.0  # how much louder the event is, lasts 3 samples


def hour_offset(now):
    # Linear between full hours, so levels don't jump on the hour.
    start = HOURLY_OFFSET[now.hour]
    end = HOURLY_OFFSET[(now.hour + 1) % 24]
    return start + (end - start) * now.minute / 60


def make_reading(base, now, rng=random):
    level = base + hour_offset(now)
    samples = [rng.gauss(level, SPREAD) for _ in range(SAMPLES)]

    if rng.random() < SPIKE_CHANCE:
        first = rng.randrange(SAMPLES - 2)
        for i in range(first, first + 3):
            samples[i] += SPIKE

    # Keep samples in the range the backend accepts.
    samples = [min(max(sample, 0.0), 150.0) for sample in samples]
    return {
        "db_avg": round(sum(samples) / len(samples), 1),
        "db_min": round(min(samples), 1),
        "db_max": round(max(samples), 1),
    }
