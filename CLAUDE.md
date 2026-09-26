# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The repo is new. It holds only a stub `README.md`, and there is no code, build system, or tests yet. Update this file as those are added. Don't assume any commands exist until they are in the repo.

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
