from datetime import datetime, timezone

from flask import current_app, has_app_context
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # 'teacher' | 'student'
    created_at = db.Column(db.DateTime, default=_now, nullable=False)

    def set_password(self, password: str) -> None:
        method = current_app.config.get("PASSWORD_HASH_METHOD") if has_app_context() else None
        self.password_hash = generate_password_hash(password, method=method) if method \
            else generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"


class Exam(db.Model):
    __tablename__ = "exams"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="", nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_now, nullable=False)
    wrong_penalty = db.Column(db.Float, nullable=False)  # 0 = wrong answers cost nothing
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    keys = db.relationship("AnswerKey", backref="exam", cascade="all, delete-orphan",
                           order_by="AnswerKey.question_no")
    submissions = db.relationship("Submission", backref="exam", cascade="all, delete-orphan")


class AnswerKey(db.Model):
    __tablename__ = "answer_keys"
    __table_args__ = (UniqueConstraint("exam_id", "question_no"),)
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    question_no = db.Column(db.Integer, nullable=False)  # 1..120 (global)
    correct_option = db.Column(db.String(1), nullable=True)  # None = cancelled question
    topic = db.Column(db.String(120), default="", nullable=False)


class Submission(db.Model):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("exam_id", "student_id"),)
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    image_path = db.Column(db.String(300), nullable=False)
    debug_image_path = db.Column(db.String(300), nullable=True)
    correct = db.Column(db.Integer, default=0, nullable=False)
    wrong = db.Column(db.Integer, default=0, nullable=False)
    blank = db.Column(db.Integer, default=0, nullable=False)
    net = db.Column(db.Float, default=0.0, nullable=False)
    submitted_at = db.Column(db.DateTime, default=_now, nullable=False)

    student = db.relationship("User")
    answers = db.relationship("SubmissionAnswer", backref="submission", cascade="all, delete-orphan",
                              order_by="SubmissionAnswer.question_no")


class SubmissionAnswer(db.Model):
    __tablename__ = "submission_answers"
    __table_args__ = (UniqueConstraint("submission_id", "question_no"),)
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    question_no = db.Column(db.Integer, nullable=False)
    marked_option = db.Column(db.String(1), nullable=True)  # None = blank, '*' = double mark
    confidence = db.Column(db.Float, default=1.0, nullable=False)
    edited_by_student = db.Column(db.Boolean, default=False, nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)


class PendingUpload(db.Model):
    """OMR draft awaiting the student's confirmation. Does not use up the one-time upload right."""
    __tablename__ = "pending_uploads"
    __table_args__ = (UniqueConstraint("exam_id", "student_id"),)
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    image_path = db.Column(db.String(300), nullable=False)
    debug_image_path = db.Column(db.String(300), nullable=True)
    omr_result = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=_now, nullable=False)
