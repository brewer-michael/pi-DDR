// pi-DDR: karaoke column, a Raspberry Pi 4 case that mounts on the stage.
// (karaoke-case.scad is the simple, free-standing version.)
//
// It stands on the stage's front border, held by two keyhole tabs and a lock
// screw, and every cable leaves from the back:
//   - The Pi faces the front, upside down: the fan on its heatsink sits right
//     behind the upper woofer, and the USB ports point down into a plinth.
//   - The mat cables plug in from below, loop in the plinth, are zip-tied to
//     the back plate (so a tug pulls on the case, not the USB port), and leave
//     through the slot at the bottom of the back plate.
//   - HDMI and USB-C power come out of the left side (seen from the front).
//     Their plugs rest on two small cradles, and zip-tie anchors carry the
//     cables down the side to the back.
//
// Parts, no supports:
//   shell     the speaker body, printed face down
//   plate     the back panel and standoff mount, printed flat, standoffs up
//   template  1.2 mm drilling template for the border screws
// part = "print" lays out the shell and plate together, ready to slice.
// part = "check_fit" / "check_slide" render the overlap between the case and
// a stand-in Pi (with its plugs), in place and along the way in; both should
// be empty apart from flat contact where the board sits on the standoffs.

part = "assembly"; // [assembly, print, shell, plate, template, check_fit, check_slide]
// Assembly view only: pull the plate and Pi this far out of the back (mm).
explode = 0;

/* [Cooler] */
// Height of the heatsink and fan above the top of the Pi's board (mm).
// Anything shorter than the USB ports (16 mm) counts as 16.
cooler_h = 16;
// Air gap between the fan and the front grille (mm).
fan_gap = 8;

/* [Case] */
wall = 1.6;       // side, top and bottom walls (4 perimeters of a 0.4 mm nozzle)
front_t = 2.0;    // front face
plate_t = 2.4;    // back plate
corner_r = 4;
plinth = 40;      // room under the USB ports for the mat plugs and their loops
channel = 7;      // room on the GPIO side for the right-hand screw bosses
standoff_h = 6;
handle_h = 13;

/* [Mounting] */
tab = [18, 24, 6];  // keyhole tabs: reach out from each side, depth, thickness
key_head = 8.5;     // entry hole, fits a #6 pan head
key_shank = 4.2;    // slot, fits a #6 shank
key_travel = 8;     // how far the case slides to lock
key_floor = 1.8;    // material under the screw head
key_channel = 3.0;  // height of the channel the head slides in
lock_hole = 3.6;    // lock screw through the right tab

/* [Screws] */
pi_hole = 2.2;      // M2.5 self-tapping (or the cooler kit's screws) into the standoffs
boss_hole = 2.2;    // M2.5 self-tapping into the shell's screw bosses
plate_clear = 2.9;

/* [Hidden] */
$fn = 48;
eps = 0.01;

// Raspberry Pi 4 Model B, from Raspberry Pi's mechanical drawing. Board
// coordinates: x along the 85 mm edge from the SD-card end, y from the edge
// with USB-C and HDMI, z up from the top of the board.
board = [85, 56, 1.6];
pi_holes = [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]];
usb_out = 2.9;                          // USB jacks stick out past the board edge
sd_out = 2.5;                           // and so does the microSD card

lift = max(cooler_h, 16);
xa = wall + 1.0;                        // case X of the board's HDMI edge
W = xa + board[1] + 0.5 + channel + wall;
D = front_t + fan_gap + lift + board[2] + standoff_h;
y_bb = D - standoff_h;                  // back of the board
y_bt = y_bb - board[2];                 // top of the board (faces the front)
zc = wall + plinth + usb_out + board[0]; // case Z of the board's SD-card end (top)
H = zc + sd_out + 1.0 + wall;

// Case coordinates: X across the front (left to right, seen from the front),
// Y from the front face (0) to the back edge (D), Z up from the bottom.
// The board is upside down: its SD-card end is at the top.
module on_pi() {
    multmatrix([[0, 1, 0, xa], [0, 0, -1, y_bt], [-1, 0, 0, zc], [0, 0, 0, 1]]) children();
}
function pi_xz(p) = [xa + p[1], zc - p[0]];

