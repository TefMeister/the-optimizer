"""make_icon.py - draws The Optimizer's icon (app/optimizer.ico) with nothing but Python: a dark rounded tile with a
gauge dial whose arc runs from cyan to violet (the family colours of our helper apps) and a needle resting just past
the top, in the "holds 72" zone. Original artwork, made for this app.

    python tools/make_icon.py            writes app/optimizer.ico (256, 64, 48, 32 and 16 px)
"""
import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "app", "optimizer.ico")
SIZES = (256, 64, 48, 32, 16)
SS = 4                                   # supersampling per pixel side, for smooth edges

BG_TOP, BG_BOT = (30, 34, 46), (12, 13, 19)
EDGE = (78, 84, 106)
CYAN, VIOLET = (56, 196, 232), (150, 108, 245)
NEEDLE = (244, 246, 252)
DIM = (52, 56, 72)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def sample(x, y):
    """Colour and cover (0..1) at a point of the unit tile (0..1 both ways)."""
    r = 0.22                                     # the tile's corner radius
    dx, dy = max(r - x, 0, x - (1 - r)), max(r - y, 0, y - (1 - r))
    if dx * dx + dy * dy > r * r:
        return (0, 0, 0), 0.0
    col = mix(BG_TOP, BG_BOT, y)
    inner = r - 0.025
    ex, ey = max(inner - x + 0.025, 0, x - (1 - inner) + 0.025 - 0.05), 0
    if (dx * dx + dy * dy > (r - 0.02) ** 2) or min(x, y, 1 - x, 1 - y) < 0.02:
        col = EDGE
    cx, cy = 0.5, 0.58
    px, py = x - cx, y - cy
    d = math.hypot(px, py)
    ang = math.degrees(math.atan2(-py, px))      # 0 = right, 90 = up
    # the dial's arc: from 210 degrees (lower left) round over the top to -30 (lower right)
    a = (210 - ang) % 360
    if 0.30 <= d <= 0.40 and a <= 240:
        t = a / 240
        col = mix(CYAN, VIOLET, t) if a <= 170 else DIM
    # tick marks inside the arc
    if 0.24 <= d <= 0.28 and a <= 240 and (a % 30) < 4:
        col = (150, 160, 190)
    # the needle: from the hub towards 75 degrees (just right of the top)
    na = math.radians(75)
    ux, uy = math.cos(na), -math.sin(na)
    along = px * ux + py * uy
    across = abs(px * uy - py * ux)
    if -0.04 <= along <= 0.33 and across <= 0.028 * (1 - max(along, 0) / 0.36):
        col = NEEDLE
    if d <= 0.065:
        col = NEEDLE if d <= 0.04 else (120, 126, 150)
    return col, 1.0


def render(n):
    rows = []
    for j in range(n):
        row = bytearray()
        for i in range(n):
            acc, cov = [0.0, 0.0, 0.0], 0.0
            for sj in range(SS):
                for si in range(SS):
                    c, a = sample((i + (si + 0.5) / SS) / n, (j + (sj + 0.5) / SS) / n)
                    for k in range(3):
                        acc[k] += c[k] * a
                    cov += a
            if cov:
                row += bytes(int(round(acc[k] / cov)) for k in range(3)) + bytes([int(round(255 * cov / SS / SS))])
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def png(n, rows):
    raw = b"".join(b"\0" + r for r in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    pics = [png(n, render(n)) for n in SIZES]
    head = struct.pack("<HHH", 0, 1, len(pics))
    at = 6 + 16 * len(pics)
    dirs, body = b"", b""
    for n, p in zip(SIZES, pics):
        dirs += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(p), at + len(body))
        body += p
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(head + dirs + body)
    print(f"wrote {OUT} ({len(head + dirs + body)} bytes)")


if __name__ == "__main__":
    main()
