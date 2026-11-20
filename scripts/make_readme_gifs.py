"""Generates the README GIFs (docs/assets/*.gif) from the project's own code. Run: python scripts/make_readme_gifs.py

human-vs-bot.gif: one trace from adversarial.generate_synthetic_human_telemetry and one from
generate_bezier_telemetry, drawn point by point; the verdict labels are the real output of
engine.analyze_behavior on those exact traces (nothing is hard-coded).
how-it-works.gif: a four-step request flow.
"""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "docs", "assets")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("SYNAPSE_DB_PATH", os.path.join(os.path.dirname(__file__), "gif_tmp.db"))

from synapse_shield import adversarial as adv  # noqa: E402
from synapse_shield.engine import analyze_behavior  # noqa: E402

BG, PANEL, GRID = (13, 17, 23), (22, 27, 34), (33, 40, 50)
TEXT, MUTED = (230, 237, 243), (139, 148, 158)
HUMAN, BOT = (0, 240, 255), (255, 107, 107)
GREEN, RED, AMBER = (63, 185, 80), (248, 81, 73), (210, 153, 34)


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE, F_LABEL, F_SMALL = font(20, True), font(16, True), font(13)


def verdict(tel):
    score, cls, _, _ = analyze_behavior(tel)
    return score, cls


def fit(points, box):
    xs, ys = [p["x"] for p in points], [p["y"] for p in points]
    x0, y0, x1, y1 = box
    sx = (x1 - x0 - 40) / max(1e-9, max(xs) - min(xs))
    sy = (y1 - y0 - 40) / max(1e-9, max(ys) - min(ys))
    s = min(sx, sy)
    ox = x0 + 20 + ((x1 - x0 - 40) - s * (max(xs) - min(xs))) / 2
    oy = y0 + 20 + ((y1 - y0 - 40) - s * (max(ys) - min(ys))) / 2
    return [(ox + (x - min(xs)) * s, oy + (y - min(ys)) * s) for x, y in zip(xs, ys)]


def human_vs_bot():
    random.seed(7)
    np.random.seed(7)
    human = adv.generate_synthetic_human_telemetry()
    bot = adv.generate_bezier_telemetry()
    hs, hc = verdict(human)
    bs, bc = verdict(bot)
    print("human:", hs, hc, "| bot:", bs, bc)

    W, H = 760, 330
    left, right = (20, 60, 370, 290), (390, 60, 740, 290)
    tl, tr = (20, 90, 370, 250), (390, 90, 740, 250)
    hp, bp = fit(human["mouse_movements"], tl), fit(bot["mouse_movements"], tr)
    n = max(len(hp), len(bp))
    frames = []
    total = n + 18
    for f in range(total):
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((20, 18), "Same task, two cursors", font=F_TITLE, fill=TEXT)
        for box, title, col in ((left, "Human-like trace", HUMAN), (right, "Bezier bot (fixed 20 ms timer)", BOT)):
            d.rounded_rectangle(box, 10, fill=PANEL)
            for gx in range(box[0] + 30, box[2], 40):
                d.line([(gx, box[1] + 8), (gx, box[3] - 8)], fill=GRID)
            d.text((box[0] + 12, box[1] + 8), title, font=F_SMALL, fill=col)
        for pts, col in ((hp, HUMAN), (bp, BOT)):
            k = min(len(pts), f + 1)
            if k > 1:
                d.line(pts[:k], fill=col, width=3, joint="curve")
            x, y = pts[k - 1]
            d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col)
        if f >= n:
            for box, cls, score in ((left, hc, hs), (right, bc, bs)):
                ok = cls == "Human"
                label = f"{'ALLOW' if ok else 'BLOCK'}  ·  risk {score:.0f}"
                d.rounded_rectangle((box[2] - 190, box[3] - 38, box[2] - 12, box[3] - 10), 8, fill=GREEN if ok else RED)
                d.text((box[2] - 178, box[3] - 34), label, font=F_LABEL, fill=(255, 255, 255))
        d.text((20, 300), "Verdicts: real output of synapse_shield.engine on these synthetic traces.", font=F_SMALL, fill=MUTED)
        frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=32))
    durations = [45] * n + [140] * 17 + [2200]
    frames[0].save(os.path.join(OUT, "human-vs-bot.gif"), save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True, disposal=2)


def how_it_works():
    steps = [
        ("1", "Visitor uses\nyour form", "moves, taps, types"),
        ("2", "SDK collects\ntiming only", "no typed text, no PII"),
        ("3", "Shield scores\nthe session", "on your own server"),
        ("4", "Decision", ""),
    ]
    W, H = 760, 262
    frames, durations = [], []
    for active in range(len(steps) + 1):
        for sub in range(2 if active < len(steps) else 1):
            im = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(im)
            d.text((20, 16), "How Synapse Shield works", font=F_TITLE, fill=TEXT)
            bw, gap, y0 = 160, 26, 62
            for i, (num, title, sub_t) in enumerate(steps):
                x0 = 20 + i * (bw + gap)
                on = i < active or (i == active and sub == 1)
                d.rounded_rectangle((x0, y0, x0 + bw, y0 + 160), 12, fill=PANEL, outline=HUMAN if on else GRID, width=3 if on else 1)
                d.ellipse((x0 + 12, y0 + 12, x0 + 40, y0 + 40), fill=HUMAN if on else GRID)
                d.text((x0 + 21, y0 + 14), num, font=F_LABEL, fill=BG if on else MUTED)
                d.multiline_text((x0 + 12, y0 + 52), title, font=F_LABEL, fill=TEXT if on else MUTED, spacing=2)
                if sub_t:
                    d.text((x0 + 12, y0 + 102), sub_t, font=F_SMALL, fill=MUTED)
                if i == 3 and on:
                    for j, (lab, col) in enumerate((("allow", GREEN), ("challenge", AMBER), ("block", RED))):
                        d.rounded_rectangle((x0 + 12, y0 + 82 + j * 25, x0 + 120, y0 + 104 + j * 25), 6, fill=col)
                        d.text((x0 + 20, y0 + 84 + j * 25), lab, font=F_SMALL, fill=(255, 255, 255))
                if i < 3:
                    ax = x0 + bw + 4
                    d.polygon([(ax, y0 + 60), (ax + gap - 8, y0 + 65), (ax, y0 + 70)], fill=HUMAN if i < active else GRID)
            d.text((20, 236), "Humans pass invisibly. Unsure sessions get a background proof-of-work, not a puzzle.", font=F_SMALL, fill=MUTED)
            frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=32))
            durations.append(2600 if active == len(steps) else 650)
    frames[0].save(os.path.join(OUT, "how-it-works.gif"), save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True, disposal=2)


human_vs_bot()
how_it_works()
for f in ("human-vs-bot.gif", "how-it-works.gif"):
    p = os.path.join(OUT, f)
    print(f, os.path.getsize(p) // 1024, "KB")
