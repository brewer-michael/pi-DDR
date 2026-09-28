import random
import unittest

from piddr.timing import (
    ChatterDetector,
    DelayStats,
    describe_poll_estimate,
    estimate_poll_interval,
    percentile,
)


def stepping_reports(interval_ms, count=120, jitter_us=40, seed=1):
    """Report times of someone stepping at random, snapped to a polling grid."""
    rng = random.Random(seed)
    period = interval_ms / 1000.0
    t, times = 10.0, []
    for _ in range(count):
        t += rng.uniform(0.04, 0.45)  # human step / release gaps
        slot = round(t / period) * period
        times.append(slot + rng.gauss(0, jitter_us / 1e6))
    return times


class PollEstimateTest(unittest.TestCase):
    def test_finds_the_grid(self):
        for interval in (1.0, 2.0, 4.0, 8.0, 16.0):
            est = estimate_poll_interval(stepping_reports(interval))
            self.assertEqual(est.interval_ms, interval, est.coherence)

    def test_needs_enough_gaps(self):
        est = estimate_poll_interval(stepping_reports(8.0, count=10))
        self.assertIsNone(est.interval_ms)
        self.assertLess(est.samples, 20)

    def test_long_gaps_are_ignored(self):
        times = [i * 1.0 for i in range(50)]  # one report a second: nothing usable
        self.assertEqual(estimate_poll_interval(times).samples, 0)

    def test_report_on_every_poll(self):
        # A noisy axis can make a device report on every poll: all gaps equal.
        for interval in (1.0, 8.0):
            times = [10.0 + i * interval / 1000.0 for i in range(100)]
            self.assertEqual(estimate_poll_interval(times).interval_ms, interval)

    def test_noisy_timestamps_give_no_answer(self):
        est = estimate_poll_interval(stepping_reports(1.0, count=200, jitter_us=250))
        self.assertIsNone(est.interval_ms)
        self.assertGreater(est.samples, 100)

    def test_describe(self):
        self.assertIn("1 ms grid", describe_poll_estimate(estimate_poll_interval(stepping_reports(1.0))))
        few = estimate_poll_interval(stepping_reports(8.0, count=10))
        self.assertIn("need more steps", describe_poll_estimate(few))
        noisy = estimate_poll_interval(stepping_reports(1.0, count=200, jitter_us=250))
        self.assertIn("no clear polling grid", describe_poll_estimate(noisy))


class ChatterTest(unittest.TestCase):
    def test_flags_fast_repress_only(self):
        det = ChatterDetector(window=0.015)
        self.assertIsNone(det.feed(0.000, 1, True))
        self.assertIsNone(det.feed(0.100, 1, False))
        self.assertAlmostEqual(det.feed(0.106, 1, True), 0.006)
        self.assertIsNone(det.feed(0.200, 1, False))
        self.assertIsNone(det.feed(0.300, 1, True))  # a real second step
        self.assertIsNone(det.feed(0.305, 2, True))  # other arrow
        self.assertEqual(len(det.hits), 1)


class StatsTest(unittest.TestCase):
    def test_percentile(self):
        values = list(range(1, 101))
        self.assertEqual(percentile(values, 0.5), 50)
        self.assertEqual(percentile(values, 0.99), 99)
        self.assertIsNone(percentile([], 0.5))

    def test_summary(self):
        stats = DelayStats()
        self.assertEqual(stats.summary(), "no samples yet")
        for us in (100, 200, 300):
            stats.add(us / 1e6)
        self.assertEqual(stats.summary(), "n=3 p50=200us p99=300us max=300us")


if __name__ == "__main__":
    unittest.main()
