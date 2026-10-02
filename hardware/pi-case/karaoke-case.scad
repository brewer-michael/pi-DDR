// pi-DDR: a Raspberry Pi 4 case shaped like a little karaoke speaker.
//
// Two printed parts, no supports:
//   shell  the speaker body. Print it face down: the grille, handle and feet
//          all start on the bed.
//   plate  the back panel and standoff mount. Print it flat, standoffs up.
// The Pi (with its heatsink and fan) screws onto the plate's standoffs, then
// the plate slides into the shell from behind and screws on.
//
// The board stands upright with its parts facing the front, so the fan on the
// heatsink draws air straight in through the woofer grille, and warm air
// rises out of the top. USB and Ethernet come out of the top, like a karaoke
// speaker's mic jacks; USB-C power, both micro-HDMI and audio come out of the
// right side (seen from the front).
//
// Render one part at a time, for example:
//   openscad -D 'part="shell"' -o shell.stl karaoke-case.scad
// part = "check_fit" or "check_slide" renders the overlap between the case and
// a stand-in Pi, in place or along the path it slides in on. Both should be
// empty ("Current top level object is empty").

part = "assembly"; // [assembly, print, shell, plate, check_fit, check_slide]
// Assembly view only: pull the plate and Pi this far out of the back (mm).
explode = 0;

/* [Cooler] */
// Height of the heatsink and fan above the top of the Pi's board (mm).
// Measure yours; anything shorter than the USB ports (16 mm) counts as 16.
cooler_h = 16;
// Air gap between the fan and the front grille (mm).
fan_gap = 8;

/* [Case] */
wall = 1.6;       // side, top and bottom walls (4 perimeters of a 0.4 mm nozzle)
front_t = 2.0;    // front face
plate_t = 2.4;    // back plate
corner_r = 4;     // rounded cabinet corners
below = 10;       // room under the board: SD card and the bottom screw bosses
channel = 7;      // room on the GPIO side for the left screw bosses
standoff_h = 6;   // air gap behind the board
foot_h = 3;
handle_h = 13;

/* [Screws] */
pi_hole = 2.2;    // M2.5 self-tapping (or the cooler kit's screws) into the standoffs
boss_hole = 2.2;  // M2.5 self-tapping into the shell's screw bosses
plate_clear = 2.9;

/* [Hidden] */
$fn = 48;
eps = 0.01;

// Raspberry Pi 4 Model B, from Raspberry Pi's mechanical drawing. Board
// coordinates: x along the 85 mm edge from the SD-card end, y from the edge
// with USB-C and HDMI, z up from the top of the board.
board = [85, 56, 1.6];
pi_holes = [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]];

lift = max(cooler_h, 16);        // the USB ports are 16 mm tall
x_br = wall + channel + 0.5 + board[1]; // case X of the board's HDMI edge
z_b0 = wall + below;                    // case Z of the board's SD-card end
W = x_br + 1.0 + wall;
H = z_b0 + board[0] + 0.5 + wall;
D = front_t + fan_gap + lift + board[2] + standoff_h;
y_bb = D - standoff_h;           // back of the board
y_bt = y_bb - board[2];          // top of the board (faces the front)

// Case coordinates: X across the front (left to right, seen from the front),
// Y from the front face (0) to the back edge (D), Z up from the floor.
module on_pi() {
    multmatrix([[0, -1, 0, x_br], [0, 0, -1, y_bt], [1, 0, 0, z_b0], [0, 0, 0, 1]])
        children();
}
function pi_xz(p) = [x_br - p[1], z_b0 + p[0]];

// A 2D shape in the XZ plane, extruded from y0 to y1.
module prism_xz(y0, y1) {
    translate([0, y1, 0]) rotate([90, 0, 0]) linear_extrude(y1 - y0) children();
}
module rrect(size, r) {
    translate([r, r]) offset(r) square([size[0] - 2 * r, size[1] - 2 * r]);
}
module box(x0, y0, z0, x1, y1, z1) {
    translate([x0, y0, z0]) cube([x1 - x0, y1 - y0, z1 - z0]);
}

woofer = [W / 2, 44];
tweeter = [W / 2, 86];

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

// Screw boss in an inside corner, at the back edge. The underside slopes at
// 45 degrees so it prints without support (the back edge is the top of the print).
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
bosses = [
    [wall, wall, [wall, wall]],                         // bottom left
    [W - wall - 7, wall, [W - wall, wall]],             // bottom right
    [wall, H - wall - 7, [wall, H - wall]],             // top left
];

