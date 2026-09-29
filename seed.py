"""python seed.py  ->  create the teacher (admin/admin) and students ogr1..ogr10 (idempotent)."""
from app import create_app
from app.seed import seed_users

if __name__ == "__main__":
    with create_app({"AUTO_SEED": False}).app_context():
        print(f"{seed_users()} kullanıcı eklendi.")
