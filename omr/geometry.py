"""Geometry of the reference MEB TYT answer sheet (measured from the PDF vectors, in pt).

A4 = 595.28 x 841.89 pt. Everything is expressed relative to the OUTER edge of the thick
black frame, because that is what the reader detects in a photo.
"""
import json
from pathlib import Path

PAGE_W, PAGE_H = 595.28, 841.89

FRAME_LINE = 2.835
_FRAME_CENTER = (44.362, 288.131, 416.125, 779.821)  # x0, y0, x1, y1 of the stroke centre line
FRAME_OUTER = (
    _FRAME_CENTER[0] - FRAME_LINE / 2, _FRAME_CENTER[1] - FRAME_LINE / 2,
    _FRAME_CENTER[2] + FRAME_LINE / 2, _FRAME_CENTER[3] + FRAME_LINE / 2,
)
FRAME_W = FRAME_OUTER[2] - FRAME_OUTER[0]
FRAME_H = FRAME_OUTER[3] - FRAME_OUTER[1]
FRAME_RATIO = FRAME_W / FRAME_H

BUBBLE_D = 9.59
COL_STEP = 12.0        # A -> B -> ... horizontal pitch
ROW_STEP = 11.995      # vertical pitch between questions
FIRST_ROW_Y = 299.90   # y of the first question row
NUMBER_DX = -11.0      # printed row number sits this far left of the A bubble

BLOCKS = (  # key, first A-bubble x, question count
    ("turkce", 68.36, 40),
    ("sosyal", 164.32, 20),
    ("matematik", 260.28, 40),
    ("fen", 356.24, 20),
)
FIRST_QUESTION = {"turkce": 1, "sosyal": 41, "matematik": 61, "fen": 101}

TEMPLATE_PATH = Path(__file__).parent / "templates" / "tyt_120.json"


def bubble_center_pt(block_index: int, row: int, option: int) -> tuple[float, float]:
    _, ax, _ = BLOCKS[block_index]
    return ax + option * COL_STEP, FIRST_ROW_Y + row * ROW_STEP


def build_template() -> dict:
    x0, y0 = FRAME_OUTER[0], FRAME_OUTER[1]
    questions = {}
    for bi, (key, _, count) in enumerate(BLOCKS):
        for row in range(count):
            q = FIRST_QUESTION[key] + row
            centers = []
            for opt in range(5):
                cx, cy = bubble_center_pt(bi, row, opt)
                centers.append([round((cx - x0) / FRAME_W, 5), round((cy - y0) / FRAME_H, 5)])
            nx = bubble_center_pt(bi, row, 0)[0] + NUMBER_DX
            ny = bubble_center_pt(bi, row, 0)[1]
            questions[str(q)] = {
                "options": centers,
                "number": [round((nx - x0) / FRAME_W, 5), round((ny - y0) / FRAME_H, 5)],
            }
    return {
        "name": "tyt_120",
        "options": ["A", "B", "C", "D", "E"],
        "frame_ratio": round(FRAME_RATIO, 5),
        "frame_w_pt": round(FRAME_W, 3),
        "frame_h_pt": round(FRAME_H, 3),
        "bubble_radius_norm_w": round(BUBBLE_D / 2 / FRAME_W, 5),
        "questions": questions,
    }


def write_template(path: Path = TEMPLATE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_template(), ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(write_template())
