import csv
import io
import math

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import tyt
from app.auth import role_required
from app.models import Exam, Submission, User, db
from app.services import report, submissions
from app.tyt_topics import TOPICS

bp = Blueprint("teacher", __name__, url_prefix="/teacher")


# ---------- exam form parsing ----------

def parse_exam_form(form) -> tuple[dict, dict]:
    """Return (values, errors). `values` keeps raw input so the form can be re-rendered."""
    errors: dict = {}
    values = {"name": form.get("name", "").strip(), "description": form.get("description", "").strip(),
              "wrong_penalty": form.get("wrong_penalty", "").strip(), "answers": {}, "topics": {}}

    if not values["name"]:
        errors["name"] = "Sınav adı zorunludur."
    elif len(values["name"]) > 200:
        errors["name"] = "Sınav adı en fazla 200 karakter olabilir."

    try:
        penalty = float(values["wrong_penalty"].replace(",", "."))
        if not math.isfinite(penalty) or penalty < 0 or penalty > 100:
            raise ValueError
        values["penalty"] = penalty
    except ValueError:
        errors["wrong_penalty"] = "Yanlış katsayısı zorunludur (0 veya pozitif bir sayı; TYT için 4)."

    key, missing = {}, set()
    for q in range(1, tyt.TOTAL_QUESTIONS + 1):
        raw = form.get(f"ans_{q}", "").strip().upper()
        values["answers"][q] = raw
        values["topics"][q] = form.get(f"topic_{q}", "").strip()[:120]
        if raw in tyt.OPTIONS:
            key[q] = raw
        elif raw == "X":
            key[q] = None  # cancelled question
        else:
            missing.add(q)
    if missing:
        errors["key"] = f"{len(missing)} sorunun cevabı girilmemiş. 120 sorunun tamamı zorunludur."
        errors["missing"] = missing
    values["key"] = key
    return values, errors


def values_from_exam(exam: Exam | None) -> dict:
    if exam is None:
        return {"name": "", "description": "", "wrong_penalty": "", "answers": {}, "topics": {}}
    return {
        "name": exam.name, "description": exam.description,
        "wrong_penalty": f"{exam.wrong_penalty:g}",
        "answers": {k.question_no: ("X" if k.correct_option is None else k.correct_option) for k in exam.keys},
        "topics": {k.question_no: k.topic for k in exam.keys},
    }


def render_exam_form(exam, values, errors):
    missing = errors.get("missing", set())
    tests = []
    for t in tyt.TESTS:
        tests.append({"key": t.key, "name": t.name, "count": t.count, "questions": [
            {"q": q, "local": q - t.first + 1, "subject": tyt.subject_of(q).name,
             "value": values["answers"].get(q, ""), "topic": values["topics"].get(q, ""),
             "missing": q in missing}
            for q in range(t.first, t.last + 1)]})
    return render_template("teacher/exam_form.html", exam=exam, values=values, errors=errors, tests=tests,
                           topics=TOPICS, subjects=tyt.SUBJECTS,
                           submission_count=len(exam.submissions) if exam else 0)


# ---------- pages ----------

@bp.route("/")
@role_required("teacher")
def dashboard():
    student_count = User.query.filter_by(role="student").count()
    rows = []
    for exam in Exam.query.order_by(Exam.created_at.desc()).all():
        nets = [s.net for s in exam.submissions]
        rows.append({"exam": exam, "submitted": len(nets), "students": student_count,
                     "avg": round(sum(nets) / len(nets), 2) if nets else None})
    return render_template("teacher/dashboard.html", rows=rows)


@bp.route("/exams/new", methods=["GET", "POST"])
@role_required("teacher")
def exam_new():
    if request.method == "POST":
        values, errors = parse_exam_form(request.form)
        if errors:
            flash("Form eksik veya hatalı. Lütfen işaretli alanları düzeltin.", "danger")
            return render_exam_form(None, values, errors), 400
        exam = Exam(name=values["name"], description=values["description"], wrong_penalty=values["penalty"],
                    created_by=current_user.id, is_active=False)
        db.session.add(exam)
        db.session.flush()
        submissions.replace_answer_key(exam, values["key"], values["topics"])
        db.session.commit()
        flash("Sınav taslak olarak kaydedildi. Öğrencilere açmak için 'Yayınla'ya basın.", "success")
        return redirect(url_for("teacher.exam_detail", exam_id=exam.id))
    return render_exam_form(None, values_from_exam(None), {})


