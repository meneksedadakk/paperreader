import pytest

from app.models import User
from app.seed import seed_users
from tests.conftest import Browser
from tests.factory import make_exam

STUDENTS = [f"ogr{i}" for i in range(1, 11)]


# ---------- seed ----------

def test_seed_creates_one_teacher_and_ten_students(ctx):
    users = User.query.all()
    assert len(users) == 11
    teachers = [u for u in users if u.role == "teacher"]
    assert [t.username for t in teachers] == ["admin"]
    assert sorted(u.username for u in users if u.role == "student") == sorted(STUDENTS)


def test_seed_passwords_are_hashed_and_match_spec(ctx):
    admin = User.query.filter_by(username="admin").one()
    assert admin.password_hash != "admin" and "admin" not in admin.password_hash
    assert admin.check_password("admin") and not admin.check_password("ogr1")
    for name in STUDENTS:
        u = User.query.filter_by(username=name).one()
        assert u.check_password(name), name
        assert not u.check_password(name + "x")


def test_seed_is_idempotent_and_keeps_changed_passwords(ctx):
    assert seed_users() == 0
    u = User.query.filter_by(username="ogr3").one()
    u.set_password("changed")
    from app.models import db
    db.session.commit()
    assert seed_users() == 0
    assert User.query.filter_by(username="ogr3").one().check_password("changed")
    assert User.query.count() == 11


# ---------- login / logout ----------

def test_login_page_and_anonymous_redirect(anon):
    assert anon.get("/").headers["Location"].endswith("/login")
    r = anon.get("/login")
    assert r.status_code == 200 and "Giriş" in r.get_data(as_text=True)


def test_teacher_login_goes_to_teacher_panel(anon):
    r = anon.login("admin")
    assert r.status_code == 302 and r.headers["Location"].endswith("/teacher/")
    assert anon.get("/teacher/").status_code == 200


def test_student_login_goes_to_student_panel(anon):
    r = anon.login("ogr1")
    assert r.status_code == 302 and r.headers["Location"].endswith("/student/")
    assert anon.get("/student/").status_code == 200


@pytest.mark.parametrize("username", ["admin"] + STUDENTS)
def test_every_seeded_account_can_log_in(app, username):
    b = Browser(app)
    assert b.login(username).status_code == 302


@pytest.mark.parametrize("user,password,role", [
    ("admin", "wrong", "teacher"), ("ogr1", "ogr2", "student"), ("nobody", "nobody", "student"),
    ("", "", "student"), ("admin", "", "teacher")])
def test_bad_credentials_are_rejected(anon, user, password, role):
    r = anon.post("/login", {"username": user, "password": password, "role": role})
    assert r.status_code == 200
    assert "hatalı" in r.get_data(as_text=True)
    assert anon.get("/teacher/").status_code == 302  # still anonymous


# ---------- role selector on the login page ----------

def test_login_page_offers_both_roles_with_student_preselected(anon):
    html = anon.get("/login").get_data(as_text=True)
    assert 'name="role" value="student" checked' in html
    assert 'name="role" value="teacher"' in html and 'name="role" value="teacher" checked' not in html
    assert "Öğrenci" in html and "Öğretmen" in html


@pytest.mark.parametrize("username,wrong_role", [("admin", "student"), ("ogr1", "teacher"), ("ogr10", "teacher")])
def test_correct_credentials_with_wrong_role_are_rejected(anon, username, wrong_role):
    r = anon.post("/login", {"username": username, "password": username, "role": wrong_role})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "giriş türü hatalı" in html
    assert anon.get("/teacher/").status_code == 302 and anon.get("/student/").status_code == 302


def test_wrong_role_message_does_not_reveal_that_the_password_was_right(anon):
    right_pw_wrong_role = anon.post("/login", {"username": "admin", "password": "admin", "role": "student"})
    wrong_pw = anon.post("/login", {"username": "admin", "password": "nope", "role": "teacher"})
    strip = lambda r: r.get_data(as_text=True).split("flash-danger")[1].split("</article>")[0]
    assert strip(right_pw_wrong_role) == strip(wrong_pw)


