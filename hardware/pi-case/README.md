# Pi cases

Two 3D-printed cases for the Raspberry Pi 4 that look like little karaoke
speakers. Both are made for a heatsink with its own fan, and both are
parametric OpenSCAD files (2021.01 or newer) you export STLs from.

| | [Karaoke column](karaoke-column.scad) | [Karaoke speaker](karaoke-case.scad) |
|---|---|---|
| Use it | Mounted on the stage's front border | Free-standing, next to the TV (the simple version) |
| Size | 4-1/16 × 1-7/16 × 5-13/16 in tall, with tabs and handle (104 × 36 × 148 mm) | 2-11/16 × 1-7/16 × 4-1/2 in tall (68 × 36 × 115 mm) |
| Filament (PETG, printed solid) | about 77 g (shell 56 g, plate 21 g), plus a 5 g drilling template | about 52 g |
| Cables | All leave from the back: mat USB through a slot at the bottom, HDMI and power down the side on cradles and zip-tie anchors | USB out of the top, HDMI and power out of the right side |
| Mounting | Two keyhole tabs and a lock screw | Stands on two feet |

Both assume a cooler 16 mm tall (flush with the USB ports). If yours is
taller, measure it from the top of the Pi's board and set `cooler_h`; the
case gets deeper by the same amount.

## Karaoke column (stage-mounted)

- **Inside:** the Pi faces the front, upside down. The fan on its heatsink sits
  8 mm behind the upper woofer and draws air in through it; warm air rises out
  of the top vents. The USB ports point down into a plinth, which the lower
  woofer vents.
- **Mat cables:** plug in from below, loop in the plinth, are zip-tied to the
  back plate just above the slot, and leave through the slot at the bottom of
  the back plate. A tug on a mat cable pulls on the case, not on the USB port.
- **HDMI and power** come out of the left side (seen from the front). Use HDMI0,
  the micro-HDMI next to USB-C. Each plug rests on a cradle, and three zip-tie
  anchors carry the cables down the side to the back, so nothing hangs on the
  micro-HDMI port.
- **SD card:** reachable through the slot in the top.

### Print

```sh
openscad -D 'part="print"' -o karaoke-column.stl karaoke-column.scad
openscad -D 'part="template"' -o karaoke-column-template.stl karaoke-column.scad
```

The first is both parts side by side (182 × 148 mm): the shell face down, the
back plate flat with its standoffs up. No supports: the grilles, handle,
cradles, anchors and keyhole tabs all start on the bed or slope at 45°.
0.4 mm nozzle, 0.2 mm layers, 4 walls. The template is a 1.2 mm plate.

### Parts

- 4 M2.5 × 6 mm screws for the Pi (or the cooler kit's own screws; the
  standoff holes run through the plate)
- 3 M2.5 × 8 mm self-tapping screws for the back plate
- 3 #6 × 5/8 in pan-head wood screws for the border (two keyholes, one lock)
- 5 small zip ties, 3 mm wide (two for the mat cables, three down the side)

### Assemble and mount

1. Screw the Pi, with its cooler, onto the back plate's standoffs, SD-card end
   toward the end of the plate with the engraved name.
2. Plug both mat cables into the lower USB ports. Zip-tie each one to the back
   plate through the pair of slots above the bottom slot, with a little slack
   between the tie and the plug.
3. Slide the plate and Pi into the shell from behind (the side connectors go
   into the window, the SD card into the top slot) and screw the plate on.
4. Plug in HDMI and power through the side window, rest the plugs on the
   cradles, and zip-tie the cables to the anchors.
5. Lay the template on the front border where the case should stand (FRONT
   toward the players), and drill 3/32 in pilot holes through its three holes.
6. Drive the two keyhole screws until their heads stand about 2 mm (5/64 in)
   above the wood. Set the case down with the heads in the round holes, slide
   it toward the right (seen from the front) until it stops, then drive the
   lock screw through the right tab.

To take it off, remove the lock screw and slide the case back to the left.

## Karaoke speaker (simple)

The board stands upright behind the woofer with its parts facing the front;
the back plate is the standoff mount. USB and Ethernet come out of the top,
USB-C power, both micro-HDMI and audio out of the right side.

```sh
openscad -D 'part="print"' -o karaoke-case.stl karaoke-case.scad
```

Parts: 4 M2.5 × 6 mm screws for the Pi, 3 M2.5 × 8 mm self-tapping screws for
the plate. Screw the Pi onto the plate (SD-card end toward the engraved name),
slide it into the shell from behind, and screw the plate on. The SD card can be
reached through the slot in the bottom.

## Checking a change

Each file can render the overlap between the case and a stand-in Pi, in place
(`check_fit`) and along the path it slides in on (`check_slide`). After any
change, both should render empty, apart from a flat, zero-volume contact where
the board sits on the standoffs:

```sh
openscad -D 'part="check_slide"' -o slide.stl karaoke-column.scad
openscad -D 'part="check_fit"' -o fit.stl karaoke-column.scad
```

`part="shell"` and `part="plate"` export the parts one at a time, but each
starts at the same corner, so a slicer that keeps file positions (Orca does
when files are opened together) stacks them on top of each other. Use
`part="print"`.

The karaoke column has been printed (in PETG) and the Pi mounts in it
(October 2026). Not yet tried: mounting it on the stage with the keyholes, the
cable cradles and zip-tie routing, and cooling under load. The simple karaoke
speaker hasn't been printed; its dimensions come from Raspberry Pi's
mechanical drawing and the checks above.
