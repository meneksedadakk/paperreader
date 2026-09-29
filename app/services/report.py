"""View-models built from a Submission (used by the student result page and the teacher detail page)."""
from app import tyt
from app.models import Submission
from app.services import grading, submissions


def build_report(sub: Submission) -> dict:
    exam = sub.exam
    result = submissions.grade_submission(sub, exam)
    key, topics = submissions.key_maps(exam)
    marks = submissions.submission_marks(sub)
    edited = {a.question_no for a in sub.answers if a.edited_by_student}

    tests = []
    for t in tyt.TESTS:
        questions = []
        for q in range(t.first, t.last + 1):
            questions.append({
                "q": q, "local": tyt.local_no(q), "subject": tyt.subject_of(q).name,
                "mark": marks.get(q), "correct": key.get(q), "status": result["statuses"][q],
                "edited": q in edited, "topic": topics.get(q) or "",
            })
        tests.append({
            "key": t.key, "name": t.name, "stats": result["tests"][t.key],
            "subjects": [{"name": s.name, **result["subjects"][s.name]}
                         for s in tyt.SUBJECTS if s.test_key == t.key],
            "questions": questions,
        })

    specified = [r for r in result["topics"] if r["topic"] != tyt.UNSPECIFIED_TOPIC]
    return {
        "submission": sub, "exam": exam, "result": result, "total": result["total"], "tests": tests,
        "topics": result["topics"], "weak_topics": result["weak_topics"],
        "chart": {
            "labels": [f'{r["subject"]} · {r["topic"]}' for r in specified],
            "percents": [round(r["ratio"] * 100) for r in specified],
        },
        "edited_count": len(edited),
    }


def rank_rows(rows: list[dict]) -> None:
    """Add competition-style 'rank' (ties share a rank) to submitted rows, in place."""
    submitted = sorted((r for r in rows if r["status"] == "submitted"), key=lambda r: -r["total"]["net"])
    last_net, last_rank = None, 0
    for i, row in enumerate(submitted, start=1):
        if row["total"]["net"] != last_net:
            last_net, last_rank = row["total"]["net"], i
        row["rank"] = last_rank
    for row in rows:
        row.setdefault("rank", None)


def exam_results(exam) -> dict:
    """Live table payload for the teacher: one row per student + class-wide analysis."""
    from app.models import User

    students = User.query.filter_by(role="student").order_by(User.id).all()
    subs = {s.student_id: s for s in exam.submissions}
    rows, results = [], []
    for st in students:
        sub = subs.get(st.id)
        row = {"student_id": st.id, "name": st.full_name, "username": st.username,
               "status": "submitted" if sub else "pending", "submitted_at": None,
               "tests": None, "total": None, "edited": 0}
        if sub:
            res = submissions.grade_submission(sub, exam)
            results.append(res)
            row["submitted_at"] = sub.submitted_at.strftime("%d.%m.%Y %H:%M")
            row["tests"] = {k: {n: v[n] for n in ("correct", "wrong", "blank", "net")}
                            for k, v in res["tests"].items()}
            row["total"] = {n: res["total"][n] for n in ("correct", "wrong", "blank", "net")}
            row["edited"] = sum(a.edited_by_student for a in sub.answers)
        rows.append(row)
    rank_rows(rows)
    nets = [r["total"]["net"] for r in rows if r["total"]]
    return {
        "exam": {"id": exam.id, "name": exam.name, "active": exam.is_active, "penalty": exam.wrong_penalty},
        "submitted": len(results), "total_students": len(students),
        "average_net": round(sum(nets) / len(nets), 2) if nets else None,
        "rows": rows,
        "class_topics": grading.class_topic_stats(results) if results else [],
        "missed": grading.most_missed_questions(results) if results else [],
    }
