import io
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from app.models import Exam, PendingUpload, Submission, SubmissionAnswer, User, db
from omr.form_generator import render_form
from tests.factory import make_exam, student_marks
from tests.helpers import answer_key, jpeg_bytes, to_photo

KEY = answer_key()


@lru_cache(maxsize=None)
def photo(variant: str = "clean") -> bytes:
    """JPEG 'photo' of a filled sheet. clean: 20 right / 20 wrong / 80 blank (net 15 with penalty 4)."""
    marks = student_marks(KEY)
    if variant == "double":
        marks[5] = marks[5] + ("A" if marks[5] != "A" else "B")     # two bubbles on Türkçe 5
    return jpeg_bytes(to_photo(render_form(marks), rotation=3, perspective=0.03))


def upload(browser, exam_id, data, name="foto.jpg", follow=False):
    return browser.post(f"/student/exams/{exam_id}/upload",
                        {"photo": (io.BytesIO(data), name)}, content_type="multipart/form-data",
                        follow_redirects=follow)


def confirm(browser, exam_id, understood=True, **edits):
    data = {f"edit_{q}": v for q, v in edits.items()}
    if understood:
        data["understood"] = "on"
    return browser.post(f"/student/exams/{exam_id}/confirm", data)


def uploaded_files(app):
    root = Path(app.config["UPLOAD_DIR"])
    return sorted(p.name for sub in ("images", "debug") for p in (root / sub).glob("*"))


@pytest.fixture
def exam_id(app):
    with app.app_context():
        return make_exam()


