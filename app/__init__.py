import hmac
import os
import secrets
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.models import User, db

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Bu sayfayı görmek için giriş yapmalısınız."
login_manager.login_message_category = "warning"

ROOT = Path(__file__).resolve().parent.parent


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


def _secret_key(instance_path: Path) -> str:
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = instance_path / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


def create_app(test_config: dict | None = None) -> Flask:
    instance_path = str((test_config or {}).get("INSTANCE_PATH") or ROOT / "instance")
    app = Flask(__name__, instance_path=instance_path, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///paperreader.db"),
        UPLOAD_DIR=str(ROOT / "uploads"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        AUTO_SEED=True,
        CSRF_ENABLED=True,
        WEAK_TOPIC_THRESHOLD=0.5,
        LIVE_POLL_SECONDS=5,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(Path(app.instance_path))
    upload_dir = Path(app.config["UPLOAD_DIR"])
    for sub in ("images", "debug"):
        (upload_dir / sub).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app import auth, files
    from app.api import bp as api_bp
    from app.student.routes import bp as student_bp
    from app.teacher.routes import bp as teacher_bp

    for bp in (auth.bp, files.bp, teacher_bp, student_bp, api_bp):
        app.register_blueprint(bp)

    # ---- CSRF ----
    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _check_csrf():
        if not app.config["CSRF_ENABLED"] or request.method in ("GET", "HEAD", "OPTIONS"):
            return
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("_csrf")
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Oturum doğrulaması başarısız. Sayfayı yenileyip tekrar deneyin.")

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    # ---- errors ----
    messages = {
        400: "Geçersiz istek.", 403: "Bu sayfaya erişim yetkiniz yok.", 404: "Sayfa bulunamadı.",
        409: "Bu işlem yapılamaz: bu sınav için gönderim zaten yapılmış.",
        413: "Dosya çok büyük (en fazla 10 MB).",
    }

    def _error(e):
        code = getattr(e, "code", 500)
        text = e.description if code in (400, 409) and getattr(e, "description", None) and \
            e.description != type(e).description else messages.get(code, "Beklenmeyen bir hata oluştu.")
        return render_template("error.html", code=code, message=text), code

    for code in messages:
        app.register_error_handler(code, _error)

    # ---- DB init / seed ----
    with app.app_context():
        db.create_all()
        if app.config["AUTO_SEED"]:
            from app.seed import seed_users
            seed_users()

    @app.cli.command("seed")
    def seed_command():
        """Create the teacher and the 10 students (idempotent)."""
        from app.seed import seed_users
        created = seed_users()
        print(f"{created} kullanıcı eklendi.")

    return app
