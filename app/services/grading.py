"""Pure grading functions (no Flask / DB imports).

marks : {question_no: 'A'..'E' | None (blank) | '*' (double mark)}
key   : {question_no: 'A'..'E' | None (cancelled question -> correct for everyone)}
topics: {question_no: topic string}
"""
from collections import defaultdict

from app import tyt

WEAK_TOPIC_THRESHOLD = 0.5

CORRECT, WRONG, BLANK = "correct", "wrong", "blank"


def question_status(mark, correct_option) -> str:
    if correct_option is None:  # cancelled question
        return CORRECT
    if mark is None or mark == "":
        return BLANK
    if mark == "*":
        return WRONG
    return CORRECT if mark == correct_option else WRONG


def net_of(correct: int, wrong: int, penalty: float) -> float:
    if not penalty or penalty <= 0:
        return float(correct)
    return correct - wrong / penalty


def _blank_counts() -> dict:
    return {"correct": 0, "wrong": 0, "blank": 0}


def _finish(counts: dict, penalty: float) -> dict:
    counts["total"] = counts["correct"] + counts["wrong"] + counts["blank"]
    counts["net"] = round(net_of(counts["correct"], counts["wrong"], penalty), 2)
    return counts


def grade(marks: dict, key: dict, topics: dict | None, penalty: float,
          weak_threshold: float = WEAK_TOPIC_THRESHOLD) -> dict:
    topics = topics or {}
    statuses = {}
    by_test = {t.key: _blank_counts() for t in tyt.TESTS}
    by_subject = {s.name: _blank_counts() for s in tyt.SUBJECTS}
    total = _blank_counts()
    topic_stats = defaultdict(lambda: {"correct": 0, "total": 0})

    for q in range(1, tyt.TOTAL_QUESTIONS + 1):
        st = question_status(marks.get(q), key.get(q))
        statuses[q] = st
        subject = tyt.subject_of(q)
        for bucket in (by_test[subject.test_key], by_subject[subject.name], total):
            bucket[st] += 1
        topic = (topics.get(q) or "").strip() or tyt.UNSPECIFIED_TOPIC
        stat = topic_stats[(subject.name, topic)]
        stat["total"] += 1
        stat["correct"] += st == CORRECT

    topic_rows = []
    for (subject, topic), s in sorted(topic_stats.items()):
        ratio = s["correct"] / s["total"]
        topic_rows.append({
            "subject": subject, "topic": topic, "correct": s["correct"], "total": s["total"],
            "ratio": round(ratio, 4),
            "weak": topic != tyt.UNSPECIFIED_TOPIC and ratio < weak_threshold,
        })

    return {
        "statuses": statuses,
        "tests": {k: _finish(v, penalty) for k, v in by_test.items()},
        "subjects": {k: _finish(v, penalty) for k, v in by_subject.items()},
        "total": _finish(total, penalty),
        "topics": topic_rows,
        "weak_topics": [r for r in topic_rows if r["weak"]],
    }


def class_topic_stats(results: list[dict], weak_threshold: float = WEAK_TOPIC_THRESHOLD) -> list[dict]:
    """Aggregate topic rows of several grade() results into class-wide success ratios."""
    agg = defaultdict(lambda: {"correct": 0, "total": 0})
    for res in results:
        for r in res["topics"]:
            a = agg[(r["subject"], r["topic"])]
            a["correct"] += r["correct"]
            a["total"] += r["total"]
    rows = []
    for (subject, topic), a in sorted(agg.items()):
        ratio = a["correct"] / a["total"] if a["total"] else 0.0
        rows.append({
            "subject": subject, "topic": topic, "correct": a["correct"], "total": a["total"],
            "ratio": round(ratio, 4),
            "weak": topic != tyt.UNSPECIFIED_TOPIC and ratio < weak_threshold,
        })
    return rows


def most_missed_questions(results: list[dict], limit: int = 10) -> list[dict]:
    """Questions answered wrong most often across submissions (blank not counted)."""
    wrong = defaultdict(int)
    for res in results:
        for q, st in res["statuses"].items():
            wrong[q] += st == WRONG
    rows = [{"question": q, "label": tyt.label(q), "wrong": n, "students": len(results)}
            for q, n in wrong.items() if n]
    rows.sort(key=lambda r: (-r["wrong"], r["question"]))
    return rows[:limit]
