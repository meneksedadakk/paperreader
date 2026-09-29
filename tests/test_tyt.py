import pytest

from app import tyt


def test_tests_cover_120_questions_without_gaps():
    assert sum(t.count for t in tyt.TESTS) == tyt.TOTAL_QUESTIONS == 120
    expected = 1
    for t in tyt.TESTS:
        assert t.first == expected
        expected = t.last + 1
    assert expected == 121


def test_subjects_partition_all_questions_exactly_once():
    seen = []
    for s in tyt.SUBJECTS:
        seen.extend(range(s.first, s.last + 1))
    assert sorted(seen) == list(range(1, 121))


@pytest.mark.parametrize("q,test,subject", [
    (1, "turkce", "Türkçe"), (40, "turkce", "Türkçe"),
    (41, "sosyal", "Tarih"), (45, "sosyal", "Tarih"),
    (46, "sosyal", "Coğrafya"), (50, "sosyal", "Coğrafya"),
    (51, "sosyal", "Felsefe"), (55, "sosyal", "Felsefe"),
    (56, "sosyal", "Din Kültürü"), (60, "sosyal", "Din Kültürü"),
    (61, "matematik", "Matematik"), (100, "matematik", "Matematik"),
    (101, "fen", "Fizik"), (107, "fen", "Fizik"),
    (108, "fen", "Kimya"), (114, "fen", "Kimya"),
    (115, "fen", "Biyoloji"), (120, "fen", "Biyoloji"),
])
def test_test_and_subject_boundaries(q, test, subject):
    assert tyt.test_of(q).key == test
    assert tyt.subject_of(q).name == subject


def test_subject_stays_inside_its_test():
    for q in range(1, 121):
        assert tyt.subject_of(q).test_key == tyt.test_of(q).key


def test_local_and_global_numbers_roundtrip():
    assert tyt.local_no(109) == 9 and tyt.test_of(109).key == "fen"
    assert tyt.local_no(61) == 1
    for q in range(1, 121):
        assert tyt.global_no(tyt.test_of(q).key, tyt.local_no(q)) == q


def test_label():
    assert tyt.label(109) == "Fen Bilimleri 9"
    assert tyt.label(1) == "Türkçe 1"


@pytest.mark.parametrize("bad", [0, 121, -1, "5", None, 3.5])
def test_invalid_question_numbers_raise(bad):
    with pytest.raises(ValueError):
        tyt.test_of(bad)


def test_global_no_rejects_out_of_range_local():
    with pytest.raises(ValueError):
        tyt.global_no("sosyal", 21)
    with pytest.raises(ValueError):
        tyt.global_no("turkce", 0)
