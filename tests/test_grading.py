import pytest

from app import tyt
from app.services import grading
from tests.helpers import answer_key

KEY = answer_key()


def marks_like_key(**overrides):
    marks = dict(KEY)
    marks.update(overrides)
    return marks


def wrong_of(q):
    return "A" if KEY[q] != "A" else "B"


# ---------- per question / net ----------

def test_question_status_rules():
    assert grading.question_status("A", "A") == grading.CORRECT
    assert grading.question_status("B", "A") == grading.WRONG
    assert grading.question_status(None, "A") == grading.BLANK
    assert grading.question_status("", "A") == grading.BLANK
    assert grading.question_status("*", "A") == grading.WRONG  # double mark
    # cancelled question: correct for everybody, whatever they did
    for mark in ("A", None, "*"):
        assert grading.question_status(mark, None) == grading.CORRECT


@pytest.mark.parametrize("c,w,p,net", [
    (100, 16, 4, 96.0), (10, 3, 3, 9.0), (10, 3, 0, 10.0), (10, 3, None, 10.0), (0, 8, 4, -2.0), (0, 0, 4, 0.0),
])
def test_net_of(c, w, p, net):
    assert grading.net_of(c, w, p) == net


# ---------- whole-sheet grading ----------

def test_perfect_sheet():
    res = grading.grade(marks_like_key(), KEY, {}, 4)
    assert res["total"]["correct"] == 120 and res["total"]["net"] == 120
    assert all(t["net"] == t["total"] for t in res["tests"].values())


def test_empty_sheet_is_all_blank_with_zero_net():
    res = grading.grade({}, KEY, {}, 4)
    assert res["total"] == {"correct": 0, "wrong": 0, "blank": 120, "total": 120, "net": 0.0}


def test_mixed_sheet_counts_and_net():
    marks = marks_like_key()
    for q in range(1, 17):          # 16 wrong
        marks[q] = wrong_of(q)
    for q in range(17, 21):         # 4 blank
        marks[q] = None
    res = grading.grade(marks, KEY, {}, 4)
    assert (res["total"]["correct"], res["total"]["wrong"], res["total"]["blank"]) == (100, 16, 4)
    assert res["total"]["net"] == 96.0
    assert res["tests"]["turkce"]["net"] == 20 - 16 / 4


def test_penalty_zero_means_wrong_costs_nothing():
    marks = {q: wrong_of(q) for q in range(1, 11)}
    marks.update({q: KEY[q] for q in range(11, 21)})
    res = grading.grade(marks, KEY, {}, 0)
    assert res["total"]["net"] == 10.0


def test_double_mark_is_wrong():
    res = grading.grade({1: "*"}, KEY, {}, 4)
    assert res["statuses"][1] == grading.WRONG and res["total"]["wrong"] == 1


def test_cancelled_question_counts_correct_for_everyone():
    key = dict(KEY)
    key[5] = None
    res = grading.grade({5: "C"}, key, {}, 4)
    assert res["statuses"][5] == grading.CORRECT
    res_blank = grading.grade({}, key, {}, 4)
    assert res_blank["statuses"][5] == grading.CORRECT and res_blank["total"]["correct"] == 1


def test_subject_and_test_partitioning():
    marks = {q: wrong_of(q) for q in range(101, 108)}   # all of Fizik wrong
    marks.update({q: KEY[q] for q in range(108, 115)})  # all of Kimya right
    res = grading.grade(marks, KEY, {}, 4)
    assert res["subjects"]["Fizik"]["wrong"] == 7 and res["subjects"]["Fizik"]["total"] == 7
    assert res["subjects"]["Kimya"]["correct"] == 7
    assert res["subjects"]["Biyoloji"]["blank"] == 6
    assert res["tests"]["fen"]["wrong"] == 7 and res["tests"]["fen"]["correct"] == 7
    assert res["tests"]["turkce"]["wrong"] == 0
    assert res["total"]["wrong"] == 7
    assert sum(s["total"] for s in res["subjects"].values()) == 120


def test_sums_are_consistent():
    marks = {q: (KEY[q] if q % 3 else wrong_of(q)) for q in range(1, 100)}
    res = grading.grade(marks, KEY, {}, 4)
    for field in ("correct", "wrong", "blank"):
        assert sum(t[field] for t in res["tests"].values()) == res["total"][field]
        assert sum(s[field] for s in res["subjects"].values()) == res["total"][field]


