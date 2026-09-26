# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The plans and the Pi-side tooling are written, but **none of it has run on the real hardware yet**: no Pi, mats, receiver or stage has been tested. Treat the items under "Not yet verified on hardware" as open until someone confirms them on the Pi, and update this file when they are.

## Project goal

This is a DIY home dance-game (DDR-style) setup:

- **Input:** two inexpensive USB dance mats, one per player.
- **Platform:** a sturdy platform built to hold the mats in place. This is a physical build, so the repo may hold plans, measurements, and bills of materials alongside code.
- **Brain:** a Raspberry Pi 4 runs the game.
- **Video:** the TV connects over HDMI.
- **Audio:** a 5.1-channel surround system connects to the Pi's audio output.

## Game engine (decided)

**Project OutFox** (a fork of StepMania 5.1) runs on the Pi. It was chosen because it officially supports the Raspberry Pi and is optimized for single-board ARM systems.

- It's distributed as a `.tar.gz` for Linux, from https://projectoutfox.com/downloads (also installable through Pi-Apps).
- Recommended OS: the latest **64-bit Raspberry Pi OS**.
- Install guide: https://outfox.wiki/en/user-guide/setup/install-linux
- OutFox is not fully open source. Customize it through its config files, themes, noteskins, and songs/simfiles, not by patching the engine.
- Use OutFox's own settings for input mapping (P1/P2 pads) and the global audio offset.

## Constraints to keep in mind

- **Target hardware is a Raspberry Pi 4 (ARM64 Linux).** Development happens on a Windows machine, so scripts that run on the Pi must be POSIX/Linux shell or cross-platform. Don't write Windows-only tooling for anything that runs on the device.
- **Audio path (decided):** the Pi outputs plain **stereo**, and the receiver upmixes it to 5.1. This was chosen for low latency. Don't add multichannel output, surround encoding, or channel-mapping config on the Pi. Keep the Pi's audio chain as direct as possible (for example, ALSA straight to the device, no extra resampling or effects). Any remaining audio delay comes from the receiver's upmix processing, so fix it with the game's global audio offset calibration rather than on the Pi.
- **Two-player input:** both USB mats must be told apart consistently as P1 and P2, even after reboots or replugging. Stable device naming (for example, udev rules) matters.
- **Latency:** input and audio latency on the Pi directly affect whether the game is playable, so treat them as primary concerns.

## Decisions made since (with the reasons)

- **P1/P2 go through the pad bridge, not udev alone.** The StepMania 5.1 code OutFox grew from numbers pads by sorting `/sys/class/input/inputN` names as text, and it ignores udev symlinks. `pi/piddr/padbridge.py` creates the virtual pads "pi-DDR P1"/"P2" at boot and feeds each from a fixed USB port (`/dev/input/by-path`). A generated udev rule (65-pi-ddr-raw-mats.rules) hides the raw mats from the game. Don't replace this with symlink-only udev rules.
- **Virtual pad layout is a contract:** control `i` in `CONTROLS` (`pi/piddr/mapping.py`) is sent as `BTN_JOYSTICK + i`, which is joystick button `i+1` in the game. The pads also carry idle ABS_X/ABS_Y axes, because SM5.1's Linux input code ignores devices without an X axis. Changing either breaks users' OutFox key maps.
- **Audio device:** OutFox `SoundDrivers=ALSA-sw`, `SoundDevice=hdmi:CARD=vc4hdmi0,DEV=0` (HDMI0 into the receiver's HDMI input; video passes through the receiver to the TV), `SoundPreferredSampleRate=48000`. No PipeWire or PulseAudio, which is why the setup uses Pi OS Lite with a bare X session (`pi/setup/xinitrc`) instead of a desktop.
- **Mat polling:** `usbhid.jspoll=1` on the kernel command line. It only affects mats whose HID descriptor says Joystick (not Gamepad), and only when the device binds.
- **Stage:** two modules (P1 left, P2 right, facing the TV), each a 3/4 in plywood base with plywood borders as thick as the mat plus underlay, forming a bay with 1/8 in clearance. Dimensions derive from measured mat size; the formulas are in `docs/platform-plans.md`.

## Repository layout

- `docs/`: `bill-of-materials.md`, `platform-plans.md`, `latency-and-sync.md` (includes the Pi setup runbook). Drawings are hand-written SVGs in `docs/img/`.
- `hardware/bom.csv`: machine-readable BOM. **Keep it in sync with `docs/bill-of-materials.md`** (items, quantities, prices).
- `pi/piddr/`: Python package run on the Pi.
  - `evcodes`, `mapping`, `timing`, `sysfs`, `config` are stdlib-only and pure.
  - `matprobe` and `padbridge` import python-evdev lazily, via `evcodes.require_evdev()`.
- `pi/tests/`: unittest suite for the pure modules, plus the bridge with fake evdev objects.
- `pi/padbridge/`: systemd unit, installer, example config.
- `pi/setup/`: `configure-pi.sh` (kernel cmdline, CPU governor, audio priority limits), `xinitrc`.
- `pi/outfox/`: recommended OutFox preferences and `apply-prefs.sh`.

## Commands

- Tests (any OS, no evdev needed): `cd pi && python3 -m unittest discover -s tests`
- Lint shell scripts: `shellcheck -s sh pi/setup/configure-pi.sh pi/padbridge/install.sh pi/outfox/apply-prefs.sh pi/setup/xinitrc`
- On the Pi (from `pi/`):
  - `sudo python3 -m piddr.matprobe list|watch|learn`
  - `python3 -m piddr.padbridge --config FILE --check|--print-udev-rules`
- Preview system changes: `sh pi/setup/configure-pi.sh --dry-run`

## Conventions

- Shell scripts that run on the Pi are POSIX `sh` (no bashisms), idempotent, and must pass shellcheck.
- Keep the pure Python modules free of third-party imports so the tests run on Windows.
- Physical dimensions: inches first with metric in parentheses. They are based on the reference mat (32-3/4 × 36-5/8 × 3/8 in), always with the formula alongside.
- SVG drawings need an explicit white background rect so they read on GitHub dark mode. Render them to check after editing: headless Chromium with a viewport about 100 px taller than the SVG.
- Claims about OutFox internals are inferred from the StepMania 5.1 source (OutFox is closed). Say so where it matters, and cite the file.

## Not yet verified on hardware

- OutFox (current Pi build) still uses `ALSA-sw`/`SoundDevice`/`SoundPreferredSampleRate`, the SM5.1 input enumeration, and `VisualDelaySeconds` as described.
- The pad bridge on a real Pi 4: uinput creation, ordering retry, forwarding delay numbers.
- The udev rule actually hides the raw mats from the game user (`TAG-="uaccess"` and `ENV{ID_INPUT_JOYSTICK}=""` at priority 65).
- The chosen mats report HID usage Joystick and can register LEFT+RIGHT jumps.
