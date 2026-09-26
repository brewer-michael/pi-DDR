"""Pad bridge configuration (an INI file, normally /etc/pi-ddr/padbridge.conf)."""

import configparser
from dataclasses import dataclass, field

from .mapping import CONTROLS, REQUIRED_CONTROLS, format_source, parse_sources

PLAYER_SECTIONS = ("player1", "player2")


class ConfigError(ValueError):
    pass


@dataclass
class PlayerConfig:
    number: int
    device: str
    mapping: dict = field(default_factory=dict)  # control -> tuple of Source


@dataclass
class BridgeConfig:
    players: list
    release_debounce_ms: float = 0.0
    stats_interval_s: float = 300.0
    mat_ids: list = field(default_factory=list)  # [(vid, pid)]


def parse_mat_ids(text):
    """Parse ``0079:0011, 12ba:0100`` into ``[(0x0079, 0x0011), (0x12ba, 0x0100)]``."""
    ids = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        vid, sep, pid = part.partition(":")
        try:
            if not sep:
                raise ValueError
            ids.append((int(vid, 16), int(pid, 16)))
        except ValueError:
            raise ConfigError(f"mat_ids: expected vendor:product in hex like 0079:0011, got {part!r}")
    return ids


def _number(section, key, default):
    try:
        return section.getfloat(key, fallback=default)
    except ValueError:
        raise ConfigError(f"[{section.name}] {key} must be a number")


def parse_config(text):
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        parser.read_string(text)
    except configparser.Error as e:
        raise ConfigError(str(e))

    bridge = parser["bridge"] if parser.has_section("bridge") else parser[parser.default_section]
    config = BridgeConfig(
        players=[],
        release_debounce_ms=_number(bridge, "release_debounce_ms", 0.0),
        stats_interval_s=_number(bridge, "stats_interval_s", 300.0),
        mat_ids=parse_mat_ids(bridge.get("mat_ids", "")),
    )

    allowed = set(CONTROLS) | {"device"} | set(parser.defaults())
    for number, name in enumerate(PLAYER_SECTIONS, start=1):
        if not parser.has_section(name):
            continue
        section = parser[name]
        unknown = sorted(set(section) - allowed)
        if unknown:
            raise ConfigError(
                f"[{name}] unknown keys: {', '.join(unknown)} (controls are: {', '.join(CONTROLS)})"
            )
        device = section.get("device", "").strip()
        if not device:
            raise ConfigError(f"[{name}] device is required (a /dev/input/by-path/... link)")
        mapping = {}
        for control in CONTROLS:
            value = section.get(control, "").strip()
            if value:
                try:
                    mapping[control] = parse_sources(value)
                except ValueError as e:
                    raise ConfigError(f"[{name}] {control}: {e}")
        missing = [c for c in REQUIRED_CONTROLS if c not in mapping]
        if missing:
            raise ConfigError(f"[{name}] missing required controls: {', '.join(missing)}")
        owner = {}
        for control, sources in mapping.items():
            for source in sources:
                if source in owner:
                    raise ConfigError(
                        f"[{name}] {format_source(source)} is mapped to both {owner[source]} and {control}"
                    )
                owner[source] = control
        config.players.append(PlayerConfig(number, device, mapping))

    if not config.players:
        raise ConfigError("no [player1] or [player2] section")
    devices = [p.device for p in config.players]
    if len(set(devices)) != len(devices):
        raise ConfigError("player1 and player2 use the same device; each mat needs its own USB port")
    return config


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return parse_config(f.read())


def format_config(config):
    """Render a config file (used by ``matprobe learn``)."""
    ids = ", ".join(f"{vid:04x}:{pid:04x}" for vid, pid in config.mat_ids)
    lines = [
        "# pi-DDR pad bridge config. Written by `matprobe learn`; safe to edit.",
        "# Syntax: control = input[, input...]. An input is a button name",
        "# (BTN_TRIGGER, key:300) or an axis direction (ABS_HAT0X-, ABS_Y+).",
        "",
        "[bridge]",
        "# USB vendor:product of the raw mats. The udev rule built from this hides",
        "# the raw mats from the game so it only sees the two virtual pads.",
        f"mat_ids = {ids}",
        "# Hold back releases this long to swallow contact chatter (0 = off).",
        "# Presses are never delayed. Try 10-20 if matprobe reports chatter.",
        f"release_debounce_ms = {config.release_debounce_ms:g}",
        f"stats_interval_s = {config.stats_interval_s:g}",
    ]
    for player in config.players:
        lines += ["", f"[player{player.number}]", f"device = {player.device}"]
        for control in CONTROLS:
            sources = player.mapping.get(control)
            if sources:
                lines.append(f"{control} = {', '.join(format_source(s) for s in sources)}")
    return "\n".join(lines) + "\n"


def udev_rules(mat_ids):
    """udev rules that hide the raw mats from everything except root (the bridge).

    The game must only see the virtual pads: if it could also open the raw
    mats it would count four pads and the P1/P2 order would drift again.
    Runs at priority 65: after 60-persistent-input.rules has made the stable
    /dev/input/by-path links the bridge uses, before 70-uaccess.rules would
    hand the desktop user access to "joysticks". MODE and GROUP use ":=" so
    they stick: Raspberry Pi OS's 99-com.rules later sets every input device
    to root:input 0660, and the default user is in the input group.
    """
    lines = [
        "# Generated by `python3 -m piddr.padbridge --print-udev-rules`.",
        "# Hides raw dance mats from the game; pi-ddr-padbridge re-exposes them",
        "# as the virtual pads 'pi-DDR P1' and 'pi-DDR P2'.",
    ]
    for vid, pid in mat_ids:
        match = f'SUBSYSTEM=="input", ATTRS{{idVendor}}=="{vid:04x}", ATTRS{{idProduct}}=="{pid:04x}"'
        lines.append(f'{match}, ENV{{ID_INPUT_JOYSTICK}}="", MODE:="0600", GROUP:="root"')
        lines.append(f'{match}, TAG-="uaccess"')
    return "\n".join(lines) + "\n"
