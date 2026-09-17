import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import db, SystemSetting
from app import app

with app.app_context():
    settings = SystemSetting.query.filter(SystemSetting.key.like("smtp_%")).all()
    print("Database SystemSetting records:")
    for s in settings:
        has_val = bool(s.value and s.value.strip())
        val_preview = s.value[:3] + "..." if has_val and s.key != "smtp_password" else ("configured" if has_val else "empty")
        print(f"Key: {s.key} | Configured: {has_val} | Value/Preview: {val_preview}")
