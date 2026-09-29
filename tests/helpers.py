"""Test helpers: synthetic answers and a simulated phone photo of a sheet."""
import io
import random

import cv2
import numpy as np
from PIL import Image

from app import tyt

OPTS = "ABCDE"


def random_answers(seed: int = 1, blank_rate: float = 0.1) -> dict:
    """{q: 'A'..'E' | None} for all 120 questions."""
    rng = random.Random(seed)
    return {q: (None if rng.random() < blank_rate else rng.choice(OPTS)) for q in range(1, tyt.TOTAL_QUESTIONS + 1)}


def answer_key(seed: int = 7) -> dict:
    rng = random.Random(seed)
    return {q: rng.choice(OPTS) for q in range(1, tyt.TOTAL_QUESTIONS + 1)}


def to_photo(pil_img: Image.Image, seed: int = 0, canvas=(1600, 2200), perspective: float = 0.04,
             rotation: float = 0.0, rot90: int = 0, shadow: float = 0.0, noise: float = 3.0,
             blur: float = 1.0, bg=(60, 85, 110), coverage: float = 0.85) -> np.ndarray:
    """Place the sheet on a table, warp it like a hand-held photo. Returns a BGR array."""
    rng = np.random.default_rng(seed)
    sheet = cv2.cvtColor(np.asarray(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = sheet.shape[:2]
    cw, ch = canvas
    scale = min(cw / w, ch / h) * coverage
    sw, sh = w * scale, h * scale
    cx, cy = cw / 2, ch / 2
    box = np.array([[-sw / 2, -sh / 2], [sw / 2, -sh / 2], [sw / 2, sh / 2], [-sw / 2, sh / 2]])
    a = np.deg2rad(rotation)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    dst = box @ rot.T + [cx, cy]
    dst += rng.uniform(-perspective, perspective, (4, 2)) * [sw, sh]
    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    out = cv2.warpPerspective(sheet, m, (cw, ch), flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=bg)
    out = out.astype(np.float32)
    if shadow:
        ramp = np.linspace(1.0, 1.0 - shadow, cw, dtype=np.float32)[None, :, None]
        out *= ramp
    if noise:
        out += rng.normal(0, noise, out.shape).astype(np.float32)
    out = np.clip(out, 0, 255).astype(np.uint8)
    if blur:
        out = cv2.GaussianBlur(out, (0, 0), blur)
    if rot90:
        out = np.ascontiguousarray(np.rot90(out, rot90))
    return out


def jpeg_bytes(bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def png_bytes(pil_img: Image.Image) -> bytes:
    buf = io.BytesIO()
    pil_img.save(buf, "PNG")
    return buf.getvalue()


def marks_of(result) -> dict:
    """SheetResult -> {q: mark}"""
    return {q: m for q, (m, _c) in result.answers.items()}
