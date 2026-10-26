"""Generates the app icon (a frosted-glass desk calendar) as a multi-size .ico file.

Pure Python, no image libraries: each shape is drawn from a signed distance
function, which also gives clean anti-aliased edges at every size.

    python tools/make_icon.py build/deskcal.ico     (also writes build/deskcal.png)
"""
import math
import struct
import sys
import zlib

SIZES = [16, 24, 32, 48, 64, 128, 256]


def rounded_box(px, py, x0, y0, x1, y1, r):
    """Signed distance from (px, py) to a rounded rectangle (negative inside)."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = abs(px - cx) - ((x1 - x0) / 2 - r)
    qy = abs(py - cy) - ((y1 - y0) / 2 - r)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def coverage(dist, size):
    """How much of the pixel lies inside the shape, for anti-aliased edges."""
    return min(1.0, max(0.0, 0.5 - dist * size))


def over(dst, col, a):
    """Paints colour col with opacity a over the pixel dst = (r, g, b, alpha)."""
    r, g, b, da = dst
    na = a + da * (1 - a)
    if na <= 0:
        return (0, 0, 0, 0)
    mix = lambda c, d: (c * a + d * da * (1 - a)) / na
    return (mix(col[0], r), mix(col[1], g), mix(col[2], b), na)


TILE = (0.05, 0.05, 0.95, 0.95, 0.23)
CARD = (0.16, 0.20, 0.84, 0.86, 0.12)


def pixel(x, y, size):
    px = (0, 0, 0, 0)
    t = coverage(rounded_box(x, y, *TILE), size)
    if t:                                        # muted blue -> lavender tile with soft glows
        c = [118 - 30 * y + 30 * x, 140 - 40 * y, 208 - 30 * y]
        for bx, by, rad, col, k in ((0.82, 0.18, 0.09, (236, 170, 170), 0.45),
                                    (0.18, 0.85, 0.10, (120, 200, 215), 0.40)):
            w = math.exp(-((x - bx) ** 2 + (y - by) ** 2) / rad) * k
            c = [c[n] + (col[n] - c[n]) * w for n in range(3)]
        px = over(px, c, t)
    d = rounded_box(x, y, *CARD)
    shadow = max(0.0, min(1.0, 1 - (rounded_box(x, y - 0.025, *CARD) + 0.02) / 0.07)) * 0.22
    if shadow and t:
        px = over(px, (30, 30, 70), shadow * t)
    cc = coverage(d, size)
    if cc:                                       # frosted glass pane
        top = 1 - (y - CARD[1]) / (CARD[3] - CARD[1])
        px = over(px, (255, 255, 255), (0.24 + 0.12 * top) * cc)
        if y < 0.36:                             # header band
            px = over(px, (255, 255, 255), 0.22 * cc)
        sheen = math.exp(-((x + y - 0.50) ** 2) / 0.004) * 0.22
        px = over(px, (255, 255, 255), sheen * cc)
        for row in range(3):                     # 4 x 3 day cells, one picked day in rose
            for col in range(4):
                x0, y0 = 0.235 + col * 0.14, 0.43 + row * 0.135
                gc = coverage(rounded_box(x, y, x0, y0, x0 + 0.11, y0 + 0.105, 0.026), size)
                if gc:
                    if (row, col) == (1, 2):
                        px = over(px, (236, 140, 152), 0.95 * gc)
                    else:
                        px = over(px, (255, 255, 255), 0.30 * gc)
    if abs(d) < 0.02 and t:                      # glass rim, lit from the top-left
        rim = max(0.0, 1 - abs(d) * size / 1.1)
        lit = 0.30 + 0.60 * max(0.0, 1 - (x + y) / 1.1)
        px = over(px, (255, 255, 255), rim * lit)
    for cx in (0.37, 0.63):                      # two small rings
        rc = coverage(rounded_box(x, y, cx - 0.03, 0.13, cx + 0.03, 0.27, 0.03), size)
        if rc:
            px = over(px, (250, 252, 255), 0.92 * rc)
    return px


def render(size):
    out = bytearray(size * size * 4)
    for j in range(size):
        for i in range(size):
            r, g, b, a = pixel((i + 0.5) / size, (j + 0.5) / size, size)
            k = (j * size + i) * 4
            out[k:k + 4] = bytes((int(r), int(g), int(b), int(round(a * 255))))
    return bytes(out)


def png(size, rgba):
    rows = b"".join(b"\x00" + rgba[y * size * 4:(y + 1) * size * 4] for y in range(size))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def ico(path):
    images = [png(s, render(s)) for s in SIZES]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(SIZES, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(head + entries + b"".join(images))
    with open(path[:-4] + ".png", "wb") as f:                # preview of the largest size
        f.write(images[-1])


if __name__ == "__main__":
    ico(sys.argv[1] if len(sys.argv) > 1 else "deskcal.ico")
