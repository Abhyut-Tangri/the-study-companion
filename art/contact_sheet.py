#!/usr/bin/env python3
"""Lays out every generated scene on one dark grid for review: python3 contact_sheet.py OUT.png"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
from generate import SCENES, OUT

CELL_W, CELL_H, PAD, LABEL = 360, 300, 16, 22
cols = 4
rows = -(-len(SCENES) // cols)
sheet = Image.new("RGB", (cols * (CELL_W + PAD) + PAD, rows * (CELL_H + LABEL + PAD) + PAD), (0x19, 0x19, 0x19))
draw = ImageDraw.Draw(sheet)
for i, (name, _) in enumerate(SCENES):
    im = Image.open(OUT / name).convert("RGBA")
    im.thumbnail((CELL_W, CELL_H), Image.NEAREST)
    x = PAD + (i % cols) * (CELL_W + PAD)
    y = PAD + (i // cols) * (CELL_H + LABEL + PAD)
    sheet.paste(im, (x + (CELL_W - im.width) // 2, y + (CELL_H - im.height) // 2), im)
    draw.text((x, y + CELL_H + 4), f"{name}  {Image.open(OUT / name).size[0]}x{Image.open(OUT / name).size[1]}", fill=(0xD4, 0xD4, 0xD4))
sheet.save(sys.argv[1] if len(sys.argv) > 1 else OUT / "contact-sheet.png")
