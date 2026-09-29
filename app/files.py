"""Authorised file serving: uploaded photos are never exposed as static files."""
from pathlib import Path

from flask import Blueprint, abort, current_app, send_file
from flask_login import current_user, login_required

from app.auth import role_required
from app.models import Submission
from app.services import submissions

bp = Blueprint("files", __name__)


def _send_upload(rel_path: str | None):
    if not rel_path:
        abort(404)
    root = Path(current_app.config["UPLOAD_DIR"]).resolve()
    target = (root / rel_path).resolve()
    if root not in target.parents or not target.is_file():
        abort(404)
    return send_file(target, mimetype="image/jpeg", max_age=0)


def _kind_path(obj, kind: str):
    if kind == "image":
        return obj.image_path
    if kind == "debug":
        return obj.debug_image_path
    abort(404)


@bp.route("/files/submission/<int:sub_id>/<kind>")
@login_required
def submission_file(sub_id: int, kind: str):
    sub = Submission.query.get_or_404(sub_id)
    if not current_user.is_teacher and sub.student_id != current_user.id:
        abort(404)  # do not reveal that it exists
    return _send_upload(_kind_path(sub, kind))


@bp.route("/files/pending/<int:exam_id>/<kind>")
@role_required("student")
def pending_file(exam_id: int, kind: str):
    pending = submissions.get_pending(exam_id, current_user.id)
    if not pending:
        abort(404)
    return _send_upload(_kind_path(pending, kind))


@bp.route("/forms/tyt_120.pdf")
@login_required
def blank_form():
    """Printable orange-and-white TYT answer sheet (generated once, cached in instance/)."""
    from omr.form_generator import save_pdf

    path = Path(current_app.instance_path) / "forms" / "tyt_120.pdf"
    if not path.exists():
        save_pdf(path)
    return send_file(path, mimetype="application/pdf", download_name="tyt_optik_form.pdf")
