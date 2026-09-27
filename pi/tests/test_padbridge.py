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
from piddr.mapping import PLAYER_BUTTONS, STAGE_BUTTONS
from piddr.padbridge import VIRTUAL_NAME, Bridge, notify_systemd

AbsInfo = namedtuple("AbsInfo", "value min max fuzz flat resolution")
KEY, SYN = evcodes.EV_KEY, evcodes.EV_SYN
LEFT, RIGHT = PLAYER_BUTTONS[1]["left"], PLAYER_BUTTONS[1]["right"]
P2_LEFT, P2_UP = PLAYER_BUTTONS[2]["left"], PLAYER_BUTTONS[2]["up"]


class Event(SimpleNamespace):
    def timestamp(self):
        return self.t


def ev(etype, code, value, t=100.0):
    return Event(type=etype, code=code, value=value, t=t)


def report(*keys, t=100.0):
    return [ev(KEY, code, value, t) for code, value in keys] + [ev(SYN, evcodes.SYN_REPORT, 0, t)]


class FakePad:
    def __init__(self, name, events, event_n):
        self.name = name
        self.events = events
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
    AbsInfo = AbsInfo

    def __init__(self, mats=None):
        self.pads = []
        self.mats = mats or {}

    def UInput(self, events, name, vendor, product, version, bustype):
        pad = FakePad(name, events, 20 + len(self.pads))
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
    def _joystick_nodes(self, stage):
        return ["js0"]


def make_bridge(evdev, config_text):
    logs = []
    bridge = TestBridge(parse_config(config_text), evdev, log=logs.append, selector=FakeSelector())
    bridge.logs = logs
    return bridge


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

    def start(self, mat, p2_mat=None):
        mats = {self.p1_path: mat}
        if p2_mat is not None:
            open(self.p2_path, "w").close()
            mats[self.p2_path] = p2_mat
        self.fake = FakeEvdev(mats=mats)
        bridge = make_bridge(self.fake, CONFIG.format(p1=self.p1_path, p2=self.p2_path))
        bridge.start()
        return bridge

    def test_one_stage_for_both_players(self):
        bridge = self.start(FakeMat(self.p1_path))
        self.assertEqual(len(self.fake.pads), 1)
        stage = self.fake.pads[0]
        self.assertEqual(stage.name, VIRTUAL_NAME)
        self.assertEqual(stage.events[KEY], list(STAGE_BUTTONS))
        self.assertEqual([code for code, _ in stage.events[evcodes.EV_ABS]], [evcodes.ABS_X, evcodes.ABS_Y])
        self.assertTrue(all(player.pad is stage for player in bridge.players))
        self.assertTrue(any("virtual stage ready" in line and "js0" in line for line in bridge.logs))

    def test_forwards_reports_and_keeps_jumps_together(self):
        mat = FakeMat(self.p1_path)
        bridge = self.start(mat)
        p1, p2 = bridge.players
        self.assertTrue(bridge.connect(p1))
        self.assertTrue(mat.grabbed)
        self.assertFalse(bridge.connect(p2))  # P2's mat is not plugged in
        mat.queue = report((0x120, 1), (0x123, 1))
        bridge.pump(p1)
        self.assertEqual(bridge.pad.sent, [(LEFT, 1), (RIGHT, 1), "syn"])
        self.assertEqual(bridge.delays.count, 1)

    def test_player_two_drives_its_own_buttons(self):
        mat1, mat2 = FakeMat(self.p1_path), FakeMat(self.p2_path)
        bridge = self.start(mat1, mat2)
        p1, p2 = bridge.players
        self.assertTrue(bridge.connect(p1) and bridge.connect(p2))
        mat2.queue = report((0x120, 1), (0x122, 1))
        bridge.pump(p2)
        self.assertEqual(bridge.pad.sent, [(P2_LEFT, 1), (P2_UP, 1), "syn"])

    def test_unplugging_one_mat_leaves_the_other_player_alone(self):
        mat1, mat2 = FakeMat(self.p1_path), FakeMat(self.p2_path)
        bridge = self.start(mat1, mat2)
        p1, p2 = bridge.players
        bridge.connect(p1)
        bridge.connect(p2)
        mat1.queue = report((0x120, 1))
        mat2.queue = report((0x120, 1))
        bridge.pump(p1)
        bridge.pump(p2)
        mat1.fail = errno.ENODEV
        bridge.pump(p1)
        self.assertEqual(bridge.pad.sent[-2:], [(LEFT, 0), "syn"])
        self.assertNotIn((P2_LEFT, 0), bridge.pad.sent)
        self.assertEqual(p2.mapper.held(), {"left"})

    def test_already_held_arrow_is_sent_on_connect(self):
        mat = FakeMat(self.p1_path, keys=[0x120])
        bridge = self.start(mat)
        bridge.connect(bridge.players[0])
        self.assertEqual(bridge.pad.sent, [(LEFT, 1), "syn"])

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
        stage = bridge.pad
        bridge.close()
        self.assertEqual(stage.sent[-2:], [(PLAYER_BUTTONS[1]["down"], 0), "syn"])
        self.assertTrue(stage.closed)
        self.assertIsNone(bridge.pad)


class NotifyTest(unittest.TestCase):
    def test_no_socket_outside_systemd(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(notify_systemd())

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
