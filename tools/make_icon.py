"""Generates the app icon (a small desk calendar) as a multi-size .ico file.

Pure Python, no image libraries: each shape is drawn from a signed distance
function, which also gives clean anti-aliased edges at every size.

    python tools/make_icon.py build/deskcal.ico
"""
import math
import struct
import sys
import zlib

SIZES = [16, 24, 32, 48, 64, 128, 256]
PAPER, HEADER, RING, CELL, TODAY = ("#f3f4f7", "#e8949b", "#2a2f3a", "#c9cfdb", "#5b8de0")


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def rounded_box(px, py, x0, y0, x1, y1, r):
    """Signed distance from (px, py) to a rounded rectangle (negative inside)."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = abs(px - cx) - ((x1 - x0) / 2 - r)
    qy = abs(py - cy) - ((y1 - y0) / 2 - r)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def shapes():
    """(distance function, color) from back to front, in 0..1 coordinates."""
    card = (0.10, 0.15, 0.90, 0.90, 0.13)
    out = [(lambda x, y: rounded_box(x, y, *card), PAPER),
           (lambda x, y: max(rounded_box(x, y, *card), y - 0.37), HEADER)]
    for cx in (0.32, 0.68):                                  # binder rings
        out.append((lambda x, y, cx=cx: rounded_box(x, y, cx - 0.04, 0.07, cx + 0.04, 0.24,
                                                    0.04), RING))
    for row in range(3):                                     # day cells
        for col in range(4):
            x0, y0 = 0.205 + col * 0.155, 0.46 + row * 0.135
            today = (row, col) == (1, 2)
            out.append((lambda x, y, x0=x0, y0=y0: rounded_box(x, y, x0, y0, x0 + 0.115,
                                                               y0 + 0.095, 0.03),
                        TODAY if today else CELL))
    return out


def render(size):
    layers = [(f, rgb(c)) for f, c in shapes()]
    px = bytearray(size * size * 4)
    for j in range(size):
        y = (j + 0.5) / size
        for i in range(size):
            x = (i + 0.5) / size
            r = g = b = a = 0.0
            for f, (cr, cg, cb) in layers:
                cov = min(1.0, max(0.0, 0.5 - f(x, y) * size))   # edge coverage
                if cov:
                    r, g, b = (r * a * (1 - cov) + cr * cov, g * a * (1 - cov) + cg * cov,
                               b * a * (1 - cov) + cb * cov)
                    a = cov + a * (1 - cov)
                    if a:
                        r, g, b = r / a, g / a, b / a
            k = (j * size + i) * 4
            px[k:k + 4] = bytes((int(r), int(g), int(b), int(round(a * 255))))
    return bytes(px)


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
