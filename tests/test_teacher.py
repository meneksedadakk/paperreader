import json

import pytest

from app.models import AnswerKey, Exam, Submission, User, db
from app.services import submissions as svc
from tests.factory import TOPICS, make_exam, omr_json, student_marks, touch_upload
from tests.helpers import answer_key

KEY = answer_key()


def form_data(key=None, topics=None, name="TYT Deneme 1", penalty="4", description="", drop=(), **extra):
    key = KEY if key is None else key
    topics = TOPICS if topics is None else topics
    data = {"name": name, "wrong_penalty": penalty, "description": description}
    for q in range(1, 121):
        if q in drop:
            continue
        data[f"ans_{q}"] = "X" if key[q] is None else key[q]
        data[f"topic_{q}"] = topics.get(q, "")
    data.update(extra)
    return data


def submit_student(app, username, marks=None, exam_id=1):
    with app.app_context():
        exam = db.session.get(Exam, exam_id)
        sid = User.query.filter_by(username=username).one().id
        marks = marks if marks is not None else student_marks(KEY)
        p = svc.save_pending(exam, sid, omr_json(marks), touch_upload(app, f"images/{username}.jpg"),
                             touch_upload(app, f"debug/{username}.jpg"))
        return svc.confirm_pending(p).id


# ---------- creating an exam ----------

def test_dashboard_starts_empty(teacher):
    r = teacher.get("/teacher/")
    assert r.status_code == 200 and "Henüz sınav yok" in r.get_data(as_text=True)


def test_dashboard_offers_the_blank_optic_form(teacher):
    html = teacher.get("/teacher/").get_data(as_text=True)
    assert "Boş optik formu indir" in html and "/forms/tyt_120.pdf" in html


def test_new_exam_form_has_all_120_rows_and_required_penalty(teacher):
    html = teacher.get("/teacher/exams/new").get_data(as_text=True)
    assert 'name="ans_1"' in html and 'name="ans_120"' in html and 'name="ans_121"' not in html
    assert html.count('type="radio"') == 120 * 6                       # A B C D E + İptal
    assert 'name="wrong_penalty"' in html and "required" in html
    for test in ("Türkçe", "Sosyal Bilimler", "Temel Matematik", "Fen Bilimleri"):
        assert test in html
    assert 'id="topics-Fizik"' in html                                  # topic suggestions per subject


def test_create_exam_saves_draft_with_full_key(app, teacher):
    r = teacher.post("/teacher/exams/new", form_data(description="Ekim denemesi"))
    assert r.status_code == 302
    with app.app_context():
        exam = Exam.query.one()
        assert exam.name == "TYT Deneme 1" and exam.description == "Ekim denemesi"
        assert exam.wrong_penalty == 4.0 and exam.is_active is False
        assert exam.created_by == User.query.filter_by(username="admin").one().id
        keys = AnswerKey.query.filter_by(exam_id=exam.id).order_by(AnswerKey.question_no).all()
        assert [k.question_no for k in keys] == list(range(1, 121))
        assert all(k.correct_option == KEY[k.question_no] for k in keys)
        assert keys[0].topic == "Sözcükte Anlam" and keys[45].topic == "" and keys[40].topic == "Tarih Bilimi"


def test_cancelled_question_is_stored_as_null(app, teacher):
    key = dict(KEY)
    key[10] = None
    teacher.post("/teacher/exams/new", form_data(key=key))
    with app.app_context():
        assert AnswerKey.query.filter_by(question_no=10).one().correct_option is None
        assert AnswerKey.query.filter_by(question_no=11).one().correct_option == KEY[11]


@pytest.mark.parametrize("penalty,expected", [("4", 4.0), ("3", 3.0), ("0", 0.0), ("4,5", 4.5), (" 2.5 ", 2.5)])
def test_valid_penalties(app, teacher, penalty, expected):
    assert teacher.post("/teacher/exams/new", form_data(penalty=penalty)).status_code == 302
    with app.app_context():
        assert Exam.query.one().wrong_penalty == expected