module shell() {
    difference() {
        union() {
            difference() {
                prism_xz(0, D) rrect([W, H], corner_r);
                prism_xz(front_t, D + 1)
                    translate([wall, wall]) rrect([W - 2 * wall, H - 2 * wall], corner_r - wall);
            }
            for (b = bosses) boss(b[0], b[1], b[2]);
            // Feet: two rails along the bottom.
            prism_xz(0, D) for (x = [6, W - 11]) translate([x, -foot_h]) square([5, foot_h + eps]);
            // Carry handle across the top, at the front.
            prism_xz(0, 8) difference() {
                translate([8, H - 1]) rrect([W - 16, handle_h + 1], 4);
                translate([13, H - 2]) rrect([W - 26, handle_h - 5 + 2], 2);
            }
        }
        // Woofer: grille in front of the fan, a cone surround and an LED ring.
        prism_xz(-1, front_t + 1) translate(woofer) hex_holes(23, 3, 4.2);
        prism_xz(-1, 0.6) translate(woofer) { ring(25, 1.2); ring(29, 1.2); }
        // Tweeter.
        prism_xz(-1, front_t + 1) translate(tweeter) hex_holes(6.5, 2.4, 3.4);
        prism_xz(-1, 0.6) translate(tweeter) ring(9, 1.2);
        // Name plate under the woofer.
        translate([W / 2, 0.6, 5]) rotate([90, 0, 0]) linear_extrude(2)
            text("pi-DDR", size = 5, font = "Liberation Sans:style=Bold",
                 halign = "center");
        // Top: USB and Ethernet, open to the back edge so they slide in.
        box(x_br - 55, y_bt - 16.5, H - wall - 1, x_br - 1.5, D + 1, H + 1);
        // Right side: USB-C, both micro-HDMI and audio, room for the plugs.
        box(x_br + 0.5, y_bt - 8, z_b0 + 4, W + 1, D + 1, z_b0 + 59);
        // Bottom: SD card access, open to the back edge.
        box(x_br - 28 - 8, y_bb - 3, -foot_h - 1, x_br - 28 + 8, D + 1, wall + 1);
        // Vents: left side (GPIO side), right side above the ports, bottom.
        for (z = [z_b0 + 4 : 6 : z_b0 + 76])
            box(-1, front_t + 5, z, wall + 1, D - 10, z + 2.5);
        for (z = [z_b0 + 65 : 6 : z_b0 + 76])
            box(W - wall - 1, front_t + 5, z, W + 1, D - 10, z + 2.5);
        for (x = [14 : 5 : W - 16])
            if (abs(x + 1.25 - (x_br - 28)) > 10)
                box(x, front_t + 4, -1, x + 2.5, y_bb - 5, wall + 1);
    }
}

module plate() {
    stand = [for (h = pi_holes) pi_xz(h)];
    screws = [for (b = bosses) [b[0] + 3.5, b[1] + 3.5]];
    difference() {
        union() {
            difference() {
                prism_xz(D, D + plate_t) rrect([W, H], corner_r);
                // Vents behind the board.
                for (z = [z_b0 + 8 : 6 : z_b0 + 78])
                    box(wall + channel + 5, D - 1, z, W - 7, D + plate_t + 1, z + 3);
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
        // Name on the outside, readable from behind.
        translate([W / 2, D + plate_t - 0.6, 4]) rotate([90, 0, 180]) linear_extrude(1)
            text("pi-DDR", size = 4, font = "Liberation Sans:style=Bold",
                 halign = "center");
    }
}

// Stand-in Pi in board coordinates, [x0, y0, z0, x1, y1, z1] per part.
pi_parts = [
    [0, 0, -board[2], 85, 56, 0],                   // board
    [70.4, 9 - 6.6, 0, 87.9, 9 + 6.6, 16],          // USB-A
    [70.4, 27 - 6.6, 0, 87.9, 27 + 6.6, 16],        // USB-A
    [66.5, 45.75 - 8, 0, 87.6, 45.75 + 8, 13.5],    // Ethernet
    [11.2 - 4.5, -1.3, 0, 11.2 + 4.5, 6.5, 3.2],    // USB-C
    [26 - 3.8, -1.0, 0, 26 + 3.8, 6.5, 3.0],        // micro-HDMI 0
    [39.5 - 3.8, -1.0, 0, 39.5 + 3.8, 6.5, 3.0],    // micro-HDMI 1
    [54 - 3.5, -2.5, 0, 54 + 3.5, 12.5, 6],         // audio
    [-2.5, 22, -board[2] - 1.4, 12, 34, -board[2]], // microSD, underneath
    [0, 0, 0, 85, 56, lift],                        // heatsink and fan
];
module pi_dummy() { on_pi() for (b = pi_parts) box(b[0], b[1], b[2], b[3], b[4], b[5]); }
// Every position on the way in: the board's -z is the case's +Y (backwards).
module pi_sweep(len) {
    on_pi() for (b = pi_parts) hull() {
        box(b[0], b[1], b[2], b[3], b[4], b[5]);
        translate([0, 0, -len]) box(b[0], b[1], b[2], b[3], b[4], b[5]);
    }
}

module shell_print() { translate([0, H + handle_h, 0]) rotate([90, 0, 0]) shell(); } // face down
module plate_print() { translate([0, 0, D + plate_t]) rotate([-90, 0, 0]) plate(); } // standoffs up

if (part == "print") {
    // Both parts side by side, ready to slice as one file.
    shell_print();
    translate([W + 10, 0, 0]) plate_print();
} else if (part == "shell") {
    shell_print();
} else if (part == "plate") {
    plate_print();
} else if (part == "check_fit") {
    intersection() { union() { shell(); plate(); } pi_dummy(); }
} else if (part == "check_slide") {
    // The Pi slides in from the back with the plate; sweep each part 50 mm back.
    intersection() { shell(); pi_sweep(50); }
} else {
    color("#e4572e") shell();
    translate([0, explode, 0]) {
        color("#3a3a3a") plate();
        color("#2e8b57", 0.8) pi_dummy();
    }
}
