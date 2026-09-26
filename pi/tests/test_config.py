import os
import unittest

from piddr.config import ConfigError, format_config, parse_config, parse_mat_ids, udev_rules
from piddr.mapping import Source

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "padbridge", "padbridge.conf.example")

MINIMAL = """
[player1]
device = /dev/input/by-path/p1
left = BTN_TRIGGER
down = BTN_THUMB
up = BTN_THUMB2
right = BTN_TOP
"""


class ParseConfigTest(unittest.TestCase):
    def test_example_file_parses(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            config = parse_config(f.read())
        self.assertEqual([p.number for p in config.players], [1, 2])
        self.assertEqual(config.mat_ids, [(0x0079, 0x0011)])
        self.assertEqual(config.players[0].mapping["left"], (Source("key", 0x120),))
        self.assertNotEqual(config.players[0].device, config.players[1].device)

    def test_defaults(self):
        config = parse_config(MINIMAL)
        self.assertEqual(config.release_debounce_ms, 0.0)
        self.assertEqual(config.stats_interval_s, 300.0)
        self.assertEqual(config.mat_ids, [])
        self.assertEqual(len(config.players), 1)

    def test_shared_mapping_in_default_section(self):
        text = """
[DEFAULT]
left = ABS_HAT0X-
down = ABS_HAT0Y+
up = ABS_HAT0Y-
right = ABS_HAT0X+
[player1]
device = /dev/a
[player2]
device = /dev/b
right = BTN_TOP
"""
        config = parse_config(text)
        self.assertEqual(config.players[0].mapping["left"], (Source("abs", 0x10, -1),))
        self.assertEqual(config.players[1].mapping["right"], (Source("key", 0x123),))

    def test_errors(self):
        cases = {
            "missing device": MINIMAL.replace("device = /dev/input/by-path/p1", ""),
            "missing arrow": MINIMAL.replace("right = BTN_TOP", ""),
            "unknown key": MINIMAL + "jump = BTN_BASE\n",
            "bad input": MINIMAL.replace("BTN_TOP", "BTN_NOPE"),
            "same port twice": MINIMAL + MINIMAL.replace("player1", "player2"),
            "no players": "[bridge]\nrelease_debounce_ms = 5\n",
            "bad number": "[bridge]\nrelease_debounce_ms = soon\n" + MINIMAL,
        }
        for name, text in cases.items():
            with self.assertRaises(ConfigError, msg=name):
                parse_config(text)

    def test_mat_ids(self):
        self.assertEqual(parse_mat_ids("0079:0011, 12BA:0100"), [(0x79, 0x11), (0x12BA, 0x100)])
        self.assertEqual(parse_mat_ids(""), [])
        with self.assertRaises(ConfigError):
            parse_mat_ids("0079-0011")

    def test_format_round_trip(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            config = parse_config(f.read())
        again = parse_config(format_config(config))
        self.assertEqual(again.players, config.players)
        self.assertEqual(again.mat_ids, config.mat_ids)
        self.assertEqual(again.release_debounce_ms, config.release_debounce_ms)


class UdevRulesTest(unittest.TestCase):
    def test_rules_hide_each_mat_model(self):
        rules = udev_rules([(0x0079, 0x0011), (0x12BA, 0x0100)])
        self.assertIn('ATTRS{idVendor}=="0079", ATTRS{idProduct}=="0011"', rules)
        self.assertIn('ATTRS{idVendor}=="12ba", ATTRS{idProduct}=="0100"', rules)
        self.assertEqual(rules.count('MODE="0600", GROUP="root"'), 2)
        self.assertEqual(rules.count('TAG-="uaccess"'), 2)
        self.assertEqual(rules.count('ENV{ID_INPUT_JOYSTICK}=""'), 2)


if __name__ == "__main__":
    unittest.main()
