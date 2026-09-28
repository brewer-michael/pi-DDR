"""USB and HID facts about an input device, read from sysfs.

These answer the two questions that decide a mat's input latency on Linux:
how often the Pi polls it, and whether ``usbhid.jspoll`` can speed that up
(it only applies to devices whose HID descriptor says "Joystick").
"""

import os

HID_USAGE_NAMES = {
    (0x01, 0x02): "Mouse",
    (0x01, 0x04): "Joystick",
    (0x01, 0x05): "Gamepad",
    (0x01, 0x06): "Keyboard",
    (0x01, 0x08): "Multi-axis controller",
}
JOYSTICK_USAGE = (0x01, 0x04)


def parse_hid_application_usage(descriptor):
    """(usage_page, usage) of the first top-level Application collection, or None."""
    i = 0
    depth = 0
    usage_page = 0
    usage = None
    usage_size = 0
    while i < len(descriptor):
        prefix = descriptor[i]
        if prefix == 0xFE:  # long item: prefix, data size, tag, data
            if i + 1 >= len(descriptor):
                break
            i += 3 + descriptor[i + 1]
            continue
        size = (0, 1, 2, 4)[prefix & 0x03]
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        data = int.from_bytes(descriptor[i + 1 : i + 1 + size], "little")
        i += 1 + size
        if item_type == 1 and tag == 0x0:  # Global: Usage Page
            usage_page = data
        elif item_type == 2 and tag == 0x0:  # Local: Usage
            usage, usage_size = data, size
        elif item_type == 0 and tag == 0xA:  # Main: Collection
            if depth == 0 and data == 0x01 and usage is not None:
                if usage_size == 4:  # extended usage carries its own page
                    return (usage >> 16, usage & 0xFFFF)
                return (usage_page, usage)
            depth += 1
            usage = None
        elif item_type == 0 and tag == 0xC:  # Main: End Collection
            depth = max(0, depth - 1)
            usage = None
        elif item_type == 0:  # other Main items clear local items
            usage = None
    return None


def usage_name(usage):
    if usage is None:
        return "unknown"
    return HID_USAGE_NAMES.get(tuple(usage), f"page 0x{usage[0]:02x} usage 0x{usage[1]:02x}")


def xhci_poll_interval_ms(binterval, speed_mbps):
    """Polling interval an xHCI controller actually uses for an interrupt endpoint.

    Full/low-speed devices give bInterval in ms and xHCI rounds it down to a
    power of two (10 ms becomes 8 ms). High-speed devices give an exponent:
    2**(bInterval-1) microframes of 125 us.
    """
    if binterval is None or speed_mbps is None or binterval < 1:
        return None
    if speed_mbps >= 480:
        return 0.125 * 2 ** (min(binterval, 16) - 1)
    exponent = min(max((8 * binterval).bit_length() - 1, 3), 10)
    return 2 ** exponent / 8.0


def _read_text(path):
    try:
        with open(path, encoding="ascii", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def _interrupt_in_binterval(interface_dir):
    try:
        entries = sorted(os.listdir(interface_dir))
    except OSError:
        return None
    for entry in entries:
        if not entry.startswith("ep_"):
            continue
        ep = os.path.join(interface_dir, entry)
        if _read_text(os.path.join(ep, "type")) == "Interrupt" and _read_text(
            os.path.join(ep, "direction")
        ) == "in":
            value = _read_text(os.path.join(ep, "bInterval"))
            try:
                return int(value, 16)
            except (TypeError, ValueError):
                return None
    return None


def describe_device_dir(device_dir):
    """Walk up from an input device's sysfs directory, collecting USB/HID facts.

    ``device_dir`` is the resolved ``/sys/class/input/eventN/device``. Missing
    facts stay None (for example on a Bluetooth or virtual device).
    """
    info = {
        "usb_port": None,
        "vid": None,
        "pid": None,
        "speed_mbps": None,
        "hid_usage": None,
        "binterval": None,
        "poll_ms": None,
    }
    path = os.path.abspath(device_dir)
    while True:
        if info["hid_usage"] is None:
            try:
                with open(os.path.join(path, "report_descriptor"), "rb") as f:
                    info["hid_usage"] = parse_hid_application_usage(f.read())
            except OSError:
                pass
        if info["binterval"] is None and os.path.isfile(os.path.join(path, "bInterfaceNumber")):
            info["binterval"] = _interrupt_in_binterval(path)
        vid = _read_text(os.path.join(path, "idVendor"))
        if vid is not None:
            info["vid"] = int(vid, 16)
            info["pid"] = int(_read_text(os.path.join(path, "idProduct")) or "0", 16)
            info["usb_port"] = os.path.basename(path)
            try:
                info["speed_mbps"] = float(_read_text(os.path.join(path, "speed")))
            except (TypeError, ValueError):
                pass
            break
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    info["poll_ms"] = xhci_poll_interval_ms(info["binterval"], info["speed_mbps"])
    return info


def describe_event_device(event_name, sys_root="/sys"):
    """USB/HID facts for ``/dev/input/<event_name>``."""
    link = os.path.join(sys_root, "class", "input", event_name, "device")
    return describe_device_dir(os.path.realpath(link))


def input_sysname(event_name, sys_root="/sys"):
    """The ``inputN`` node that owns ``eventN``."""
    link = os.path.join(sys_root, "class", "input", event_name, "device")
    return os.path.basename(os.path.realpath(link))


def joystick_nodes(input_name, sys_root="/sys"):
    """The classic joystick nodes (``jsN``) that the kernel's joydev made for ``inputN``."""
    path = os.path.join(sys_root, "class", "input", input_name)
    try:
        return sorted(name for name in os.listdir(path) if name.startswith("js"))
    except OSError:
        return []


def usbhid_jspoll(sys_root="/sys"):
    """Current ``usbhid.jspoll`` value in ms (0 = use the device's own bInterval)."""
    value = _read_text(os.path.join(sys_root, "module", "usbhid", "parameters", "jspoll"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
