from app.models import User, db

TEACHER = ("admin", "admin", "Öğretmen")
STUDENT_COUNT = 10


def seed_users() -> int:
    """Create admin + ogr1..ogr10 if missing. Existing users (and their passwords) are untouched."""
    wanted = [(*TEACHER, "teacher")]
    wanted += [(f"ogr{i}", f"ogr{i}", f"Öğrenci {i}", "student") for i in range(1, STUDENT_COUNT + 1)]
    existing = {u.username for u in User.query.all()}
    created = 0
    for username, password, full_name, role in wanted:
        if username in existing:
            continue
        user = User(username=username, full_name=full_name, role=role)
        user.set_password(password)
        db.session.add(user)
        created += 1
    db.session.commit()
    return created
