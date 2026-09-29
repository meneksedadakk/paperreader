import numpy as np
import pytest

from omr import OMRError, geometry, read_sheet
from omr import reader
from omr.form_generator import MAGENTA, ORANGE, render_form
from omr.preprocess import load_image
from tests.helpers import jpeg_bytes, marks_of, random_answers, to_photo

ANSWERS = random_answers(seed=3)


def _mismatches(result, expected):
    got = marks_of(result)
    return [q for q in expected if got[q] != expected[q]]


# ---------- template ----------

def test_template_covers_120_questions_with_5_options():
    tpl = reader.load_template()
    assert len(tpl["questions"]) == 120
    assert all(len(q["options"]) == 5 for q in tpl["questions"].values())


def test_template_positions_are_monotonic_and_inside_frame():
    tpl = reader.load_template()
    for q in range(1, 121):
        pts = tpl["questions"][str(q)]["options"]
        xs = [p[0] for p in pts]
        assert xs == sorted(xs)
        assert all(0 < x < 1 and 0 < y < 1 for x, y in pts)
    # rows go downwards within a block
    assert tpl["questions"]["2"]["options"][0][1] > tpl["questions"]["1"]["options"][0][1]
    # blocks go left to right
    assert tpl["questions"]["41"]["options"][0][0] > tpl["questions"]["1"]["options"][0][0]


def test_template_file_matches_geometry():
    fresh = geometry.build_template()
    saved = reader.load_template()
    assert fresh["questions"]["120"] == saved["questions"]["120"]
    assert fresh["frame_ratio"] == saved["frame_ratio"]


def test_reference_measurements():
    # last row of the Turkish block (row 40) as measured from the MEB PDF: y = 767.7 pt
    assert abs(geometry.bubble_center_pt(0, 39, 0)[1] - 767.7) < 0.3
    assert abs(geometry.bubble_center_pt(3, 0, 4)[0] - 404.2) < 0.2


# ---------- decision logic ----------

@pytest.mark.parametrize("fills,mark", [
    ([0.9, 0.02, 0.0, 0.03, 0.0], "A"),
    ([0.0, 0.0, 0.85, 0.0, 0.05], "C"),
    ([0.0, 0.05, 0.0, 0.02, 0.01], None),
    ([0.0, 0.0, 0.0, 0.0, 0.0], None),
])
def test_decide_single_and_blank(fills, mark):
    got, conf = reader.decide(fills)
    assert got == mark
    assert conf > reader.LOW_CONFIDENCE


def test_decide_double_mark_is_star_and_flagged():
    got, conf = reader.decide([0.8, 0.0, 0.75, 0.0, 0.0])
    assert got == "*"
    assert conf < reader.LOW_CONFIDENCE


def test_decide_erasure_remnant_keeps_strong_mark_but_low_confidence():
    got, conf = reader.decide([0.9, 0.0, 0.45, 0.0, 0.0])
    assert got == "A"
    assert conf < reader.LOW_CONFIDENCE


def test_decide_faint_smudge_is_blank_but_flagged():
    got, conf = reader.decide([0.33, 0.0, 0.0, 0.0, 0.0])
    assert got is None
    assert conf < reader.LOW_CONFIDENCE


# ---------- reading synthetic sheets ----------

@pytest.mark.parametrize("color", [ORANGE, MAGENTA], ids=["orange", "magenta"])
def test_clean_render_is_read_exactly(color):
    img = to_photo(render_form(ANSWERS, color=color), perspective=0.0, noise=0, blur=0)
    res = read_sheet(img)
    assert _mismatches(res, ANSWERS) == []
    assert res.flagged == []


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("color", [ORANGE, MAGENTA], ids=["orange", "magenta"])
def test_tilted_noisy_photo(seed, color):
    img = to_photo(render_form(ANSWERS, color=color, seed=seed), seed=seed, rotation=6, perspective=0.05,
                   noise=4, blur=1.2)
    res = read_sheet(img)
    assert _mismatches(res, ANSWERS) == []


def test_jpeg_roundtrip_through_load_image():
    img = to_photo(render_form(ANSWERS), rotation=-4, perspective=0.04)
    res = read_sheet(load_image(jpeg_bytes(img, quality=70)))
    assert _mismatches(res, ANSWERS) == []


@pytest.mark.parametrize("rot90", [1, 2, 3])
def test_rotated_photo_is_reoriented(rot90):
    img = to_photo(render_form(ANSWERS), rotation=3, rot90=rot90)
    res = read_sheet(img)
    assert _mismatches(res, ANSWERS) == []


def test_uneven_lighting_shadow():
    img = to_photo(render_form(ANSWERS), shadow=0.55, noise=3)
    res = read_sheet(img)
    assert _mismatches(res, ANSWERS) == []


def test_dark_table_and_light_table_backgrounds():
    for bg in [(15, 15, 15), (235, 235, 235)]:
        img = to_photo(render_form(ANSWERS), bg=bg, rotation=2)
        assert _mismatches(read_sheet(img), ANSWERS) == []


def test_light_pencil_marks_are_still_detected():
    img = to_photo(render_form(ANSWERS, pencil=(115, 115, 120), mark_fill=0.75), noise=3)
    res = read_sheet(img)
    assert _mismatches(res, ANSWERS) == []


def test_double_mark_and_blank_are_reported():
    answers = dict(ANSWERS)
    answers[5] = "AC"     # double
    answers[6] = None     # blank
    answers[105] = "BE"   # double in Fen
    res = read_sheet(to_photo(render_form(answers), perspective=0.02))
    got = marks_of(res)
    assert got[5] == "*" and got[105] == "*"
    assert got[6] is None
    assert {5, 105} <= set(res.flagged)
    assert 6 not in res.flagged
    assert _mismatches(res, {q: a for q, a in answers.items() if q not in (5, 105)}) == []


def test_all_blank_sheet():
    res = read_sheet(to_photo(render_form({})))
    assert all(m is None for m in marks_of(res).values())
    assert res.flagged == []


def test_all_a_sheet():
    answers = {q: "A" for q in range(1, 121)}
    res = read_sheet(to_photo(render_form(answers)))
    assert set(marks_of(res).values()) == {"A"}


def test_result_json_shape():
    res = read_sheet(to_photo(render_form(ANSWERS)))
    data = res.to_json()
    assert len(data["answers"]) == 120
    assert set(data["answers"]["1"]) == {"o", "c"}
    assert data["flagged"] == res.flagged


def test_debug_overlay_same_size_as_warp():
    res = read_sheet(to_photo(render_form(ANSWERS)))
    overlay = reader.debug_overlay(res)
    assert overlay.shape == res.warped.shape
    assert not np.array_equal(overlay, res.warped)


# ---------- failures ----------

def test_no_frame_raises_user_facing_error():
    blank = np.full((1200, 900, 3), 240, dtype=np.uint8)
    with pytest.raises(OMRError) as e:
        read_sheet(blank)
    assert "çerçeve" in str(e.value)


def test_random_noise_image_raises():
    rng = np.random.default_rng(0)
    with pytest.raises(OMRError):
        read_sheet(rng.integers(0, 255, (1000, 800, 3), dtype=np.uint8))


def test_cropped_form_without_full_frame_raises():
    img = to_photo(render_form(ANSWERS), perspective=0.0, noise=0, blur=0)
    h, w = img.shape[:2]
    with pytest.raises(OMRError):
        read_sheet(img[: h // 2, : w // 2])


def test_non_image_bytes_raise():
    with pytest.raises(OMRError):
        load_image(b"this is not an image")
