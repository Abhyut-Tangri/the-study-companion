#!/usr/bin/env python3
"""Procedural pixel-art night scenes for the "study space" Notion page.

Every scene is drawn at 1/5 size with a fixed 9-colour palette, then upscaled with
nearest-neighbour so the pixels stay crisp. Randomness is seeded, so re-running gives
identical images; pass --seed N for a different set.

    python3 generate.py            # writes the PNGs next to this file
    python3 generate.py --seed 7   # a different variation of every scene
"""
import argparse
import math
import random
from pathlib import Path

from PIL import Image

NAVY = (0x0B, 0x10, 0x26)
DEEP = (0x14, 0x20, 0x4A)
MID = (0x24, 0x35, 0x7A)
PERI = (0x5B, 0x6F, 0xD6)
ICE = (0xA9, 0xC4, 0xFF)
TEAL = (0x3F, 0xB8, 0xAF)
MOON = (0xE8, 0xEC, 0xFF)
WARM = (0xE0, 0x7A, 0x5F)
BLACK = (0x0D, 0x0D, 0x0F)
PALETTE = {NAVY, DEEP, MID, PERI, ICE, TEAL, MOON, WARM, BLACK}

SCALE = 5
OUT = Path(__file__).resolve().parent
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def dither(x, y, t):
    """True when an ordered-dither pattern at (x, y) should show the second colour for blend t."""
    return t > (BAYER[y % 4][x % 4] + 0.5) / 16


