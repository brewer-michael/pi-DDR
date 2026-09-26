"""Linux input event codes used by pi-DDR.

A built-in subset of <linux/input-event-codes.h>, so the pure logic runs
without python-evdev (for example in tests on Windows). Names that are not in
the tables are looked up in python-evdev's ``ecodes`` when it is installed,
which it always is on the Pi.
"""

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0
SYN_DROPPED = 3

BUS_USB = 0x03

BTN_JOYSTICK = 0x120  # same code as BTN_TRIGGER

ABS_X = 0x00
ABS_Y = 0x01

_KEYS = {
    "KEY_ESC": 1,
    "KEY_ENTER": 28,
    "KEY_UP": 103,
    "KEY_LEFT": 105,
    "KEY_RIGHT": 106,
    "KEY_DOWN": 108,
    **{f"BTN_{i}": 0x100 + i for i in range(10)},
    "BTN_TRIGGER": 0x120,
    "BTN_THUMB": 0x121,
    "BTN_THUMB2": 0x122,
    "BTN_TOP": 0x123,
    "BTN_TOP2": 0x124,
    "BTN_PINKIE": 0x125,
    "BTN_BASE": 0x126,
    "BTN_BASE2": 0x127,
    "BTN_BASE3": 0x128,
    "BTN_BASE4": 0x129,
    "BTN_BASE5": 0x12A,
    "BTN_BASE6": 0x12B,
    "BTN_DEAD": 0x12F,
    "BTN_SOUTH": 0x130,
    "BTN_EAST": 0x131,
    "BTN_C": 0x132,
    "BTN_NORTH": 0x133,
    "BTN_WEST": 0x134,
    "BTN_Z": 0x135,
    "BTN_TL": 0x136,
    "BTN_TR": 0x137,
    "BTN_TL2": 0x138,
    "BTN_TR2": 0x139,
    "BTN_SELECT": 0x13A,
    "BTN_START": 0x13B,
    "BTN_MODE": 0x13C,
    "BTN_THUMBL": 0x13D,
    "BTN_THUMBR": 0x13E,
    "BTN_DPAD_UP": 0x220,
    "BTN_DPAD_DOWN": 0x221,
    "BTN_DPAD_LEFT": 0x222,
    "BTN_DPAD_RIGHT": 0x223,
    **{f"BTN_TRIGGER_HAPPY{i}": 0x2BF + i for i in range(1, 41)},
}

# Accepted when parsing, never produced when formatting.
_KEY_ALIASES = {
    "BTN_MISC": 0x100,
    "BTN_JOYSTICK": 0x120,
    "BTN_GAMEPAD": 0x130,
    "BTN_A": 0x130,
    "BTN_B": 0x131,
    "BTN_X": 0x133,
    "BTN_Y": 0x134,
}

_ABS = {
    "ABS_X": 0x00,
    "ABS_Y": 0x01,
    "ABS_Z": 0x02,
    "ABS_RX": 0x03,
    "ABS_RY": 0x04,
    "ABS_RZ": 0x05,
    "ABS_THROTTLE": 0x06,
    "ABS_RUDDER": 0x07,
    "ABS_WHEEL": 0x08,
    "ABS_GAS": 0x09,
    "ABS_BRAKE": 0x0A,
    "ABS_HAT0X": 0x10,
    "ABS_HAT0Y": 0x11,
    "ABS_HAT1X": 0x12,
    "ABS_HAT1Y": 0x13,
    "ABS_HAT2X": 0x14,
    "ABS_HAT2Y": 0x15,
    "ABS_HAT3X": 0x16,
    "ABS_HAT3Y": 0x17,
}

_KEY_NAMES = {code: name for name, code in _KEYS.items()}
_ABS_NAMES = {code: name for name, code in _ABS.items()}


def require_evdev():
    """Import python-evdev, or exit with install instructions."""
    try:
        import evdev
    except ImportError:
        raise SystemExit("python-evdev is missing. On the Pi: sudo apt install python3-evdev")
    return evdev


def _evdev_code(name):
    try:
        from evdev import ecodes
    except ImportError:
        return None
    return ecodes.ecodes.get(name)


def _evdev_name(table, code):
    try:
        from evdev import ecodes
    except ImportError:
        return None
    name = getattr(ecodes, table, {}).get(code)
    if isinstance(name, (list, tuple)):
        name = name[0]
    return name


def _parse_int(text):
    try:
        return int(text, 0)
    except ValueError:
        return None


def key_code(name):
    """Code for a key/button name such as ``BTN_TRIGGER``, ``key:288`` or ``0x120``."""
    text = name.strip()
    if text.lower().startswith("key:"):
        text = text[4:]
    code = _parse_int(text)
    if code is None:
        upper = text.upper()
        code = _KEYS.get(upper, _KEY_ALIASES.get(upper))
        if code is None and upper.startswith(("KEY_", "BTN_")):
            code = _evdev_code(upper)
    if code is None or code < 0:
        raise ValueError(f"unknown key or button name: {name!r}")
    return code


def abs_code(name):
    """Code for an axis name such as ``ABS_HAT0X`` or ``abs:16``."""
    text = name.strip()
    if text.lower().startswith("abs:"):
        text = text[4:]
    code = _parse_int(text)
    if code is None:
        upper = text.upper()
        code = _ABS.get(upper)
        if code is None and upper.startswith("ABS_"):
            code = _evdev_code(upper)
    if code is None or code < 0:
        raise ValueError(f"unknown axis name: {name!r}")
    return code


def key_name(code):
    """Readable name for a key code; ``key:<n>`` when the code has no name."""
    return _KEY_NAMES.get(code) or _evdev_name("BTN", code) or _evdev_name("KEY", code) or f"key:{code}"


def abs_name(code):
    """Readable name for an axis code; ``abs:<n>`` when the code has no name."""
    return _ABS_NAMES.get(code) or _evdev_name("ABS", code) or f"abs:{code}"
