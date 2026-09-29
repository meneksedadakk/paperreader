"""Read a photographed TYT answer sheet into {question_no: (mark, confidence)}."""
import json
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np

from omr import geometry, preprocess
from omr.preprocess import OMRError  # noqa: F401  (re-exported)

FILL_THRESHOLD = 0.40     # ink fraction that counts as "this bubble is marked"
INK_LEVEL = 0.72          # normalised brightness below this is ink
MASK_RADIUS_FACTOR = 0.80
LOW_CONFIDENCE = 0.50     # below this the question is flagged for the student to check
RESIDUE_RATIO = 0.60      # 2nd bubble weaker than this * 1st -> treated as an erasure remnant

OPTIONS = ("A", "B", "C", "D", "E")


@dataclass
class SheetResult:
    answers: dict = field(default_factory=dict)  # q -> (mark, confidence); mark: 'A'..'E' | None | '*'
    fills: dict = field(default_factory=dict)    # q -> [5 ink fractions]
    warped: np.ndarray | None = None             # canonical BGR sheet

    @property
    def flagged(self) -> list[int]:
        return sorted(q for q, (m, c) in self.answers.items() if m == "*" or c < LOW_CONFIDENCE)

    def to_json(self) -> dict:
        return {
            "answers": {str(q): {"o": m, "c": round(c, 3)} for q, (m, c) in sorted(self.answers.items())},
            "flagged": self.flagged,
        }


@lru_cache(maxsize=1)
def load_template(path: str | None = None) -> dict:
    p = geometry.TEMPLATE_PATH if path is None else path
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def decide(fills: list[float]) -> tuple[str | None, float]:
    """Turn 5 ink fractions into (mark, confidence)."""
    order = sorted(range(5), key=lambda i: fills[i], reverse=True)
    f1, f2 = fills[order[0]], fills[order[1]]
    cands = [i for i in range(5) if fills[i] >= FILL_THRESHOLD]
    if not cands:
        return None, float(np.clip(1 - f1 / FILL_THRESHOLD, 0, 1))
    base = min(np.clip((f1 - f2) / 0.4, 0, 1), np.clip((f1 - 0.25) / 0.35, 0, 1))
    if len(cands) == 1:
        return OPTIONS[order[0]], float(base)
    if f2 < RESIDUE_RATIO * f1:  # one clear mark plus a faint remnant (e.g. incomplete erasure)
        return OPTIONS[order[0]], float(min(base, 0.45))
    return "*", 0.3


def _circle_mask(r: int) -> np.ndarray:
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r


def measure_fills(warped_bgr: np.ndarray, template: dict) -> dict:
    h, w = warped_bgr.shape[:2]
    norm = preprocess.normalize_lighting(warped_bgr[:, :, 2])
    ink = norm < INK_LEVEL
    r_px = template["bubble_radius_norm_w"] * w
    r = max(int(round(r_px * MASK_RADIUS_FACTOR)), 2)
    mask = _circle_mask(r)
    area = mask.sum()
    fills = {}
    for qs, q in template["questions"].items():
        row = []
        for cx_n, cy_n in q["options"]:
            cx, cy = int(round(cx_n * w)), int(round(cy_n * h))
            x0, y0 = cx - r, cy - r
            if x0 < 0 or y0 < 0 or cx + r + 1 > w or cy + r + 1 > h:
                row.append(0.0)
                continue
            patch = ink[y0:cy + r + 1, x0:cx + r + 1]
            row.append(float((patch & mask).sum() / area))
        fills[int(qs)] = row
    return fills


def read_warped(warped_bgr: np.ndarray, template: dict | None = None) -> SheetResult:
    template = template or load_template()
    fills = measure_fills(warped_bgr, template)
    answers = {q: decide(f) for q, f in fills.items()}
    return SheetResult(answers=answers, fills=fills, warped=warped_bgr)


def read_sheet(img_bgr: np.ndarray, template: dict | None = None) -> SheetResult:
    template = template or load_template()
    warped = preprocess.rectify(img_bgr, template)
    return read_warped(warped, template)


def debug_overlay(result: SheetResult, template: dict | None = None) -> np.ndarray:
    """Warped sheet with detected marks (green), double marks (red) and flagged rows (yellow)."""
    template = template or load_template()
    img = result.warped.copy()
    h, w = img.shape[:2]
    r = int(round(template["bubble_radius_norm_w"] * w))
    flagged = set(result.flagged)
    for q, (mark, _) in result.answers.items():
        centers = [(int(round(x * w)), int(round(y * h))) for x, y in template["questions"][str(q)]["options"]]
        if mark == "*":
            for i, c in enumerate(centers):
                if result.fills[q][i] >= FILL_THRESHOLD:
                    cv2.circle(img, c, r, (0, 0, 220), 2)
        elif mark is not None:
            cv2.circle(img, centers[OPTIONS.index(mark)], r, (0, 170, 0), 2)
        if q in flagged:
            cv2.rectangle(img, (centers[0][0] - r - 3, centers[0][1] - r - 2),
                          (centers[4][0] + r + 3, centers[4][1] + r + 2), (0, 200, 255), 2)
    return img
