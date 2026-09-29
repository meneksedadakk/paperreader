"""Builders shared by the service-level and app-level tests."""
from pathlib import Path

from app import tyt
from app.models import Exam, User, db
from app.services import submissions
from tests.helpers import answer_key

# Türkçe 1-20 "Sözcükte Anlam", 21-40 "Paragraf", 41-45 "Tarih Bilimi", everything else has no topic
TOPICS = {**{q: "Sözcükte Anlam" for q in range(1, 21)}, **{q: "Paragraf" for q in range(21, 41)},
          **{q: "Tarih Bilimi" for q in range(41, 46)}}


def wrong_option(correct: str) -> str:
    return "A" if correct != "A" else "B"


def student_marks(key: dict) -> dict:
    """Türkçe 1-20 correct, Türkçe 21-40 wrong, the rest blank.
    -> 20 correct, 20 wrong, 80 blank; net (penalty 4) = 15.00
    """
    marks = {q: None for q in range(1, tyt.TOTAL_QUESTIONS + 1)}
    for q in range(1, 21):
        marks[q] = key[q]
    for q in range(21, 41):
        marks[q] = wrong_option(key[q])
    return marks


def make_exam(name="TYT Deneme 1", penalty=4.0, active=True, key=None, topics=None) -> int:
    key = key or answer_key()
    teacher = User.query.filter_by(username="admin").first()
    exam = Exam(name=name, description="", wrong_penalty=penalty, created_by=teacher.id, is_active=active)
    db.session.add(exam)
    db.session.flush()
    submissions.replace_answer_key(exam, key, TOPICS if topics is None else topics)
    db.session.commit()
    return exam.id


def omr_json(marks: dict, flagged=()) -> dict:
    return {
        "answers": {str(q): {"o": m, "c": 0.3 if q in flagged else 1.0} for q, m in marks.items()},
        "flagged": sorted(flagged),
    }


def touch_upload(app, rel: str) -> str:
    path = Path(app.config["UPLOAD_DIR"]) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return rel
