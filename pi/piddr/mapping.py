"""Translate a physical mat's raw events into buttons of the virtual stage.

The game sees one virtual joystick, "pi-DDR Stage", for both mats. P1's
controls are its buttons 1-11 and P2's are buttons 12-22, whatever the mats
report, so the game's key mapping survives swapping a mat for another model.
Only the bridge config (which raw input is which arrow) changes.
"""

from dataclasses import dataclass

from . import evcodes

# Order is part of the contract: control i of player n is button
# (n - 1) * 11 + i + 1 of the stage in the game.
CONTROLS = (
    "left",
    "down",
    "up",
    "right",
    "upleft",
    "upright",
    "downleft",
    "downright",
    "start",
    "back",
    "select",
)
REQUIRED_CONTROLS = ("left", "down", "up", "right")

# Linux numbers a joystick's buttons by ascending event code from BTN_JOYSTICK
# up (joydev's button map, and SDL's evdev backend, which OutFox reads pads
# through). So P1 takes BTN_JOYSTICK + i and P2 the BTN_TRIGGER_HAPPY codes,
# which come next in that order: generic "extra button" codes that no gamepad
# layout gives a meaning to.
BUTTON_BASE = {1: evcodes.BTN_JOYSTICK, 2: evcodes.BTN_TRIGGER_HAPPY1}
PLAYER_BUTTONS = {n: {name: base + i for i, name in enumerate(CONTROLS)} for n, base in BUTTON_BASE.items()}
STAGE_BUTTONS = tuple(sorted(code for buttons in PLAYER_BUTTONS.values() for code in buttons.values()))


def game_button(player, control):
    """The joystick button number (1-based) the game shows for a control."""
    return (player - 1) * len(CONTROLS) + CONTROLS.index(control) + 1

# An axis counts as pressed past half of its travel from the centre.
AXIS_THRESHOLD = 0.5


@dataclass(frozen=True)
class Source:
    """One raw input: a key/button, or one direction of an axis."""

    kind: str  # "key" or "abs"
    code: int
    direction: int = 0  # -1 or +1 for "abs"

    def __str__(self):
        return format_source(self)


def parse_source(text):
    """Parse ``BTN_TRIGGER``, ``key:288``, ``ABS_HAT0X-`` or ``abs:16+``."""
    spec = text.strip()
    if not spec:
        raise ValueError("empty input name")
    is_axis = spec.upper().startswith("ABS_") or spec.lower().startswith("abs:")
    if is_axis:
        if spec[-1] not in "+-":
            raise ValueError(f"axis {spec!r} needs a direction: add '+' or '-'")
        direction = -1 if spec[-1] == "-" else 1
        return Source("abs", evcodes.abs_code(spec[:-1]), direction)
    return Source("key", evcodes.key_code(spec))


def parse_sources(text):
    """Parse a comma-separated list of sources."""
    return tuple(parse_source(part) for part in text.split(",") if part.strip())


def format_source(source):
    if source.kind == "abs":
        return evcodes.abs_name(source.code) + ("-" if source.direction < 0 else "+")
    return evcodes.key_name(source.code)


def axis_pressed(value, lo, hi, direction):
    """True when ``value`` is past the threshold in ``direction``."""
    if hi <= lo:
        return False
    norm = 2.0 * (value - lo) / (hi - lo) - 1.0
    return norm < -AXIS_THRESHOLD if direction < 0 else norm > AXIS_THRESHOLD


class Mapper:
    """Raw events of one mat in, stage button changes out.

    Feed every raw event with ``feed()`` and call ``flush()`` at each
    SYN_REPORT, so arrows pressed in the same USB report (a jump) reach the
    game in the same report too.

    ``release_debounce`` (seconds) hides contact chatter: a release is held
    back that long and dropped if the arrow is pressed again in the meantime.
    Presses are never delayed.
    """

    def __init__(self, mapping, abs_ranges=None, release_debounce=0.0, player=1):
        self._buttons = PLAYER_BUTTONS[player]
        self._mapping = {c: tuple(s) for c, s in mapping.items() if s}
        unknown = set(self._mapping) - set(CONTROLS)
        if unknown:
            raise ValueError(f"unknown controls: {', '.join(sorted(unknown))}")
        self._ranges = dict(abs_ranges or {})
        self._debounce = release_debounce
        self._keys = set()
        self._abs = {}
        self._sent = dict.fromkeys(self._mapping, False)
        self._pending = {}  # control -> monotonic time its release is due

    def set_abs_ranges(self, ranges):
        self._ranges = dict(ranges)

    @property
    def abs_codes(self):
        return tuple(self._ranges)

    def held(self):
        """Controls the game currently sees as held."""
        return {c for c, held in self._sent.items() if held}

    def feed(self, etype, code, value):
        if etype == evcodes.EV_KEY:
            if value == 0:
                self._keys.discard(code)
            elif value == 1:
                self._keys.add(code)
            # value 2 is key auto-repeat: not a new press
        elif etype == evcodes.EV_ABS:
            self._abs[code] = value

    def _active(self, source):
        if source.kind == "key":
            return source.code in self._keys
        value = self._abs.get(source.code)
        if value is None:
            return False
        lo, hi = self._ranges.get(source.code, (-1, 1))
        return axis_pressed(value, lo, hi, source.direction)

    def flush(self, now):
        """Return ``[(button_code, value)]`` to send for the current raw state."""
        # A held-back release whose window has passed is final, even if this
        # report presses the arrow again: that press is a new step.
        changes = self.expire(now)
        for control, sources in self._mapping.items():
            if any(self._active(s) for s in sources):
                if self._pending.pop(control, None) is not None:
                    continue  # pressed again inside the window: the game never saw a release
                if not self._sent[control]:
                    self._sent[control] = True
                    changes.append((self._buttons[control], 1))
            elif self._sent[control] and control not in self._pending:
                if self._debounce > 0:
                    self._pending[control] = now + self._debounce
                else:
                    self._sent[control] = False
                    changes.append((self._buttons[control], 0))
        return changes

    def expire(self, now):
        """Send the held-back releases whose window has passed."""
        changes = []
        for control, due in list(self._pending.items()):
            if due <= now:
                del self._pending[control]
                self._sent[control] = False
                changes.append((self._buttons[control], 0))
        return changes

    def next_deadline(self):
        return min(self._pending.values(), default=None)

    def reset(self, keys, abs_values, now):
        """Replace the raw state, e.g. after a reconnect or SYN_DROPPED."""
        self._keys = set(keys)
        self._abs = dict(abs_values)
        return self.flush(now)

    def release_all(self):
        """Release everything the game sees as held, e.g. when the mat is unplugged."""
        self._keys.clear()
        self._abs.clear()
        self._pending.clear()
        changes = [(self._buttons[c], 0) for c, held in self._sent.items() if held]
        self._sent = dict.fromkeys(self._sent, False)
        return changes