def hash01(i, j, seed):
    n = (i * 374761393 + j * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 2**32


def noise(x, y, cell, seed):
    """Smooth value noise in [0, 1]."""
    fx, fy = x / cell, y / cell
    i, j = math.floor(fx), math.floor(fy)
    tx, ty = fx - i, fy - j
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a, b = hash01(i, j, seed), hash01(i + 1, j, seed)
    c, d = hash01(i, j + 1, seed), hash01(i + 1, j + 1, seed)
    return (a + (b - a) * tx) * (1 - ty) + (c + (d - c) * tx) * ty


def fbm(x, y, cell, seed, octaves=4):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * noise(x, y, cell / 2**o, seed + o * 101)
        norm += amp
        amp *= 0.5
    return total / norm


class Canvas:
    def __init__(self, w, h, bg=NAVY, transparent=False):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w, h), (0, 0, 0, 0) if transparent else bg + (255,))
        self.px = self.img.load()

    def inside(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def set(self, x, y, c):
        x, y = int(round(x)), int(round(y))
        if self.inside(x, y):
            self.px[x, y] = c + (255,)

    def get(self, x, y):
        p = self.px[int(x), int(y)]
        return p[:3] if p[3] else None

    def rect(self, x0, y0, x1, y1, c):
        for y in range(max(0, int(y0)), min(self.h, int(y1))):
            for x in range(max(0, int(x0)), min(self.w, int(x1))):
                self.px[x, y] = c + (255,)

    def gradient(self, stops, y0, y1, x0=0, x1=None):
        x1 = self.w if x1 is None else x1
        span = max(1, y1 - y0 - 1)
        for y in range(max(0, y0), min(self.h, y1)):
            f = (y - y0) / span * (len(stops) - 1)
            i = min(int(f), len(stops) - 2)
            t = f - i
            for x in range(x0, x1):
                self.px[x, y] = (stops[i + 1] if dither(x, y, t) else stops[i]) + (255,)

    def save(self, name):
        out = self.img.resize((self.w * SCALE, self.h * SCALE), Image.NEAREST)
        out.save(OUT / name, optimize=True)
        return out


# ---- reusable pieces -------------------------------------------------------------------

def stars(cv, rng, n, y1, on=(NAVY, DEEP, MID), colors=((ICE, 5), (PERI, 4), (MOON, 2)), y0=0, bright=0):
    choices = [c for c, w in colors for _ in range(w)]
    for _ in range(n):
        x, y = rng.randrange(cv.w), rng.randrange(y0, y1)
        if cv.get(x, y) in on:
            cv.set(x, y, rng.choice(choices))
    for _ in range(bright):  # four-point twinkle
        x, y = rng.randrange(2, cv.w - 2), rng.randrange(y0 + 2, max(y0 + 3, y1 - 2))
        if cv.get(x, y) in on:
            cv.set(x, y, MOON)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cv.set(x + dx, y + dy, ICE)


def halo(cv, cx, cy, r, width, on=(NAVY, DEEP), to=MID, strength=0.45):
    for y in range(int(cy - r - width), int(cy + r + width) + 1):
        for x in range(int(cx - r - width), int(cx + r + width) + 1):
            if not cv.inside(x, y):
                continue
            d = math.hypot(x - cx, y - cy)
            if r < d <= r + width and cv.get(x, y) in on:
                if dither(x, y, strength * (1 - (d - r) / width)):
                    cv.set(x, y, to)


def moon(cv, cx, cy, r, crescent=0.0, craters=None, rng=None):
    """Full moon when crescent == 0, otherwise a crescent opening to the lower left."""
    ox, oy = cx + crescent, cy - crescent * 0.45
    for y in range(int(cy - r) - 1, int(cy + r) + 2):
        for x in range(int(cx - r) - 1, int(cx + r) + 2):
            if math.hypot(x - cx, y - cy) <= r + 0.25:
                if crescent and math.hypot(x - ox, y - oy) <= r:
                    continue
                cv.set(x, y, MOON)
    if craters and rng:
        for _ in range(craters):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(0, r * 0.65)
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            cv.set(x, y, ICE)
            if rng.random() < 0.5:
                cv.set(x + 1, y, ICE)


def cloud(cv, rng, cx, cy, w, h, body, top=None, under=None):
    blobs = [(cx + rng.uniform(-w / 2, w / 2), cy + rng.uniform(-h / 3, h / 4), rng.uniform(h * 0.45, h * 0.8))
             for _ in range(max(3, int(w / 4)))]
    cells = set()
    for bx, by, br in blobs:
        for y in range(int(by - br), int(by + br) + 1):
            for x in range(int(bx - br * 1.6), int(bx + br * 1.6) + 1):
                if ((x - bx) / 1.6) ** 2 + (y - by) ** 2 <= br * br and y <= cy + h / 3:
                    cells.add((x, y))
    for x, y in cells:
        cv.set(x, y, body)
    for x, y in cells:
        if top and (x, y - 1) not in cells:
            cv.set(x, y, top)
        elif under and (x, y + 1) not in cells:
            cv.set(x, y, under)


def skyline(cv, rng, x0, x1, base, hmin, hmax, wmin, wmax, color, windows=(), lit=0.25, antenna=0.15):
    x = x0
    while x < x1:
        w, h = rng.randint(wmin, wmax), rng.randint(hmin, hmax)
        top = base - h
        cv.rect(x, top, x + w, base, color)
        if rng.random() < 0.3 and w > 4:  # stepped roof
            cv.rect(x + 1, top - 2, x + w - 1, top, color)
        if rng.random() < antenna:
            ax = x + w // 2
            for y in range(top - rng.randint(3, 7), top):
                cv.set(ax, y, color)
        if windows:
            for wy in range(top + 2, base - 1, 2):
                for wx in range(x + 1, x + w - 1, 2):
                    if rng.random() < lit:
                        cv.set(wx, wy, rng.choice(windows))
        x += w + rng.choice((0, 0, 1))


def ridge(cv, rng, base, amp, color, waves=3, x0=0, x1=None):
    x1 = cv.w if x1 is None else x1
    phases = [(rng.uniform(0.02, 0.09), rng.uniform(0, 6.28), amp * rng.uniform(0.4, 1.0)) for _ in range(waves)]
    heights = []
    for x in range(x0, x1):
        y = base - sum(a * math.sin(x * f + p) for f, p, a in phases)
        heights.append(int(y))
        cv.rect(x, y, x + 1, cv.h, color)
    return heights


def pine(cv, x, base, h, color):
    for row in range(h):
        half = int((row / h) * (h * 0.33)) + (row % 3 == 2)
        cv.rect(x - half, base - h + row, x + half + 1, base - h + row + 1, color)
    cv.rect(x, base, x + 1, base + 2, color)


def ringed_planet(cv, cx, cy, r, ring_rx, ring_ry, tilt=-0.35, light=(-0.55, -0.65)):
    lx, ly = light
    ln = math.hypot(lx, ly, 0.6)
    lx, ly, lz = lx / ln, ly / ln, 0.6 / ln
    ca, sa = math.cos(tilt), math.sin(tilt)

    def ring_hit(x, y):
        u = (x - cx) * ca + (y - cy) * sa
        v = -(x - cx) * sa + (y - cy) * ca
        q = (u / ring_rx) ** 2 + (v / ring_ry) ** 2
        return 0.62 < q <= 1.0, v

    reach = int(max(r, ring_rx)) + 2
    for y in range(int(cy - reach), int(cy + reach) + 1):
        for x in range(int(cx - reach), int(cx + reach) + 1):
            dx, dy = x - cx, y - cy
            hit, v = ring_hit(x, y)
            in_planet = dx * dx + dy * dy <= r * r
            if hit and v < 0 and not in_planet:          # back half of the ring
                cv.set(x, y, PERI)
            if in_planet:
                nz = math.sqrt(max(0.0, r * r - dx * dx - dy * dy)) / r
                l = (dx / r) * lx + (dy / r) * ly + nz * lz
                band = 0.12 * math.sin(dy / r * 9)
                l += band
                if l < 0.05:
                    c = DEEP
                elif l < 0.35:
                    c = MID if not dither(x, y, (l - 0.05) / 0.3 * 0.5) else PERI
                elif l < 0.75:
                    c = PERI if not dither(x, y, (l - 0.35) / 0.4 * 0.6) else ICE
                else:
                    c = ICE
                cv.set(x, y, c)
            if hit and v >= 0:                            # front half crosses the planet
                cv.set(x, y, ICE if (x + y) % 5 else MOON)
    cv.set(cx - r * 0.45, cy - r * 0.5, MOON)


# ---- scenes ----------------------------------------------------------------------------

def banner(seed):
    rng = random.Random(seed * 11 + 1)
    cv = Canvas(300, 120)
    cv.gradient([NAVY, NAVY, DEEP, MID], 0, 84)
    stars(cv, rng, 170, 60, bright=6)
    halo(cv, 214, 16, 4, 6)
    moon(cv, 214, 16, 4, crescent=2.5)
    skyline(cv, rng, 50, 260, 86, 14, 44, 5, 11, DEEP, windows=(PERI, MID), lit=0.12)
    skyline(cv, rng, 40, 270, 92, 8, 30, 4, 9, NAVY, windows=(ICE, PERI, TEAL, PERI), lit=0.3)
    cv.rect(0, 92, 300, 120, BLACK)
    cv.gradient([NAVY, BLACK], 92, 100)
    for x in range(0, 300, 9):                     # distant road lights
        cv.set(x + (seed % 5), 93, ICE if x % 18 else PERI)
    for x in (122, 131, 176):                      # two cars far away: tail lights, used sparingly
        cv.set(x, 95, WARM)
        cv.set(x + 2, 95, WARM)
    for side, (bx0, bx1) in enumerate(((0, 48), (262, 300))):   # near buildings framing the street
        top = 10 if side == 0 else 18
        cv.rect(bx0, top, bx1, 104, BLACK)
        for wy in range(top + 4, 98, 4):
            for wx in range(bx0 + 3, bx1 - 3, 4):
                r = rng.random()
                if r < 0.06:
                    cv.rect(wx, wy, wx + 2, wy + 2, WARM)
                elif r < 0.45:
                    cv.rect(wx, wy, wx + 2, wy + 2, rng.choice((ICE, TEAL, PERI, MID)))
        sx = bx1 - 7 if side == 0 else bx0 + 3   # vertical sign
        cv.rect(sx, top + 10, sx + 4, top + 34, NAVY)
        for k in range(top + 12, top + 32, 3):
            cv.rect(sx + 1, k, sx + 3, k + 2, TEAL if k % 2 else PERI)
    cv.rect(96, 26, 98, 100, BLACK)                 # utility pole and wires
    cv.rect(90, 30, 104, 32, BLACK)
    for i, (ya, yb, sag) in enumerate(((22, 30, 10), (30, 31, 8), (40, 36, 12))):
        for x in range(48, 262):
            t = (x - 48) / 214
            y = ya + (yb - ya) * t + sag * 4 * t * (1 - t)
            cv.set(x, y, BLACK)
    cv.gradient([BLACK, BLACK], 104, 120)
    return cv


def city_moon(seed):
    rng = random.Random(seed * 11 + 2)
    cv = Canvas(180, 100)
    cv.gradient([NAVY, DEEP, DEEP, MID], 0, 82)
    stars(cv, rng, 90, 60, bright=4)
    halo(cv, 90, 20, 7, 7)
    moon(cv, 90, 20, 7, crescent=4)
    for cx, cy, w in ((25, 64, 36), (75, 70, 44), (140, 62, 40), (170, 72, 24)):
        cloud(cv, rng, cx, cy, w, 9, MID, top=PERI)
    for x in (34, 35):                               # lattice radio tower
        for y in range(52, 92):
            cv.set(x + (1 if y < 60 else 0) * (x == 34), y, DEEP)
    for y in range(56, 92, 3):
        cv.rect(33, y, 37, y + 1, DEEP)
    cv.set(34, 49, PERI)
    skyline(cv, rng, 0, 180, 92, 8, 26, 5, 10, DEEP, windows=(PERI, MID), lit=0.2)
    skyline(cv, rng, 0, 180, 94, 4, 16, 4, 8, NAVY, windows=(ICE, TEAL, PERI, ICE, WARM), lit=0.32, antenna=0.1)
    cv.rect(0, 94, 180, 100, BLACK)
    return cv


def moon_sea(seed):
    rng = random.Random(seed * 11 + 3)
    cv = Canvas(120, 140)
    horizon = 72
    cv.gradient([NAVY, DEEP, MID], 0, horizon)
    stars(cv, rng, 70, 60, bright=3)
    halo(cv, 30, 20, 9, 7)
    moon(cv, 30, 20, 9, crescent=5)
    for i in range(7):                               # long wispy teal cloud drifting up-right
        cloud(cv, rng, 44 + i * 11, 44 - i * 3.5, 16, 6, TEAL, top=ICE, under=MID)
    cloud(cv, rng, 20, 58, 26, 5, MID, top=PERI)
    cv.rect(0, horizon, 120, horizon + 1, PERI)
    darker = {MOON: ICE, ICE: PERI, TEAL: TEAL, PERI: MID, MID: DEEP, DEEP: NAVY, NAVY: NAVY}
    for y in range(horizon + 1, 140):
        depth = (y - horizon) / (140 - horizon)
        sy = horizon - 1 - int((y - horizon) * 0.85)
        for x in range(120):
            base = DEEP if not dither(x, y, depth * 0.9) else NAVY
            cv.set(x, y, base)
            if sy >= 0 and (y % 2 == 0 or noise(x, y, 6, seed) > 0.55):
                sx = int(x + math.sin(y * 0.9 + seed) * (1 + depth * 2))
                if 0 <= sx < 120:
                    c = cv.get(sx, sy)
                    if c in (MOON, ICE, TEAL, PERI) and noise(x * 0.5, y * 2, 4, seed + 9) > 0.3:
                        cv.set(x, y, darker[c])
    for y in range(horizon + 2, 140, 2):             # moonlight path
        w = 3 + (y - horizon) // 9
        for x in range(30 - w, 30 + w + 1):
            if noise(x, y * 3, 3, seed + 3) > 0.45:
                cv.set(x, y, ICE if (y - horizon) < 30 and x % 3 else PERI)
    return cv


def galaxy_hills(seed):
    rng = random.Random(seed * 11 + 4)
    cv = Canvas(120, 180)
    cv.gradient([NAVY, NAVY, DEEP, DEEP, MID], 0, 158)
    ax, ay, bx, by = -10, 150, 130, 10               # milky way runs bottom-left to top-right
    L = math.hypot(bx - ax, by - ay)
    nx, ny = -(by - ay) / L, (bx - ax) / L
    for y in range(158):
        for x in range(120):
            d = (x - ax) * nx + (y - ay) * ny
            n = fbm(x, y, 22, seed + 40)
            w = 16 + 10 * n
            inten = math.exp(-(d / w) ** 2) * (0.45 + 0.65 * fbm(x, y, 10, seed + 50))
            along = (x - ax) * -ny + (y - ay) * nx
            lane_c = 3 * math.sin(along / 17 + seed) + 4 * (fbm(along, 0, 30, seed + 60) - 0.5)
            lane_w = 1.5 + 2.5 * fbm(along, 5, 12, seed + 65)
            if abs(d - lane_c) < lane_w:              # thin wandering dust lane along the band
                inten *= 0.4 if not dither(x, y, 0.3) else 0.6
            if inten > 0.88:
                c = ICE if not dither(x, y, 0.3) else MOON
            elif inten > 0.62:
                c = PERI if not dither(x, y, (inten - 0.62) / 0.23) else ICE
            elif inten > 0.4:
                c = MID if not dither(x, y, (inten - 0.4) / 0.22) else PERI
            elif inten > 0.22:
                c = cv.get(x, y) if not dither(x, y, (inten - 0.22) / 0.18) else MID
            else:
                continue
            cv.set(x, y, c)
    stars(cv, rng, 220, 158, on=(NAVY, DEEP, MID, PERI), bright=6)
    ridge(cv, rng, 150, 8, NAVY, waves=3)
    heights = ridge(cv, rng, 160, 6, BLACK, waves=2)
    cv.rect(0, 168, 120, 180, DEEP)                  # still lake at the bottom
    for y in range(168, 180):
        for x in range(120):
            if dither(x, y, (y - 168) / 12):
                cv.set(x, y, NAVY)
            if y % 2 == 0 and noise(x, y * 4, 5, seed + 70) > 0.72:
                cv.set(x, y, PERI)
    for x in range(50, 70):                          # small island
        h = int(5 * math.sin((x - 50) / 20 * math.pi))
        cv.rect(x, 168 - h, x + 1, 169, BLACK)
    return cv


def retro_road(seed):
    rng = random.Random(seed * 11 + 5)
    cv = Canvas(120, 180)
    horizon = 118
    cv.gradient([BLACK, NAVY, NAVY, DEEP], 0, horizon)
    stars(cv, rng, 120, horizon - 10, on=(BLACK, NAVY, DEEP), bright=5)
    ringed_planet(cv, 88, 58, 9, 18, 4.5)
    moon(cv, 22, 30, 3)
    cv.gradient([DEEP, MID, PERI], horizon - 9, horizon)          # horizon glow
    skyline(cv, rng, 0, 120, horizon, 3, 20, 3, 7, BLACK, windows=(PERI, ICE, TEAL), lit=0.35, antenna=0.2)
    cv.rect(0, horizon, 120, 180, BLACK)
    vx = 60
    for k in range(1, 14):                           # perspective grid
        y = horizon + int(k * k * 0.36)
        if y < 180:
            for x in range(120):
                if dither(x, y, 0.55):
                    cv.set(x, y, DEEP)
    for k in range(-8, 9):
        for y in range(horizon + 1, 180):
            t = (y - horizon) / (180 - horizon)
            cv.set(vx + k * 18 * t, y, DEEP)
    for y in range(horizon + 1, 180):                # the road
        t = (y - horizon) / (180 - horizon)
        half = 2 + t * 44
        cv.rect(vx - half, y, vx + half + 1, y + 1, NAVY)
        cv.set(vx - half, y, PERI)
        cv.set(vx + half, y, PERI)
        seg = math.sqrt(t) * 7
        if int(seg * 2) % 2 == 0 and t > 0.05:
            cv.rect(vx - (t > 0.5), y, vx + 1 + (t > 0.5), y + 1, MOON)
    cx, cy = 60, 166                                 # car seen from behind
    cv.rect(cx - 9, cy, cx + 10, cy + 7, BLACK)
    cv.rect(cx - 6, cy - 4, cx + 7, cy, BLACK)
    cv.rect(cx - 5, cy - 3, cx + 6, cy - 1, MID)
    cv.rect(cx - 9, cy, cx + 10, cy + 1, PERI)
    for tx in (cx - 8, cx + 7):
        cv.rect(tx, cy + 2, tx + 2, cy + 4, WARM)
    cv.rect(cx - 8, cy + 7, cx - 4, cy + 9, BLACK)
    cv.rect(cx + 5, cy + 7, cx + 9, cy + 9, BLACK)
    return cv


def course_forest(seed):
    rng = random.Random(seed * 11 + 6)
    cv = Canvas(180, 100)
    cv.gradient([NAVY, NAVY, DEEP], 0, 60)
    cv.rect(0, 60, 180, 100, DEEP)
    stars(cv, rng, 50, 40)
    for _ in range(26):                              # misty back canopy
        cx, cy, r = rng.randrange(180), rng.randrange(44, 64), rng.randint(6, 12)
        for y in range(cy - r, cy + r):
            for x in range(cx - r, cx + r):
                if math.hypot(x - cx, (y - cy) * 1.2) < r:
                    cv.set(x, y, MID)
    cv.rect(0, 64, 180, 100, MID)
    cv.gradient([MID, DEEP], 64, 80)
    for _ in range(9):                               # trunks
        x, w = rng.randrange(180), rng.randint(2, 5)
        cv.rect(x, 20 + rng.randrange(25), x + w, 100, NAVY)
        for _ in range(3):
            by = rng.randrange(25, 60)
            for i in range(rng.randint(5, 12)):
                cv.set(x + (i if rng.random() < 0.5 else -i), by - i // 2, NAVY)
    for x in range(180):                             # bumpy undergrowth
        top = int(84 - 9 * fbm(x, 0, 14, seed + 30) - 3 * noise(x, 3, 3, seed + 31))
        cv.rect(x, top, x + 1, 100, NAVY)
        if noise(x, 7, 2, seed + 32) > 0.45:
            cv.set(x, top, MID)
    cv.rect(0, 94, 180, 100, BLACK)
    for x in range(0, 180, 2):                       # grass tufts
        cv.set(x, 93 - rng.randint(0, 2), BLACK)
    for _ in range(46):                              # fireflies
        x, y = rng.randrange(180), rng.randrange(50, 96)
        if rng.random() < 0.25:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cv.set(x + dx, y + dy, TEAL)
            cv.set(x, y, ICE)
        else:
            cv.set(x, y, TEAL)
    return cv


def course_nebula(seed):
    rng = random.Random(seed * 11 + 7)
    cv = Canvas(180, 100)
    for y in range(100):
        for x in range(180):
            v = fbm(x, y, 40, seed + 80)
            t = fbm(x + 300, y, 26, seed + 90)
            dust = fbm(x, y + 200, 16, seed + 95)
            c = NAVY
            if v > 0.5:
                c = DEEP if not dither(x, y, (v - 0.5) / 0.08) else MID
            if v > 0.58:
                c = MID if not dither(x, y, (v - 0.58) / 0.1) else PERI
            if v > 0.68:
                c = PERI if not dither(x, y, (v - 0.68) / 0.12) else ICE
            if t > 0.6 and v > 0.48:
                c = TEAL if dither(x, y, min(1, (t - 0.6) / 0.08)) else c
            if dust > 0.62 and v < 0.66:
                c = BLACK if dither(x, y, (dust - 0.62) / 0.06) else c
            cv.set(x, y, c)
    stars(cv, rng, 160, 100, on=(NAVY, DEEP, MID, BLACK), bright=7)
    return cv


def course_pines(seed):
    rng = random.Random(seed * 11 + 8)
    cv = Canvas(180, 100)
    cv.gradient([NAVY, DEEP, MID, MID], 0, 70)
    stars(cv, rng, 90, 55, bright=3)
    halo(cv, 128, 22, 8, 8, on=(NAVY, DEEP, MID), to=PERI, strength=0.3)
    moon(cv, 128, 22, 8, crescent=4.5)
    for base, amp, color, size, count in ((60, 6, DEEP, (6, 10), 34), (74, 7, NAVY, (9, 15), 26), (90, 5, BLACK, (16, 26), 12)):
        heights = ridge(cv, rng, base, amp, color)
        for _ in range(count):
            x = rng.randrange(180)
            pine(cv, x, heights[x] + 1, rng.randint(*size), color)
    cv.rect(146, 38, 148, 92, BLACK)                 # a lone pole and its wire
    cv.rect(142, 42, 152, 43, BLACK)
    for x in range(148, 180):
        cv.set(x, 43 + (x - 148) ** 1.4 * 0.05, BLACK)
    return cv


def course_desert(seed):
    rng = random.Random(seed * 11 + 9)
    cv = Canvas(180, 100)
    cv.gradient([NAVY, NAVY, DEEP, MID], 0, 72)
    stars(cv, rng, 230, 66, bright=8)
    halo(cv, 40, 22, 8, 7)
    moon(cv, 40, 22, 8, craters=7, rng=rng)
    for i in range(16):                              # shooting star
        x, y = 150 - i * 2, 12 + i
        cv.set(x, y, ICE if i < 6 else PERI)
        if i < 4:
            cv.set(x, y - 1, MOON)
    back = ridge(cv, rng, 70, 5, MID, waves=2)
    for x, h in enumerate(back):
        cv.set(x, h, PERI)
    ridge(cv, rng, 80, 6, DEEP, waves=2)
    front = ridge(cv, rng, 90, 4, NAVY, waves=2)
    cx = 140                                         # saguaro silhouette
    base = front[cx]
    cv.rect(cx, base - 22, cx + 3, base + 1, BLACK)
    cv.rect(cx - 5, base - 14, cx, base - 12, BLACK)
    cv.rect(cx - 5, base - 20, cx - 3, base - 12, BLACK)
    cv.rect(cx + 3, base - 10, cx + 7, base - 8, BLACK)
    cv.rect(cx + 6, base - 17, cx + 8, base - 8, BLACK)
    cv.rect(60, front[60] - 2, 66, front[60] + 1, BLACK)
    return cv


def course_rooftop(seed):
    rng = random.Random(seed * 11 + 10)
    cv = Canvas(180, 100)
    cv.gradient([NAVY, DEEP, DEEP], 0, 80)
    stars(cv, rng, 80, 50, bright=3)
    halo(cv, 150, 20, 10, 8)
    moon(cv, 150, 20, 10, craters=8, rng=rng)
    skyline(cv, rng, 0, 180, 82, 10, 34, 5, 11, MID, windows=(PERI, ICE), lit=0.18)
    skyline(cv, rng, 0, 180, 84, 6, 22, 4, 9, NAVY, windows=(ICE, TEAL, PERI, WARM), lit=0.3)
    cv.rect(0, 82, 180, 100, BLACK)                  # roof slab and parapet
    cv.rect(0, 82, 180, 83, NAVY)
    cv.rect(18, 50, 38, 70, BLACK)                   # water tank on legs
    cv.rect(16, 48, 40, 50, BLACK)
    cv.rect(26, 44, 28, 48, BLACK)
    for y in (55, 62):
        cv.rect(18, y, 38, y + 1, NAVY)
    for lx in (19, 27, 36):
        cv.rect(lx, 70, lx + 1, 82, BLACK)
    cv.rect(62, 30, 63, 82, BLACK)                   # antenna mast
    for y in range(34, 60, 7):
        cv.rect(59, y, 67, y + 1, BLACK)
    cv.set(62, 29, WARM)
    cx, cy = 112, 81                                 # cat sitting on the parapet
    cv.rect(cx, cy - 7, cx + 6, cy, BLACK)
    cv.rect(cx + 1, cy - 11, cx + 6, cy - 7, BLACK)
    cv.set(cx + 1, cy - 12, BLACK)
    cv.set(cx + 5, cy - 12, BLACK)
    cv.set(cx + 4, cy - 10, TEAL)
    for i in range(6):
        cv.set(cx - 1 - i // 2, cy - 1 - (i if i < 3 else 5 - i), BLACK)
    for x in range(70, 105, 4):                      # string of small lights
        y = 70 + int(4 * math.sin((x - 70) / 35 * math.pi))
        cv.set(x, y, ICE if x % 8 else TEAL)
    return cv


def icon_planet(seed):
    cv = Canvas(56, 56, transparent=True)
    ringed_planet(cv, 28, 29, 14, 26, 6.5, tilt=-0.4)
    for x, y in ((8, 10), (47, 8), (50, 46), (6, 44)):
        cv.set(x, y, MOON)
    return cv


SCENES = [
    ("banner.png", banner),
    ("city-moon.png", city_moon),
    ("moon-sea.png", moon_sea),
    ("galaxy-hills.png", galaxy_hills),
    ("retro-road.png", retro_road),
    ("course-1.png", course_forest),
    ("course-2.png", course_nebula),
    ("course-3.png", course_pines),
    ("course-4.png", course_desert),
    ("course-5.png", course_rooftop),
    ("icon-planet.png", icon_planet),
]


def check_palette(cv, name):
    for y in range(cv.h):
        for x in range(cv.w):
            p = cv.px[x, y]
            if p[3] and p[:3] not in PALETTE:
                raise SystemExit(f"{name}: off-palette colour {p[:3]} at {x},{y}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    for name, fn in SCENES:
        cv = fn(args.seed)
        check_palette(cv, name)
        out = cv.save(name)
        print(f"{name:18} {out.size[0]}x{out.size[1]}")


if __name__ == "__main__":
    main()
