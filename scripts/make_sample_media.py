"""Generate synthetic gallery tiles: screenshot-like cards with readable text.
Run: python scripts/make_sample_media.py     (needs Pillow >= 10.1 for scalable fonts)

These stand in for saved posts/screenshots. The baked-in text is what OCR would read later, so Role 1/Role 2
can use them as test inputs. Replace or extend with real consented screenshots in data/media/.
"""
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "data" / "media"
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 720


def font(px: int):
    try:
        return ImageFont.load_default(size=px)      # scalable default font (Pillow >= 10.1)
    except TypeError:
        return ImageFont.load_default()             # old Pillow: tiny bitmap font, upgrade Pillow


# (file, category, title, body lines, base colour)
TILES = [
    ("recipe_wrap.png", "RECIPE", "No-oven paneer wrap",
     ["Serves 2  |  15 min", "paneer 200 g", "yoghurt 3 tbsp", "2 rotis, chaat masala", "No oven needed"], (176, 82, 36)),
    ("recipe_overnight_oats.png", "RECIPE", "Overnight oats, 3 ways",
     ["Serves 1  |  5 min + fridge", "oats 50 g, milk 120 ml", "chia 1 tbsp", "Rest 8 hours. No oven."], (150, 104, 40)),
    ("recipe_chickpea_salad.png", "RECIPE", "High-protein chickpea salad",
     ["Serves 2  |  10 min", "chickpeas 1 can", "cucumber, lemon, mint", "About 18 g protein", "No oven needed"], (52, 112, 66)),
    ("workout_shoulder.png", "WORKOUT", "Dumbbell shoulder burn",
     ["Beginner  |  20 min", "Lateral raise 3 x 12", "Arnold press 3 x 10", "Front raise 3 x 12"], (52, 62, 150)),
    ("workout_beginner_legs.png", "WORKOUT", "Beginner leg day",
     ["Bodyweight  |  25 min", "Squats 3 x 15", "Lunges 3 x 10 each", "Glute bridge 3 x 15"], (28, 88, 140)),
    ("place_jaipur.png", "PLACE", "Jaipur weekend: Amber Fort + old city",
     ["2 days  |  Rajasthan", "Day 1: Amber Fort", "Day 2: Hawa Mahal, bazaars", "Best: Oct to Mar"], (150, 58, 96)),
    ("place_goa.png", "PLACE", "Goa off-season cafes",
     ["Short trip  |  Beach", "Quiet cafes, fewer crowds", "Best: Nov to Feb"], (26, 112, 120)),
    ("learn_bayes.png", "LEARNING", "Bayes theorem cheat sheet",
     ["Statistics", "P(A|B) = P(B|A) P(A) / P(B)", "prior, likelihood, posterior"], (96, 62, 140)),
    ("learn_sql_joins.png", "LEARNING", "SQL joins diagram",
     ["SQL", "INNER JOIN: matching rows", "LEFT JOIN: all from left", "FULL OUTER: everything"], (62, 72, 100)),
]


def card(cat, title, lines, base) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), base)
    d = ImageDraw.Draw(img)
    for y in range(SIZE):                                    # vertical gradient, darker toward the bottom
        k = 1 - 0.45 * (y / SIZE)
        d.line([(0, y), (SIZE, y)], fill=tuple(int(c * k) for c in base))
    d.ellipse([SIZE - 260, -120, SIZE + 100, 240], fill=tuple(min(255, int(c * 1.25)) for c in base))  # soft accent

    pad = 48
    f_pill, f_title, f_body = font(26), font(50), font(32)
    tw = d.textlength(cat, font=f_pill)
    d.rounded_rectangle([pad, pad, pad + tw + 40, pad + 48], 24, fill=(255, 255, 255))
    d.text((pad + 20, pad + 7), cat, font=f_pill, fill=(20, 20, 20))

    y = 150
    for ln in textwrap.wrap(title, 20):
        d.text((pad, y), ln, font=f_title, fill=(255, 255, 255))
        y += 62
    y += 18
    for i, ln in enumerate(lines):
        d.text((pad, y), ln, font=f_body, fill=(255, 255, 255) if i else (255, 236, 200))
        y += 46
    return img


def make(fname, cat, title, lines, base):
    card(cat, title, lines, base).save(OUT / fname)


# Sample video: 3 slides x 3 s, like a short workout reel. Needs ffmpeg on PATH.
VIDEO = ("workout_full_body.mp4", "workout_full_body_thumb.jpg", [
    ("VIDEO", "10-minute full body routine", ["Beginner  |  Bodyweight", "Part 1: Squats 3 x 15", "Rest 30 s between sets"]),
    ("VIDEO", "10-minute full body routine", ["Part 2: Lunges 3 x 10 each", "Keep knees over ankles"]),
    ("VIDEO", "10-minute full body routine", ["Part 3: Glute bridge 3 x 15", "Finish: plank 3 x 30 s"]),
], (120, 52, 120))


def make_video():
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found: skipped the sample video (install ffmpeg to generate it)")
        return
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=15, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"ffmpeg can't run on this machine ({e}): skipped the sample video. The repo already contains it.")
        return
    name, thumb, slides, base = VIDEO
    with tempfile.TemporaryDirectory() as tmp:
        for i, (cat, title, lines) in enumerate(slides):
            card(cat, title, lines, base).save(Path(tmp) / f"s{i}.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "1/3", "-i", str(Path(tmp) / "s%d.png"),
                        "-c:v", "libx264", "-r", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(OUT / name)], check=True)
        card(*slides[0], base).save(OUT / thumb, quality=88)
    print(f"wrote sample video {name} and {thumb}")


for t in TILES:
    make(*t)
print(f"wrote {len(TILES)} tiles to {OUT}")
make_video()