module prism_xz(y0, y1) {
    translate([0, y1, 0]) rotate([90, 0, 0]) linear_extrude(y1 - y0) children();
}
module rrect(size, r) {
    translate([r, r]) offset(r) square([size[0] - 2 * r, size[1] - 2 * r]);
}
module box(x0, y0, z0, x1, y1, z1) {
    translate([x0, y0, z0]) cube([x1 - x0, y1 - y0, z1 - z0]);
}
module hex_holes(r, d, pitch) {
    n = ceil(r / pitch) + 1;
    for (j = [-n:n], i = [-n:n]) {
        p = [(i + (abs(j) % 2) / 2) * pitch, j * pitch * sqrt(3) / 2];
        if (norm(p) + d / 2 <= r) translate(p) circle(d = d, $fn = 16);
    }
}
module ring(r, w) {
    difference() { circle(r + w / 2); circle(r - w / 2); }
}

// Front: the upper woofer sits in front of the fan (over the SoC), the lower
// one vents the plinth.
woofer = [W / 2, zc - 29];
tweeter = [W / 2, 65];
low_woofer = [W / 2, 37];

// Screw bosses at the back edge, in inside corners clear of the board.
bosses = [
    [wall, wall, [wall, wall]],                         // bottom left
    [W - wall - 7, wall, [W - wall, wall]],             // bottom right
    [W - wall - 7, H - wall - 7, [W - wall, H - wall]], // top right
];
module boss(x0, z0, corner) {
    difference() {
        hull() {
            box(x0, D - 8, z0, x0 + 7, D, z0 + 7);
            translate([corner[0], D - 8 - 10, corner[1]]) cube(0.1, center = true);
        }
        translate([x0 + 3.5, D + eps, z0 + 3.5]) rotate([90, 0, 0])
            cylinder(d = boss_hole, h = 8);
    }
}

// Keyholes: drop the case over the screw heads, slide it +X (toward the right)
// by key_travel, then drive the lock screw.
key_left = [-tab[0] + 5.25 + key_travel, tab[1] - 9];
key_right = [W + tab[0] - 4.75, tab[1] - 9];
lock = [W + 9, tab[1] - 2.5];
module keyhole(c) {
    translate([c[0], c[1], 0]) {
        translate([0, 0, -1]) cylinder(d = key_head, h = tab[2] + 2);
        hull() for (x = [0, -key_travel]) translate([x, 0, -1]) cylinder(d = key_shank, h = tab[2] + 2);
        hull() for (x = [0, -key_travel]) translate([x, 0, key_floor]) cylinder(d = key_head, h = key_channel);
    }
}

// Cable riser on the left side: a cradle under each plug (it also forms a sill
// in the side window) and zip-tie anchors down the wall. Each cradle starts at
// the front face and slopes out at 45 degrees, so it prints without support.
module cradle(z_top, reach) {
    translate([0, 0, z_top - 2.5]) linear_extrude(2.5)
        polygon([[wall, 0], [-6, 0], [-reach, reach - 6], [-reach, y_bt + 5], [wall, y_bt + 5]]);
}
anchors = [12, 36, 58];
module anchor(z) {
    difference() {
        hull() {
            box(-7, y_bt - 6, z, eps, y_bt + 2, z + 6);
            box(-eps, y_bt - 13, z, eps, y_bt - 12.9, z + 6);
        }
        box(-5, y_bt - 7, z + 0.75, -3, y_bt + 3, z + 5.25); // zip-tie slot
    }
}

