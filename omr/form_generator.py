"""Render the printable orange-and-white TYT answer sheet (same geometry as the MEB reference).

Also used by tests to draw synthetic pencil marks on a blank sheet.
"""
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from omr import geometry as g

ORANGE = (255, 127, 0)
MAGENTA = (237, 0, 140)
PENCIL = (60, 60, 64)

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf",
)
_BOLD_CANDIDATES = (
    r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@lru_cache(maxsize=32)
def _font(px: int, bold: bool = False):
    for path in (_BOLD_CANDIDATES if bold else ()) + _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, px)
    return ImageFont.load_default(px)


def render_form(answers: dict | None = None, color=ORANGE, scale: float = 3.0,
                pencil=PENCIL, mark_fill: float = 0.95, seed: int | None = None) -> Image.Image:
    """Draw the sheet. `answers` maps question -> 'A'..'E', 'AB' (double mark) or None."""
    rng = random.Random(seed)
    s = scale
    img = Image.new("RGB", (round(g.PAGE_W * s), round(g.PAGE_H * s)), "white")
    d = ImageDraw.Draw(img)

    d.text((120 * s, 60 * s), "TYT OPTİK CEVAP FORMU", fill=color, font=_font(round(20 * s), True))
    d.text((60 * s, 100 * s), "ÖĞRENCİ BİLGİLERİ", fill=color, font=_font(round(8 * s), True))
    for i, lab in enumerate(("AD SOYAD", "SINIF / ŞUBE", "OKUL ADI")):
        y = (112 + i * 14) * s
        d.text((60 * s, y), lab, fill=color, font=_font(round(7 * s)))
        d.line([(60 * s, y + 12 * s), (400 * s, y + 12 * s)], fill=color, width=max(1, round(0.7 * s)))
    d.text((45 * s, 240 * s), "Kodlamalarınızı koyu, yumuşak uçlu kurşun kalemle yapınız.", fill=color,
           font=_font(round(7 * s)))

    lw = max(1, round(g.FRAME_LINE * s))
    x0, y0, x1, y1 = (v * s for v in g.FRAME_OUTER)
    d.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(0, 0, 0), width=lw)

    r = g.BUBBLE_D / 2 * s
    number_font = _font(round(6.5 * s))
    letter_font = _font(round(5 * s))
    light = tuple(min(255, c + (255 - c) * 6 // 10) for c in color)
    answers = answers or {}
    for bi, (key, ax, count) in enumerate(g.BLOCKS):
        title = {"turkce": "TÜRKÇE", "sosyal": "SOSYAL BİLİMLER", "matematik": "TEMEL MATEMATİK",
                 "fen": "FEN BİLİMLERİ"}[key]
        d.text(((ax - 8) * s, (g.FRAME_OUTER[1] - 14) * s), title, fill=(0, 0, 0), font=_font(round(7 * s)))
        for row in range(count):
            q = g.FIRST_QUESTION[key] + row
            cy = (g.FIRST_ROW_Y + row * g.ROW_STEP) * s
            d.text(((ax + g.NUMBER_DX) * s, cy), str(row + 1), fill=(0, 0, 0), font=number_font, anchor="mm")
            marked = answers.get(q) or ""
            for opt in range(5):
                cx = (ax + opt * g.COL_STEP) * s
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(1, round(0.9 * s)))
                d.text((cx, cy), "ABCDE"[opt], fill=light, font=letter_font, anchor="mm")
                if "ABCDE"[opt] in marked:
                    jx, jy = rng.uniform(-0.6, 0.6) * s * 0.4, rng.uniform(-0.6, 0.6) * s * 0.4
                    rr = r * mark_fill
                    d.ellipse([cx + jx - rr, cy + jy - rr, cx + jx + rr, cy + jy + rr], fill=pencil)
    return img


def save_pdf(path, color=ORANGE, scale: float = 3.0) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    render_form(color=color, scale=scale).save(path, "PDF", resolution=72 * scale)
    return path