def test_net_is_rounded_to_two_decimals():
    res = grading.grade({1: wrong_of(1), 2: wrong_of(2), 3: wrong_of(3)}, KEY, {}, 4)
    assert res["total"]["net"] == -0.75
    res = grading.grade({1: wrong_of(1)}, KEY, {}, 3)
    assert res["total"]["net"] == -0.33


# ---------- topics ----------

def topics_for(mapping):
    return {q: name for name, qs in mapping.items() for q in qs}


def test_topic_ratio_and_weak_flag():
    topics = topics_for({"Paragraf": range(1, 11), "Sözcükte Anlam": range(11, 21)})
    marks = {q: KEY[q] for q in range(11, 21)}           # Paragraf 0/10, Sözcükte Anlam 10/10
    res = grading.grade(marks, KEY, topics, 4)
    rows = {r["topic"]: r for r in res["topics"] if r["topic"] in ("Paragraf", "Sözcükte Anlam")}
    assert rows["Paragraf"]["ratio"] == 0 and rows["Paragraf"]["weak"] is True
    assert rows["Sözcükte Anlam"]["ratio"] == 1 and rows["Sözcükte Anlam"]["weak"] is False
    assert [r["topic"] for r in res["weak_topics"]] == ["Paragraf"]


def test_exactly_half_is_not_weak_but_below_half_is():
    topics = topics_for({"T": range(1, 5)})
    half = grading.grade({1: KEY[1], 2: KEY[2]}, KEY, topics, 4)
    assert not next(r for r in half["topics"] if r["topic"] == "T")["weak"]
    below = grading.grade({1: KEY[1]}, KEY, topics, 4)
    assert next(r for r in below["topics"] if r["topic"] == "T")["weak"]


def test_blank_topic_is_unspecified_and_never_weak():
    res = grading.grade({}, KEY, {}, 4)  # everything blank, no topics
    assert {r["topic"] for r in res["topics"]} == {tyt.UNSPECIFIED_TOPIC}
    assert res["weak_topics"] == []
    # one row per subject
    assert len(res["topics"]) == len(tyt.SUBJECTS)


def test_same_topic_name_in_two_subjects_is_kept_separate():
    topics = {1: "Genel", 41: "Genel"}
    res = grading.grade({}, KEY, topics, 4)
    generals = [r for r in res["topics"] if r["topic"] == "Genel"]
    assert {r["subject"] for r in generals} == {"Türkçe", "Tarih"}


def test_cancelled_question_counts_as_correct_in_topic():
    key = dict(KEY)
    key[1] = None
    res = grading.grade({}, key, {1: "T"}, 4)
    row = next(r for r in res["topics"] if r["topic"] == "T")
    assert row["correct"] == 1 and row["ratio"] == 1


def test_custom_weak_threshold():
    topics = topics_for({"T": range(1, 5)})
    marks = {1: KEY[1], 2: KEY[2], 3: KEY[3]}  # 75 %
    assert grading.grade(marks, KEY, topics, 4, weak_threshold=0.8)["weak_topics"][0]["topic"] == "T"
    assert not [r for r in grading.grade(marks, KEY, topics, 4)["weak_topics"] if r["topic"] == "T"]


# ---------- class analysis ----------

def test_class_topic_stats_aggregates_students():
    topics = topics_for({"T": range(1, 5)})
    a = grading.grade({q: KEY[q] for q in range(1, 5)}, KEY, topics, 4)  # 4/4
    b = grading.grade({}, KEY, topics, 4)                                # 0/4
    rows = grading.class_topic_stats([a, b])
    t = next(r for r in rows if r["topic"] == "T")
    assert (t["correct"], t["total"], t["ratio"]) == (4, 8, 0.5)
    assert t["weak"] is False
    c = grading.class_topic_stats([b, b])
    assert next(r for r in c if r["topic"] == "T")["weak"] is True


def test_most_missed_questions_ranking():
    def res(wrongs):
        return grading.grade({q: wrong_of(q) for q in wrongs}, KEY, {}, 4)
    results = [res([3, 5]), res([3]), res([3, 7])]
    top = grading.most_missed_questions(results)
    assert top[0]["question"] == 3 and top[0]["wrong"] == 3 and top[0]["students"] == 3
    assert [r["question"] for r in top[1:]] == [5, 7]  # ties broken by question number
    assert grading.most_missed_questions([res([])]) == []
    assert len(grading.most_missed_questions([res(range(1, 30))], limit=5)) == 5