module shell() {
    difference() {
        union() {
            difference() {
                prism_xz(0, D) rrect([W, H], corner_r);
                prism_xz(front_t, D + 1)
                    translate([wall, wall]) rrect([W - 2 * wall, H - 2 * wall], corner_r - wall);
            }
            for (b = bosses) boss(b[0], b[1], b[2]);
            // Carry handle across the top, at the front.
            prism_xz(0, 8) difference() {
                translate([12, H - 1]) rrect([W - 24, handle_h + 1], 4);
                translate([17, H - 2]) rrect([W - 34, handle_h - 5 + 2], 2);
            }
            // Keyhole tabs.
            box(-tab[0], 0, 0, 4, tab[1], tab[2]);
            box(W - 4, 0, 0, W + tab[0], tab[1], tab[2]);
        }
        // Front: woofers, tweeter, name.
        prism_xz(-1, front_t + 1) {
            translate(woofer) hex_holes(22, 3, 4.2);
            translate(tweeter) hex_holes(4.5, 2.2, 3.2);
            translate(low_woofer) hex_holes(15, 2.6, 3.8);
        }
        prism_xz(-1, 0.6) {
            translate(woofer) { ring(24.5, 1.2); ring(27.5, 1.2); }
            translate(tweeter) ring(6.5, 1.2);
            translate(low_woofer) { ring(17, 1.2); ring(19.5, 1.2); }
        }
        translate([W / 2, 0.6, 5]) rotate([90, 0, 0]) linear_extrude(2)
            text("pi-DDR", size = 5, font = "Liberation Sans:style=Bold", halign = "center");
        // Left side: USB-C, micro-HDMI and audio, open to the back edge so they slide in.
        box(-1, y_bt - 8, zc - 59, wall + 0.5, D + 1, zc - 5);
        // Top: SD card, open to the back edge; vents behind the handle.
        box(23, y_bb - 2, H - wall - 1, 38, D + 1, H + 1);
        for (x = [8 : 5 : W - 10]) box(x, 10, H - wall - 1, x + 2.5, y_bb - 4, H + 1);
        // Right side vents.
        for (z = [14 : 7 : zc - 8]) box(W - wall - 1, front_t + 4, z, W + 1, D - 10, z + 3);
        // Mounting.
        keyhole(key_left);
        keyhole(key_right);
        translate([lock[0], lock[1], -1]) cylinder(d = lock_hole, h = tab[2] + 2);
    }
    cradle(zc - 26 - 5.5 - 0.5, 15);    // under the micro-HDMI plug (HDMI0)
    cradle(zc - 11.2 - 4.25 - 0.5, 13); // under the USB-C plug
    for (z = anchors) anchor(z);
}

usb_slot = [10, 52, 20];   // X from, X to, height: mat cables leave here
tie_z = 24;
mat_x = [xa + 9, xa + 27, xa + 45.75]; // under each USB stack (and Ethernet)

module plate() {
    stand = [for (h = pi_holes) pi_xz(h)];
    screws = [for (b = bosses) [b[0] + 3.5, b[1] + 3.5]];
    difference() {
        union() {
            difference() {
                prism_xz(D, D + plate_t) rrect([W, H], corner_r);
                for (z = [usb_slot[2] + 18 : 7 : zc - 12])
                    box(12, D - 1, z, W - 12, D + plate_t + 1, z + 3);
            }
            prism_xz(D, D + plate_t) {
                for (p = stand) translate(p) circle(d = 9);
                for (p = screws) translate(p) circle(d = 8);
            }
            for (p = stand) translate([p[0], D + eps, p[1]]) rotate([90, 0, 0])
                cylinder(d = 5.5, h = standoff_h + eps);
        }
        for (p = stand) translate([p[0], D + plate_t + 1, p[1]]) rotate([90, 0, 0])
            cylinder(d = pi_hole, h = standoff_h + plate_t + 2);
        for (p = screws) translate([p[0], D + plate_t + 1, p[1]]) rotate([90, 0, 0])
            cylinder(d = plate_clear, h = plate_t + 2);
        // Mat cables: slot at the bottom, zip-tie slots above it.
        box(usb_slot[0], D - 1, -1, usb_slot[1], D + plate_t + 1, usb_slot[2]);
        for (x = mat_x, dx = [-7, 7])
            box(x + dx - 1, D - 1, tie_z, x + dx + 1, D + plate_t + 1, tie_z + 4.5);
        translate([W / 2, D + plate_t - 0.6, H - 10]) rotate([90, 0, 180]) linear_extrude(1)
            text("pi-DDR", size = 4, font = "Liberation Sans:style=Bold", halign = "center");
    }
}