@bp.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
@role_required("teacher")
def exam_edit(exam_id: int):
    exam = db.get_or_404(Exam, exam_id)
    if request.method == "POST":
        values, errors = parse_exam_form(request.form)
        if errors:
            flash("Form eksik veya hatalı. Lütfen işaretli alanları düzeltin.", "danger")
            return render_exam_form(exam, values, errors), 400
        exam.name, exam.description, exam.wrong_penalty = values["name"], values["description"], values["penalty"]
        submissions.replace_answer_key(exam, values["key"], values["topics"])
        db.session.flush()
        count = submissions.rescore_exam(exam)
        db.session.commit()
        msg = "Sınav güncellendi."
        if count:
            msg += f" {count} öğrencinin sonucu yeniden hesaplandı."
        flash(msg, "success")
        return redirect(url_for("teacher.exam_detail", exam_id=exam.id))
    return render_exam_form(exam, values_from_exam(exam), {})


@bp.route("/exams/<int:exam_id>/toggle", methods=["POST"])
@role_required("teacher")
def exam_toggle(exam_id: int):
    exam = db.get_or_404(Exam, exam_id)
    exam.is_active = not exam.is_active
    db.session.commit()
    flash("Sınav yayınlandı. Öğrenciler yükleme yapabilir." if exam.is_active
          else "Sınav yayından kaldırıldı. Yeni yükleme yapılamaz.", "success")
    return redirect(url_for("teacher.exam_detail", exam_id=exam.id))


@bp.route("/exams/<int:exam_id>")
@role_required("teacher")
def exam_detail(exam_id: int):
    exam = db.get_or_404(Exam, exam_id)
    return render_template("teacher/exam_detail.html", exam=exam, data=report.exam_results(exam),
                           test_pairs=[[t.key, t.name] for t in tyt.TESTS])


@bp.route("/exams/<int:exam_id>/students/<int:student_id>")
@role_required("teacher")
def student_detail(exam_id: int, student_id: int):
    exam = db.get_or_404(Exam, exam_id)
    student = db.get_or_404(User, student_id)
    if student.role != "student":
        abort(404)
    sub = submissions.get_submission(exam.id, student.id)
    if not sub:
        abort(404)
    return render_template("teacher/student_detail.html", exam=exam, student=student,
                           rep=report.build_report(sub))


@bp.route("/exams/<int:exam_id>/students/<int:student_id>/reset", methods=["POST"])
@role_required("teacher")
def submission_reset(exam_id: int, student_id: int):
    sub = submissions.get_submission(exam_id, student_id)
    if not sub:
        abort(404)
    submissions.reset_submission(sub)
    flash("Gönderim sıfırlandı. Öğrenci yeniden yükleme yapabilir.", "success")
    return redirect(url_for("teacher.exam_detail", exam_id=exam_id))


@bp.route("/exams/<int:exam_id>/results.csv")
@role_required("teacher")
def exam_csv(exam_id: int):
    exam = db.get_or_404(Exam, exam_id)
    data = report.exam_results(exam)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    head = ["Sıra", "Öğrenci", "Kullanıcı adı", "Durum"]
    for t in tyt.TESTS:
        head += [f"{t.name} D", f"{t.name} Y", f"{t.name} B", f"{t.name} Net"]
    head += ["Toplam D", "Toplam Y", "Toplam B", "Toplam Net"]
    w.writerow(head)
    for r in data["rows"]:
        line = [r["rank"] or "", r["name"], r["username"], "Gönderdi" if r["status"] == "submitted" else "Göndermedi"]
        for t in tyt.TESTS:
            s = r["tests"][t.key] if r["tests"] else None
            line += [s[k] for k in ("correct", "wrong", "blank", "net")] if s else ["", "", "", ""]
        tot = r["total"]
        line += [tot[k] for k in ("correct", "wrong", "blank", "net")] if tot else ["", "", "", ""]
        w.writerow(line)
    body = "﻿" + out.getvalue()
    return Response(body, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="sinav_{exam.id}_sonuclar.csv"'})


@bp.route("/students")
@role_required("teacher")
def students():
    exams = Exam.query.order_by(Exam.created_at).all()
    subs = {(s.student_id, s.exam_id): s for s in Submission.query.all()}
    rows = []
    for st in User.query.filter_by(role="student").order_by(User.id).all():
        cells = [subs.get((st.id, e.id)) for e in exams]
        nets = [c.net for c in cells if c]
        rows.append({"student": st, "cells": cells,
                     "avg": round(sum(nets) / len(nets), 2) if nets else None})
    return render_template("teacher/students.html", exams=exams, rows=rows)