@pytest.mark.parametrize("penalty", ["", "  ", "abc", "-1", "nan", "inf", "101", "4 yanlış"])
def test_penalty_is_required_and_validated(app, teacher, penalty):
    r = teacher.post("/teacher/exams/new", form_data(penalty=penalty))
    assert r.status_code == 400
    assert "Yanlış katsayısı zorunludur" in r.get_data(as_text=True)
    with app.app_context():
        assert Exam.query.count() == 0


@pytest.mark.parametrize("name", ["", "   "])
def test_exam_name_is_required(app, teacher, name):
    r = teacher.post("/teacher/exams/new", form_data(name=name))
    assert r.status_code == 400 and "Sınav adı zorunludur" in r.get_data(as_text=True)
    with app.app_context():
        assert Exam.query.count() == 0


def test_name_too_long_is_rejected(app, teacher):
    assert teacher.post("/teacher/exams/new", form_data(name="x" * 201)).status_code == 400


def test_all_120_answers_are_mandatory(app, teacher):
    r = teacher.post("/teacher/exams/new", form_data(drop={7, 77}))
    html = r.get_data(as_text=True)
    assert r.status_code == 400
    assert "2 sorunun cevabı girilmemiş" in html
    assert html.count("key-row missing") == 2                            # exactly the two rows are highlighted
    with app.app_context():
        assert Exam.query.count() == 0 and AnswerKey.query.count() == 0


def test_missing_answers_keep_everything_else_the_teacher_typed(teacher):
    r = teacher.post("/teacher/exams/new", form_data(name="Yarım kalan", drop={120}, penalty="3"))
    html = r.get_data(as_text=True)
    assert 'value="Yarım kalan"' in html and 'value="3"' in html
    assert html.count(" checked") == 119
    assert 'value="Paragraf"' in html


@pytest.mark.parametrize("bad", ["F", "", "AB", "1", "*", "a b"])
def test_invalid_answer_values_count_as_missing(app, teacher, bad):
    data = form_data()
    data["ans_50"] = bad
    r = teacher.post("/teacher/exams/new", data)
    assert r.status_code == 400
    with app.app_context():
        assert Exam.query.count() == 0


def test_lowercase_answers_are_accepted(app, teacher):
    data = form_data()
    data["ans_1"] = "c"
    assert teacher.post("/teacher/exams/new", data).status_code == 302
    with app.app_context():
        assert AnswerKey.query.filter_by(question_no=1).one().correct_option == "C"


def test_topics_are_optional_and_trimmed(app, teacher):
    data = form_data(topics={})
    data["topic_1"] = "   Paragraf   "
    data["topic_2"] = "y" * 300
    assert teacher.post("/teacher/exams/new", data).status_code == 302
    with app.app_context():
        k = {row.question_no: row.topic for row in AnswerKey.query.all()}
        assert k[1] == "Paragraf" and len(k[2]) == 120 and k[3] == ""


def test_exam_lists_appear_on_dashboard(app, teacher):
    teacher.post("/teacher/exams/new", form_data(name="Deneme A"))
    html = teacher.get("/teacher/").get_data(as_text=True)
    assert "Deneme A" in html and "Taslak" in html and "0 / 10" in html


# ---------- publish ----------

def test_toggle_publish(app, teacher):
    with app.app_context():
        eid = make_exam(active=False)
    r = teacher.post(f"/teacher/exams/{eid}/toggle")
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Exam, eid).is_active is True
    teacher.post(f"/teacher/exams/{eid}/toggle")
    with app.app_context():
        assert db.session.get(Exam, eid).is_active is False


def test_unknown_exam_is_404(teacher):
    assert teacher.get("/teacher/exams/999").status_code == 404
    assert teacher.get("/teacher/exams/999/edit").status_code == 404
    assert teacher.post("/teacher/exams/999/toggle").status_code == 404
    assert teacher.get("/api/teacher/exams/999/results").status_code == 404


# ---------- editing ----------

def test_edit_form_is_prefilled(app, teacher):
    key = dict(KEY)
    key[3] = None
    with app.app_context():
        eid = make_exam(key=key, penalty=3)
    html = teacher.get(f"/teacher/exams/{eid}/edit").get_data(as_text=True)
    assert 'value="TYT Deneme 1"' in html and 'value="3"' in html
    assert html.count(" checked") == 120
    assert 'value="Paragraf"' in html


