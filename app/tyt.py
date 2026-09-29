"""TYT structure: 120 questions, options A-E. Question numbers are global (1..120)."""
from dataclasses import dataclass

OPTIONS = ("A", "B", "C", "D", "E")
TOTAL_QUESTIONS = 120
UNSPECIFIED_TOPIC = "Belirtilmemiş"


@dataclass(frozen=True)
class Test:
    key: str
    name: str
    first: int  # global number of the first question
    count: int

    @property
    def last(self) -> int:
        return self.first + self.count - 1

    def contains(self, q: int) -> bool:
        return self.first <= q <= self.last


@dataclass(frozen=True)
class Subject:
    name: str
    test_key: str
    first: int
    last: int


TESTS = (
    Test("turkce", "Türkçe", 1, 40),
    Test("sosyal", "Sosyal Bilimler", 41, 20),
    Test("matematik", "Temel Matematik", 61, 40),
    Test("fen", "Fen Bilimleri", 101, 20),
)

SUBJECTS = (
    Subject("Türkçe", "turkce", 1, 40),
    Subject("Tarih", "sosyal", 41, 45),
    Subject("Coğrafya", "sosyal", 46, 50),
    Subject("Felsefe", "sosyal", 51, 55),
    Subject("Din Kültürü", "sosyal", 56, 60),
    Subject("Matematik", "matematik", 61, 100),
    Subject("Fizik", "fen", 101, 107),
    Subject("Kimya", "fen", 108, 114),
    Subject("Biyoloji", "fen", 115, 120),
)

TESTS_BY_KEY = {t.key: t for t in TESTS}


def _check(q: int) -> None:
    if not isinstance(q, int) or not 1 <= q <= TOTAL_QUESTIONS:
        raise ValueError(f"Geçersiz soru numarası: {q!r}")


def test_of(q: int) -> Test:
    _check(q)
    return next(t for t in TESTS if t.contains(q))


def subject_of(q: int) -> Subject:
    _check(q)
    return next(s for s in SUBJECTS if s.first <= q <= s.last)


def local_no(q: int) -> int:
    """Question number inside its own test (Fen 9 -> global 109 -> 9)."""
    return q - test_of(q).first + 1


def global_no(test_key: str, local: int) -> int:
    t = TESTS_BY_KEY[test_key]
    if not 1 <= local <= t.count:
        raise ValueError(f"{t.name} için geçersiz soru numarası: {local}")
    return t.first + local - 1


def label(q: int) -> str:
    return f"{test_of(q).name} {local_no(q)}"
