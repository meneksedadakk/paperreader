from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AnswerKey, Exam, PendingUpload, Submission, SubmissionAnswer, User, db
from app.services import submissions as svc
from tests.factory import make_exam, omr_json, student_marks, touch_upload, wrong_option
from tests.helpers import answer_key

KEY = answer_key()


@pytest.fixture
def env(ctx):
    exam_id = make_exam()
    student = User.query.filter_by(username="ogr1").one()
    return ctx, db.session.get(Exam, exam_id), student


def pending_for(env, marks=None, flagged=(), tag="a"):
    app, exam, student = env
    marks = marks if marks is not None else student_marks(KEY)
    img = touch_upload(app, f"images/{tag}.jpg")
    dbg = touch_upload(app, f"debug/{tag}.jpg")
    return svc.save_pending(exam, student.id, omr_json(marks, flagged), img, dbg)


def exists(app, rel):
    return (Path(app.config["UPLOAD_DIR"]) / rel).exists()


# ---------- pending draft ----------

def test_save_pending_creates_draft_only(env):
    _, exam, student = env
    p = pending_for(env)
    assert PendingUpload.query.count() == 1
    assert Submission.query.count() == 0
    assert svc.get_pending(exam.id, student.id).id == p.id
    assert svc.pending_marks(p)[1] == KEY[1]


def test_new_upload_replaces_old_draft_and_deletes_old_files(env):
    app, exam, student = env
    pending_for(env, tag="first")
    pending_for(env, marks={q: None for q in range(1, 121)}, tag="second")
    assert PendingUpload.query.count() == 1
    assert not exists(app, "images/first.jpg") and not exists(app, "debug/first.jpg")
    assert exists(app, "images/second.jpg")
    assert all(m is None for m in svc.pending_marks(svc.get_pending(exam.id, student.id)).values())


def test_drafts_of_different_students_are_independent(env):
    app, exam, student = env
    other = User.query.filter_by(username="ogr2").one()
    pending_for(env)
    svc.save_pending(exam, other.id, omr_json(student_marks(KEY)), touch_upload(app, "images/o.jpg"), None)
    assert PendingUpload.query.count() == 2


# ---------- confirm ----------

def test_confirm_creates_scored_submission_and_removes_draft(env):
    _, exam, student = env
    sub = svc.confirm_pending(pending_for(env))
    assert PendingUpload.query.count() == 0
    assert (sub.correct, sub.wrong, sub.blank) == (20, 20, 80)
    assert sub.net == 15.0
    assert SubmissionAnswer.query.filter_by(submission_id=sub.id).count() == 120
    assert svc.get_submission(exam.id, student.id).id == sub.id
    correct_rows = [a for a in sub.answers if a.is_correct]
    assert len(correct_rows) == 20 and all(a.question_no <= 20 for a in correct_rows)
    assert not any(a.edited_by_student for a in sub.answers)


def test_second_confirmation_and_second_upload_are_blocked(env):
    _, exam, student = env
    p = pending_for(env)
    svc.confirm_pending(p)
    with pytest.raises(svc.AlreadySubmitted):
        pending_for(env, tag="again")       # cannot even save a new draft
    assert Submission.query.count() == 1


def test_confirm_stale_draft_after_submission_is_blocked(env):
    app, exam, student = env
    p = pending_for(env)
    stale = PendingUpload(exam_id=exam.id, student_id=student.id, image_path="images/s.jpg",
                          omr_result=p.omr_result)
    svc.confirm_pending(p)
    db.session.add(stale)
    db.session.commit()
    with pytest.raises(svc.AlreadySubmitted):
        svc.confirm_pending(stale)
    assert Submission.query.count() == 1