def test_edit_updates_key_and_rescoring_recalculates_results(app, teacher):
    with app.app_context():
        eid = make_exam()
    submit_student(app, "ogr1", exam_id=eid)
    with app.app_context():
        assert Submission.query.one().net == 15.0
    key = dict(KEY)
    marks = student_marks(KEY)
    key[21] = marks[21]      # student's "wrong" answer is now the key
    key[22] = None           # cancelled
    r = teacher.post(f"/teacher/exams/{eid}/edit", form_data(key=key, penalty="2", name="Yeni ad"),
                     follow_redirects=True)
    assert "1 öğrencinin sonucu yeniden hesaplandı" in r.get_data(as_text=True)
    with app.app_context():
        sub = Submission.query.one()
        assert (sub.correct, sub.wrong, sub.blank, sub.net) == (22, 18, 80, 13.0)
        assert db.session.get(Exam, eid).name == "Yeni ad"
        assert AnswerKey.query.filter_by(exam_id=eid).count() == 120


def test_edit_with_missing_answer_changes_nothing(app, teacher):
    with app.app_context():
        eid = make_exam()
    r = teacher.post(f"/teacher/exams/{eid}/edit", form_data(name="Değişmesin", drop={1}))
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(Exam, eid).name == "TYT Deneme 1"


def test_edit_warns_when_submissions_exist(app, teacher):
    with app.app_context():
        eid = make_exam()
    submit_student(app, "ogr1", exam_id=eid)
    assert "yeniden hesaplanır" in teacher.get(f"/teacher/exams/{eid}/edit").get_data(as_text=True)


# ---------- live results / API ----------

def test_api_before_any_submission(app, teacher):
    with app.app_context():
        eid = make_exam()
    data = teacher.get(f"/api/teacher/exams/{eid}/results").get_json()
    assert data["submitted"] == 0 and data["total_students"] == 10 and data["average_net"] is None
    assert len(data["rows"]) == 10
    assert all(r["status"] == "pending" and r["rank"] is None and r["total"] is None for r in data["rows"])
    assert data["class_topics"] == [] and data["missed"] == []


def test_api_reflects_new_submissions_immediately(app, teacher):
    with app.app_context():
        eid = make_exam()
    submit_student(app, "ogr1", exam_id=eid)
    data = teacher.get(f"/api/teacher/exams/{eid}/results").get_json()
    assert data["submitted"] == 1
    row = next(r for r in data["rows"] if r["username"] == "ogr1")
    assert row["status"] == "submitted" and row["rank"] == 1
    assert row["total"] == {"correct": 20, "wrong": 20, "blank": 80, "net": 15.0}
    assert row["tests"]["turkce"] == {"correct": 20, "wrong": 20, "blank": 0, "net": 15.0}
    assert row["tests"]["fen"] == {"correct": 0, "wrong": 0, "blank": 20, "net": 0.0}
    assert data["average_net"] == 15.0
    assert next(r for r in data["rows"] if r["username"] == "ogr2")["status"] == "pending"
    weak = {(t["subject"], t["topic"]) for t in data["class_topics"] if t["weak"]}
    assert ("Türkçe", "Paragraf") in weak and ("Tarih", "Tarih Bilimi") in weak
    assert ("Türkçe", "Sözcükte Anlam") not in weak


def test_ranking_orders_by_net_and_ties_share_a_rank(app, teacher):
    with app.app_context():
        eid = make_exam()
    best = dict(KEY)                                                       # 120 correct
    ok = student_marks(KEY)
    submit_student(app, "ogr1", marks=ok, exam_id=eid)                     # net 15
    submit_student(app, "ogr2", marks=best, exam_id=eid)                   # net 120
    submit_student(app, "ogr3", marks=ok, exam_id=eid)                     # net 15 (tie)
    rows = {r["username"]: r for r in teacher.get(f"/api/teacher/exams/{eid}/results").get_json()["rows"]}
    assert rows["ogr2"]["rank"] == 1
    assert rows["ogr1"]["rank"] == rows["ogr3"]["rank"] == 2
    assert rows["ogr4"]["rank"] is None