@pytest.mark.parametrize("role", ["", "admin", "TEACHER", "root", "student "])
def test_missing_or_invalid_role_is_rejected(anon, role):
    r = anon.post("/login", {"username": "ogr1", "password": "ogr1", "role": role})
    assert r.status_code == 200 and "giriş türünü seçin" in r.get_data(as_text=True)
    assert anon.get("/student/").status_code == 302


def test_login_without_role_field_is_rejected(anon):
    r = anon.post("/login", {"username": "ogr1", "password": "ogr1"})
    assert r.status_code == 200 and anon.get("/student/").status_code == 302


def test_selected_role_stays_selected_after_a_failed_attempt(anon):
    r = anon.post("/login", {"username": "admin", "password": "wrong", "role": "teacher"})
    assert 'name="role" value="teacher" checked' in r.get_data(as_text=True)


def test_student_can_log_in_as_student_and_teacher_as_teacher(app):
    s = Browser(app)
    assert s.login("ogr7", role="student").headers["Location"].endswith("/student/")
    t = Browser(app)
    assert t.login("admin", role="teacher").headers["Location"].endswith("/teacher/")


def test_logged_in_user_visiting_login_is_redirected(teacher):
    assert teacher.get("/login").status_code == 302


def test_logout_requires_post_and_ends_session(student):
    assert student.get("/logout").status_code == 405
    r = student.post("/logout")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert student.get("/student/").status_code == 302


# ---------- role separation ----------

TEACHER_URLS = ["/teacher/", "/teacher/exams/new", "/teacher/students", "/teacher/exams/1",
                "/teacher/exams/1/edit", "/teacher/exams/1/results.csv", "/api/teacher/exams/1/results",
                "/teacher/exams/1/students/2"]
STUDENT_URLS = ["/student/", "/student/exams/1/upload", "/student/exams/1/review", "/student/exams/1/result"]


@pytest.mark.parametrize("url", TEACHER_URLS + STUDENT_URLS + ["/files/submission/1/image", "/forms/tyt_120.pdf"])
def test_anonymous_users_are_redirected_to_login(anon, url):
    r = anon.get(url)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


@pytest.mark.parametrize("url", TEACHER_URLS)
def test_students_cannot_open_teacher_pages(app, student, url):
    with app.app_context():
        make_exam()
    assert student.get(url).status_code == 403


@pytest.mark.parametrize("url", STUDENT_URLS)
def test_teacher_cannot_open_student_pages(app, teacher, url):
    with app.app_context():
        make_exam()
    assert teacher.get(url).status_code == 403


def test_students_cannot_post_teacher_actions(app, student):
    with app.app_context():
        eid = make_exam()
    assert student.post(f"/teacher/exams/{eid}/toggle").status_code == 403
    assert student.post("/teacher/exams/new", {"name": "x"}).status_code == 403
    assert student.post(f"/teacher/exams/{eid}/students/2/reset").status_code == 403


# ---------- CSRF ----------

def test_post_without_csrf_token_is_rejected(app):
    c = app.test_client()
    assert c.post("/login", data={"username": "admin", "password": "admin"}).status_code == 400


def test_post_with_wrong_csrf_token_is_rejected(app):
    b = Browser(app)
    r = b.client.post("/login", data={"username": "admin", "password": "admin", "_csrf": "nope"})
    assert r.status_code == 400
    assert b.client.get("/teacher/").status_code == 302  # not logged in


def test_csrf_header_is_accepted_for_fetch_calls(app):
    b = Browser(app)
    from tests.conftest import TOKEN
    r = b.client.post("/login", data={"username": "admin", "password": "admin", "role": "teacher"},
                      headers={"X-CSRF-Token": TOKEN})
    assert r.status_code == 302


def test_login_form_embeds_a_csrf_token(app):
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    assert 'name="_csrf"' in html


# ---------- misc ----------

def test_security_headers_and_custom_404(teacher):
    r = teacher.get("/nope")
    assert r.status_code == 404 and "Sayfa bulunamadı" in r.get_data(as_text=True)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