def test_database_enforces_one_submission_per_student_and_exam(env):
    _, exam, student = env
    svc.confirm_pending(pending_for(env))
    db.session.add(Submission(exam_id=exam.id, student_id=student.id, image_path="x"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_confirm_on_unpublished_exam_is_rejected(env):
    _, exam, _ = env
    p = pending_for(env)
    exam.is_active = False
    db.session.commit()
    with pytest.raises(svc.SubmissionError):
        svc.confirm_pending(p)
    assert Submission.query.count() == 0 and PendingUpload.query.count() == 1


# ---------- student edits ----------

def flagged_case(env):
    marks = student_marks(KEY)
    marks[100] = "*"   # double mark
    marks[101] = "C"   # low confidence
    return pending_for(env, marks=marks, flagged=(100, 101)), marks


def test_edit_flagged_questions(env):
    p, _ = flagged_case(env)
    sub = svc.confirm_pending(p, {100: KEY[100], 101: ""})
    by_q = {a.question_no: a for a in sub.answers}
    assert by_q[100].marked_option == KEY[100] and by_q[100].is_correct and by_q[100].edited_by_student
    assert by_q[101].marked_option is None and by_q[101].edited_by_student
    assert by_q[102].edited_by_student is False


def test_unedited_double_mark_stays_wrong(env):
    p, _ = flagged_case(env)
    sub = svc.confirm_pending(p, {})
    by_q = {a.question_no: a for a in sub.answers}
    assert by_q[100].marked_option == "*" and not by_q[100].is_correct
    q101_right = KEY[101] == "C"
    assert sub.wrong == 20 + 1 + (0 if q101_right else 1)   # 20 wrong answers + double mark (+ Q101)
    assert sub.correct == 20 + (1 if q101_right else 0)


def test_edit_that_keeps_the_same_value_is_not_marked_edited(env):
    p, _ = flagged_case(env)
    sub = svc.confirm_pending(p, {101: "C"})
    assert next(a for a in sub.answers if a.question_no == 101).edited_by_student is False


def test_cannot_edit_unflagged_question(env):
    p, _ = flagged_case(env)
    with pytest.raises(svc.InvalidEdit):
        svc.confirm_pending(p, {1: "E"})
    assert Submission.query.count() == 0 and PendingUpload.query.count() == 1


@pytest.mark.parametrize("bad", ["F", "AB", "*", "1"])
def test_invalid_edit_values_are_rejected(env, bad):
    p, _ = flagged_case(env)
    with pytest.raises(svc.InvalidEdit):
        svc.confirm_pending(p, {100: bad})


def test_normalize_edit():
    assert svc.normalize_edit(" b ") == "B"
    assert svc.normalize_edit("") is None and svc.normalize_edit(None) is None


# ---------- rescoring ----------

def test_rescore_after_key_and_penalty_change(env):
    _, exam, _ = env
    sub = svc.confirm_pending(pending_for(env))
    assert sub.net == 15.0
    # teacher fixes the key for Türkçe 21 (student answered it wrong -> now right) and cancels Türkçe 22
    new_key = dict(KEY)
    marks = student_marks(KEY)
    new_key[21] = marks[21]
    new_key[22] = None
    svc.replace_answer_key(exam, new_key, {})
    exam.wrong_penalty = 2
    db.session.flush()
    assert svc.rescore_exam(exam) == 1
    db.session.commit()
    sub = db.session.get(Submission, sub.id)
    assert (sub.correct, sub.wrong, sub.blank) == (22, 18, 80)
    assert sub.net == 22 - 18 / 2
    by_q = {a.question_no: a for a in sub.answers}
    assert by_q[21].is_correct and by_q[22].is_correct


def test_rescore_with_no_submissions(env):
    _, exam, _ = env
    assert svc.rescore_exam(exam) == 0


# ---------- reset ----------

def test_reset_deletes_submission_and_files_and_reopens_upload(env):
    app, exam, student = env
    sub = svc.confirm_pending(pending_for(env, tag="r"))
    svc.reset_submission(sub)
    assert Submission.query.count() == 0 and SubmissionAnswer.query.count() == 0
    assert not exists(app, "images/r.jpg") and not exists(app, "debug/r.jpg")
    pending_for(env, tag="r2")                       # may upload again
    assert svc.confirm_pending(svc.get_pending(exam.id, student.id)).net == 15.0


def test_remove_upload_never_leaves_the_upload_dir(env):
    app, _, _ = env
    outside = Path(app.config["UPLOAD_DIR"]).parent / "secret.txt"
    outside.write_text("keep me")
    svc.remove_upload("../secret.txt")
    assert outside.exists()
    svc.remove_upload(None)
    svc.remove_upload("images/does-not-exist.jpg")


# ---------- answer key ----------

def test_replace_answer_key_requires_all_120(env):
    _, exam, _ = env
    partial = {q: "A" for q in range(1, 120)}
    with pytest.raises(svc.SubmissionError):
        svc.replace_answer_key(exam, partial, {})


def test_replace_answer_key_updates_in_place_and_keeps_120_rows(env):
    _, exam, _ = env
    new = {q: "E" for q in range(1, 121)}
    new[3] = None
    svc.replace_answer_key(exam, new, {3: "  Konu  "})
    db.session.commit()
    rows = AnswerKey.query.filter_by(exam_id=exam.id).order_by(AnswerKey.question_no).all()
    assert len(rows) == 120
    assert rows[2].correct_option is None and rows[2].topic == "Konu"
    assert rows[0].correct_option == "E"
