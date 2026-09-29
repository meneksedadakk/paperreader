"""Validate the template against the REAL MEB TYT form (docs/reference): draw pencil marks on it and read."""
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from omr import geometry, read_sheet
from tests.helpers import marks_of, random_answers, to_photo

REF = Path(__file__).resolve().parent.parent / "docs" / "reference" / "tyt_optik_meb_sakarya.png"
SCALE = 110 / 72  # the PNG was rendered at 110 dpi

pytestmark = pytest.mark.skipif(not REF.exists(), reason="reference form image missing")


def marked_reference(answers: dict) -> Image.Image:
    img = Image.open(REF).convert("RGB")
    d = ImageDraw.Draw(img)
    r = geometry.BUBBLE_D / 2 * SCALE * 0.92
    for bi, (key, _, count) in enumerate(geometry.BLOCKS):
        for row in range(count):
            q = geometry.FIRST_QUESTION[key] + row
            for opt, letter in enumerate("ABCDE"):
                if letter in (answers.get(q) or ""):
                    cx, cy = geometry.bubble_center_pt(bi, row, opt)
                    cx, cy = cx * SCALE, cy * SCALE
                    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(55, 55, 60))
    return img


ANSWERS = random_answers(seed=11)


def test_reference_form_dimensions():
    assert Image.open(REF).size == (910, 1287)


@pytest.mark.parametrize("kwargs", [
    dict(perspective=0.0, noise=0, blur=0),
    dict(rotation=5, perspective=0.04, noise=3, blur=1.0),
    dict(rotation=-7, perspective=0.05, shadow=0.4, noise=3, blur=1.0),
    dict(rotation=2, rot90=1),
    dict(rotation=2, rot90=2),
], ids=["straight", "tilted", "shadow", "rot90", "rot180"])
def test_marked_reference_form_is_read_exactly(kwargs):
    res = read_sheet(to_photo(marked_reference(ANSWERS), seed=5, **kwargs))
    got = marks_of(res)
    bad = [q for q in ANSWERS if got[q] != ANSWERS[q]]
    assert bad == []
    assert res.flagged == []


def test_unmarked_reference_form_reads_blank_even_when_upside_down():
    for rot90 in (0, 2):
        res = read_sheet(to_photo(marked_reference({}), rot90=rot90))
        assert all(m is None for m in marks_of(res).values())
        assert res.flagged == []


def test_double_mark_on_reference_form():
    answers = dict(ANSWERS)
    answers[61] = "BD"
    res = read_sheet(to_photo(marked_reference(answers), rotation=3))
    assert marks_of(res)[61] == "*"
    assert 61 in res.flagged
