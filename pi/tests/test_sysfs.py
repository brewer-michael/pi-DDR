import os
import tempfile
import unittest

from piddr import sysfs

JOYSTICK = bytes.fromhex("05 01 09 04 a1 01 15 00 25 01 75 01 95 0c 05 09 19 01 29 0c 81 02 c0")
GAMEPAD = bytes.fromhex("05 01 09 05 a1 01 c0")
KEYBOARD = bytes.fromhex("05 01 09 06 a1 01 c0")


class HidDescriptorTest(unittest.TestCase):
    def test_top_level_usage(self):
        self.assertEqual(sysfs.parse_hid_application_usage(JOYSTICK), (0x01, 0x04))
        self.assertEqual(sysfs.parse_hid_application_usage(GAMEPAD), (0x01, 0x05))
        self.assertEqual(sysfs.usage_name(sysfs.parse_hid_application_usage(KEYBOARD)), "Keyboard")

    def test_extended_usage_and_long_item(self):
        long_item = bytes.fromhex("fe 02 10 aa bb")
        extended = bytes.fromhex("0b 04 00 01 00 a1 01 c0")  # Usage 0x0001_0004 (4-byte form)
        self.assertEqual(sysfs.parse_hid_application_usage(long_item + extended), (0x01, 0x04))

    def test_nested_collections_do_not_confuse_it(self):
        desc = bytes.fromhex("05 01 09 05 a1 01 09 01 a1 00 c0 c0 05 01 09 04 a1 01 c0")
        self.assertEqual(sysfs.parse_hid_application_usage(desc), (0x01, 0x05))

    def test_garbage(self):
        self.assertIsNone(sysfs.parse_hid_application_usage(b""))
        self.assertIsNone(sysfs.parse_hid_application_usage(bytes.fromhex("09 04 c0")))


class PollIntervalTest(unittest.TestCase):
    def test_full_speed_rounds_down_to_power_of_two(self):
        self.assertEqual(sysfs.xhci_poll_interval_ms(1, 12), 1.0)
        self.assertEqual(sysfs.xhci_poll_interval_ms(4, 12), 4.0)
        self.assertEqual(sysfs.xhci_poll_interval_ms(10, 12), 8.0)
        self.assertEqual(sysfs.xhci_poll_interval_ms(10, 1.5), 8.0)
        self.assertEqual(sysfs.xhci_poll_interval_ms(255, 12), 128.0)

    def test_high_speed_is_an_exponent(self):
        self.assertEqual(sysfs.xhci_poll_interval_ms(1, 480), 0.125)
        self.assertEqual(sysfs.xhci_poll_interval_ms(4, 480), 1.0)

    def test_unknown(self):
        self.assertIsNone(sysfs.xhci_poll_interval_ms(None, 12))
        self.assertIsNone(sysfs.xhci_poll_interval_ms(10, None))


def write(path, content, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        f.write(content)


class DescribeDeviceTest(unittest.TestCase):
    def test_walks_up_from_the_input_node(self):
        with tempfile.TemporaryDirectory() as root:
            usb_dev = os.path.join(root, "devices", "usb1", "1-1", "1-1.3")
            iface = os.path.join(usb_dev, "1-1.3:1.0")
            hid = os.path.join(iface, "0003:0079:0011.0001")
            input_dir = os.path.join(hid, "input", "input5")
            os.makedirs(input_dir)
            write(os.path.join(usb_dev, "idVendor"), "0079\n")
            write(os.path.join(usb_dev, "idProduct"), "0011\n")
            write(os.path.join(usb_dev, "speed"), "12\n")
            write(os.path.join(iface, "bInterfaceNumber"), "00\n")
            write(os.path.join(iface, "ep_02", "type"), "Interrupt\n")
            write(os.path.join(iface, "ep_02", "direction"), "out\n")
            write(os.path.join(iface, "ep_02", "bInterval"), "01\n")
            write(os.path.join(iface, "ep_81", "type"), "Interrupt\n")
            write(os.path.join(iface, "ep_81", "direction"), "in\n")
            write(os.path.join(iface, "ep_81", "bInterval"), "0a\n")
            write(os.path.join(hid, "report_descriptor"), JOYSTICK, mode="wb")

            info = sysfs.describe_device_dir(input_dir)
            self.assertEqual(info["usb_port"], "1-1.3")
            self.assertEqual((info["vid"], info["pid"]), (0x0079, 0x0011))
            self.assertEqual(info["hid_usage"], sysfs.JOYSTICK_USAGE)
            self.assertEqual(info["binterval"], 10)
            self.assertEqual(info["poll_ms"], 8.0)

    def test_virtual_device_has_no_usb_facts(self):
        with tempfile.TemporaryDirectory() as root:
            input_dir = os.path.join(root, "devices", "virtual", "input", "input30")
            os.makedirs(input_dir)
            info = sysfs.describe_device_dir(input_dir)
            self.assertIsNone(info["usb_port"])
            self.assertIsNone(info["poll_ms"])

    def test_jspoll(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(sysfs.usbhid_jspoll(root))
            write(os.path.join(root, "module", "usbhid", "parameters", "jspoll"), "1\n")
            self.assertEqual(sysfs.usbhid_jspoll(root), 1)


if __name__ == "__main__":
    unittest.main()
