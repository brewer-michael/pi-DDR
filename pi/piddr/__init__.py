"""pi-DDR tools for the Raspberry Pi.

- ``piddr.matprobe``: inspect USB dance mats (polling rate, button layout)
  and write the pad bridge config.
- ``piddr.padbridge``: daemon that turns the two physical mats into two
  virtual pads that the game always sees as P1 and P2.

Needs Python 3 and python3-evdev from Raspberry Pi OS; ``pi/install.sh``
installs both.
"""