// Drilling template: lay it on the border where the case should end up, mark
// or drill through the three holes.
module template() {
    difference() {
        linear_extrude(1.2) union() {
            square([W, D + plate_t]);
            translate([-tab[0], 0]) square([W + 2 * tab[0], tab[1]]);
        }
        for (c = [key_left, key_right]) translate([c[0] - key_travel, c[1], -1]) cylinder(d = 2.5, h = 3);
        translate([lock[0], lock[1], -1]) cylinder(d = 2.5, h = 3);
        translate([W / 2, 4, 0.6]) linear_extrude(1) text("FRONT", size = 4, halign = "center");
        translate([W / 2, D - 8, 0.6]) linear_extrude(1) text("BACK", size = 4, halign = "center");
    }
}

// Stand-in Pi with the mat plugs, HDMI and USB-C plugs, all in board coordinates.
pi_parts = [
    [0, 0, -board[2], 85, 56, 0],                   // board
    [70.4, 9 - 6.6, 0, 87.9, 9 + 6.6, 16],          // USB-A
    [70.4, 27 - 6.6, 0, 87.9, 27 + 6.6, 16],        // USB-A
    [66.5, 45.75 - 8, 0, 87.6, 45.75 + 8, 13.5],    // Ethernet
    [11.2 - 4.5, -1.3, 0, 11.2 + 4.5, 6.5, 3.2],    // USB-C
    [26 - 3.8, -1.0, 0, 26 + 3.8, 6.5, 3.0],        // micro-HDMI 0
    [39.5 - 3.8, -1.0, 0, 39.5 + 3.8, 6.5, 3.0],    // micro-HDMI 1
    [54 - 3.5, -2.5, 0, 54 + 3.5, 12.5, 6],         // audio
    [-sd_out, 22, -board[2] - 1.4, 12, 34, -board[2]], // microSD, underneath
    [0, 0, 0, 85, 56, lift],                        // heatsink and fan
    [87.9, 9 - 8, 0, 87.9 + 26, 9 + 8, 7.8],        // mat plug (lower port)
    [87.9, 27 - 8, 0, 87.9 + 26, 27 + 8, 7.8],      // mat plug (lower port)
];
side_plugs = [
    [26 - 5.5, -23, -1.9, 26 + 5.5, -1.0, 5.1],     // micro-HDMI plug in HDMI0
    [11.2 - 4.25, -18, -1.4, 11.2 + 4.25, -1.3, 4.6], // USB-C plug
];
module boxes(list) { for (b = list) box(b[0], b[1], b[2], b[3], b[4], b[5]); }
// Every position on the way in (the board's -z is the case's +Y). The side
// plugs go in afterwards, through the window, so they don't sweep.
module pi_sweep(len) {
    on_pi() for (b = pi_parts) hull() {
        box(b[0], b[1], b[2], b[3], b[4], b[5]);
        translate([0, 0, -len]) box(b[0], b[1], b[2], b[3], b[4], b[5]);
    }
}

module shell_print() { translate([tab[0], H + handle_h, 0]) rotate([90, 0, 0]) shell(); } // face down
module plate_print() { translate([0, 0, D + plate_t]) rotate([-90, 0, 0]) plate(); }      // standoffs up

if (part == "print") {
    shell_print();
    translate([W + 2 * tab[0] + 10, 0, 0]) plate_print();
} else if (part == "shell") {
    shell_print();
} else if (part == "plate") {
    plate_print();
} else if (part == "template") {
    template();
} else if (part == "check_fit") {
    intersection() { union() { shell(); plate(); } on_pi() boxes(concat(pi_parts, side_plugs)); }
} else if (part == "check_slide") {
    intersection() { shell(); pi_sweep(60); }
} else {
    color("#e4572e") shell();
    translate([0, explode, 0]) {
        color("#3a3a3a") plate();
        color("#2e8b57", 0.8) on_pi() boxes(pi_parts);
    }
    color("#111") on_pi() boxes(side_plugs);
}
