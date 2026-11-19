import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def run_main(interval):
    env = {**os.environ, "SIM_INTERVAL": interval}
    return subprocess.run([sys.executable, "main.py"], cwd=HERE, env=env,
                          capture_output=True, text=True, timeout=10)


class IntervalTest(unittest.TestCase):
    def test_bad_interval_stops_at_start(self):
        for value in ["0", "-5", "nan", "inf", "-inf"]:
            with self.subTest(value=value):
                result = run_main(value)
                self.assertEqual(result.returncode, 1)
                self.assertIn("SIM_INTERVAL must be a number greater than 0", result.stderr)


if __name__ == "__main__":
    unittest.main()
