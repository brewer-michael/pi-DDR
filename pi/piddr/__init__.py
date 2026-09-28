"""pi-DDR tools for the Raspberry Pi.

- ``piddr.matprobe``: inspect USB dance mats (polling rate, button layout)
  and write the pad bridge config.
- ``piddr.padbridge``: daemon that turns the two physical mats into one
  virtual joystick, "pi-DDR Stage", with P1 on buttons 1-11 and P2 on 12-22.

Needs Python 3 and python3-evdev from Raspberry Pi OS; ``pi/install.sh``
installs both.
"""
