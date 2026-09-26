# pi-DDR

A home DDR-style dance game for two players:

- **Game:** a Raspberry Pi 4 running Project OutFox.
- **Mats:** two inexpensive USB dance mats, held in place by a wooden stage.
- **Picture:** the TV, over HDMI.
- **Sound:** a 5.1 surround receiver. The Pi sends stereo and the receiver upmixes it.

```
 Mat P1 ─┐  USB (1 ms polling)                     HDMI (stereo + video)
         ├──> Raspberry Pi 4 ── pad bridge ── OutFox ───────> AV receiver ──> 5.1 speakers
 Mat P2 ─┘    (Pi OS Lite, no desktop)                         (upmix)   └──> TV (Game Mode)
```

## Documents

| | |
|---|---|
| [Bill of materials](docs/bill-of-materials.md) | Everything to buy, with rough 2026 prices (about $405–480 for the core build). CSV copy: [`hardware/bom.csv`](hardware/bom.csv). |
| [Platform plans](docs/platform-plans.md) | The two-module stage that holds the mats: dimensions, formulas for your mat size, cut list, drawings, build steps, optional safety bars. |
| [Latency and sync](docs/latency-and-sync.md) | How the game, the mats and the audio stay in sync, what to configure, how to calibrate, and troubleshooting. Includes the full Pi setup, in order. |

## What runs on the Pi

| Path | What it does |
|---|---|
| [`pi/setup/configure-pi.sh`](pi/setup/configure-pi.sh) | System tuning: 1 ms mat polling, CPU at full clock, audio thread priority, pinned HDMI mode. |
| [`pi/piddr/matprobe.py`](pi/piddr/matprobe.py) | Checks mats (HID type, real polling rate, chatter, jumps) and writes the pad bridge config. |
| [`pi/piddr/padbridge.py`](pi/piddr/padbridge.py) + [`pi/padbridge/`](pi/padbridge/) | Service that presents the mats to the game as two fixed virtual pads, so P1 and P2 never swap. |
| [`pi/outfox/`](pi/outfox/) | Recommended OutFox audio and input preferences, and a script that merges them in. |
| [`pi/setup/xinitrc`](pi/setup/xinitrc) | Boots straight into OutFox on a bare X server. |

## Build order

1. **Buy** the parts ([BOM](docs/bill-of-materials.md)). Test both mats with `matprobe`
   the day they arrive, while they can still be returned.
2. **Set up the Pi** ([Setup, in order](docs/latency-and-sync.md#setup-in-order)).
3. **Build the stage** ([plans](docs/platform-plans.md)). Measure your mats before
   cutting anything.
4. **Configure the receiver and TV**, then **calibrate**
   ([Calibration](docs/latency-and-sync.md#calibration)).

## Development

The Pi tools are Python 3 and POSIX `sh`. Their core logic has no third-party
dependencies, so the tests run anywhere, including Windows:

```sh
cd pi
python3 -m unittest discover -s tests
```

On the Pi, `matprobe` and the pad bridge also need `python3-evdev`.
