import random
import unittest
from datetime import datetime
from unittest import mock

import noise


def at(hour, minute=0):
    return datetime(2026, 11, 9, hour, minute)


class HourOffsetTest(unittest.TestCase):
    def test_full_hour_uses_table(self):
        self.assertEqual(noise.hour_offset(at(8)), noise.HOURLY_OFFSET[8])

    def test_half_hour_is_between_hours(self):
        expected = (noise.HOURLY_OFFSET[7] + noise.HOURLY_OFFSET[8]) / 2
        self.assertAlmostEqual(noise.hour_offset(at(7, 30)), expected)

    def test_last_hour_moves_towards_midnight(self):
        expected = (noise.HOURLY_OFFSET[23] + noise.HOURLY_OFFSET[0]) / 2
        self.assertAlmostEqual(noise.hour_offset(at(23, 30)), expected)


class ReadingTest(unittest.TestCase):
    def test_values_are_ordered_and_in_range(self):
        rng = random.Random(1)
        for hour in range(24):
            for base in (0, 60, 150):
                reading = noise.make_reading(base, at(hour), rng)
                self.assertLessEqual(reading["db_min"], reading["db_avg"])
                self.assertLessEqual(reading["db_avg"], reading["db_max"])
                self.assertGreaterEqual(reading["db_min"], 0)
                self.assertLessEqual(reading["db_max"], 150)

    def test_night_is_quieter_than_rush_hour(self):
        rng = random.Random(2)
        night = [noise.make_reading(60, at(3), rng)["db_avg"] for _ in range(50)]
        rush = [noise.make_reading(60, at(8), rng)["db_avg"] for _ in range(50)]
        self.assertLess(sum(night) / 50 + 10, sum(rush) / 50)

    def test_spike_raises_max(self):
        rng = random.Random(3)
        with mock.patch.object(noise, "SPIKE_CHANCE", 1.0):
            reading = noise.make_reading(60, at(12), rng)
        self.assertGreater(reading["db_max"], 60 + noise.SPIKE / 2)


class SensorsTest(unittest.TestCase):
    def test_sensors_are_in_poznan(self):
        self.assertEqual(len(noise.SENSORS), 6)
        for name, lat, lon, base in noise.SENSORS:
            self.assertTrue(52.35 < lat < 52.47, name)
            self.assertTrue(16.80 < lon < 17.05, name)
            self.assertTrue(30 <= base <= 80, name)


if __name__ == "__main__":
    unittest.main()
