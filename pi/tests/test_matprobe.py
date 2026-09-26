import os
import tempfile
import unittest

from piddr.mapping import Source
from piddr.matprobe import mapped_to, previous_config, write_config

CONFIG = """
[bridge]
release_debounce_ms = 15
stats_interval_s = 60
[player1]
device = /dev/input/by-path/p1
left = BTN_TRIGGER
down = BTN_THUMB
up = BTN_THUMB2
right = BTN_TOP
"""


class LearnHelpersTest(unittest.TestCase):
    def test_mapped_to(self):
        mapping = {"left": (Source("key", 0x120),), "down": (Source("key", 0x121),)}
        self.assertEqual(mapped_to(mapping, Source("key", 0x120)), "left")
        self.assertIsNone(mapped_to(mapping, Source("key", 0x122)))

    def test_previous_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "padbridge.conf")
            self.assertIsNone(previous_config(path))
            self.assertIsNone(previous_config(None))
            with open(path, "w", encoding="utf-8") as f:
                f.write("[player1]\nleft = nonsense\n")
            self.assertIsNone(previous_config(path))
            with open(path, "w", encoding="utf-8") as f:
                f.write(CONFIG)
            old = previous_config(path)
            self.assertEqual(old.release_debounce_ms, 15)
            self.assertEqual(old.stats_interval_s, 60)

    def test_write_config_keeps_a_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "padbridge.conf")
            self.assertIsNone(write_config(path, "first\n"))
            self.assertEqual(write_config(path, "second\n"), path + ".bak")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "second\n")
            with open(path + ".bak", encoding="utf-8") as f:
                self.assertEqual(f.read(), "first\n")
            self.assertFalse(os.path.exists(path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
