"""Linux input event codes, from python-evdev (apt package python3-evdev).

On top of ``evdev.ecodes`` this adds parsing for the names and numbers people
write in the bridge config, and one stable name per code for output
(``BTN_TRIGGER`` rather than its alias ``BTN_JOYSTICK``).
"""

try:
    from evdev import ecodes
except ImportError:
    raise SystemExit("python-evdev is missing: sudo apt install python3-evdev")

EV_SYN = ecodes.EV_SYN
EV_KEY = ecodes.EV_KEY
EV_ABS = ecodes.EV_ABS
SYN_REPORT = ecodes.SYN_REPORT
SYN_DROPPED = ecodes.SYN_DROPPED
BUS_USB = ecodes.BUS_USB
BTN_JOYSTICK = ecodes.BTN_JOYSTICK
ABS_X = ecodes.ABS_X
ABS_Y = ecodes.ABS_Y

# Range markers and letter aliases that share a code with a more specific name.
_ALIASES = {
    "BTN_MISC",
    "BTN_MOUSE",
    "BTN_JOYSTICK",
    "BTN_GAMEPAD",
    "BTN_DIGI",
    "BTN_WHEEL",
    "BTN_TRIGGER_HAPPY",
    "BTN_A",
    "BTN_B",
    "BTN_X",
    "BTN_Y",
    "KEY_MIN_INTERESTING",
}


def _preferred(names):
    if isinstance(names, str):
        return names
    return next((name for name in names if name not in _ALIASES), names[0])


def _parse_int(text):
    try:
        return int(text, 0)
    except ValueError:
        return None


def _code(name, prefix, kinds):
    text = name.strip()
    if text.lower().startswith(prefix):
        text = text[len(prefix) :]
    code = _parse_int(text)
    if code is None and text.upper().startswith(kinds):
        code = ecodes.ecodes.get(text.upper())
    return code if code is not None and code >= 0 else None


def key_code(name):
    """Code for a key/button name such as ``BTN_TRIGGER``, ``key:288`` or ``0x120``."""
    code = _code(name, "key:", ("KEY_", "BTN_"))
    if code is None:
        raise ValueError(f"unknown key or button name: {name!r}")
    return code


def abs_code(name):
    """Code for an axis name such as ``ABS_HAT0X`` or ``abs:16``."""
    code = _code(name, "abs:", ("ABS_",))
    if code is None:
        raise ValueError(f"unknown axis name: {name!r}")
    return code


def key_name(code):
    """Readable name for a key code; ``key:<n>`` when the code has no name."""
    names = ecodes.BTN.get(code) or ecodes.KEY.get(code)
    return _preferred(names) if names else f"key:{code}"


def abs_name(code):
    """Readable name for an axis code; ``abs:<n>`` when the code has no name."""
    names = ecodes.ABS.get(code)
    return _preferred(names) if names else f"abs:{code}"
