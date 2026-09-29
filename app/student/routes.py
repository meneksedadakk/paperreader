import uuid
from pathlib import Path

import cv2
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import tyt
from app.auth import role_required
from app.models import Exam, db
from app.services import report, submissions
from app.services.submissions import AlreadySubmitted, SubmissionError
from omr import OMRError, reader
from omr.preprocess import load_image

bp = Blueprint("student", __name__, url_prefix="/student")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _visible_exam(exam_id: int) -> Exam:
    exam = db.get_or_404(Exam, exam_id)
    if not exam.is_active and not submissions.get_submission(exam.id, current_user.id):
        abort(404)
    return exam


@bp.route("/")
@role_required("student")
def dashboard():
    rows = []
    for exam in Exam.query.order_by(Exam.created_at.desc()).all():
        sub = submissions.get_submission(exam.id, current_user.id)
        if not exam.is_active and not sub:
            continue
        rows.append({"exam": exam, "submission": sub,
                     "pending": None if sub else submissions.get_pending(exam.id, current_user.id)})
    return render_template("student/dashboard.html", rows=rows)


def _save_jpeg(img, subdir: str) -> str:
    rel = f"{subdir}/{uuid.uuid4().hex}.jpg"
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise SubmissionError("Görsel kaydedilemedi.")
    (Path(current_app.config["UPLOAD_DIR"]) / rel).write_bytes(buf.tobytes())
    return rel


@bp.route("/exams/<int:exam_id>/upload", methods=["GET", "POST"])
@role_required("student")
def upload(exam_id: int):
    exam = _visible_exam(exam_id)
    if submissions.get_submission(exam.id, current_user.id):
        if request.method == "POST":
            abort(409)
        flash("Bu sınav için gönderiminizi zaten yaptınız.", "info")
        return redirect(url_for("student.result", exam_id=exam.id))
    if not exam.is_active:
        abort(404)

    if request.method == "POST":
        file = request.files.get("photo")
        if not file or not file.filename:
            flash("Lütfen optik formun fotoğrafını seçin.", "danger")
            return redirect(url_for("student.upload", exam_id=exam.id))
        if Path(file.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
            flash("Yalnızca JPG, PNG, WEBP veya BMP görseller yüklenebilir.", "danger")
            return redirect(url_for("student.upload", exam_id=exam.id))
        try:
            img = load_image(file.read())
            result = reader.read_sheet(img)
        except OMRError as exc:  # unreadable photo: nothing is stored, upload right is untouched
            flash(str(exc), "danger")
            return redirect(url_for("student.upload", exam_id=exam.id))

        image_path = debug_path = None
        try:
            image_path = _save_jpeg(img, "images")
            debug_path = _save_jpeg(reader.debug_overlay(result), "debug")
            submissions.save_pending(exam, current_user.id, result.to_json(), image_path, debug_path)
        except AlreadySubmitted:
            submissions.remove_upload(image_path)
            submissions.remove_upload(debug_path)
            abort(409)
        return redirect(url_for("student.review", exam_id=exam.id))

    pending = submissions.get_pending(exam.id, current_user.id)
    return render_template("student/upload.html", exam=exam, pending=pending)


@bp.route("/exams/<int:exam_id>/review")
@role_required("student")
def review(exam_id: int):
    exam = _visible_exam(exam_id)
    if submissions.get_submission(exam.id, current_user.id):
        return redirect(url_for("student.result", exam_id=exam.id))
    pending = submissions.get_pending(exam.id, current_user.id)
    if not pending:
        flash("Önce optik formunuzun fotoğrafını yükleyin.", "info")
        return redirect(url_for("student.upload", exam_id=exam.id))
    marks = submissions.pending_marks(pending)
    flagged = set(pending.omr_result["flagged"])
    tests = []
    for t in tyt.TESTS:
        tests.append({"name": t.name, "questions": [
            {"q": q, "local": tyt.local_no(q), "mark": marks[q], "flagged": q in flagged,
             "confidence": pending.omr_result["answers"][str(q)]["c"]}
            for q in range(t.first, t.last + 1)]})
    answered = sum(1 for m in marks.values() if m in tyt.OPTIONS)
    return render_template("student/review.html", exam=exam, tests=tests, flagged=sorted(flagged),
                           answered=answered, blank=sum(1 for m in marks.values() if m is None),
                           doubles=sum(1 for m in marks.values() if m == "*"))


@bp.route("/exams/<int:exam_id>/confirm", methods=["POST"])
@role_required("student")
def confirm(exam_id: int):
    exam = _visible_exam(exam_id)
    if submissions.get_submission(exam.id, current_user.id):
        abort(409)
    pending = submissions.get_pending(exam.id, current_user.id)
    if not pending:
        flash("Onaylanacak bir yükleme bulunamadı. Fotoğrafı yeniden yükleyin.", "warning")
        return redirect(url_for("student.upload", exam_id=exam.id))
    if request.form.get("understood") != "on":
        flash("Göndermeden önce 'gönderimin kesin olduğunu' onaylamalısınız.", "danger")
        return redirect(url_for("student.review", exam_id=exam.id))
    edits = {int(k[5:]): v for k, v in request.form.items() if k.startswith("edit_") and k[5:].isdigit()}
    try:
        submissions.confirm_pending(pending, edits)
    except AlreadySubmitted:
        abort(409)
    except SubmissionError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("student.review", exam_id=exam.id))
    flash("Sonuçlarınız kaydedildi.", "success")
    return redirect(url_for("student.result", exam_id=exam.id))


@bp.route("/exams/<int:exam_id>/result")
@role_required("student")
def result(exam_id: int):
    exam = db.get_or_404(Exam, exam_id)
    sub = submissions.get_submission(exam.id, current_user.id)  # always the current user's own row
    if not sub:
        flash("Bu sınav için henüz gönderim yapmadınız.", "info")
        return redirect(url_for("student.dashboard"))
    return render_template("student/result.html", exam=exam, rep=report.build_report(sub))
