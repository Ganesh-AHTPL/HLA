"""
Application and Platform Configuration.
Loads environment variables and platform defaults (RULE 47).
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Platform configuration settings."""
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ganesh@localhost:5432/hla_db")
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    DEFAULT_TARGET_SCHEMA = os.getenv("TARGET_SCHEMA", "ra_ctrl")
    PORT = int(os.getenv("PORT", 5000))
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "hla-platform-secret-key-2026")
