from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.models import User

bp = Blueprint("auth", __name__)

ROLES = ("teacher", "student")


def role_required(role: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def home_for(user) -> str:
    return url_for("teacher.dashboard" if user.is_teacher else "student.dashboard")


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    role = "student"
    if request.method == "POST":
        role = request.form.get("role", "")
        username = request.form.get("username", "").strip()
        if role not in ROLES:
            flash("Lütfen giriş türünü seçin: Öğretmen veya Öğrenci.", "danger")
            role = "student"
        else:
            user = User.query.filter_by(username=username).first()
            # one generic message: never reveal whether the password or the chosen role was wrong
            if user and user.role == role and user.check_password(request.form.get("password", "")):
                login_user(user)
                return redirect(home_for(user))
            flash("Kullanıcı adı, şifre veya giriş türü hatalı.", "danger")
    return render_template("login.html", role=role)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
