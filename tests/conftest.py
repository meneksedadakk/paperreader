import pytest

from app import create_app
from app.models import User, db

TOKEN = "test-csrf-token"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "INSTANCE_PATH": str(tmp_path / "instance"),
        "SECRET_KEY": "test-secret",
        "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",  # fast hashing, tests only
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield app


class Browser:
    """Thin wrapper around the Flask test client that knows the CSRF token."""

    def __init__(self, app):
        self.client = app.test_client()
        with self.client.session_transaction() as s:
            s["_csrf"] = TOKEN

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        data.setdefault("_csrf", TOKEN)
        return self.client.post(url, data=data, **kw)

    def login(self, username, password=None, role=None):
        role = role or ("teacher" if username == "admin" else "student")
        return self.post("/login", {"username": username, "password": password or username, "role": role})


def _browser(app, username):
    b = Browser(app)
    r = b.login(username)
    assert r.status_code == 302, f"login failed for {username}"
    return b


@pytest.fixture
def anon(app):
    return Browser(app)


@pytest.fixture
def teacher(app):
    return _browser(app, "admin")


@pytest.fixture
def student_factory(app):
    def make(n: int = 1) -> Browser:
        return _browser(app, f"ogr{n}")
    return make


@pytest.fixture
def student(student_factory):
    return student_factory(1)


def user_id(app, username: str) -> int:
    with app.app_context():
        return User.query.filter_by(username=username).one().id
