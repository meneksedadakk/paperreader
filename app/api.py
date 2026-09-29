from flask import Blueprint, jsonify

from app.auth import role_required
from app.models import Exam, db
from app.services import report

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/teacher/exams/<int:exam_id>/results")
@role_required("teacher")
def exam_results(exam_id: int):
    exam = db.get_or_404(Exam, exam_id)
    resp = jsonify(report.exam_results(exam))
    resp.headers["Cache-Control"] = "no-store"
    return resp
