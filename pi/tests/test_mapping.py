import unittest

from piddr import evcodes
from piddr.mapping import VIRTUAL_BUTTONS, Mapper, Source, format_source, parse_source, parse_sources

KEY, ABS = evcodes.EV_KEY, evcodes.EV_ABS
LEFT, DOWN, UP, RIGHT = (VIRTUAL_BUTTONS[c] for c in ("left", "down", "up", "right"))
HAT0X, HAT0Y = 0x10, 0x11


class ParseSourceTest(unittest.TestCase):
    def test_names_numbers_and_axes(self):
        self.assertEqual(parse_source("BTN_TRIGGER"), Source("key", 0x120))
        self.assertEqual(parse_source("btn_thumb2"), Source("key", 0x122))
        self.assertEqual(parse_source("key:300"), Source("key", 300))
        self.assertEqual(parse_source("0x2c0"), Source("key", 0x2C0))
        self.assertEqual(parse_source("ABS_HAT0X-"), Source("abs", HAT0X, -1))
        self.assertEqual(parse_source("abs:1+"), Source("abs", 1, 1))

    def test_errors(self):
        for bad in ("", "BTN_NOPE", "ABS_HAT0X", "ABS_BOGUS+"):
            with self.assertRaises(ValueError, msg=bad):
                parse_source(bad)

    def test_round_trip(self):
        for text in ("BTN_TRIGGER", "BTN_TRIGGER_HAPPY3", "ABS_HAT0Y+", "ABS_X-"):
            self.assertEqual(format_source(parse_source(text)), text)
        # Numeric codes may or may not have a name (python-evdev knows more names).
        for text in ("key:1000", "abs:40-"):
            source = parse_source(text)
            self.assertEqual(parse_source(format_source(source)), source)

    def test_list(self):
        self.assertEqual(
            parse_sources("BTN_TRIGGER, ABS_HAT0X-"), (Source("key", 0x120), Source("abs", HAT0X, -1))
        )


def button_mapper(**kwargs):
    mapping = {
        "left": parse_sources("BTN_TRIGGER"),
        "down": parse_sources("BTN_THUMB"),
        "up": parse_sources("BTN_THUMB2"),
        "right": parse_sources("BTN_TOP"),
    }
    return Mapper(mapping, **kwargs)


class MapperTest(unittest.TestCase):
    def test_press_and_release(self):
        m = button_mapper()
        m.feed(KEY, 0x120, 1)
        self.assertEqual(m.flush(0.0), [(LEFT, 1)])
        self.assertEqual(m.flush(0.0), [])
        m.feed(KEY, 0x120, 0)
        self.assertEqual(m.flush(0.1), [(LEFT, 0)])

    def test_jump_stays_in_one_report(self):
        m = button_mapper()
        m.feed(KEY, 0x120, 1)
        m.feed(KEY, 0x123, 1)
        self.assertEqual(m.flush(0.0), [(LEFT, 1), (RIGHT, 1)])

    def test_autorepeat_is_not_a_press(self):
        m = button_mapper()
        m.feed(KEY, 0x121, 2)
        self.assertEqual(m.flush(0.0), [])

    def test_unmapped_input_is_ignored(self):
        m = button_mapper()
        m.feed(KEY, 0x12B, 1)
        self.assertEqual(m.flush(0.0), [])

    def test_hat_arrows(self):
        mapping = {
            "left": parse_sources("ABS_HAT0X-"),
            "right": parse_sources("ABS_HAT0X+"),
            "up": parse_sources("ABS_HAT0Y-"),
            "down": parse_sources("ABS_HAT0Y+"),
        }
        m = Mapper(mapping, abs_ranges={HAT0X: (-1, 1), HAT0Y: (-1, 1)})
        m.feed(ABS, HAT0X, -1)
        self.assertEqual(m.flush(0.0), [(LEFT, 1)])
        m.feed(ABS, HAT0X, 1)  # rocks straight from left to right
        self.assertEqual(sorted(m.flush(0.0)), sorted([(LEFT, 0), (RIGHT, 1)]))
        m.feed(ABS, HAT0X, 0)
        self.assertEqual(m.flush(0.0), [(RIGHT, 0)])

    def test_analog_axis_uses_its_range(self):
        m = Mapper({"left": parse_sources("ABS_X-"), "right": parse_sources("ABS_X+")}, abs_ranges={0: (0, 255)})
        m.feed(ABS, 0, 128)  # centred
        self.assertEqual(m.flush(0.0), [])
        m.feed(ABS, 0, 0)
        self.assertEqual(m.flush(0.0), [(LEFT, 1)])
        m.feed(ABS, 0, 255)
        self.assertEqual(sorted(m.flush(0.0)), sorted([(LEFT, 0), (RIGHT, 1)]))

    def test_any_source_holds_the_control(self):
        m = Mapper({"left": parse_sources("BTN_TRIGGER, BTN_BASE")})
        m.feed(KEY, 0x120, 1)
        m.feed(KEY, 0x126, 1)
        self.assertEqual(m.flush(0.0), [(LEFT, 1)])
        m.feed(KEY, 0x120, 0)
        self.assertEqual(m.flush(0.0), [])
        m.feed(KEY, 0x126, 0)
        self.assertEqual(m.flush(0.0), [(LEFT, 0)])

    def test_release_debounce_swallows_chatter(self):
        m = button_mapper(release_debounce=0.02)
        m.feed(KEY, 0x120, 1)
        self.assertEqual(m.flush(0.000), [(LEFT, 1)])  # the press goes out at once
        m.feed(KEY, 0x120, 0)
        self.assertEqual(m.flush(0.005), [])  # release held back
        self.assertEqual(m.next_deadline(), 0.025)
        m.feed(KEY, 0x120, 1)
        self.assertEqual(m.flush(0.009), [])  # bounce: the game never sees it
        self.assertIsNone(m.next_deadline())
        m.feed(KEY, 0x120, 0)
        self.assertEqual(m.flush(0.100), [])
        self.assertEqual(m.expire(0.110), [])
        self.assertEqual(m.expire(0.121), [(LEFT, 0)])
        self.assertIsNone(m.next_deadline())

    def test_press_after_the_window_is_a_new_step(self):
        # The loop can see the next press before it gets round to expiring
        # the held-back release; that press must still count as a new step.
        m = button_mapper(release_debounce=0.015)
        m.feed(KEY, 0x120, 1)
        m.flush(0.000)
        m.feed(KEY, 0x120, 0)
        self.assertEqual(m.flush(0.030), [])  # release due at 0.045
        m.feed(KEY, 0x120, 1)
        self.assertEqual(m.flush(0.0456), [(LEFT, 0), (LEFT, 1)])
        self.assertIsNone(m.next_deadline())

    def test_release_all_and_reset(self):
        m = button_mapper()
        m.feed(KEY, 0x120, 1)
        m.feed(KEY, 0x122, 1)
        m.flush(0.0)
        self.assertEqual(m.held(), {"left", "up"})
        self.assertEqual(m.release_all(), [(LEFT, 0), (UP, 0)])
        self.assertEqual(m.held(), set())
        self.assertEqual(m.reset({0x121}, {}, 1.0), [(DOWN, 1)])

    def test_unknown_control(self):
        with self.assertRaises(ValueError):
            Mapper({"jump": parse_sources("BTN_TRIGGER")})

    def test_virtual_buttons_are_joystick_buttons_1_to_11(self):
        self.assertEqual(VIRTUAL_BUTTONS["left"], 0x120)
        self.assertEqual(VIRTUAL_BUTTONS["select"], 0x12A)


if __name__ == "__main__":
    unittest.main()