def uid(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().id


# ---------- dashboard / visibility ----------

def test_dashboard_lists_only_published_exams(app, student):
    with app.app_context():
        make_exam(name="Yayında Sınav")
        make_exam(name="Taslak Sınav", active=False)
    html = student.get("/student/").get_data(as_text=True)
    assert "Yayında Sınav" in html and "Taslak Sınav" not in html and "Yüklenmedi" in html


def test_empty_dashboard(student):
    assert "yayında bir sınav yok" in student.get("/student/").get_data(as_text=True)


def test_unpublished_exam_cannot_be_opened_or_uploaded(app, student):
    with app.app_context():
        eid = make_exam(active=False)
    assert student.get(f"/student/exams/{eid}/upload").status_code == 404
    assert upload(student, eid, photo()).status_code == 404
    assert student.get("/student/exams/9999/upload").status_code == 404


def test_upload_page_warns_about_single_submission(student, exam_id):
    html = student.get(f"/student/exams/{exam_id}/upload").get_data(as_text=True)
    assert "yalnızca <strong>bir kez</strong>" in html and 'capture="environment"' in html


# ---------- happy path ----------

def test_full_flow_upload_review_confirm_result(app, student, teacher, exam_id):
    r = upload(student, exam_id, photo())
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/student/exams/{exam_id}/review")
    with app.app_context():
        assert PendingUpload.query.count() == 1 and Submission.query.count() == 0   # draft only, right unused
        assert len(uploaded_files(app)) == 2

    review = student.get(f"/student/exams/{exam_id}/review").get_data(as_text=True)
    assert "Tüm sorular net okundu" in review and "80 soru boş" in review
    assert "Onayla ve Gönder" in review and 'name="understood"' in review

    r = confirm(student, exam_id)
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/student/exams/{exam_id}/result")
    with app.app_context():
        sub = Submission.query.one()
        assert (sub.correct, sub.wrong, sub.blank, sub.net) == (20, 20, 80, 15.0)
        assert PendingUpload.query.count() == 0
        assert SubmissionAnswer.query.filter_by(submission_id=sub.id).count() == 120
        assert not any(a.edited_by_student for a in sub.answers)

    html = student.get(f"/student/exams/{exam_id}/result").get_data(as_text=True)
    assert "15.00" in html
    assert "Türkçe" in html and "Sosyal Bilimler" in html and "Temel Matematik" in html and "Fen Bilimleri" in html
    assert "Eksik konular" in html and "Paragraf" in html and "Tarih Bilimi" in html
    assert 'id="topicChart"' in html
    dash = student.get("/student/").get_data(as_text=True)
    assert "Gönderildi" in dash and "15.00" in dash

    # the teacher sees it live
    data = teacher.get(f"/api/teacher/exams/{exam_id}/results").get_json()
    assert data["submitted"] == 1 and data["rows"][0]["total"]["net"] == 15.0


def test_result_page_shows_correct_answers_of_wrong_questions(app, student, exam_id):
    upload(student, exam_id, photo())
    confirm(student, exam_id)
    html = student.get(f"/student/exams/{exam_id}/result").get_data(as_text=True)
    assert f"→ {KEY[21]}" in html


def test_result_before_submission_redirects_to_dashboard(student, exam_id):
    r = student.get(f"/student/exams/{exam_id}/result")
    assert r.status_code == 302 and r.headers["Location"].endswith("/student/")


def test_review_without_draft_redirects_to_upload(student, exam_id):
    assert student.get(f"/student/exams/{exam_id}/review").headers["Location"].endswith("/upload")


# ---------- one-time upload rule ----------

def test_second_upload_after_submission_is_refused(app, student, exam_id):
    upload(student, exam_id, photo())
    confirm(student, exam_id)
    files_before = uploaded_files(app)
    assert upload(student, exam_id, photo()).status_code == 409
    assert uploaded_files(app) == files_before                              # nothing new was stored
    with app.app_context():
        assert Submission.query.count() == 1 and PendingUpload.query.count() == 0


def test_upload_page_after_submission_redirects_to_result(student, exam_id):
    upload(student, exam_id, photo())
    confirm(student, exam_id)
    r = student.get(f"/student/exams/{exam_id}/upload")
    assert r.status_code == 302 and r.headers["Location"].endswith("/result")


def test_second_confirmation_is_refused(app, student, exam_id):
    upload(student, exam_id, photo())
    assert confirm(student, exam_id).status_code == 302
    assert confirm(student, exam_id).status_code == 409
    with app.app_context():
        assert Submission.query.count() == 1


def test_confirm_requires_the_final_checkbox(app, student, exam_id):
    upload(student, exam_id, photo())
    r = confirm(student, exam_id, understood=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/review")
    with app.app_context():
        assert Submission.query.count() == 0 and PendingUpload.query.count() == 1


def test_confirm_without_draft_sends_back_to_upload(student, exam_id):
    assert confirm(student, exam_id).headers["Location"].endswith("/upload")


def test_unreadable_photo_does_not_use_up_the_right(app, student, exam_id):
    blank = jpeg_bytes(np.full((900, 700, 3), 235, dtype=np.uint8))
    r = upload(student, exam_id, blank, follow=True)
    assert "çerçevesi bulunamadı" in r.get_data(as_text=True)
    with app.app_context():
        assert PendingUpload.query.count() == 0 and Submission.query.count() == 0
    assert uploaded_files(app) == []                                        # nothing stored
    assert upload(student, exam_id, photo()).status_code == 302             # a valid photo still works
    assert confirm(student, exam_id).status_code == 302


def test_reuploading_replaces_the_draft_and_cleans_old_files(app, student, exam_id):
    upload(student, exam_id, photo())
    first = uploaded_files(app)
    upload(student, exam_id, photo("double"))
    with app.app_context():
        assert PendingUpload.query.count() == 1
    now = uploaded_files(app)
    assert len(now) == 2 and not set(now) & set(first)
    assert "Çoklu" in student.get(f"/student/exams/{exam_id}/review").get_data(as_text=True)


def test_abandoned_draft_keeps_right_and_shows_on_dashboard(app, student, exam_id):
    upload(student, exam_id, photo())
    dash = student.get("/student/").get_data(as_text=True)
    assert "Onay bekliyor" in dash and "Onaya devam et" in dash
    assert student.get(f"/student/exams/{exam_id}/upload").status_code == 200   # can still re-upload


# ---------- input validation ----------

def test_upload_without_file(app, student, exam_id):
    r = student.post(f"/student/exams/{exam_id}/upload", {}, content_type="multipart/form-data", follow_redirects=True)
    assert "fotoğrafını seçin" in r.get_data(as_text=True)


@pytest.mark.parametrize("name", ["evil.exe", "notes.txt", "sheet.pdf", "noext"])
def test_disallowed_extensions(student, exam_id, name):
    r = upload(student, exam_id, photo(), name=name, follow=True)
    assert "Yalnızca JPG" in r.get_data(as_text=True)


def test_file_with_image_extension_but_not_an_image(app, student, exam_id):
    r = upload(student, exam_id, b"MZ\x90\x00 definitely not a jpeg", name="foto.jpg", follow=True)
    assert "okunabilir bir görsel değil" in r.get_data(as_text=True)
    assert uploaded_files(app) == []


def test_oversized_upload_is_rejected(student, exam_id):
    assert upload(student, exam_id, b"\0" * (10 * 1024 * 1024 + 10)).status_code == 413


def test_stored_names_are_random_not_user_controlled(app, student, exam_id):
    upload(student, exam_id, photo(), name="../../evil name.jpg")
    for f in uploaded_files(app):
        assert f.endswith(".jpg") and len(f) == 36 and "evil" not in f


# ---------- flagged questions ----------

def test_double_mark_is_flagged_and_can_be_fixed(app, student, teacher, exam_id):
    upload(student, exam_id, photo("double"))
    review = student.get(f"/student/exams/{exam_id}/review").get_data(as_text=True)
    assert 'name="edit_5"' in review and review.count('name="edit_') == 1     # only the doubtful question
    assert "1 soruda birden fazla şık işaretli" in review
    fixed = KEY[5]
    assert confirm(student, exam_id, **{"5": fixed}).status_code == 302
    with app.app_context():
        sub = Submission.query.one()
        a5 = next(a for a in sub.answers if a.question_no == 5)
        assert a5.marked_option == fixed and a5.is_correct and a5.edited_by_student
        assert (sub.correct, sub.wrong) == (20, 20)                          # back to the original clean sheet
    assert "1 soruyu kendiniz düzelttiniz" in student.get(f"/student/exams/{exam_id}/result").get_data(as_text=True)
    row = teacher.get(f"/api/teacher/exams/{exam_id}/results").get_json()["rows"][0]
    assert row["edited"] == 1


def test_unfixed_double_mark_counts_wrong(app, student, exam_id):
    upload(student, exam_id, photo("double"))
    confirm(student, exam_id)
    with app.app_context():
        sub = Submission.query.one()
        assert next(a for a in sub.answers if a.question_no == 5).marked_option == "*"
        assert (sub.correct, sub.wrong) == (19, 21)                          # Q5 was right before the extra bubble


def test_cannot_edit_questions_that_were_read_confidently(app, student, exam_id):
    upload(student, exam_id, photo())
    r = confirm(student, exam_id, **{"1": "E"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/review")
    with app.app_context():
        assert Submission.query.count() == 0


def test_invalid_edit_value_is_rejected(app, student, exam_id):
    upload(student, exam_id, photo("double"))
    assert confirm(student, exam_id, **{"5": "Z"}).headers["Location"].endswith("/review")
    with app.app_context():
        assert Submission.query.count() == 0


def test_confirm_after_exam_was_unpublished(app, student, teacher, exam_id):
    upload(student, exam_id, photo())
    teacher.post(f"/teacher/exams/{exam_id}/toggle")
    assert student.get(f"/student/exams/{exam_id}/review").status_code == 404
    with app.app_context():
        assert Submission.query.count() == 0


def test_result_stays_visible_after_unpublishing(app, student, teacher, exam_id):
    upload(student, exam_id, photo())
    confirm(student, exam_id)
    teacher.post(f"/teacher/exams/{exam_id}/toggle")
    assert student.get(f"/student/exams/{exam_id}/result").status_code == 200
    assert "Gönderildi" in student.get("/student/").get_data(as_text=True)


# ---------- privacy: students only see themselves ----------

def test_student_only_sees_own_result_and_files(app, student_factory, teacher, exam_id):
    s1, s2 = student_factory(1), student_factory(2)
    upload(s1, exam_id, photo())
    confirm(s1, exam_id)
    with app.app_context():
        sub_id = Submission.query.one().id

    assert s2.get(f"/student/exams/{exam_id}/result").status_code == 302        # has no result of his own
    assert "Öğrenci 1" not in s2.get("/student/").get_data(as_text=True)
    assert s2.get(f"/files/submission/{sub_id}/image").status_code == 404
    assert s2.get(f"/files/submission/{sub_id}/debug").status_code == 404
    assert s1.get(f"/files/submission/{sub_id}/image").status_code == 200
    assert s1.get(f"/files/submission/{sub_id}/image").mimetype == "image/jpeg"
    assert s1.get(f"/files/submission/{sub_id}/debug").status_code == 200
    assert teacher.get(f"/files/submission/{sub_id}/image").status_code == 200
    assert s1.get(f"/files/submission/{sub_id}/other").status_code == 404


def test_pending_files_are_private_to_their_owner(app, student_factory, exam_id):
    s1, s2 = student_factory(1), student_factory(2)
    upload(s1, exam_id, photo())
    assert s1.get(f"/files/pending/{exam_id}/debug").status_code == 200
    assert s2.get(f"/files/pending/{exam_id}/debug").status_code == 404


def test_each_student_can_submit_the_same_exam_once(app, student_factory, teacher, exam_id):
    for n in (1, 2, 3):
        b = student_factory(n)
        upload(b, exam_id, photo())
        assert confirm(b, exam_id).status_code == 302
    with app.app_context():
        assert Submission.query.count() == 3
    assert teacher.get(f"/api/teacher/exams/{exam_id}/results").get_json()["submitted"] == 3


def test_results_are_scoped_to_each_students_own_submission(app, student_factory, exam_id):
    s1, s2 = student_factory(1), student_factory(2)
    upload(s1, exam_id, photo())
    confirm(s1, exam_id)
    upload(s2, exam_id, photo("double"))
    confirm(s2, exam_id)                              # unfixed double mark -> 19 correct
    assert "1 soruyu kendiniz" not in s1.get(f"/student/exams/{exam_id}/result").get_data(as_text=True)
    with app.app_context():
        nets = {s.student.username: s.correct for s in Submission.query.all()}
    assert nets == {"ogr1": 20, "ogr2": 19}


# ---------- teacher reset re-opens the upload ----------

def test_after_reset_student_can_upload_again_and_old_files_are_gone(app, student, teacher, exam_id):
    upload(student, exam_id, photo())
    confirm(student, exam_id)
    old_files = uploaded_files(app)
    assert upload(student, exam_id, photo()).status_code == 409
    assert teacher.post(f"/teacher/exams/{exam_id}/students/{uid(app, 'ogr1')}/reset").status_code == 302
    assert not set(uploaded_files(app)) & set(old_files)
    assert upload(student, exam_id, photo("double")).status_code == 302
    assert confirm(student, exam_id).status_code == 302
    with app.app_context():
        assert Submission.query.count() == 1


# ---------- printable form ----------

def test_blank_form_pdf_is_served(student):
    r = student.get("/forms/tyt_120.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")


def test_generated_blank_form_is_readable_by_the_reader(app):
    """The printable orange form must itself be a valid input for the OMR (all blank)."""
    from omr import read_sheet
    img = to_photo(render_form({}), rotation=2)
    res = read_sheet(img)
    assert all(m is None for _, (m, _c) in res.answers.items())
