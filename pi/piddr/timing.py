"""Timing analysis for mat input: polling interval, chatter, delay stats."""

import cmath
import math
from collections import deque, namedtuple

# xHCI controllers (every USB-A port on a Pi 4) poll interrupt endpoints on
# power-of-two intervals, so these are the only rates a mat can really get.
CANDIDATE_INTERVALS_MS = (0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)

PollEstimate = namedtuple("PollEstimate", "interval_ms samples coherence")


def estimate_poll_interval(
    report_times,
    candidates_ms=CANDIDATE_INTERVALS_MS,
    max_gap=0.5,
    min_samples=20,
    threshold=0.7,
):
    """Estimate how often the host really polls a device.

    Reports can only arrive on polling slots, so the gaps between consecutive
    reports are whole multiples of the polling interval. For each candidate
    interval this measures how well the gaps line up with it (1.0 = perfect,
    ~0 = random) and returns the largest candidate that lines up. It works
    from ordinary stepping, with no test hardware.

    Gaps longer than ``max_gap`` seconds are skipped: over long gaps the USB
    clock drifts against the system clock enough to blur a 1 ms grid.
    """
    times = sorted(report_times)
    gaps = [b - a for a, b in zip(times, times[1:]) if 0 < b - a <= max_gap]
    coherence = {}
    for p_ms in candidates_ms:
        period = p_ms / 1000.0
        if gaps:
            total = sum(cmath.exp(2j * math.pi * gap / period) for gap in gaps)
            coherence[p_ms] = abs(total) / len(gaps)
        else:
            coherence[p_ms] = 0.0
    if len(gaps) < min_samples:
        return PollEstimate(None, len(gaps), coherence)
    interval = None
    for p_ms in candidates_ms:
        if coherence[p_ms] >= threshold:
            interval = p_ms
    return PollEstimate(interval, len(gaps), coherence)


class ChatterDetector:
    """Flags a press that follows a release of the same input within ``window`` seconds.

    On a mat this is almost always contact bounce, which the game would count
    as a second step.
    """

    def __init__(self, window=0.015):
        self.window = window
        self._released_at = {}
        self.hits = []

    def feed(self, t, key, pressed):
        """Return the gap in seconds when this press looks like chatter, else None."""
        if not pressed:
            self._released_at[key] = t
            return None
        released = self._released_at.pop(key, None)
        if released is not None and t - released <= self.window:
            self.hits.append((key, t - released))
            return t - released
        return None


def percentile(sorted_values, fraction):
    """Nearest-rank percentile of an already sorted list."""
    if not sorted_values:
        return None
    rank = max(1, math.ceil(fraction * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


class DelayStats:
    """Rolling delay statistics, reported in microseconds."""

    def __init__(self, maxlen=5000):
        self._samples = deque(maxlen=maxlen)
        self.count = 0
        self.worst = 0.0

    def add(self, seconds):
        self._samples.append(seconds)
        self.count += 1
        self.worst = max(self.worst, seconds)

    def summary(self):
        ordered = sorted(self._samples)
        if not ordered:
            return "no samples yet"
        p50 = percentile(ordered, 0.50) * 1e6
        p99 = percentile(ordered, 0.99) * 1e6
        return f"n={self.count} p50={p50:.0f}us p99={p99:.0f}us max={self.worst * 1e6:.0f}us"
