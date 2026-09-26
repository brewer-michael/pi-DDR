"""pi-DDR helpers that run on the Raspberry Pi.

- ``piddr.matprobe``: inspect USB dance mats (polling rate, button layout)
  and write the pad bridge config.
- ``piddr.padbridge``: daemon that turns the two physical mats into two
  virtual pads that the game always sees as P1 and P2.

The modules ``evcodes``, ``mapping``, ``timing``, ``sysfs`` and ``config``
are pure Python with no third-party imports, so their tests also run on the
Windows development machine. Only ``matprobe`` and ``padbridge`` need
python-evdev, and they import it lazily.
"""
