# Bill of materials

Everything needed for a two-player setup: a Raspberry Pi 4 running Project
OutFox, two USB dance mats, and the stage that holds them. The TV and the 5.1
receiver are assumed to exist already. A machine-readable copy of this list is in
[`hardware/bom.csv`](../hardware/bom.csv).

Prices are rough 2026 US retail estimates, to help with budgeting. Check before
buying: Raspberry Pi prices in particular rose several times in 2025–26 as
memory got more expensive.

## Budget at a glance

| Section | Estimate | Notes |
|---|---|---|
| Game computer | $145 (2 GB Pi) to $190 (4 GB Pi) | About $90 if you already own a Pi 4 |
| Dance mats (2) | $50–80 | |
| Platform (stage) | about $210 | Plus tools you may already have |
| **Core total** | **about $415–480** | |
| Safety bars (optional) | about $160 | Both modules |
| Optical audio adapter | about $20 | Only if the receiver has no HDMI input |

## Game computer

| Qty | Item | Est. | Why / notes |
|---|---|---|---|
| 1 | Raspberry Pi 4 Model B, 2 GB or more | $55–100 | The decided platform. 2 GB ($55) runs OutFox; 3 GB ($83.75) or 4 GB (about $100) gives headroom for big song libraries and background videos. |
| 1 | Official Raspberry Pi 15 W USB-C power supply (5.1 V 3 A) | $8 | Weak phone chargers cause under-voltage throttling and USB dropouts: stutter and lost steps. |
| 1 | microSD card, 64 GB, A2 / U3 rated | $12 | Song packs are big; A2 cards load them noticeably faster. |
| 1 | Case with a heatsink or fan | $15 | The Pi 4 slows itself down near 80 °C, which shows up as dropped frames. |
| 1 | Micro-HDMI to HDMI cable, 2 m | $8 | The Pi 4 has micro-HDMI ports. Use **HDMI0**, the one next to the USB-C power port. It goes to the receiver's HDMI input. |
| 1 | USB keyboard | $15 | Setup, plus the F-key hotkeys during sync calibration. Borrow one if you like. |
| 2 | USB 2.0 extension, A-male to A-female, 3 m (10 ft) | $16 | Only if the Pi sits by the TV rather than the stage. Keep each run (mat cable plus extension) under 5 m (16 ft); longer needs an *active* extension. |
| 1 | Floor cable cover, about 6 ft | $15 | The mat cables cross the floor; don't trip on them. |

**Why the Pi sits by the receiver:** that keeps the HDMI run short and puts
only USB cables across the floor. The mats' own cables are typically about 1.7 m,
so a 3 m extension each gives about 4.7 m of reach, just inside USB 2.0's 5 m limit.

## Dance mats

| Qty | Item | Est. | Notes |
|---|---|---|---|
| 2 | USB dance mat, **PC version**, both the same model | $25–40 each | Example of the type: OSTENT USB non-slip mat, about 93 × 83 cm. |

Cheap mats vary a lot inside, even under the same brand name. What matters:

- **USB "PC" version.** Some listings are the "TV" version with built-in games
  and RCA plugs. You want the one that plugs into a computer's USB port.
- **Buy both at once, same model**, from a shop with easy returns, and test them
  the day they arrive:
  - `matprobe list` should say **HID type: Joystick**. Only those mats can be
    switched to 1 ms polling. "Gamepad" mats stay at their built-in rate,
    typically 8 ms, which adds up to ±4 ms of timing jitter. See
    [Mat polling](latency-and-sync.md#mat-polling).
  - `matprobe learn` checks that each arrow is its own input and that
    **LEFT+RIGHT and UP+DOWN jumps register**. Mats that report arrows like a
    D-pad can't do those jumps. Some have a mode button or key combo that fixes it.
  - `matprobe watch` reports **chatter** (one step read as two).
- **Avoid:** wireless or Bluetooth mats (tens of ms of variable delay), mats that
  act as a keyboard, and PS2/Wii mats on USB adapters (the adapter adds its own
  polling delay).
- **Size:** the stage plans are drawn for a 32-3/4 × 36-5/8 × 3/8 in mat and
  include formulas for any other size. Measure yours before cutting wood.

Upgrade path: thicker foam-insert soft mats feel better, and a USB hard pad works
too. Both plug into the same pad bridge, so only its config changes.

## Platform (stage for two mats)

Full plans: [platform-plans.md](platform-plans.md).

| Qty | Item | Est. | Notes |
|---|---|---|---|
| 1 | 3/4 in (18 mm) sanded plywood, 4 × 8 ft | $60 | Both bases. Pick the flattest sheet in the stack. |
| 1 | 1/2 in (12 mm) sanded plywood, 4 × 4 ft | $30 | Borders. Thickness = mat + underlay; see the table in the plans. |
| 1 | Wood glue (Titebond II), 8 oz | $6 | |
| 1 | #8 × 1 in flat-head wood screws, box of 100 | $8 | Length depends on border thickness (table in the plans). |
| 1 | Non-slip rug pad, 4 × 6 ft, about 1/8 in | $20 | Cut into the two underlays that stop the mats creeping. |
| 1 | Rubber-backed rug pad, 5 × 8 ft | $30 | Under the whole stage: grip, plus less stomp noise downstairs. |
| 1 | Floor and porch paint (1 qt) with anti-skid additive | $25 | Or water-based polyurethane plus clear anti-slip tape. |
| 1 | Wood filler; sandpaper 120 and 180 grit | $12 | |
| 2 | 4 in flat mending plates with screws | $6 | Join the two modules. |
| 1 | Adhesive cable clips | $6 | Strain relief for the mat cables. |
| 1 | Double-sided carpet tape (optional) | $8 | Only if a mat still shifts in its bay. |

**Tools:** circular saw and straightedge (or have the store cut the sheets),
drill/driver, countersink bit, 1/8 in bit, jigsaw or handsaw and chisel, sander,
clamps, square, tape measure; router with a 1/4 in roundover bit (optional).
Safety glasses, hearing protection, dust mask.

## Optional: safety bars (both modules)

| Qty | Item | Est. |
|---|---|---|
| 4 | 3/4 in black-iron floor flange | $36 |
| 6 | 3/4 × 30 in black-iron pipe (per module: two uprights, one bar) | $78 |
| 4 | 3/4 in black-iron 90° elbow | $16 |
| 16 | 1/4-20 × 2 in flat-head machine screw, washer, nylon lock nut | $12 |
| 2 | Grip tape or foam grips | $16 |

## Audio and video (already owned)

| Item | Notes |
|---|---|
| TV with HDMI and a Game Mode | Game Mode typically cuts the TV's own delay from 50–150 ms to 10–25 ms. |
| 5.1 AV receiver with HDMI in and out | The Pi sends plain stereo; the receiver upmixes it to 5.1 and passes video on to the TV. |
| HDMI cable, receiver to TV | |
| *If the receiver has no HDMI input:* USB audio adapter with optical (TOSLINK) out, about $20 | Audio goes out over optical, and a second HDMI cable runs from the Pi to the TV. See [latency-and-sync.md](latency-and-sync.md#if-the-receiver-has-no-hdmi-input). |

Do not use Bluetooth speakers or headphones anywhere in this chain. Their delay
is long and varies, so it can't be calibrated out.
