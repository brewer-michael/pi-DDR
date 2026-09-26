import errno
import os
import socket
import tempfile
import unittest
from collections import namedtuple
from types import SimpleNamespace
from unittest import mock

from piddr import evcodes, padbridge
from piddr.config import parse_config
from piddr.mapping import VIRTUAL_BUTTONS
from piddr.padbridge import Bridge, notify_systemd, sorts_before

AbsInfo = namedtuple("AbsInfo", "value min max fuzz flat resolution")
KEY, SYN = evcodes.EV_KEY, evcodes.EV_SYN
LEFT, RIGHT = VIRTUAL_BUTTONS["left"], VIRTUAL_BUTTONS["right"]


class Event(SimpleNamespace):
    def timestamp(self):
        return self.t


def ev(etype, code, value, t=100.0):
    return Event(type=etype, code=code, value=value, t=t)


def report(*keys, t=100.0):
    return [ev(KEY, code, value, t) for code, value in keys] + [ev(SYN, evcodes.SYN_REPORT, 0, t)]


class FakePad:
    def __init__(self, name, input_n, event_n):
        self.name = name
        self.sysnames = (f"input{input_n}", f"event{event_n}")
        self.device = SimpleNamespace(path=f"/dev/input/event{event_n}")
        self.sent = []
        self.closed = False

    def write(self, etype, code, value):
        self.sent.append((code, value))

    def syn(self):
        self.sent.append("syn")

    def close(self):
        self.closed = True


class FakeMat:
    def __init__(self, path, keys=(), axes=None):
        self.path = path
        self.name = "USB Gamepad"
        self.info = SimpleNamespace(vendor=0x0079, product=0x0011)
        self._keys = list(keys)
        self._axes = axes or {}
        self.queue = []
        self.fail = None  # errno raised by read()
        self.fail_state = None  # errno raised by the state queries
        self.grabbed = False
        self.closed = False

    def grab(self):
        self.grabbed = True

    def close(self):
        self.closed = True

    def capabilities(self, absinfo=True):
        return {evcodes.EV_ABS: list(self._axes.items())}

    def active_keys(self):
        if self.fail_state:
            raise OSError(self.fail_state, os.strerror(self.fail_state))
        return list(self._keys)

    def absinfo(self, code):
        if self.fail_state:
            raise OSError(self.fail_state, os.strerror(self.fail_state))
        return self._axes[code]

    def read(self):
        if self.fail:
            raise OSError(self.fail, os.strerror(self.fail))
        if not self.queue:
            raise BlockingIOError
        events, self.queue = self.queue, []
        return iter(events)


class FakeEvdev:
    """Hands out pads the way the kernel numbers them: input numbers only grow,
    event numbers reuse the lowest free slot."""

    AbsInfo = AbsInfo

    def __init__(self, next_input, next_event, mats=None):
        self.next_input = next_input
        self.free_from = next_event
        self.used_events = set()
        self.pads = []
        self.mats = mats or {}

    def UInput(self, events, name, vendor, product, version, bustype):
        event_n = self.free_from
        while event_n in self.used_events:
            event_n += 1
        self.used_events.add(event_n)
        pad = FakePad(name, self.next_input, event_n)
        self.next_input += 1
        original_close = pad.close

        def close():
            self.used_events.discard(event_n)
            original_close()

        pad.close = close
        self.pads.append(pad)
        return pad

    def InputDevice(self, path):
        return self.mats[path]


class FakeSelector:
    def __init__(self):
        self.registered = {}

    def register(self, fileobj, events, data):
        self.registered[id(fileobj)] = data

    def unregister(self, fileobj):
        del self.registered[id(fileobj)]


class TestBridge(Bridge):
    def _sysnames(self, pad):
        return pad.sysnames


def make_bridge(evdev, config_text):
    logs = []
    bridge = TestBridge(parse_config(config_text), evdev, log=logs.append, selector=FakeSelector())
    bridge.logs = logs
    return bridge


class OrderTest(unittest.TestCase):
    def test_sorts_before(self):
        self.assertTrue(sorts_before("input8", "input9"))
        self.assertFalse(sorts_before("input9", "input10"))  # right by number, wrong as text
        self.assertTrue(sorts_before("input10", "input11"))
        self.assertFalse(sorts_before("event3", "event2"))

    def test_retries_until_p1_sorts_first(self):
        for next_input, next_event in ((5, 3), (9, 3), (8, 9), (99, 9)):
            fake = FakeEvdev(next_input, next_event)
            bridge = make_bridge(fake, CONFIG.format(p1="/x", p2="/y"))
            pads = bridge.create_pads()
            p1, p2 = pads[1].sysnames, pads[2].sysnames
            for a, b in zip(p1, p2):
                self.assertTrue(sorts_before(a, b), (next_input, next_event, p1, p2))
            self.assertEqual(pads[1].name, "pi-DDR P1")
            placeholders = [p for p in fake.pads if p.name == "pi-DDR placeholder"]
            self.assertTrue(all(p.closed for p in placeholders))
            self.assertFalse(pads[1].closed or pads[2].closed)


CONFIG = """
[bridge]
mat_ids = 0079:0011
release_debounce_ms = {debounce}
[player1]
device = {p1}
left = BTN_TRIGGER
down = BTN_THUMB
up = BTN_THUMB2
right = BTN_TOP
[player2]
device = {p2}
left = BTN_TRIGGER
down = BTN_THUMB
up = BTN_THUMB2
right = BTN_TOP
""".replace("{debounce}", "0")


class ForwardingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p1_path = os.path.join(self.tmp.name, "p1")
        self.p2_path = os.path.join(self.tmp.name, "p2")
        open(self.p1_path, "w").close()  # connect() only needs the path to exist

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, mat):
        fake = FakeEvdev(20, 5, mats={self.p1_path: mat})
        bridge = make_bridge(fake, CONFIG.format(p1=self.p1_path, p2=self.p2_path))
        bridge.start()
        return bridge

    def test_forwards_reports_and_keeps_jumps_together(self):
        mat = FakeMat(self.p1_path)
        bridge = self.start(mat)
        p1, p2 = bridge.players
        self.assertTrue(bridge.connect(p1))
        self.assertTrue(mat.grabbed)
        self.assertFalse(bridge.connect(p2))  # P2's mat is not plugged in
        mat.queue = report((0x120, 1), (0x123, 1))
        bridge.pump(p1)
        self.assertEqual(p1.pad.sent, [(LEFT, 1), (RIGHT, 1), "syn"])
        self.assertEqual(p2.pad.sent, [])
        self.assertEqual(bridge.delays.count, 1)

    def test_already_held_arrow_is_sent_on_connect(self):
        mat = FakeMat(self.p1_path, keys=[0x120])
        bridge = self.start(mat)
        bridge.connect(bridge.players[0])
        self.assertEqual(bridge.players[0].pad.sent, [(LEFT, 1), "syn"])

    def test_unplug_releases_held_arrows(self):
        mat = FakeMat(self.p1_path)
        bridge = self.start(mat)
        p1 = bridge.players[0]
        bridge.connect(p1)
        mat.queue = report((0x120, 1))
        bridge.pump(p1)
        mat.fail = errno.ENODEV
        bridge.pump(p1)
        self.assertIsNone(p1.dev)
        self.assertTrue(mat.closed)
        self.assertEqual(p1.pad.sent[-2:], [(LEFT, 0), "syn"])
        self.assertEqual(bridge.selector.registered, {})
        self.assertTrue(any("unplugged" in line for line in bridge.logs))

    def test_dropped_events_resync_from_device_state(self):
        mat = FakeMat(self.p1_path)
        bridge = self.start(mat)
        p1 = bridge.players[0]
        bridge.connect(p1)
        mat._keys = [0x123]  # what the kernel says is held after the overflow
        mat.queue = [ev(SYN, evcodes.SYN_DROPPED, 0), ev(KEY, 0x120, 1)] + report()
        bridge.pump(p1)
        self.assertEqual(p1.pad.sent, [(RIGHT, 1), "syn"])

    def test_mat_vanishing_while_connecting_is_not_fatal(self):
        mat = FakeMat(self.p1_path)
        mat.fail_state = errno.ENODEV
        bridge = self.start(mat)
        p1 = bridge.players[0]
        self.assertFalse(bridge.connect(p1))
        self.assertIsNone(p1.dev)
        self.assertTrue(mat.closed)
        self.assertEqual(bridge.selector.registered, {})

    def test_mat_vanishing_during_resync_is_not_fatal(self):
        mat = FakeMat(self.p1_path)
        bridge = self.start(mat)
        p1 = bridge.players[0]
        bridge.connect(p1)
        mat.fail_state = errno.ENODEV
        mat.queue = [ev(SYN, evcodes.SYN_DROPPED, 0)] + report((0x120, 1)) + report((0x123, 1))
        bridge.pump(p1)
        self.assertIsNone(p1.dev)
        self.assertEqual(p1.pad.sent, [])

    def test_stray_mat_check_only_rescans_on_change(self):
        bridge = self.start(FakeMat(self.p1_path))
        stray = "/dev/input/by-path/platform-usb-0:1.1:1.0-event-joystick"
        links = [stray]
        calls = []

        def describe(event):
            calls.append(event)
            return {"vid": 0x0079, "pid": 0x0011}

        with mock.patch.object(padbridge.glob, "glob", lambda pattern: list(links)), mock.patch.object(
            padbridge.sysfs, "describe_event_device", describe
        ):
            bridge._warn_stray_mats()
            bridge._warn_stray_mats()
            self.assertEqual(len(calls), 1)
            self.assertEqual(sum("not P1 or P2" in line for line in bridge.logs), 1)
            links.clear()  # unplugged...
            bridge._warn_stray_mats()
            links.append(stray)  # ...and plugged into the wrong port again
            bridge._warn_stray_mats()
            self.assertEqual(sum("not P1 or P2" in line for line in bridge.logs), 2)

    def test_close_releases_everything(self):
        mat = FakeMat(self.p1_path)
        bridge = self.start(mat)
        p1 = bridge.players[0]
        bridge.connect(p1)
        mat.queue = report((0x121, 1))
        bridge.pump(p1)
        pads = list(bridge.pads.values())
        bridge.close()
        self.assertEqual(p1.pad.sent[-2:], [(VIRTUAL_BUTTONS["down"], 0), "syn"])
        self.assertTrue(all(p.closed for p in pads))


class NotifyTest(unittest.TestCase):
    def test_no_socket_outside_systemd(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(notify_systemd())

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "needs Unix sockets")
    def test_sends_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "notify")
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
                server.bind(path)
                with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": path}):
                    self.assertTrue(notify_systemd())
                self.assertEqual(server.recv(64), b"READY=1")


if __name__ == "__main__":
    unittest.main()