def test_class_level_most_missed_questions(app, teacher):
    with app.app_context():
        eid = make_exam()
    for name in ("ogr1", "ogr2"):
        submit_student(app, name, exam_id=eid)       # both answer Türkçe 21-40 wrong
    data = teacher.get(f"/api/teacher/exams/{eid}/results").get_json()
    assert data["missed"][0]["wrong"] == 2 and data["missed"][0]["question"] == 21
    assert data["missed"][0]["label"] == "Türkçe 21"


def test_exam_page_embeds_initial_data(app, teacher):
    with app.app_context():
        eid = make_exam(name="Canlı Sınav")
    submit_student(app, "ogr1", exam_id=eid)
    html = teacher.get(f"/teacher/exams/{eid}").get_data(as_text=True)
    assert "Canlı Sınav" in html and 'id="live"' in html and 'data-poll="5"' in html
    start = html.index('id="initial-data"')
    payload = html[html.index(">", start) + 1: html.index("</script>", start)]
    assert json.loads(payload)["submitted"] == 1


def test_api_requires_teacher(app, student):
    with app.app_context():
        eid = make_exam()
    assert student.get(f"/api/teacher/exams/{eid}/results").status_code == 403


def test_api_is_not_cacheable(app, teacher):
    with app.app_context():
        eid = make_exam()
    assert teacher.get(f"/api/teacher/exams/{eid}/results").headers["Cache-Control"] == "no-store"


# ---------- per student detail / reset ----------

def test_student_detail_shows_analysis(app, teacher):
    with app.app_context():
        eid = make_exam()
    submit_student(app, "ogr2", exam_id=eid)
    sid = None
    with app.app_context():
        sid = User.query.filter_by(username="ogr2").one().id
    html = teacher.get(f"/teacher/exams/{eid}/students/{sid}").get_data(as_text=True)
    assert "Öğrenci 2" in html and "15.00" in html
    assert "Eksik konular" in html and "Paragraf" in html
    assert "Gönderimi sıfırla" in html


def test_student_detail_404_without_submission_or_for_teacher_id(app, teacher):
    with app.app_context():
        eid = make_exam()
        sid = User.query.filter_by(username="ogr2").one().id
        tid = User.query.filter_by(username="admin").one().id
    assert teacher.get(f"/teacher/exams/{eid}/students/{sid}").status_code == 404
    assert teacher.get(f"/teacher/exams/{eid}/students/{tid}").status_code == 404
    assert teacher.get(f"/teacher/exams/{eid}/students/9999").status_code == 404


def test_teacher_reset_deletes_only_that_students_submission(app, teacher):
    with app.app_context():
        eid = make_exam()
    submit_student(app, "ogr1", exam_id=eid)
    submit_student(app, "ogr2", exam_id=eid)
    with app.app_context():
        sid = User.query.filter_by(username="ogr1").one().id
    r = teacher.post(f"/teacher/exams/{eid}/students/{sid}/reset")
    assert r.status_code == 302
    with app.app_context():
        left = Submission.query.all()
        assert len(left) == 1 and left[0].student.username == "ogr2"
    assert teacher.post(f"/teacher/exams/{eid}/students/{sid}/reset").status_code == 404


# ---------- CSV / students ----------

def test_csv_export(app, teacher):
    with app.app_context():
        eid = make_exam()
    submit_student(app, "ogr1", exam_id=eid)
    r = teacher.get(f"/teacher/exams/{eid}/results.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]
    text = r.get_data(as_text=True)
    assert text.startswith("﻿")
    lines = text.lstrip("﻿").strip().splitlines()
    assert len(lines) == 11                                              # header + 10 students
    assert lines[0].startswith("Sıra;Öğrenci;Kullanıcı adı;Durum;Türkçe D")
    first = lines[1].split(";")
    assert first[1] == "Öğrenci 1" and first[3] == "Gönderdi" and first[-1] == "15.0"
    assert lines[2].split(";")[3] == "Göndermedi"


def test_students_page_lists_all_students(app, teacher):
    with app.app_context():
        make_exam(name="Deneme X")
    submit_student(app, "ogr1")
    html = teacher.get("/teacher/students").get_data(as_text=True)
    assert "Deneme X" in html and html.count("(ogr") == 10 and "15.00" in html
