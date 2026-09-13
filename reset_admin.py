"""
reset_admin.py - Diagnostic & Password Reset Tool for HLA Studio
Run this on your Ubuntu server to verify DB connection and reset/seed the admin account:
    python reset_admin.py
"""

import sys
import os

# Ensure script directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

print("=" * 65)
print("  HLA STUDIO • UBUNTU DATABASE & AUTH DIAGNOSTIC")
print("=" * 65)

db_url = os.getenv("DATABASE_URL", "")
print(f"\n[1] Checking DATABASE_URL from .env: {db_url}")

if not db_url:
    print("[ERROR] DATABASE_URL is missing in your .env file!")
    print("Example: DATABASE_URL=postgresql://postgres:ganesh@localhost:5432/hla_db")
    sys.exit(1)

try:
    from app import app, db
    from models import User
except Exception as e:
    print(f"[ERROR] Failed to import app or models: {e}")
    sys.exit(1)

with app.app_context():
    print("[2] Connecting to PostgreSQL database...")
    try:
        # Test basic connection
        with db.engine.connect() as conn:
            res = conn.execute(db.text("SELECT current_database(), current_user, version();")).fetchone()
            print(f"[OK] Successfully connected to PostgreSQL!")
            print(f"     Database: {res[0]} | User: {res[1]}")
    except Exception as e:
        print(f"\n[FAIL] Cannot connect to PostgreSQL: {e}\n")
        print("To fix this on Ubuntu, verify:")
        print("  1. Is PostgreSQL running? -> sudo systemctl status postgresql")
        print("  2. Does the password match? Run:")
        print("     sudo -u postgres psql -c \"ALTER USER postgres WITH PASSWORD 'ganesh';\"")
        print("  3. Does the database exist? Run:")
        print("     sudo -u postgres psql -c \"CREATE DATABASE hla_db OWNER postgres;\"")
        sys.exit(1)

    print("\n[3] Checking 'users' table and accounts...")
    try:
        db.create_all()
        users = User.query.all()
        print(f"     Found {len(users)} user(s) in database.")
        for u in users:
            print(f"     - ID: {u.id} | Username: {u.username} | Role: {u.role} | Email: {u.email}")
    except Exception as e:
        print(f"[ERROR] Could not query users table: {e}")
        sys.exit(1)

    print("\n[4] Resetting / Ensuring default 'admin' account...")
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        print("     Creating new 'admin' user...")
        admin = User(
            username="admin",
            email="admin@hlaproject.local",
            role="admin"
        )
        admin.set_password("admin123")
        db.session.add(admin)
    else:
        print("     Updating existing 'admin' user password to 'admin123'...")
        admin.set_password("admin123")
        admin.role = "admin"

    # Also ensure architect and viewer exist
    for udata in [
        {"username": "architect", "email": "architect@hlaproject.local", "role": "architect", "password": "architect123"},
        {"username": "viewer", "email": "viewer@hlaproject.local", "role": "viewer", "password": "viewer123"}
    ]:
        u = User.query.filter_by(username=udata["username"]).first()
        if not u:
            u = User(username=udata["username"], email=udata["email"], role=udata["role"])
            u.set_password(udata["password"])
            db.session.add(u)
        else:
            u.set_password(udata["password"])

    db.session.commit()
    print("[OK] Admin credentials verified successfully!")
    print("\n" + "=" * 65)
    print("  LOGIN CREDENTIALS READY:")
    print("    Username: admin")
    print("    Password: admin123")
    print("    Role:     admin")
    print("=" * 65 + "\n")
