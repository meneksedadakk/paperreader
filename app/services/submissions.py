"""Submission lifecycle: draft (PendingUpload) -> one-time confirmed Submission -> scoring/reset."""
from pathlib import Path

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app import tyt
from app.models import AnswerKey, Exam, PendingUpload, Submission, SubmissionAnswer, db
from app.services import grading


class SubmissionError(Exception):
    """Business-rule violation; message is user-facing (Turkish)."""


class AlreadySubmitted(SubmissionError):
    pass


class InvalidEdit(SubmissionError):
    pass


VALID_MARKS = set(tyt.OPTIONS)


# ---------- scoring ----------

def key_maps(exam: Exam) -> tuple[dict, dict]:
    key = {k.question_no: k.correct_option for k in exam.keys}
    topics = {k.question_no: k.topic for k in exam.keys}
    return key, topics


def submission_marks(sub: Submission) -> dict:
    return {a.question_no: a.marked_option for a in sub.answers}


def grade_submission(sub: Submission, exam: Exam | None = None) -> dict:
    exam = exam or sub.exam
    key, topics = key_maps(exam)
    return grading.grade(submission_marks(sub), key, topics, exam.wrong_penalty)


def apply_scores(sub: Submission, result: dict) -> None:
    for a in sub.answers:
        a.is_correct = result["statuses"][a.question_no] == grading.CORRECT
    total = result["total"]
    sub.correct, sub.wrong, sub.blank, sub.net = total["correct"], total["wrong"], total["blank"], total["net"]


def rescore_exam(exam: Exam) -> int:
    """Re-grade every submission of the exam (after the key or penalty changed)."""
    for sub in exam.submissions:
        apply_scores(sub, grade_submission(sub, exam))
    return len(exam.submissions)


# ---------- files ----------

def _upload_root() -> Path:
    return Path(current_app.config["UPLOAD_DIR"])


def remove_upload(rel_path: str | None) -> None:
    if not rel_path:
        return
    root = _upload_root().resolve()
    target = (root / rel_path).resolve()
    if root in target.parents and target.exists():
        target.unlink()


# ---------- draft ----------

def get_submission(exam_id: int, student_id: int) -> Submission | None:
    return Submission.query.filter_by(exam_id=exam_id, student_id=student_id).first()


def get_pending(exam_id: int, student_id: int) -> PendingUpload | None:
    return PendingUpload.query.filter_by(exam_id=exam_id, student_id=student_id).first()


def save_pending(exam: Exam, student_id: int, omr_json: dict, image_path: str,
                 debug_path: str | None) -> PendingUpload:
    """Store/replace the student's draft. Never uses up the upload right."""
    if get_submission(exam.id, student_id):
        raise AlreadySubmitted("Bu sınav için zaten bir gönderim yaptınız.")
    pending = get_pending(exam.id, student_id)
    if pending:
        remove_upload(pending.image_path)
        remove_upload(pending.debug_image_path)
        pending.image_path, pending.debug_image_path = image_path, debug_path
        pending.omr_result = omr_json
    else:
        pending = PendingUpload(exam_id=exam.id, student_id=student_id, image_path=image_path,
                                debug_image_path=debug_path, omr_result=omr_json)
        db.session.add(pending)
    db.session.commit()
    return pending


def pending_marks(pending: PendingUpload) -> dict:
    return {int(q): v["o"] for q, v in pending.omr_result["answers"].items()}


def normalize_edit(value) -> str | None:
    value = (value or "").strip().upper()
    if value == "":
        return None
    if value not in VALID_MARKS:
        raise InvalidEdit(f"Geçersiz şık: {value!r}")
    return value


def confirm_pending(pending: PendingUpload, edits: dict | None = None) -> Submission:
    """Turn the draft into the one and only submission. `edits`: {question_no: 'A'..'E' | ''}.

    Only questions the reader flagged (double mark / low confidence) may be edited.
    """
    exam = db.session.get(Exam, pending.exam_id)
    if not exam or not exam.is_active:
        raise SubmissionError("Bu sınav şu anda gönderime kapalı.")
    if get_submission(pending.exam_id, pending.student_id):
        raise AlreadySubmitted("Bu sınav için zaten bir gönderim yaptınız.")

    flagged = set(pending.omr_result.get("flagged", []))
    marks = pending_marks(pending)
    detected = dict(marks)
    edited = set()
    for q, value in (edits or {}).items():
        q = int(q)
        if q not in flagged:
            raise InvalidEdit("Yalnızca şüpheli olarak işaretlenen sorular düzeltilebilir.")
        new = normalize_edit(value)
        if new != detected[q]:
            edited.add(q)
        marks[q] = new
    # unresolved double marks ('*') are kept as they are and counted wrong

    sub = Submission(exam_id=exam.id, student_id=pending.student_id, image_path=pending.image_path,
                     debug_image_path=pending.debug_image_path)
    for q in range(1, tyt.TOTAL_QUESTIONS + 1):
        conf = pending.omr_result["answers"][str(q)]["c"]
        sub.answers.append(SubmissionAnswer(question_no=q, marked_option=marks[q], confidence=conf,
                                            edited_by_student=q in edited))
    db.session.add(sub)
    db.session.flush()
    apply_scores(sub, grade_submission(sub, exam))
    db.session.delete(pending)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AlreadySubmitted("Bu sınav için zaten bir gönderim yaptınız.") from None
    return sub


def reset_submission(sub: Submission) -> None:
    """Teacher-only: delete the submission so the student may upload again."""
    remove_upload(sub.image_path)
    remove_upload(sub.debug_image_path)
    db.session.delete(sub)
    db.session.commit()


# ---------- answer key ----------

def replace_answer_key(exam: Exam, key: dict, topics: dict) -> None:
    """key: {q: 'A'..'E' | None}; topics: {q: str}. Must contain all 120 questions."""
    if set(key) != set(range(1, tyt.TOTAL_QUESTIONS + 1)):
        raise SubmissionError("Cevap anahtarı 120 sorunun tamamını içermelidir.")
    existing = {k.question_no: k for k in exam.keys}
    for q, opt in key.items():
        row = existing.get(q)
        if row is None:
            row = AnswerKey(exam_id=exam.id, question_no=q)
            db.session.add(row)
        row.correct_option = opt
        row.topic = (topics.get(q) or "").strip()
