"""Image preprocessing: load, find the black frame, perspective-correct, normalise lighting.

The reader works on the RED channel only: orange/magenta print is bright in red, while pencil
marks and the thick black frame stay dark.
"""
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

from omr import geometry

MAX_SIDE = 2000
PX_PER_PT = 3.0
WARP_W = int(round(geometry.FRAME_W * PX_PER_PT))
WARP_H = int(round(geometry.FRAME_H * PX_PER_PT))
RATIO_TOLERANCE = 0.10


class OMRError(Exception):
    """The photo could not be read as a TYT answer sheet (message is user-facing, Turkish)."""


def load_image(data: bytes, max_side: int = MAX_SIDE) -> np.ndarray:
    """Decode bytes to a BGR array, honouring EXIF orientation and limiting the size."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            if max(w, h) > max_side:
                s = max_side / max(w, h)
                im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
            rgb = np.asarray(im)
    except Exception as exc:  # unreadable / not an image
        raise OMRError("Yüklenen dosya okunabilir bir görsel değil.") from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners as tl, tr, br, bl (clockwise from top-left)."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()  # y - x
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
                    dtype=np.float32)


def _side_ratio(c: np.ndarray) -> float:
    w = (np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[2] - c[3])) / 2
    h = (np.linalg.norm(c[3] - c[0]) + np.linalg.norm(c[2] - c[1])) / 2
    return w / h if h else 0.0


def _edge_is_dark(red: np.ndarray, corners: np.ndarray) -> bool:
    """True if just inside the candidate's edges the image is dark (thick black frame line).

    Rejects the paper's own edge (white just inside) and the inner boundary of the frame ring.
    """
    center = corners.mean(axis=0)
    side = (np.linalg.norm(corners[1] - corners[0]) + np.linalg.norm(corners[2] - corners[3])) / 2
    inset = max(1.5, 0.5 * geometry.FRAME_LINE * side / geometry.FRAME_W)
    pts = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        for t in np.linspace(0.05, 0.95, 40):
            p = a + (b - a) * t
            v = center - p
            pts.append(p + v / (np.linalg.norm(v) or 1) * inset)
    pts = np.round(np.array(pts)).astype(int)
    h, w = red.shape
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
    edge = float(np.median(red[pts[:, 1], pts[:, 0]]))
    paper = float(np.percentile(red, 75))
    return edge < 0.55 * paper


def _binary_candidates(red: np.ndarray):
    blur = cv2.GaussianBlur(red, (5, 5), 0)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    yield otsu
    block = max(31, (min(red.shape) // 20) | 1)
    yield cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 12)


def find_frame(img_bgr: np.ndarray) -> np.ndarray:
    """Find the outer black frame; returns 4 corners (tl, tr, br, bl) in image pixels.

    The sheet may be rotated by 90 degrees; the caller resolves the final orientation.
    """
    red = img_bgr[:, :, 2]
    img_area = red.shape[0] * red.shape[1]
    ratio = geometry.FRAME_RATIO
    best, best_area = None, 0.0
    for binary in _binary_candidates(red):
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 0.05 * img_area or area <= best_area:
                continue
            approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            x, y, bw, bh = cv2.boundingRect(approx)
            if x <= 2 or y <= 2 or x + bw >= red.shape[1] - 2 or y + bh >= red.shape[0] - 2:
                continue  # touches the image border: table/background blob, not the frame
            corners = order_corners(approx)
            r = _side_ratio(corners)
            if (min(abs(r - ratio) / ratio, abs(r - 1 / ratio) * ratio) < RATIO_TOLERANCE
                    and _edge_is_dark(red, corners)):
                best, best_area = corners, area
        if best is not None:
            break
    if best is None:
        raise OMRError("Optik formun siyah çerçevesi bulunamadı. Formun 4 köşesi görünecek şekilde, "
                       "düz ve iyi aydınlatılmış bir zeminde tekrar çekin.")
    return best


def warp(img_bgr: np.ndarray, corners: np.ndarray) -> np.ndarray:
    dst = np.array([[0, 0], [WARP_W - 1, 0], [WARP_W - 1, WARP_H - 1], [0, WARP_H - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
    return cv2.warpPerspective(img_bgr, m, (WARP_W, WARP_H), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)


def normalize_lighting(gray: np.ndarray) -> np.ndarray:
    """Divide by an estimate of the paper brightness so shadows/gradients disappear.

    Result: ~1.0 on blank paper, small values on ink.
    """
    small = cv2.resize(gray, (gray.shape[1] // 4, gray.shape[0] // 4), interpolation=cv2.INTER_AREA)
    bg = cv2.medianBlur(small, 31)
    bg = cv2.resize(bg, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
    bg = np.maximum(bg.astype(np.float32), 30.0)
    return np.clip(gray.astype(np.float32) / bg, 0.0, 1.5)


def _empty_zone_ink(warped_red: np.ndarray) -> float:
    """Ink in the areas that are blank on an upright sheet (rows 21-40 of the 20-question blocks).

    On an upside-down sheet those areas fall on printed rows, numbers and pencil marks.
    """
    ink = normalize_lighting(warped_red) < 0.6
    x_off, y_off = geometry.FRAME_OUTER[0], geometry.FRAME_OUTER[1]
    total = area = 0
    for bi in (1, 3):  # sosyal, fen
        ax = geometry.BLOCKS[bi][1]
        x0 = int((ax - 14 - x_off) * PX_PER_PT)
        x1 = int((ax + 4 * geometry.COL_STEP + 6 - x_off) * PX_PER_PT)
        y0 = int((geometry.FIRST_ROW_Y + 20 * geometry.ROW_STEP - 6 - y_off) * PX_PER_PT)
        y1 = int((geometry.FIRST_ROW_Y + 39 * geometry.ROW_STEP + 6 - y_off) * PX_PER_PT)
        zone = ink[y0:y1, x0:x1]
        total += zone.sum()
        area += zone.size
    return total / area


def rectify(img_bgr: np.ndarray, template: dict) -> np.ndarray:
    """Frame detection + perspective correction + orientation resolution -> canonical BGR sheet."""
    corners = find_frame(img_bgr)
    ratio = geometry.FRAME_RATIO
    r = _side_ratio(corners)
    landscape = abs(r - 1 / ratio) * ratio < abs(r - ratio) / ratio
    # Portrait: shifts 0 (upright) or 2 (upside down). Landscape: shifts 1 or 3 (rotated +-90).
    shifts = (1, 3) if landscape else (0, 2)
    best, best_score = None, float("inf")
    for shift in shifts:
        candidate = warp(img_bgr, np.roll(corners, -shift, axis=0))
        score = _empty_zone_ink(candidate[:, :, 2])
        if score < best_score - 1e-9:
            best, best_score = candidate, score
    return best
