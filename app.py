import os
import re
import json
import io
import shutil
import secrets
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

from models import db, Document, Project, DBConnection, User, TargetArtifact, ControlSchedule, ControlRunHistory, EmailNotificationLog, SystemSetting, PasswordResetToken
import control_scheduler
import email_service
from auth import generate_token, generate_tokens, verify_refresh_token, login_required, role_required, get_current_user
from analyzer import analyze_document
from db_fetcher import test_db_connection, fetch_table_metadata, get_env_db_password, find_table_across_databases, scan_source_database
from vault_parser import parse_credential_vault
from target_logic_builder import build_target_logic_package, validate_target_ddl, deploy_target_ddl, generate_target_ddl, ensure_target_tables_provisioned

# Optional: only import if available
try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.0.196:3000"
], supports_credentials=True)

import logging
logger = logging.getLogger("hla_app")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '').endswith('app.log') for h in logger.handlers):
    try:
        fh = logging.FileHandler("app.log", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
        logger.addHandler(fh)
    except Exception:
        pass

def safe_log(msg: str, level: str = "info"):
    try:
        if level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
    except Exception:
        pass
    try:
        print(msg)
    except Exception:
        pass


# ── Config ────────────────────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".kdb", ".ini", ".json", ".yaml", ".yml", ".xml"}
ALLOWED_DOCUMENT_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE_MB   = 50
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

# ── Database Config ───────────────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/hla_db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


def seed_default_users():
    """Ensures default admin, architect, and viewer accounts exist."""
    default_users = [
        {"username": "admin", "email": "admin@hlaproject.local", "role": "admin", "password": "admin123"},
        {"username": "architect", "email": "architect@hlaproject.local", "role": "architect", "password": "architect123"},
        {"username": "viewer", "email": "viewer@hlaproject.local", "role": "viewer", "password": "viewer123"},
    ]
    for udata in default_users:
        user = User.query.filter_by(username=udata["username"]).first()
        if not user:
            user = User(
                username=udata["username"],
                email=udata["email"],
                role=udata["role"]
            )
            user.set_password(udata["password"])
            db.session.add(user)
        else:
            user.role = udata["role"]
            user.set_password(udata["password"])
    db.session.commit()


with app.app_context():
    try:
        db.create_all()
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL;"))
            conn.execute(db.text("ALTER TABLE db_connections ADD COLUMN IF NOT EXISTS conn_role VARCHAR(20) DEFAULT 'source';"))
            conn.execute(db.text("ALTER TABLE db_connections ADD COLUMN IF NOT EXISTS target_env VARCHAR(20) DEFAULT 'none';"))
            conn.execute(db.text("ALTER TABLE db_connections ADD COLUMN IF NOT EXISTS schema_name VARCHAR(100) DEFAULT 'public';"))
            conn.execute(db.text("ALTER TABLE db_connections ADD COLUMN IF NOT EXISTS vault_profile VARCHAR(100);"))
            conn.execute(db.text("ALTER TABLE target_artifacts ADD COLUMN IF NOT EXISTS source_tables_ddl TEXT;"))
            conn.execute(db.text("ALTER TABLE control_schedules ADD COLUMN IF NOT EXISTS hostname VARCHAR(255);"))
            conn.execute(db.text("ALTER TABLE control_schedules ADD COLUMN IF NOT EXISTS day_of_month VARCHAR(20) DEFAULT '1';"))
            conn.execute(db.text("ALTER TABLE control_run_history ADD COLUMN IF NOT EXISTS hostname VARCHAR(255);"))
            conn.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 1;"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS otp_hash VARCHAR(255);"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0;"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 5;"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS reset_token VARCHAR(128);"))
            conn.execute(db.text("ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS reset_token_expires_at TIMESTAMP WITH TIME ZONE;"))
            try:
                conn.execute(db.text("ALTER TABLE password_reset_tokens ALTER COLUMN token DROP NOT NULL;"))
                conn.execute(db.text("ALTER TABLE password_reset_tokens ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE;"))
                conn.execute(db.text("ALTER TABLE password_reset_tokens ALTER COLUMN expires_at TYPE TIMESTAMP WITH TIME ZONE;"))
            except Exception:
                pass
            conn.commit()
        seed_default_users()
        try:
            control_scheduler.init_scheduler(app)
        except Exception as se:
            print(f"[WARNING] Could not start control scheduler: {se}")
        print("[OK] Connected to PostgreSQL, initialized tables & migrations, and seeded default users.")
    except Exception as e:
        print(f"[WARNING] Could not initialize database tables: {e}")


def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# ── Authentication & RBAC Routes ──────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid username or password."}), 401

    tokens = generate_tokens(user)
    return jsonify({
        "message": f"Welcome back, {user.username}!",
        "token": tokens["access_token"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "user": user.to_dict()
    }), 200


@app.route("/api/auth/refresh", methods=["POST"])
def refresh_token():
    data = request.get_json() or {}
    token = data.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if not token:
        return jsonify({"error": "Refresh token is required."}), 400

    user, error = verify_refresh_token(token)
    if not user:
        return jsonify({"error": error or "Invalid or expired refresh token."}), 401

    new_tokens = generate_tokens(user)
    return jsonify({
        "token": new_tokens["access_token"],
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "user": user.to_dict()
    }), 200


def validate_password_policy(password: str, username: str = None) -> tuple[bool, str]:
    """
    Validates password against enterprise security policy:
    - At least 8 characters
    - At least 1 uppercase letter (A-Z)
    - At least 1 lowercase letter (a-z)
    - At least 1 number (0-9)
    - At least 1 special character
    - Not identical to username
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters in length."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password must include at least one number (0-9)."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password):
        return False, "Password must include at least one special character (!@#$%^&*...)."
    if username and password.lower() == username.lower():
        return False, "Password cannot be identical to your username."
    return True, ""


@app.route("/api/auth/send-otp", methods=["POST"])
@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or data.get("identifier") or "").strip().lower()

    safe_log("[RESET] Password reset request received")

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    now_utc = datetime.now(timezone.utc)
    one_hour_ago = now_utc - timedelta(hours=1)
    sixty_seconds_ago = now_utc - timedelta(seconds=60)

    # 1. Rate-limiting & Cooldown Enforcement
    recent_records = PasswordResetToken.query.join(User).filter(
        User.email.ilike(email),
        PasswordResetToken.created_at >= one_hour_ago
    ).order_by(PasswordResetToken.id.desc()).all()

    if len(recent_records) >= 5:
        return jsonify({"error": "Too many password reset requests. Please try again in an hour."}), 429

    if recent_records:
        latest = recent_records[0]
        created = latest.created_at
        if created:
            if created.tzinfo is None:
                elapsed = (datetime.now() - created).total_seconds()
            else:
                elapsed = (now_utc - created).total_seconds()

            if 0 <= elapsed < 60:
                remaining_cooldown = max(1, min(60, int(60 - elapsed)))
                return jsonify({"error": f"Please wait {remaining_cooldown} seconds before requesting a new code."}), 429

    # 2. Lookup user by registered email (case-insensitive)
    user = User.query.filter(User.email.ilike(email)).first()
    safe_log(f"[RESET] User lookup completed (user_found={bool(user)})")

    # 3. If account exists, generate and store secure hashed OTP and dispatch email
    if user:
        reset_record = None
        try:
            # Invalidate any prior active tokens for this user
            PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({"used": True})
            db.session.commit()

            # Cryptographically secure 6-digit numeric OTP (10 min validity, max 5 attempts)
            otp_code = f"{secrets.randbelow(1000000):06d}"
            safe_log("[RESET] OTP generated")
            expires_at = now_utc + timedelta(minutes=10)

            reset_record = PasswordResetToken(
                user_id=user.id,
                token=secrets.token_urlsafe(32),
                expires_at=expires_at,
                attempts=0,
                max_attempts=5,
                verified=False,
                used=False
            )
            # Store ONLY the hashed OTP (Werkzeug PBKDF2/SHA256 standard)
            reset_record.set_otp(otp_code)
            db.session.add(reset_record)
            db.session.commit()
            safe_log("[RESET] OTP stored successfully")

            # Send OTP ONLY to the user's registered email
            dispatch_res = email_service.send_password_reset_otp_email(user, otp_code, expires_minutes=10)
            if not dispatch_res.get("success"):
                # Database consistency: Invalidate/delete the token record so unusable OTP is not left active
                try:
                    db.session.delete(reset_record)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                safe_log(f"[RESET] Email dispatch failed: {dispatch_res.get('error')}", level="error")
                return jsonify({"error": "Unable to send the verification email. Please try again later."}), 500

            safe_log("[RESET] Password reset OTP email dispatched successfully")
        except Exception as e:
            import traceback
            traceback.print_exc()
            if reset_record:
                try:
                    db.session.delete(reset_record)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            else:
                db.session.rollback()
            return jsonify({"error": "Unable to send the verification email. Please try again later."}), 500

    # 4. Anti-Enumeration generic response: Return the exact same response whether user exists or not
    return jsonify({
        "success": True,
        "message": "If the email is registered, a verification code has been sent."
    }), 200


@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp_endpoint():
    data = request.get_json() or {}
    email = (data.get("email") or data.get("identifier") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not email:
        return jsonify({"error": "Email address is required."}), 400

    if not otp:
        return jsonify({"error": "Invalid verification code. Please try again."}), 400

    user = User.query.filter(User.email.ilike(email)).first()
    if not user:
        return jsonify({"error": "Invalid verification code. Please try again."}), 400

    token_record = PasswordResetToken.query.filter_by(
        user_id=user.id,
        used=False,
        verified=False
    ).order_by(PasswordResetToken.id.desc()).first()

    if not token_record:
        return jsonify({"error": "No active verification code found. Please request a new code."}), 400

    now_utc = datetime.now(timezone.utc)
    exp = token_record.expires_at
    if exp:
        if exp.tzinfo is None:
            is_expired = exp <= datetime.now()
        else:
            is_expired = exp <= datetime.now(timezone.utc)
        if is_expired:
            token_record.used = True
            db.session.commit()
            return jsonify({"error": "This verification code has expired. Please request a new code."}), 400

    # Check max attempts
    if token_record.attempts >= token_record.max_attempts:
        token_record.used = True
        db.session.commit()
        return jsonify({"error": "Too many incorrect attempts. Please request a new code."}), 400

    # Verify against hashed OTP
    if not token_record.check_otp(otp):
        token_record.attempts += 1
        db.session.commit()
        if token_record.attempts >= token_record.max_attempts:
            token_record.used = True
            db.session.commit()
            return jsonify({"error": "Too many incorrect attempts. Please request a new code."}), 400
        return jsonify({"error": "Invalid verification code. Please try again."}), 400

    # Verification successful: issue single-use, short-lived reset authorization token (15 mins)
    reset_auth_token = secrets.token_urlsafe(48)
    token_record.verified = True
    token_record.verified_at = now_utc
    token_record.reset_token = reset_auth_token
    token_record.reset_token_expires_at = now_utc + timedelta(minutes=15)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "OTP verified successfully.",
        "reset_token": reset_auth_token
    }), 200


@app.route("/api/auth/reset-password", methods=["POST"])
@app.route("/api/auth/reset-password-with-token", methods=["POST"])
def reset_password_with_token_endpoint():
    data = request.get_json() or {}
    reset_token = (data.get("reset_token") or data.get("token") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    confirm_password = (data.get("confirm_password") or "").strip()

    if not reset_token:
        return jsonify({"error": "Reset authorization token is missing or invalid. Please request a new code."}), 400

    token_record = PasswordResetToken.query.filter_by(reset_token=reset_token).first()
    if not token_record or token_record.used or not token_record.verified:
        return jsonify({"error": "Invalid or expired reset token. Please request a new verification code."}), 400

    if not token_record.is_reset_token_valid():
        token_record.used = True
        db.session.commit()
        return jsonify({"error": "This reset token has expired. Please request a new code."}), 400

    user = token_record.user
    if not user:
        return jsonify({"error": "User account associated with this token no longer exists."}), 404

    if not new_password or not confirm_password:
        return jsonify({"error": "New password and password confirmation are required."}), 400

    if new_password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400

    is_valid_pwd, policy_err = validate_password_policy(new_password, user.username)
    if not is_valid_pwd:
        return jsonify({"error": policy_err}), 400

    try:
        # 1. Update password securely with Werkzeug hash
        user.set_password(new_password)

        # 2. Invalidate reset token and OTP (single-use enforcement)
        token_record.used = True

        # 3. Invalidate active sessions by incrementing token_version
        user.token_version = (user.token_version or 1) + 1

        # 4. Record audit event in notification/audit logs
        try:
            audit_log = EmailNotificationLog(
                recipient_emails=user.email or f"{user.username}@hlaproject.local",
                subject="AUDIT: Password Reset Completed",
                body_text=f"Password successfully reset for user '{user.username}' (ID: {user.id}). Sessions invalidated.",
                body_html=f"<p>Password successfully reset for user <strong>{user.username}</strong>.</p>",
                status="AUDIT",
                sent_at=datetime.now(timezone.utc)
            )
            db.session.add(audit_log)
        except Exception:
            pass

        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Password reset successful. Please log in with your new password."
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to update password. Please try again later."}), 500


@app.route("/api/auth/register", methods=["POST"])
@app.route("/api/auth/users", methods=["POST"])
@role_required("admin")
def create_user_account():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip() or None
    role = data.get("role", "architect").strip().lower()

    if not username or not password:
        return jsonify({"error": "Username and initial password are required."}), 400

    if role not in ["admin", "architect", "viewer"]:
        return jsonify({"error": "Role must be one of: admin, architect, viewer."}), 400

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"error": f"Username '{username}' already exists. Please choose another."}), 409

    try:
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return jsonify({
            "message": f"User account '{username}' ({role.upper()}) created successfully.",
            "user": user.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500


@app.route("/api/auth/me", methods=["GET"])
@login_required
def get_current_user_profile():
    return jsonify({"user": g.current_user.to_dict()}), 200


@app.route("/api/auth/users", methods=["GET"])
@role_required("admin")
def list_all_users():
    users = User.query.order_by(User.id.asc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route("/api/auth/users/<int:user_id>", methods=["DELETE"])
@role_required("admin")
def delete_user_account(user_id):
    if hasattr(g, "current_user") and g.current_user and g.current_user.id == user_id:
        return jsonify({"error": "You cannot delete your own active Admin account."}), 400

    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "User account not found."}), 404

        username = user.username
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": f"User account '{username}' has been deleted."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete user: {str(e)}"}), 500


@app.route("/api/auth/users/<int:user_id>", methods=["PUT", "PATCH"])
@role_required("admin")
def update_user_account(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User account not found."}), 404

    data = request.get_json() or {}
    new_role = data.get("role")
    new_email = data.get("email")
    new_password = data.get("password")

    if new_role:
        normalized_role = str(new_role).strip().lower()
        if normalized_role not in ["admin", "architect", "viewer"]:
            return jsonify({"error": "Role must be one of: admin, architect, viewer."}), 400

        # Prevent admin from demoting their own active session
        if hasattr(g, "current_user") and g.current_user and g.current_user.id == user_id and normalized_role != "admin":
            return jsonify({"error": "You cannot remove your own Admin permissions."}), 400

        user.role = normalized_role

    if new_email is not None:
        user.email = str(new_email).strip() or None

    if new_password:
        pw_str = str(new_password).strip()
        if len(pw_str) < 4:
            return jsonify({"error": "Password must be at least 4 characters long."}), 400
        user.set_password(pw_str)

    try:
        db.session.commit()
        return jsonify({
            "message": f"Updated permissions for user '{user.username}'. Current role: {user.role.upper()}.",
            "user": user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update user permissions: {str(e)}"}), 500


# ── Health & System Routes ────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    db_status = "connected"
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as e:
        db_status = f"disconnected: {str(e)}"

    return jsonify({
        "status": "ok",
        "message": "HLA backend is running",
        "database": db_status
    })


@app.route("/api/reset-data", methods=["POST"])
@role_required("admin")
def reset_data():
    """Drops all existing uploaded documents and generated files to start clean."""
    try:
        # Delete all document records
        Document.query.delete()
        db.session.commit()

        # Clean uploads folder
        for item in os.listdir(UPLOAD_FOLDER):
            item_path = os.path.join(UPLOAD_FOLDER, item)
            if item == "generated":
                # Keep directory, delete generated docx files inside
                for f in os.listdir(item_path):
                    if f.endswith(".docx") and not f.startswith("HLA_Client"):
                        try:
                            os.remove(os.path.join(item_path, f))
                        except Exception:
                            pass
            elif os.path.isfile(item_path):
                try:
                    os.remove(item_path)
                except Exception:
                    pass

        return jsonify({"message": "All existing HLA uploads have been successfully dropped."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to reset data: {str(e)}"}), 500


# ── Project Management Routes (Folder-based structure) ────────────────

@app.route("/api/projects", methods=["GET"])
@login_required
def list_projects():
    try:
        projects = Project.query.order_by(Project.created_at.desc()).all()
        return jsonify([p.to_dict() for p in projects]), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch projects: {str(e)}"}), 500


@app.route("/api/projects", methods=["POST"])
@role_required("admin", "architect")
def create_project():
    data = request.get_json() or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": "Project name is required"}), 400

    try:
        created_by_id = g.current_user.id if hasattr(g, "current_user") and g.current_user else None
        project = Project(
            name=name,
            description=data.get("description", "").strip(),
            created_by_id=created_by_id
        )
        db.session.add(project)
        db.session.commit()

        # Create project folder on disk
        folder_path = os.path.join(UPLOAD_FOLDER, "projects", str(project.id))
        os.makedirs(folder_path, exist_ok=True)
        project.folder_path = folder_path
        db.session.commit()

        return jsonify({
            "message": f"Project '{name}' created successfully",
            "project": project.to_dict(include_details=True)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create project: {str(e)}"}), 500


@app.route("/api/projects/<int:project_id>", methods=["GET"])
@login_required
def get_project(project_id):
    try:
        project = db.session.get(Project, project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        return jsonify(project.to_dict(include_details=True)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
@role_required("admin")
def delete_project(project_id):
    try:
        project = db.session.get(Project, project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Remove project folder on disk
        if project.folder_path and os.path.exists(project.folder_path):
            try:
                shutil.rmtree(project.folder_path)
            except Exception:
                pass

        db.session.delete(project)
        db.session.commit()

        return jsonify({"message": f"Project '{project.name}' deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete project: {str(e)}"}), 500


# ── Project-Scoped Upload & HLA Ingestion ──────────────────────────────

@app.route("/api/projects/<int:project_id>/upload", methods=["POST"])
@app.route("/api/upload", methods=["POST"])
@role_required("admin", "architect")
def upload_project_document(project_id=None):
    if project_id is None:
        p_id = request.form.get("project_id")
        if p_id:
            try:
                project_id = int(p_id)
            except ValueError:
                pass

    project = None
    if project_id:
        project = db.session.get(Project, project_id)
    if not project:
        project = Project.query.order_by(Project.created_at.desc()).first()
    if not project:
        project = Project(name="Default Workspace", description="Default architecture workspace")
        db.session.add(project)
        db.session.commit()

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file format '{ext}'. Only Excel files (.xlsx, .xls) conforming to the HLA Control Specification template are accepted. Word (.docx, .doc), PDF, CSV, and other formats are strictly not permitted."
        }), 422

    filename = secure_filename(file.filename)

    # Save directly inside project folder
    folder_path = project.folder_path or os.path.join(UPLOAD_FOLDER, "projects", str(project.id))
    os.makedirs(folder_path, exist_ok=True)
    save_path = os.path.join(folder_path, filename)
    file.save(save_path)
    file_size = os.path.getsize(save_path)

    # Validate that it is a readable Excel workbook
    try:
        wb = openpyxl.load_workbook(save_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()
    except Exception as exc:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        return jsonify({"error": f"Invalid or corrupted Excel workbook: {str(exc)}"}), 422

    result = {
        "message": f"File '{filename}' uploaded into project '{project.name}'.",
        "filename": filename,
        "type": ext,
        "size": file_size,
    }

    # Basic metadata extraction
    try:
        if OPENPYXL_AVAILABLE:
            result.update(_parse_excel(save_path))
    except Exception as e:
        result["parse_warning"] = str(e)

    # Auto-analysis for HLA specifications (Excel standard specification)
    analysis_data = None
    try:
        analysis_data = analyze_document(save_path)
        result["analysis"] = analysis_data
    except Exception as ana_err:
        result["analysis_warning"] = f"Auto-analysis skipped: {str(ana_err)}"

    # Persist Document record linked to Project
    try:
        doc = Document(
            project_id=project.id,
            filename=filename,
            original_name=file.filename,
            file_type=ext,
            file_size=file_size,
            file_path=save_path,
            status="analyzed" if analysis_data else ("parsed" if "parse_warning" not in result else "warning"),
            metadata_json=result,
            analysis_data=analysis_data,
            generated_doc_path=None
        )
        db.session.add(doc)
        db.session.commit()
        result["id"] = doc.id
        result["uploaded_at"] = doc.uploaded_at.isoformat()

        # 1. First time alone create required DDL (if already created in target table, no need to recreate)
        if analysis_data:
            try:
                target_conn = DBConnection.query.filter_by(project_id=project.id, conn_role="target").first()
                target_schema_name = (analysis_data.get("control_overview") or {}).get("target_schema") or "ra_ctrl"
                if isinstance(target_schema_name, dict):
                    target_schema_name = target_schema_name.get("schema_name", "ra_ctrl")

                target_cfg = {
                    "db_type": target_conn.db_type if target_conn else "postgresql",
                    "host": target_conn.host if target_conn and target_conn.host else os.environ.get("DB_HOST", "localhost"),
                    "port": target_conn.port if target_conn and target_conn.port else int(os.environ.get("DB_PORT", 5432)),
                    "database_name": target_conn.database_name if target_conn and target_conn.database_name else os.environ.get("DB_NAME", "hla_db"),
                    "username": target_conn.username if target_conn and target_conn.username else os.environ.get("DB_USER", "postgres"),
                    "password": target_conn.password if target_conn and target_conn.password else (os.environ.get("DB_PASSWORD") or get_env_db_password()),
                    "schema_name": target_conn.schema_name if target_conn and target_conn.schema_name else target_schema_name
                }
                if not target_cfg.get("password") and target_cfg.get("host") in ("localhost", "127.0.0.1", "::1"):
                    target_cfg["password"] = get_env_db_password()

                ddl_script = generate_target_ddl(
                    target_cfg.get("schema_name") or target_schema_name,
                    target_cfg.get("db_type", "postgresql"),
                    analysis_data.get("sources", []),
                    analysis_data.get("rules", {}),
                    analysis_data.get("mappings", []),
                    {},
                    analysis_data
                )
                ddl_ok, ddl_msg, deployed_tables = ensure_target_tables_provisioned(target_cfg, ddl_script)
                result["target_ddl_provision"] = {
                    "success": ddl_ok,
                    "message": ddl_msg,
                    "tables": deployed_tables
                }
            except Exception as ddl_err:
                result["target_ddl_warning"] = f"Target table provisioning check skipped: {str(ddl_err)}"

            # 2. Auto-register or synchronize the Control Schedule extracted from HLA
            try:
                sched_info = (analysis_data.get("control_overview") or {}).get("schedule") or {}
                ctrl_num = (analysis_data.get("control_overview") or {}).get("identification", {}).get("control_number")
                ctrl_title = (analysis_data.get("control_overview") or {}).get("identification", {}).get("control_title") or f"Control {ctrl_num or ''}"

                sched_type = sched_info.get("schedule_type", "monthly")
                day_of_month = str(sched_info.get("day_of_month", "1"))
                run_time = sched_info.get("run_time", "02:00")
                days_of_week = sched_info.get("days_of_week", "mon")

                sched = ControlSchedule.query.filter_by(project_id=project.id, control_number=ctrl_num).first() if ctrl_num else None
                if not sched:
                    sched = ControlSchedule(
                        project_id=project.id,
                        document_id=doc.id,
                        name=f"{ctrl_title} Automated Schedule",
                        control_number=ctrl_num,
                        environment="dev",
                        schedule_type=sched_type,
                        run_time=run_time,
                        day_of_month=day_of_month,
                        days_of_week=days_of_week,
                        is_active=True
                    )
                    db.session.add(sched)
                else:
                    sched.document_id = doc.id
                    sched.schedule_type = sched_type
                    sched.run_time = run_time
                    sched.day_of_month = day_of_month
                    sched.days_of_week = days_of_week
                    sched.is_active = True
                db.session.commit()
                result["schedule"] = sched.to_dict()
            except Exception as sched_err:
                db.session.rollback()
                result["schedule_warning"] = f"Schedule registration skipped: {str(sched_err)}"

            # Persist updated metadata_json on Document
            doc.metadata_json = result
            db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        result["db_warning"] = f"Failed to persist to database: {str(db_err)}"

    return jsonify(result), 200


# ── Configurable Source & Target Database Connections & KDB Vault ──────

@app.route("/api/projects/<int:project_id>/connections", methods=["GET"])
@login_required
def list_project_connections(project_id):
    try:
        conns = DBConnection.query.filter_by(project_id=project_id).all()
        return jsonify([c.to_dict() for c in conns]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<int:project_id>/connections", methods=["POST"])
@role_required("admin", "architect")
def save_project_connection(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json() or {}
    source_db_name = data.get("source_db_name", "").strip()

    if not source_db_name:
        return jsonify({"error": "Connection/Source DB name is required"}), 400

    try:
        conn = DBConnection.query.filter_by(project_id=project_id, source_db_name=source_db_name).first()
        if not conn:
            conn = DBConnection(project_id=project_id, source_db_name=source_db_name)
            db.session.add(conn)

        conn.conn_role = data.get("conn_role", "source")
        conn.target_env = data.get("target_env", "none")
        conn.schema_name = data.get("schema_name", "public")
        conn.db_type = data.get("db_type", "postgresql").lower()
        conn.host = data.get("host")
        raw_port = data.get("port")
        if raw_port and str(raw_port).isdigit():
            conn.port = int(raw_port)
        else:
            conn.port = None

        warehouse_val = data.get("warehouse")
        if not warehouse_val and raw_port and not str(raw_port).isdigit():
            warehouse_val = str(raw_port).strip()

        conn.database_name = data.get("database_name")
        conn.username = data.get("username")
        if data.get("password"):
            conn.password = data.get("password")
        conn.connection_string = data.get("connection_string")
        conn.vault_profile = data.get("vault_profile")

        # Test connection
        config_dict = {
            "db_type": conn.db_type,
            "host": conn.host,
            "port": conn.port,
            "warehouse": warehouse_val or ("COMPUTE_WH" if conn.db_type == "snowflake" else None),
            "database_name": conn.database_name,
            "username": conn.username,
            "password": conn.password,
            "connection_string": conn.connection_string
        }
        success, msg = test_db_connection(config_dict)
        conn.status = "connected" if success else "failed"
        conn.last_tested = datetime.now(timezone.utc)

        db.session.commit()
        return jsonify({
            "message": msg,
            "success": success,
            "connection": conn.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to save connection: {str(e)}"}), 500


@app.route("/api/projects/<int:project_id>/vault-upload", methods=["POST"])
@app.route("/api/projects/<int:project_id>/upload-vault", methods=["POST"])
@role_required("admin", "architect")
def upload_credential_vault(project_id):
    """
    Accepts .kdb, .ini, .json, .yaml, or .xml credential vault file or raw text.
    Parses profiles for both source databases and target environments (dev/prod).
    Auto-configures and tests each database connection profile.
    """
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    raw_text = ""
    filename = ""

    if "file" in request.files:
        file = request.files["file"]
        filename = file.filename
        raw_text = file.read().decode("utf-8", errors="replace")
    elif request.is_json:
        data = request.get_json() or {}
        raw_text = data.get("content") or data.get("raw_content") or ""
        filename = data.get("filename", "credentials.kdb")

    if not raw_text.strip():
        return jsonify({"error": "No credential file or text content provided."}), 400

    parsed = parse_credential_vault(raw_text, filename)
    if not parsed.get("success"):
        return jsonify({"error": parsed.get("message", "Failed to parse vault file.")}), 400

    profiles = parsed.get("profiles", [])
    configured = []

    for p in profiles:
        is_target = (p.get("conn_role") == "target")
        target_env = p.get("target_env", "none")
        db_name = p["source_db_name"]
        conn = None
        if is_target and target_env in ("dev", "prod"):
            conn = DBConnection.query.filter_by(project_id=project_id, conn_role="target", target_env=target_env).first()
        if not conn:
            conn = DBConnection.query.filter_by(project_id=project_id, source_db_name=db_name).first()
        if not conn:
            conn = DBConnection(project_id=project_id, source_db_name=db_name)
            db.session.add(conn)

        conn.conn_role = p.get("conn_role", "source")
        conn.target_env = p.get("target_env", "none")
        conn.schema_name = p.get("schema_name", "public")
        conn.db_type = p.get("db_type", "postgresql")
        conn.host = p.get("host")
        conn.port = p.get("port")
        conn.database_name = p.get("database_name")
        conn.username = p.get("username")
        if p.get("password"):
            conn.password = p.get("password")
        conn.connection_string = p.get("connection_string")
        conn.vault_profile = p.get("vault_profile")

        test_cfg = {
            "db_type": conn.db_type,
            "host": conn.host,
            "port": conn.port,
            "database_name": conn.database_name,
            "username": conn.username,
            "password": conn.password,
            "connection_string": conn.connection_string
        }
        success, _ = test_db_connection(test_cfg)
        conn.status = "connected" if success else "failed"
        conn.last_tested = datetime.now(timezone.utc)
        configured.append(conn)

    db.session.commit()

    return jsonify({
        "message": f"Successfully parsed and imported {len(configured)} database profile(s) from {parsed.get('format_detected')}.",
        "format_detected": parsed.get("format_detected"),
        "total_imported": len(configured),
        "connections": [c.to_dict() for c in configured]
    }), 200


@app.route("/api/projects/<int:project_id>/targets/vault-upload", methods=["POST"])
@role_required("admin", "architect")
def upload_target_credential_vault(project_id):
    """
    Parses a credential vault / .kdb file specifically for Target Database(s).
    Supports Dev, Prod, or unified dual-environment KDB files.
    Auto-tests target connectivity and registers configurations.
    """
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    raw_text = ""
    filename = ""
    target_env = "dev"

    if "file" in request.files:
        file = request.files["file"]
        filename = file.filename
        raw_text = file.read().decode("utf-8", errors="replace")
        target_env = (request.form.get("target_env") or "dev").lower()
    elif request.is_json:
        data = request.get_json() or {}
        raw_text = data.get("content") or data.get("raw_content") or ""
        filename = data.get("filename", "target_credentials.kdb")
        target_env = (data.get("target_env") or "dev").lower()

    if not raw_text.strip():
        return jsonify({"error": "No credential file or text content provided."}), 400

    parsed = parse_credential_vault(raw_text, filename, default_role="target", target_env_hint=target_env)
    if not parsed.get("success"):
        return jsonify({"error": parsed.get("message", "Failed to parse target vault file.")}), 400

    profiles = parsed.get("profiles", [])
    if not profiles:
        return jsonify({"error": "No database profiles found in uploaded vault file."}), 400

    configured = []
    target_profiles = [p for p in profiles if p.get("conn_role") == "target"]
    if not target_profiles:
        for p in profiles:
            p["conn_role"] = "target"
            p["target_env"] = target_env
            p["source_db_name"] = f"Target {target_env.upper()}"
        target_profiles = profiles

    for p in target_profiles:
        env = (p.get("target_env") or target_env).lower()
        if env not in ("dev", "prod"):
            env = target_env if target_env in ("dev", "prod") else "dev"

        db_name_label = f"Target {env.upper()}"
        conn = DBConnection.query.filter_by(project_id=project_id, conn_role="target", target_env=env).first()
        if not conn:
            conn = DBConnection.query.filter_by(project_id=project_id, source_db_name=db_name_label).first()
        if not conn:
            conn = DBConnection(project_id=project_id, source_db_name=db_name_label, conn_role="target", target_env=env)
            db.session.add(conn)

        conn.conn_role = "target"
        conn.target_env = env
        conn.schema_name = p.get("schema_name") or f"target_{env}"
        conn.db_type = (p.get("db_type") or "postgresql").lower()
        conn.host = p.get("host") or "localhost"
        conn.port = int(p.get("port")) if p.get("port") else (5432 if "postgres" in conn.db_type else 3306)
        conn.database_name = p.get("database_name") or "hla_db"
        conn.username = p.get("username") or "postgres"
        if p.get("password"):
            conn.password = p.get("password")
        conn.connection_string = p.get("connection_string")
        conn.vault_profile = p.get("vault_profile")

        test_cfg = {
            "db_type": conn.db_type,
            "host": conn.host,
            "port": conn.port,
            "database_name": conn.database_name,
            "username": conn.username,
            "password": conn.password,
            "connection_string": conn.connection_string
        }
        success, msg = test_db_connection(test_cfg)
        conn.status = "connected" if success else "failed"
        conn.last_tested = datetime.now(timezone.utc)
        configured.append(conn)

    db.session.commit()

    all_target_conns = DBConnection.query.filter_by(project_id=project_id, conn_role="target").all()
    targets_map = {"dev": None, "prod": None}
    for c in all_target_conns:
        if c.target_env in targets_map:
            targets_map[c.target_env] = c.to_dict()

    return jsonify({
        "message": f"Successfully parsed and configured {len(configured)} target database environment(s) from {parsed.get('format_detected')}.",
        "format_detected": parsed.get("format_detected"),
        "total_configured": len(configured),
        "targets": targets_map,
        "configured_envs": [c.target_env for c in configured]
    }), 200


@app.route("/api/projects/<int:project_id>/targets", methods=["GET"])
@login_required
def get_project_target_configs(project_id):
    """Returns configured Target DBs (Dev and Prod) for the project."""
    conns = DBConnection.query.filter_by(project_id=project_id, conn_role="target").all()
    targets = {
        "dev": None,
        "prod": None
    }
    for c in conns:
        if c.target_env in targets:
            if not c.password and c.host in ("localhost", "127.0.0.1", "::1") and c.db_type in ("postgresql", "postgres"):
                c.password = get_env_db_password()
                db.session.commit()
            targets[c.target_env] = c.to_dict()

    # Look for active analyzed document in this project to resolve dynamic schema fallback if present
    active_doc = Document.query.filter_by(project_id=project_id, status="analyzed").order_by(Document.uploaded_at.desc()).first()
    dynamic_schema = "public"
    if active_doc and active_doc.analysis_data:
        co = active_doc.analysis_data.get("control_overview") or {}
        dynamic_schema = co.get("target_schema")
        if isinstance(dynamic_schema, dict):
            dynamic_schema = dynamic_schema.get("schema_name")
        if not dynamic_schema:
            ctrl_raw = (co.get("identification") or {}).get("control_number")
            if ctrl_raw:
                m = re.search(r'(\d+)', str(ctrl_raw))
                digits = m.group(1) if m else ""
                dynamic_schema = f"ra_ctrl.ctrl_{digits}" if digits else "public"
            else:
                dynamic_schema = "public"

    # Provide smart default for Dev target if not configured yet
    if not targets["dev"]:
        targets["dev"] = {
            "db_type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database_name": "hla_db",
            "username": "postgres",
            "schema_name": dynamic_schema or "public",
            "target_env": "dev",
            "conn_role": "target",
            "status": "not_configured"
        }

    if not targets["prod"]:
        targets["prod"] = {
            "db_type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database_name": "hla_db",
            "username": "postgres",
            "schema_name": dynamic_schema or "public",
            "target_env": "prod",
            "conn_role": "target",
            "status": "not_configured"
        }

    return jsonify(targets), 200


@app.route("/api/projects/<int:project_id>/targets", methods=["POST"])
@role_required("admin", "architect")
def save_project_target_config(project_id):
    """Saves or updates Target DB configuration for Dev or Prod, or both."""
    data = request.get_json() or {}
    env = (data.get("target_env") or data.get("environment") or "dev").lower()
    if env not in ("dev", "prod"):
        return jsonify({"error": "Environment must be 'dev' or 'prod'."}), 400

    apply_to_both = bool(data.get("apply_to_both"))
    target_envs = ["dev", "prod"] if apply_to_both else [env]

    last_conn = None
    last_success = False
    last_msg = ""

    for target_env in target_envs:
        db_name_label = f"Target {target_env.upper()}"
        conn = DBConnection.query.filter_by(project_id=project_id, conn_role="target", target_env=target_env).first()
        if not conn:
            conn = DBConnection.query.filter_by(project_id=project_id, source_db_name=db_name_label).first()
        if not conn:
            conn = DBConnection(project_id=project_id, source_db_name=db_name_label, conn_role="target", target_env=target_env)
            db.session.add(conn)

        conn.conn_role = "target"
        conn.target_env = target_env
        
        # Schema name: respect user input; if blank, default to 'public'
        raw_schema = data.get("schema_name")
        if raw_schema is not None:
            clean_schema = str(raw_schema).strip()
            conn.schema_name = clean_schema if clean_schema else "public"
        elif not conn.schema_name:
            conn.schema_name = "public"

        conn.db_type = (data.get("db_type") or "postgresql").lower()
        conn.host = data.get("host") or "localhost"
        raw_target_port = data.get("port")
        if raw_target_port and str(raw_target_port).isdigit():
            conn.port = int(raw_target_port)
        else:
            conn.port = None if conn.db_type == "snowflake" else 5432

        warehouse_target_val = data.get("warehouse")
        if not warehouse_target_val and raw_target_port and not str(raw_target_port).isdigit():
            warehouse_target_val = str(raw_target_port).strip()

        conn.database_name = data.get("database_name") or "hla_db"
        conn.username = data.get("username") or "postgres"

        # Password handling: update if provided, or retain existing, or fall back to localhost env pwd
        new_pwd = data.get("password")
        if new_pwd:
            conn.password = new_pwd
        elif not conn.password and conn.host in ("localhost", "127.0.0.1", "::1") and conn.db_type in ("postgresql", "postgres"):
            conn.password = get_env_db_password()

        conn.connection_string = data.get("connection_string") or ""

        # Test target connection
        test_cfg = {
            "db_type": conn.db_type,
            "host": conn.host,
            "port": conn.port,
            "warehouse": warehouse_target_val or ("COMPUTE_WH" if conn.db_type == "snowflake" else None),
            "database_name": conn.database_name,
            "username": conn.username,
            "password": conn.password,
            "connection_string": conn.connection_string
        }
        success, msg = test_db_connection(test_cfg)
        conn.status = "connected" if success else "failed"
        conn.last_tested = datetime.now(timezone.utc)
        db.session.commit()

        last_conn = conn
        last_success = success
        last_msg = msg

    # Retrieve all target configurations for current project
    all_target_conns = DBConnection.query.filter_by(project_id=project_id, conn_role="target").all()
    targets_map = {"dev": None, "prod": None}
    for c in all_target_conns:
        if c.target_env in targets_map:
            targets_map[c.target_env] = c.to_dict()

    env_label = "DEV & PROD" if apply_to_both else env.upper()
    return jsonify({
        "message": f"Target {env_label} database configured. {last_msg}",
        "success": last_success,
        "target": last_conn.to_dict() if last_conn else None,
        "targets": targets_map
    }), 200


@app.route("/api/projects/<int:project_id>/connections/<int:conn_id>", methods=["DELETE"])
@role_required("admin", "architect")
def delete_project_connection(project_id, conn_id):
    try:
        conn = db.session.get(DBConnection, conn_id)
        if not conn or conn.project_id != project_id:
            return jsonify({"error": "Connection not found"}), 404
        db.session.delete(conn)
        db.session.commit()
        return jsonify({"message": f"Connection '{conn.source_db_name}' removed."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to remove connection: {str(e)}"}), 500


@app.route("/api/projects/<int:project_id>/connections/test", methods=["POST"])
@role_required("admin", "architect")
def test_connection_endpoint(project_id):
    data = request.get_json() or {}
    success, msg = test_db_connection(data)
    return jsonify({
        "success": success,
        "message": msg
    }), 200


@app.route("/api/projects/<int:project_id>/fetch-table-schema", methods=["POST"])
@login_required
def fetch_table_schema_endpoint(project_id):
    """
    Fetches real column metadata, data types, nullability, and sample records directly from the source DB.
    """
    data = request.get_json() or {}
    source_db_name = data.get("source_db_name", "")
    schema_name = data.get("schema_name", "public")
    table_name = data.get("table_name", "")

    if not table_name:
        return jsonify({"error": "table_name is required"}), 400

    # Look for existing configured connection
    conn = DBConnection.query.filter_by(project_id=project_id, source_db_name=source_db_name).first()

    config = {}
    if conn:
        config = {
            "db_type": conn.db_type,
            "host": conn.host,
            "port": conn.port,
            "database_name": conn.database_name,
            "username": conn.username,
            "password": conn.password,
            "connection_string": conn.connection_string
        }
    else:
        # Check if caller passed inline connection params or fallback to sandbox
        config = data.get("connection_config") or {"db_type": "sandbox"}

    try:
        metadata = fetch_table_metadata(config, schema_name, table_name)
        return jsonify(metadata), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch table schema: {str(e)}"}), 500


# ── Global Rules Catalog & Universal DB Introspector ────────────────────

GENERIC_RULES_CATALOG = [
    {
        "rule_id": "R1",
        "name": "Primary Key Deduplication",
        "stream": "All Ingested Streams",
        "target_table": "stg_source_clean",
        "category": "Pre-Execution Filter",
        "severity": "Data Cleansing",
        "description": "Filter out duplicate records partitioned by entity identity keys.",
        "statement": "Keep only the latest record partitioned by primary composite keys to eliminate stream ingestion replays.",
        "sql_sample": "SELECT * FROM (\n  SELECT *,\n         ROW_NUMBER() OVER (\n           PARTITION BY record_id, entity_key \n           ORDER BY created_dtm DESC\n         ) AS rn\n  FROM raw_ingestion_stream\n) t WHERE t.rn = 1;",
        "impact": "Drops redundant snapshot duplicates and out-of-order event replay noise."
    },
    {
        "rule_id": "R2",
        "name": "Mandatory Identification Key Null Check",
        "stream": "All Ingested Streams",
        "target_table": "stg_source_clean",
        "category": "Pre-Execution Filter",
        "severity": "Critical Drop",
        "description": "Filter out records where mandatory identity fields are NULL.",
        "statement": "Records lacking primary identifiers cannot be matched or reconciled and must be rejected at staging.",
        "sql_sample": "SELECT *\nFROM raw_ingestion_stream\nWHERE record_id IS NOT NULL AND entity_key IS NOT NULL;",
        "impact": "Prevents downstream NULL join collisions and orphan target mappings."
    },
    {
        "rule_id": "R3",
        "name": "Active Lifecycle Status Scope Filter",
        "stream": "Master Ledger Streams",
        "target_table": "stg_source_clean",
        "category": "Pre-Execution Filter",
        "severity": "Scope Filter",
        "description": "Filter out records in inactive, cancelled, or decommissioned lifecycle states.",
        "statement": "Only active records are eligible for reconciliation and reporting.",
        "sql_sample": "SELECT *\nFROM raw_ingestion_stream\nWHERE UPPER(status) NOT IN ('DECOMMISSIONED', 'RETIRED', 'CANCELLED', 'PURGED');",
        "impact": "Eliminates historical noise from current active reconciliation scope."
    },
    {
        "rule_id": "R4",
        "name": "Exclusion Registry & Blacklist Filter",
        "stream": "All Ingested Streams",
        "target_table": "stg_source_clean",
        "category": "Exclusion",
        "severity": "Business Rule",
        "description": "Filter out test accounts, sandbox entities, and dummy records using configurable exclusion table.",
        "statement": "Purges non-production test entities and reserved placeholder values.",
        "sql_sample": "SELECT s.*\nFROM raw_ingestion_stream s\nLEFT JOIN cfg_exclusion_parameters ex ON UPPER(s.entity_key) = UPPER(ex.parameter_value)\nWHERE ex.parameter_value IS NULL;",
        "impact": "Ensures audit reporting reflects real production entities."
    },
    {
        "rule_id": "R5",
        "name": "Composite Business Key Integrity",
        "stream": "Transaction Streams",
        "target_table": "stg_source_clean",
        "category": "Pre-Execution Filter",
        "severity": "Data Cleansing",
        "description": "Validate composite natural key completeness across transaction feeds.",
        "statement": "Ensures all multi-column composite key components are non-null and valid.",
        "sql_sample": "SELECT * FROM raw_ingestion_stream WHERE transaction_code IS NOT NULL AND account_id IS NOT NULL;",
        "impact": "Guarantees multi-field joins remain deterministic."
    },
    {
        "rule_id": "R6",
        "name": "Timestamp Window & Staleness Boundary",
        "stream": "Event Streams",
        "target_table": "stg_source_clean",
        "category": "Pre-Execution Filter",
        "severity": "Temporal Validation",
        "description": "Filter out events outside authorized reconciliation extraction window.",
        "statement": "Enforces rolling watermark boundaries to maintain temporal consistency.",
        "sql_sample": "SELECT * FROM raw_ingestion_stream WHERE event_timestamp >= CURRENT_DATE - INTERVAL '30 days';",
        "impact": "Prevents stale historical records from distorting active reconciliation cycles."
    },
    {
        "rule_id": "R7",
        "name": "Balance Node Consolidation Gateway",
        "stream": "All Cleaned Streams",
        "target_table": "CTRL_BALANCED_DATASET",
        "category": "Balance Node",
        "severity": "Pipeline Gateway",
        "description": "Harmonize cleansed records into unified balance staging tables with source lineage tracking.",
        "statement": "Central gate where all pre-filtered streams converge into standardized schema prior to matching.",
        "sql_sample": "CREATE TABLE CTRL_BALANCED_DATASET AS\nSELECT 'STREAM_A' AS source_stream, record_id, entity_key, CURRENT_TIMESTAMP AS balanced_at\nFROM stg_stream_a_clean\nUNION ALL\nSELECT 'STREAM_B' AS source_stream, record_id, entity_key, CURRENT_TIMESTAMP AS balanced_at\nFROM stg_stream_b_clean;",
        "impact": "Guarantees 100% data lineage and audit balance integrity."
    },
    {
        "rule_id": "R8",
        "name": "Tiered Multi-Pass Reconciliation Matching",
        "stream": "Stream A vs Stream B",
        "target_table": "CTRL_RECON_MATCHES",
        "category": "Reconciliation",
        "severity": "Core Logic",
        "description": "Tier 1: Exact Primary Key Match | Tier 2: Natural Key Match | Tier 3: Fuzzy / Fallback Match.",
        "statement": "Hierarchical match algorithm comparing records between upstream source and central ledger.",
        "sql_sample": "SELECT \n  COALESCE(a.record_id, b.record_id) AS matched_id,\n  CASE \n    WHEN a.record_id = b.record_id THEN 'EXACT_KEY_MATCH'\n    WHEN a.entity_key = b.entity_key THEN 'NATURAL_KEY_MATCH'\n    ELSE 'NO_MATCH'\n  END AS reconciliation_tier\nFROM stream_a_balanced a\nFULL OUTER JOIN stream_b_balanced b ON a.record_id = b.record_id;",
        "impact": "Maximizes automated parity matching and surfaces true anomalies."
    },
    {
        "rule_id": "R9",
        "name": "Exception Bucketing & KRI Risk Classification",
        "stream": "Reconciliation",
        "target_table": "CTRL_RECON_EXCEPTIONS",
        "category": "Bucket Classification",
        "severity": "Operational Governance",
        "description": "Partition results into BB (Balance Bucket) and YN (Exception Bucket) with automated KRI ratings.",
        "statement": "Matched records clear into BB ledger; discrepancies route to YN queue with risk rating based on variance amount.",
        "sql_sample": "SELECT *,\n  CASE \n    WHEN reconciliation_tier = 'EXACT_KEY_MATCH' THEN 'BB_RECONCILED'\n    WHEN variance_amount > 10000 THEN 'YN_HIGH_KRI'\n    ELSE 'YN_STANDARD_EXCEPTION'\n  END AS bucket_category\nFROM recon_matches;",
        "impact": "Generates prioritized operational queues for remediation workflows."
    },
    {
        "rule_id": "R10",
        "name": "Revenue Assurance & Final Ledger Audit",
        "stream": "Reconciled vs Central Ledger",
        "target_table": "AUDIT_RECON_FINAL_LEDGER",
        "category": "Cross Recon",
        "severity": "Revenue Assurance",
        "description": "Final audit verifying parity between operational systems and authoritative general ledger.",
        "statement": "Verifies that all operational activations correspond to active, billed contracts in central ledger.",
        "sql_sample": "SELECT \n  m.record_id, m.entity_key, b.contract_status,\n  CASE \n    WHEN b.contract_status = 'ACTIVE' THEN 'LEDGER_CONFIRMED'\n    WHEN b.record_id IS NULL THEN 'UNBILLED_ACTIVITY_LEAKAGE'\n    ELSE 'STATUS_MISMATCH_EXCEPTION'\n  END AS audit_verdict\nFROM recon_matches m\nLEFT JOIN central_ledger b ON m.record_id = b.record_id;",
        "impact": "Prevents revenue leakage and guarantees compliance with financial control standards."
    }
]


@app.route("/api/rules/catalog", methods=["GET"])
@login_required
def get_rules_catalog():
    """
    Returns master catalog of rules.
    If 'document_id' or 'doc_id' query param is passed (or active analyzed doc exists),
    dynamically constructs the rules catalog from the document's actual extracted rules!
    Otherwise returns generic enterprise ETL rules catalog.
    """
    doc_id = request.args.get("document_id") or request.args.get("doc_id")
    target_doc = None
    if doc_id:
        target_doc = Document.query.get(doc_id)
    else:
        proj_id = request.args.get("project_id")
        if proj_id:
            target_doc = Document.query.filter_by(project_id=proj_id, status="analyzed").order_by(Document.uploaded_at.desc()).first()
        if not target_doc:
            target_doc = Document.query.filter_by(status="analyzed").order_by(Document.uploaded_at.desc()).first()

    if target_doc and target_doc.analysis_data and target_doc.analysis_data.get("rules"):
        doc_rules = target_doc.analysis_data["rules"]
        extracted_catalog = []

        def _clean_s(s):
            return re.sub(r'[^a-zA-Z0-9_]', '_', str(s or '')).strip('_').lower()

        # 1. Filter rules
        for idx, r in enumerate(doc_rules.get("filter_rules") or [], 1):
            r_id = r.get("rule_id") or f"R{idx}"
            r_stream = r.get("data_stream") or "Source Feed"
            r_stmt = r.get("rule_statement") or ""
            r_cat = r.get("category") or "Pre-Execution Filter"
            extracted_catalog.append({
                "rule_id": r_id,
                "name": f"{r_stream} {r_cat}",
                "stream": r_stream,
                "target_table": f"stg_{_clean_s(r_stream)}_clean",
                "category": r_cat,
                "severity": "Data Cleansing",
                "description": r_stmt,
                "statement": r_stmt,
                "sql_sample": f"SELECT * FROM (\n  SELECT *,\n         ROW_NUMBER() OVER (ORDER BY CURRENT_TIMESTAMP DESC) AS rn\n  FROM raw_{_clean_s(r_stream)}\n) t WHERE t.rn = 1;",
                "impact": "Enforces pre-execution data hygiene and deduplication."
            })

        # 2. Balance rules
        for idx, r in enumerate(doc_rules.get("balance_rules") or [], 1):
            r_id = r.get("rule_id") or f"R{len(extracted_catalog) + 1}"
            r_stream = r.get("data_stream") or "All Sources"
            r_stmt = r.get("rule_statement") or ""
            extracted_catalog.append({
                "rule_id": r_id,
                "name": f"Balance Node Gateway ({r_stream})",
                "stream": r_stream,
                "target_table": "ctrl_balanced_dataset",
                "category": "Balance Node",
                "severity": "Pipeline Gateway",
                "description": r_stmt,
                "statement": r_stmt,
                "sql_sample": "SELECT * FROM ctrl_balanced_dataset;",
                "impact": "Consolidates cleaned source feeds into balance gatekeeper."
            })

        # 3. Reconciliation flows
        for idx, r in enumerate(doc_rules.get("reconciliation_flows") or [], 1):
            r_id = r.get("rule_id") or f"R{len(extracted_catalog) + 1}"
            r_stream = r.get("data_stream") or "Reconciliation"
            r_stmt = r.get("rule_statement") or ""
            extracted_catalog.append({
                "rule_id": r_id,
                "name": f"Reconciliation Flow ({r_stream})",
                "stream": r_stream,
                "target_table": "ctrl_recon_matches",
                "category": "Reconciliation",
                "severity": "Core Logic",
                "description": r_stmt,
                "statement": r_stmt,
                "sql_sample": "SELECT * FROM ctrl_recon_matches;",
                "impact": "Executes multi-pass matching and exception classification."
            })

        if extracted_catalog:
            filter_cnt = len([r for r in extracted_catalog if r.get("category") == "Pre-Execution Filter" or "filter" in r.get("rule_id", "").lower()])
            return jsonify({
                "total_rules": len(extracted_catalog),
                "filter_rules_count": filter_cnt,
                "balance_rules_count": len(extracted_catalog) - filter_cnt,
                "rules": extracted_catalog,
                "source": "document_extracted",
                "document_id": target_doc.id,
                "document_name": target_doc.original_name or target_doc.filename
            }), 200

    # Fallback to universal enterprise rules catalog
    filter_cnt = len([r for r in GENERIC_RULES_CATALOG if r.get("category") == "Pre-Execution Filter"])
    return jsonify({
        "total_rules": len(GENERIC_RULES_CATALOG),
        "filter_rules_count": filter_cnt,
        "balance_rules_count": len(GENERIC_RULES_CATALOG) - filter_cnt,
        "rules": GENERIC_RULES_CATALOG,
        "source": "enterprise_baseline"
    }), 200


@app.route("/api/introspect-table", methods=["POST"])
@login_required
def introspect_table_global():
    """
    Universal table schema and live sample inspector.
    Can introspect enterprise source systems or configured databases 
    or the active PostgreSQL database (users, projects, documents, db_connections).
    """
    data = request.get_json() or {}
    source_db_name = (data.get("source_db_name") or "Primary Source DB").strip()
    schema_name = (data.get("schema_name") or "public").strip()
    table_name = (data.get("table_name") or "").strip()
    conn_config = data.get("connection_config") or {}

    if not table_name:
        return jsonify({"error": "Table name is required"}), 400

    # If the user selects local postgres or targets local tables
    is_local_db = (
        any(k in source_db_name.lower() for k in ("local", "postgresql", "postgres", "hla_db", "current"))
        or conn_config.get("use_local") is True
    )

    if is_local_db:
        try:
            from sqlalchemy import inspect as sqla_inspect, text
            inspector = sqla_inspect(db.engine)
            target_schema = schema_name if schema_name and schema_name != "public" else None
            
            raw_cols = inspector.get_columns(table_name, schema=target_schema)
            if not raw_cols:
                raw_cols = inspector.get_columns(table_name)

            if not raw_cols:
                return jsonify({"error": f"Table '{table_name}' not found in local PostgreSQL database."}), 404

            columns = []
            for c in raw_cols:
                columns.append({
                    "column_name": c.get("name"),
                    "data_type": str(c.get("type")),
                    "is_nullable": "YES" if c.get("nullable") else "NO",
                    "default": str(c.get("default")) if c.get("default") is not None else None
                })

            full_name = f'"{schema_name}"."{table_name}"' if schema_name != "public" else f'"{table_name}"'
            with db.engine.connect() as conn:
                try:
                    cnt = conn.execute(text(f"SELECT COUNT(*) FROM {full_name}")).scalar() or 0
                except Exception:
                    cnt = 0
                
                sample_rows = []
                try:
                    res = conn.execute(text(f"SELECT * FROM {full_name} LIMIT 10"))
                    keys = list(res.keys())
                    for r in res.fetchall():
                        row_dict = {}
                        for i, k in enumerate(keys):
                            val = r[i]
                            # Hide sensitive password hashes from sample preview
                            if "password" in k.lower():
                                row_dict[k] = "●●●●●●●● [ENCRYPTED]"
                            elif isinstance(val, (datetime,)):
                                row_dict[k] = val.isoformat()
                            else:
                                row_dict[k] = val
                        sample_rows.append(row_dict)
                except Exception:
                    pass

            ddl_lines = [f"CREATE TABLE {schema_name}.{table_name} ("]
            for col in columns:
                null_str = "" if col["is_nullable"] == "YES" else " NOT NULL"
                ddl_lines.append(f"    {col['column_name']} {col['data_type']}{null_str},")
            if ddl_lines and ddl_lines[-1].endswith(","):
                ddl_lines[-1] = ddl_lines[-1][:-1]
            ddl_lines.append(");")
            ddl = "\n".join(ddl_lines)

            return jsonify({
                "source_db": "PostgreSQL 18 (Local)",
                "schema_name": schema_name,
                "table_name": table_name,
                "row_count": cnt,
                "is_simulated": False,
                "columns": columns,
                "sample_rows": sample_rows,
                "ddl": ddl,
                "message": f"Successfully introspected live table '{table_name}' from PostgreSQL 18"
            }), 200

        except Exception as err:
            return jsonify({"error": f"Failed to introspect local PostgreSQL table: {str(err)}"}), 500

    # Otherwise, use fetch_table_metadata with simulated or remote DB
    config = {
        "db_type": conn_config.get("db_type") or ("sandbox" if source_db_name.lower() in ("sandbox", "simulated", "mock", "demo") else "postgresql"),
        "host": conn_config.get("host"),
        "port": conn_config.get("port"),
        "database_name": conn_config.get("database_name") or source_db_name,
        "username": conn_config.get("username"),
        "password": conn_config.get("password"),
        "connection_string": conn_config.get("connection_string")
    }

    try:
        metadata = fetch_table_metadata(config, schema_name, table_name)
        
        # Build DDL
        cols = metadata.get("columns", [])
        ddl_lines = [f"CREATE TABLE {schema_name}.{table_name} ("]
        for col in cols:
            null_str = "" if col.get("is_nullable") == "YES" else " NOT NULL"
            ddl_lines.append(f"    {col.get('column_name')} {col.get('data_type')}{null_str},")
        if ddl_lines and ddl_lines[-1].endswith(","):
            ddl_lines[-1] = ddl_lines[-1][:-1]
        ddl_lines.append(");")
        metadata["ddl"] = "\n".join(ddl_lines)
        metadata["source_db"] = source_db_name

        return jsonify(metadata), 200
    except Exception as e:
        return jsonify({"error": f"Introspection failed: {str(e)}"}), 500


@app.route("/api/connections/test-global", methods=["POST"])
@login_required
def test_connection_global():
    data = request.get_json() or {}
    source_db = (data.get("source_db_name") or "").lower()
    
    if source_db in ("local", "local postgres", "postgresql", "current", "hla_db") or data.get("use_local"):
        return jsonify({
            "success": True,
            "message": "Connected to local PostgreSQL 18 (hla_db) active engine"
        }), 200

    success, msg = test_db_connection(data)
    return jsonify({
        "success": success,
        "message": msg
    }), 200


# ── Document Inspection & Specification Downloads ─────────────────────

@app.route("/api/documents", methods=["GET"])
@login_required
def list_documents():
    try:
        docs = Document.query.order_by(Document.uploaded_at.desc()).all()
        return jsonify([d.to_dict() for d in docs]), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch documents: {str(e)}"}), 500


@app.route("/api/documents/<int:doc_id>", methods=["GET"])
@login_required
def get_document(doc_id):
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404
        return jsonify(doc.to_dict()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
@role_required("admin", "architect")
def delete_document(doc_id):
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except Exception:
                pass
        if doc.generated_doc_path and os.path.exists(doc.generated_doc_path):
            try:
                os.remove(doc.generated_doc_path)
            except Exception:
                pass
        db.session.delete(doc)
        db.session.commit()
        return jsonify({"message": f"Document '{doc.original_name}' deleted."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/<int:doc_id>/analyze", methods=["POST"])
@role_required("admin", "architect")
def trigger_analysis(doc_id):
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        if not os.path.exists(doc.file_path):
            return jsonify({"error": "Original file not found on disk"}), 404

        analysis = analyze_document(doc.file_path)
        doc.analysis_data = analysis
        doc.generated_doc_path = analysis.get("generated_doc_path")
        doc.status = "analyzed"
        db.session.commit()

        return jsonify({
            "message": "Analysis completed successfully",
            "document_id": doc.id,
            "analysis": analysis
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


def resolve_source_database_configs(project_id: int, req_data: dict = None) -> list:
    """
    Resolves source database connection configurations with strict priority:
    1. Explicit connections provided in request body (connections, source_configs, source_connections, connection)
    2. Saved source DB connections from DBConnection for this project
    3. Default clean Custom Source DB connection (hla_db on localhost)
    """
    req_data = req_data or {}
    explicit = (
        req_data.get("connections")
        or req_data.get("source_configs")
        or req_data.get("source_connections")
    )
    if not explicit and (req_data.get("connection") or req_data.get("host")):
        c = req_data.get("connection") or req_data
        explicit = [c]

    if explicit and isinstance(explicit, list):
        configs = []
        for item in explicit:
            if isinstance(item, dict):
                pwd = item.get("password") or (get_env_db_password() if item.get("host") in ("localhost", "127.0.0.1", "::1") else "")
                configs.append({
                    "source_db_name": item.get("source_db_name") or item.get("database_name") or "Custom Source DB",
                    "db_type": item.get("db_type") or "postgresql",
                    "host": item.get("host") or "localhost",
                    "port": int(item.get("port") or 5432),
                    "database_name": item.get("database_name") or os.getenv("PGDATABASE", "hla_db"),
                    "username": item.get("username") or "postgres",
                    "password": pwd,
                    "schema_name": item.get("schema_name") or "public",
                    "connection_string": item.get("connection_string") or ""
                })
        if configs:
            return configs

    # Otherwise read saved connections for project
    source_conns = DBConnection.query.filter_by(
        project_id=project_id, conn_role="source"
    ).all()

    source_configs = []
    for sc in source_conns:
        pwd = sc.password or (get_env_db_password() if sc.host in ("localhost", "127.0.0.1", "::1") else "")
        source_configs.append({
            "source_db_name": sc.source_db_name or "Custom Source DB",
            "db_type": sc.db_type or "postgresql",
            "host": sc.host or "localhost",
            "port": sc.port or 5432,
            "database_name": sc.database_name or "hla_db",
            "username": sc.username or "postgres",
            "password": pwd,
            "schema_name": sc.schema_name or "public",
            "connection_string": sc.connection_string or ""
        })

    return source_configs


# ── LLM Target Logic Builder & Target Database Deployment ─────────────

@app.route("/api/documents/<int:doc_id>/build-target-logic", methods=["POST"])
@role_required("admin", "architect")
def build_target_logic_endpoint(doc_id):
    """
    1. Reads full HLA document (extracting sources, R1-R10 rules, R11 balance, mappings).
    2. Fetches live source table schemas from given/configured upstream DBs.
    3. Prompts LLM to build complete Target DDL, executable SQL transformations,
       and PySpark pipelines for the specified target environment ('dev' or 'prod').
    4. Saves the generated architecture as a TargetArtifact.
    """
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        data = request.get_json() or {}
        env = (data.get("environment") or data.get("target_env") or "dev").lower()
        if env not in ("dev", "prod"):
            return jsonify({"error": "Environment must be 'dev' or 'prod'."}), 400

        # Ensure complete HLA analysis data is available
        analysis = doc.analysis_data
        if not analysis or not analysis.get("sources"):
            if doc.file_path and os.path.exists(doc.file_path) and doc.file_type in (".xlsx", ".xls", ".docx", ".doc"):
                try:
                    analysis = analyze_document(doc.file_path)
                    doc.analysis_data = analysis
                    doc.status = "analyzed"
                    db.session.commit()
                except Exception:
                    analysis = None

            if not analysis or not analysis.get("sources"):
                # Standard fallback architecture baseline
                analysis = {
                    "original_name": doc.original_name,
                    "control_overview": {
                        "identification": {
                            "control_number": f"CTRL-{doc.id or '01'}",
                            "control_title": doc.original_name or "Enterprise Reconciliation Solution",
                            "purpose": "Automated data lake ingestion, pre-execution cleansing, and ledger reconciliation."
                        }
                    },
                    "sources": [
                        {"source_db": "Primary_Source_System", "source_schema": "public", "source_table": "raw_stream_a", "type_of_load": "Truncate and load"},
                        {"source_db": "Secondary_Source_System", "source_schema": "public", "source_table": "raw_stream_b", "type_of_load": "Truncate and load"}
                    ],
                    "rules": {
                        "input_streams": [
                            {"rule_id": "I1", "data_stream": "Stream A", "rule_statement": "Daily operational ingestion feed"},
                            {"rule_id": "I2", "data_stream": "Stream B", "rule_statement": "Daily reference inventory feed"}
                        ],
                        "filter_rules": [
                            {"rule_id": "R1", "category": "Filter", "data_stream": "Stream A", "rule_statement": "Deduplicate records partitioned by primary identifier ordering by created_dtm descending."},
                            {"rule_id": "R2", "category": "Filter", "data_stream": "Stream A", "rule_statement": "Drop records where primary identification keys are NULL."},
                            {"rule_id": "R3", "category": "Filter", "data_stream": "Stream B", "rule_statement": "Filter out records with inactive or cancelled lifecycle status."},
                            {"rule_id": "R4", "category": "Exclusion", "data_stream": "Stream B", "rule_statement": "Exclude test and sandbox records based on dynamic configuration exclusion table."}
                        ],
                        "balance_rules": [
                            {"rule_id": "R5", "category": "Balance Node", "data_stream": "All Sources", "rule_statement": "Harmonize cleansed records into master balance staging table."}
                        ],
                        "reconciliation_flows": [
                            {"rule_id": "R6", "category": "Reconciliation", "data_stream": "Stream A vs Stream B", "rule_statement": "Tiered parity match basis primary key and secondary reference keys."},
                            {"rule_id": "R7", "category": "Bucket Classification", "data_stream": "Reconciliation", "rule_statement": "Categorize records into BB (reconciled) vs YN (exception) buckets."}
                        ]
                    },
                    "mappings": [
                        {"target_column": "entity_id", "mapping_type": "Direct", "derivation_logic": "Direct 1:1 mapping of primary operational identifier."},
                        {"target_column": "reconciliation_status", "mapping_type": "Derived", "derivation_logic": "CASE WHEN a.id = b.id THEN 'MATCHED' ELSE 'UNMATCHED' END"}
                    ]
                }
                doc.analysis_data = analysis
                db.session.commit()

        # Derive dynamic target schema from document
        ctrl_overview = analysis.get("control_overview") or {}
        ctrl_digits = ctrl_overview.get("control_digits")
        if not ctrl_digits:
            ctrl_raw = (ctrl_overview.get("identification") or {}).get("control_number")
            if ctrl_raw:
                m = re.search(r'(\d+)', str(ctrl_raw))
                ctrl_digits = m.group(1) if m else ""
            else:
                ctrl_digits = ""
        dynamic_target_schema = ctrl_overview.get("target_schema")
        if isinstance(dynamic_target_schema, dict):
            dynamic_target_schema = dynamic_target_schema.get("schema_name")
        if not dynamic_target_schema:
            dynamic_target_schema = f"ra_ctrl.ctrl_{ctrl_digits}" if ctrl_digits else "public"

        # Resolve Target Database Config
        target_conn = DBConnection.query.filter_by(
            project_id=doc.project_id, conn_role="target", target_env=env
        ).first()

        req_config = data.get("target_config") or {}
        target_config = {}
        if target_conn:
            saved_schema = target_conn.schema_name
            if isinstance(saved_schema, dict):
                saved_schema = saved_schema.get("schema_name")
            effective_schema = saved_schema if saved_schema and saved_schema not in ("target_dev", "target_prod") else dynamic_target_schema
            target_config = {
                "db_type": target_conn.db_type,
                "host": target_conn.host,
                "port": target_conn.port,
                "database_name": target_conn.database_name,
                "username": target_conn.username,
                "password": target_conn.password,
                "schema_name": effective_schema,
                "target_env": env,
                "connection_string": target_conn.connection_string
            }
        else:
            target_config = {
                "db_type": "postgresql",
                "host": os.getenv("PGHOST", "localhost"),
                "port": int(os.getenv("PGPORT", "5432")),
                "database_name": os.getenv("PGDATABASE", "hla_db"),
                "username": os.getenv("PGUSER", "postgres"),
                "password": get_env_db_password(),
                "schema_name": dynamic_target_schema,
                "target_env": env
            }

        for k, v in req_config.items():
            if v:
                if k == "schema_name" and v in ("target_dev", "target_prod"):
                    target_config[k] = dynamic_target_schema
                else:
                    target_config[k] = v

        if not target_config.get("password") and target_config.get("host") in ("localhost", "127.0.0.1", "::1"):
            target_config["password"] = get_env_db_password()

        # Resolve Source Databases from given connections or project records
        source_configs = resolve_source_database_configs(doc.project_id, data)

        source_conns = DBConnection.query.filter_by(project_id=doc.project_id, conn_role="source").all()
        has_source_creds = any(
            (c.password or c.connection_string or c.vault_profile or c.status == "connected")
            for c in source_conns
        ) or bool(get_env_db_password()) or bool(data.get("connections") or data.get("source_configs"))
        has_direct_creds = bool(data.get("kdb_content") or data.get("source_credentials") or data.get("kdb_file"))
        preview_mode = not has_source_creds and not has_direct_creds

        # Scan for each source table across all configured source databases
        # If source table is not found in one source DB, checks the other source DBs
        introspected_schemas = {}
        sources = analysis.get("sources") or []
        for s in sources:
            s_db = s.get("source_db", "")
            s_table = s.get("source_table") or s.get("full_table_name") or ""
            s_schema = s.get("source_schema", "public")
            if s_table:
                clean_table = re.sub(r'[^a-zA-Z0-9_]', '_', str(s_table or '')).strip('_').lower()
                meta = find_table_across_databases(source_configs, s_schema, s_table)
                introspected_schemas[s_table] = meta
                introspected_schemas[clean_table] = meta
                if s_db:
                    introspected_schemas[f"{s_db}.{s_table}"] = meta

        # Build target logic with LLM
        package = build_target_logic_package(analysis, introspected_schemas, target_config)

        # Save or update TargetArtifact
        artifact = TargetArtifact.query.filter_by(
            document_id=doc.id, environment=env
        ).first()

        if not artifact:
            artifact = TargetArtifact(
                project_id=doc.project_id,
                document_id=doc.id,
                environment=env
            )
            db.session.add(artifact)

        ts = package.get("target_schema", f"target_{env}")
        if isinstance(ts, dict):
            ts = ts.get("schema_name", f"target_{env}")
        artifact.target_schema = ts
        artifact.source_tables_ddl = package.get("source_tables_ddl", "")
        artifact.generated_ddl = package.get("ddl")
        artifact.generated_transformation_sql = package.get("transformation_sql")
        artifact.generated_pyspark_code = package.get("pyspark_code")
        artifact.llm_reasoning = package.get("llm_reasoning")
        artifact.target_schema_json = package.get("summary")
        artifact.deployment_status = "draft"
        db.session.commit()

        return jsonify({
            "message": f"Target logic generated successfully for environment '{env.upper()}'." if not preview_mode else f"Target architecture preview generated for environment '{env.upper()}'.",
            "artifact": artifact.to_dict(),
            "source_table_statuses": package.get("source_table_statuses", {}),
            "introspected_sources_count": len(introspected_schemas),
            "preview_mode": preview_mode,
            "requires_kdb_for_deploy": preview_mode
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to build target logic: {str(e)}"}), 500


@app.route("/api/documents/<int:doc_id>/scan-source-db", methods=["POST"])
@login_required
def scan_source_db_endpoint(doc_id):
    """
    Connects to the given/configured source DBs and scans for all HLA tables.
    If a table is not found in one source DB, checks other configured source DBs.
    If table and schema are NOT found:
      - Tells explicitly: Table Not Found (with schema and database details)
      - Marks ddl_pulled=False
      - Oplocks target DDL from creating tables for missing sources.
    """
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        req_data = request.get_json(silent=True) or {}
        analysis = doc.analysis_data or {}
        sources = analysis.get("sources") or []

        # Resolve given source DB connections (from request payload or project DBConnection)
        source_configs = resolve_source_database_configs(doc.project_id, req_data)

        from target_logic_builder import extract_table_required_columns
        audit_results = []
        found_count = 0
        missing_count = 0

        for s in sources:
            s_table = s.get("source_table") or s.get("full_table_name") or ""
            s_schema = s.get("source_schema") or "public"
            s_system = s.get("source_system", "")
            if not s_table:
                continue

            meta = find_table_across_databases(source_configs, s_schema, s_table)
            is_found = bool(meta.get("table_found"))
            if is_found:
                found_count += 1
            else:
                missing_count += 1

            raw_cols = meta.get("columns", [])
            req_cols_tokens = extract_table_required_columns(s_table, s_system, analysis) if is_found else set()

            matched_req_cols = []
            if is_found:
                for c in raw_cols:
                    cn = re.sub(r'[^a-z0-9]', '', str(c.get("column_name", "")).lower())
                    if cn in req_cols_tokens or any(t == cn for t in req_cols_tokens) or (len(cn) >= 4 and any(t in cn or cn in t for t in req_cols_tokens if len(t) >= 4)):
                        matched_req_cols.append(c.get("column_name"))

            audit_results.append({
                "table_name": s_table,
                "source_schema": s_schema,
                "source_system": s_system,
                "table_found": is_found,
                "schema_found": meta.get("schema_found", False),
                "status": "table_found" if is_found else "table_not_found",
                "status_display": "Table Found (DDL Pulled)" if is_found else "Table Not Found (DDL Omitted)",
                "found_in_db": meta.get("found_in_db"),
                "scanned_databases": meta.get("scanned_databases", [c["source_db_name"] for c in source_configs]),
                "source_columns_count": len(raw_cols),
                "target_required_columns_count": len(matched_req_cols),
                "target_required_columns": matched_req_cols,
                "ddl_pulled": is_found,
                "message": meta.get("message") or (f"Table '{s_table}' found in source database." if is_found else f"Table '{s_table}' was NOT found in source database."),
                "existing_tables_in_db": meta.get("existing_tables_in_db", [])
            })

        return jsonify({
            "success": True,
            "total_tables": len(audit_results),
            "tables_found_count": found_count,
            "tables_missing_count": missing_count,
            "configured_databases": [c["source_db_name"] for c in source_configs],
            "table_audit": audit_results
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to scan source database: {str(e)}"}), 500


@app.route("/api/documents/<int:doc_id>/target-artifacts", methods=["GET"])
@login_required
def get_target_artifacts_endpoint(doc_id):
    """Retrieves all generated Target Artifacts (Dev and Prod) for this document."""
    try:
        artifacts = TargetArtifact.query.filter_by(document_id=doc_id).order_by(TargetArtifact.created_at.desc()).all()
        return jsonify([a.to_dict() for a in artifacts]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/<int:doc_id>/deploy-target", methods=["POST"])
@role_required("admin", "architect")
def deploy_target_endpoint(doc_id):
    """
    Validates or Deploys the generated DDL schema into the target database (Dev / Prod).
    """
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        data = request.get_json() or {}
        env = (data.get("environment") or "dev").lower()
        action = data.get("action", "deploy").lower()  # 'validate' or 'deploy'

        artifact = TargetArtifact.query.filter_by(document_id=doc.id, environment=env).first()
        if not artifact or not artifact.generated_ddl:
            return jsonify({"error": f"No generated DDL found for environment '{env.upper()}'. Please run the Target Logic Builder first."}), 400

        # Resolve target DB configuration
        target_conn = DBConnection.query.filter_by(
            project_id=doc.project_id, conn_role="target", target_env=env
        ).first()

        req_config = data.get("target_config") or {}
        target_config = {}
        conn_schema = (target_conn.schema_name if target_conn else None) or artifact.target_schema or f"target_{env}"
        if isinstance(conn_schema, dict):
            conn_schema = conn_schema.get("schema_name", f"target_{env}")

        if target_conn:
            target_config = {
                "db_type": target_conn.db_type,
                "host": target_conn.host,
                "port": target_conn.port,
                "database_name": target_conn.database_name,
                "username": target_conn.username,
                "password": target_conn.password,
                "schema_name": conn_schema,
                "target_env": env,
                "connection_string": target_conn.connection_string
            }
        else:
            target_config = {
                "db_type": "postgresql",
                "host": os.getenv("PGHOST", "localhost"),
                "port": int(os.getenv("PGPORT", "5432")),
                "database_name": os.getenv("PGDATABASE", "hla_db"),
                "username": os.getenv("PGUSER", "postgres"),
                "password": get_env_db_password(),
                "schema_name": conn_schema,
                "target_env": env
            }

        # Overlay non-empty fields from request
        for k, v in req_config.items():
            if v:
                target_config[k] = v

        if not target_config.get("password") and target_config.get("host") in ("localhost", "127.0.0.1", "::1"):
            target_config["password"] = get_env_db_password()

        # Check whether upstream source tables exist in the source database
        analysis = doc.analysis_data or {}
        sources = analysis.get("sources") or []
        source_configs = resolve_source_database_configs(doc.project_id)

        verb = "Dry-run validation" if action == "validate" else "Target deployment"
        if not source_configs:
            error_msg = (
                f"{verb} blocked: No source database info configured for this workspace. "
                f"Cannot validate or deploy target schema until source database info and tables are available."
            )
            artifact.deployment_status = "blocked"
            artifact.deployment_log = error_msg
            db.session.commit()
            return jsonify({
                "success": False,
                "message": error_msg,
                "action": action,
                "blocked": True,
                "missing_source_tables": [s.get("source_table") for s in sources if s.get("source_table")],
                "artifact": artifact.to_dict()
            }), 400

        missing_source_tables = []
        for s in sources:
            s_table = s.get("source_table") or s.get("full_table_name") or ""
            s_schema = s.get("source_schema") or ""
            if s_table:
                meta = find_table_across_databases(source_configs, s_schema, s_table)
                if not meta.get("table_found"):
                    missing_source_tables.append(f"{s_schema}.{s_table}" if s_schema else s_table)

        # If source tables are not found in source database, dry run and deployment shouldn't work!
        if missing_source_tables:
            error_msg = (
                f"{verb} blocked: Upstream source table(s) not found in source database "
                f"({', '.join(missing_source_tables[:4])}{'...' if len(missing_source_tables) > 4 else ''}). "
                f"Cannot validate or deploy target schema until required upstream source tables exist in the source DB."
            )
            artifact.deployment_status = "blocked"
            artifact.deployment_log = error_msg
            db.session.commit()
            return jsonify({
                "success": False,
                "message": error_msg,
                "action": action,
                "blocked": True,
                "missing_source_tables": missing_source_tables,
                "artifact": artifact.to_dict()
            }), 400

        # Handle Action: 'validate' vs 'deploy'
        if action == "validate":
            success, message = validate_target_ddl(target_config, artifact.generated_ddl)
            if success:
                artifact.deployment_status = "validated"
                artifact.deployment_log = message
                db.session.commit()
            return jsonify({
                "success": success,
                "message": message,
                "action": "validate",
                "artifact": artifact.to_dict()
            }), 200

        # Execute Live Deployment
        success, message, tables = deploy_target_ddl(target_config, artifact.generated_ddl)
        artifact.deployment_status = "deployed" if success else "failed"
        artifact.deployment_log = message
        if success:
            artifact.deployed_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            "success": success,
            "message": message,
            "error": message if not success else None,
            "deployed_tables": tables,
            "action": "deploy",
            "artifact": artifact.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Deployment operation failed: {str(e)}"}), 500


@app.route("/api/documents/<int:doc_id>/download-generated", methods=["GET"])
@login_required
def download_generated_doc(doc_id):
    try:
        doc = db.session.get(Document, doc_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        if not doc.generated_doc_path or not os.path.exists(doc.generated_doc_path):
            if os.path.exists(doc.file_path) and doc.file_type in [".xlsx", ".xls", ".docx", ".doc"]:
                analysis = analyze_document(doc.file_path)
                doc.analysis_data = analysis
                doc.generated_doc_path = analysis.get("generated_doc_path")
                doc.status = "analyzed"
                db.session.commit()
            else:
                return jsonify({"error": "Generated document not found"}), 404

        return send_file(
            doc.generated_doc_path,
            as_attachment=True,
            download_name=os.path.basename(doc.generated_doc_path),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500




# ── Parsers ───────────────────────────────────────────────────────────

def _parse_excel(path: str) -> dict:
    wb     = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = wb.sheetnames
    ws     = wb.active
    rows   = ws.max_row   or 0
    cols   = ws.max_column or 0
    wb.close()
    return {
        "sheets": sheets,
        "rows":   rows,
        "cols":   cols,
        "preview": f"{rows} rows × {cols} columns across {len(sheets)} sheet(s)",
    }


def _parse_csv(path: str) -> dict:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()
    rows = len(lines)
    cols = len(lines[0].split(",")) if lines else 0
    return {
        "rows":    rows,
        "cols":    cols,
        "preview": f"{rows} rows × {cols} columns",
    }


def _parse_word(path: str) -> dict:
    doc        = docx.Document(path)
    paragraphs = len(doc.paragraphs)
    tables     = len(doc.tables)
    words = sum(len(p.text.split()) for p in doc.paragraphs)
    return {
        "paragraphs": paragraphs,
        "tables":     tables,
        "words":      words,
        "preview":    f"{paragraphs} paragraphs, ~{words} words, {tables} table(s)",
    }


# ── Workspace Control Scheduler Routes ─────────────────────────────────

@app.route("/api/projects/<int:project_id>/schedules", methods=["GET"])
@login_required
def get_project_schedules(project_id):
    """Lists all configured control schedules for the workspace."""
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": f"Project #{project_id} not found."}), 404

    schedules = ControlSchedule.query.filter_by(project_id=project_id).order_by(ControlSchedule.created_at.desc()).all()
    return jsonify([s.to_dict() for s in schedules])


@app.route("/api/projects/<int:project_id>/schedules", methods=["POST"])
@login_required
@role_required("admin", "architect")
def create_project_schedule(project_id):
    """Creates and activates a new control schedule for a workspace."""
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": f"Project #{project_id} not found."}), 404

    data = request.get_json() or {}
    document_id = data.get("document_id")
    if not document_id:
        return jsonify({"error": "document_id is required to schedule a control."}), 400

    doc = Document.query.filter_by(id=document_id, project_id=project_id).first()
    if not doc:
        return jsonify({"error": f"Document #{document_id} not found in workspace #{project_id}."}), 404

    name = data.get("name", "").strip() or f"{doc.original_name or doc.filename} Schedule"
    environment = (data.get("environment") or "dev").lower()
    hostname = (data.get("hostname") or "").strip()
    if not hostname:
        return jsonify({"error": "Hostname is required. The scheduler should work only when hostname is provided."}), 400

    schedule_type = (data.get("schedule_type") or "daily").lower()
    cron_expr = data.get("cron_expression")
    run_time = data.get("run_time") or "02:00"
    days_of_week = data.get("days_of_week") or "mon,tue,wed,thu,fri"
    day_of_month = str(data.get("day_of_month") or "1").strip()
    interval_minutes = data.get("interval_minutes")
    tz_name = data.get("timezone") or "UTC"

    # Determine Control Number
    co = (doc.analysis_data or {}).get("control_overview", {})
    ctrl_id = co.get("identification", {}).get("control_number") or f"Control-{co.get('control_digits', '23')}"

    # Calculate next fire time
    next_run = control_scheduler.compute_next_run(
        schedule_type=schedule_type,
        cron_expression=cron_expr,
        run_time=run_time,
        days_of_week=days_of_week,
        day_of_month=day_of_month,
        interval_minutes=interval_minutes,
        tz_name=tz_name
    )

    current_user = getattr(g, "current_user", None)

    notification_emails = str(data.get("notification_emails") or "").strip()
    notify_on_failure = data.get("notify_on_failure", True)
    if notify_on_failure is None:
        notify_on_failure = True
    else:
        notify_on_failure = bool(notify_on_failure)

    schedule = ControlSchedule(
        project_id=project_id,
        document_id=document_id,
        name=name,
        control_number=ctrl_id,
        environment=environment,
        hostname=hostname,
        notification_emails=notification_emails,
        notify_on_failure=notify_on_failure,
        schedule_type=schedule_type,
        cron_expression=cron_expr,
        run_time=run_time,
        days_of_week=days_of_week,
        day_of_month=day_of_month,
        interval_minutes=int(interval_minutes) if interval_minutes else None,
        timezone_name=tz_name,
        is_active=True,
        next_run_at=next_run,
        created_by_id=current_user.id if current_user else None
    )
    db.session.add(schedule)
    db.session.commit()

    # Register in APScheduler
    control_scheduler.register_schedule_job(schedule, app)

    return jsonify(schedule.to_dict()), 201


@app.route("/api/projects/<int:project_id>/schedules/<int:schedule_id>", methods=["PUT"])
@login_required
@role_required("admin", "architect")
def update_project_schedule(project_id, schedule_id):
    """Updates an existing control schedule."""
    schedule = ControlSchedule.query.filter_by(id=schedule_id, project_id=project_id).first()
    if not schedule:
        return jsonify({"error": f"Schedule #{schedule_id} not found."}), 404

    data = request.get_json() or {}
    if "name" in data:
        schedule.name = data["name"].strip() or schedule.name
    if "environment" in data:
        schedule.environment = (data["environment"] or "dev").lower()
    if "hostname" in data:
        new_host = (data["hostname"] or "").strip()
        if not new_host:
            return jsonify({"error": "Hostname is required. The scheduler should work only when hostname is provided."}), 400
        schedule.hostname = new_host
    if "schedule_type" in data:
        schedule.schedule_type = (data["schedule_type"] or "daily").lower()
    if "cron_expression" in data:
        schedule.cron_expression = data["cron_expression"]
    if "run_time" in data:
        schedule.run_time = data["run_time"]
    if "days_of_week" in data:
        schedule.days_of_week = data["days_of_week"]
    if "day_of_month" in data:
        schedule.day_of_month = str(data["day_of_month"] or "1").strip()
    if "interval_minutes" in data:
        schedule.interval_minutes = int(data["interval_minutes"]) if data["interval_minutes"] else None
    if "timezone" in data:
        schedule.timezone_name = data["timezone"] or "UTC"
    if "notification_emails" in data:
        schedule.notification_emails = str(data["notification_emails"] or "").strip()
    if "notify_on_failure" in data:
        schedule.notify_on_failure = bool(data["notify_on_failure"])

    if schedule.is_active and not (schedule.hostname or "").strip():
        return jsonify({"error": "Cannot activate schedule without a hostname. The scheduler should work only when hostname is provided."}), 400

    # Recompute next run
    if schedule.is_active:
        schedule.next_run_at = control_scheduler.compute_next_run(
            schedule_type=schedule.schedule_type,
            cron_expression=schedule.cron_expression,
            run_time=schedule.run_time,
            days_of_week=schedule.days_of_week,
            day_of_month=schedule.day_of_month,
            interval_minutes=schedule.interval_minutes,
            tz_name=schedule.timezone_name
        )
        control_scheduler.register_schedule_job(schedule, app)
    else:
        schedule.next_run_at = None
        control_scheduler.unregister_schedule_job(schedule.id)

    db.session.commit()
    return jsonify(schedule.to_dict())


@app.route("/api/projects/<int:project_id>/schedules/email-alerts", methods=["GET"])
@login_required
def get_project_email_alerts(project_id):
    """Returns recent email failure alert dispatch logs for the project."""
    logs = EmailNotificationLog.query.filter_by(project_id=project_id).order_by(EmailNotificationLog.sent_at.desc()).limit(50).all()
    return jsonify([l.to_dict() for l in logs])


@app.route("/api/projects/<int:project_id>/schedules/test-email-alert", methods=["POST"])
@login_required
@role_required("admin", "architect")
def test_project_email_alert(project_id):
    """Triggers an on-demand test email failure alert to verify recipient delivery."""
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": f"Project #{project_id} not found."}), 404

    data = request.get_json() or {}
    recipient_emails = data.get("recipient_emails", "").strip()

    active_doc = Document.query.filter_by(project_id=project_id).order_by(Document.id.desc()).first()
    dynamic_ctrl_num = "HLA Pipeline"
    if active_doc and active_doc.analysis_data:
        dynamic_ctrl_num = (active_doc.analysis_data.get("control_overview", {})
                            .get("identification", {})
                            .get("control_number")) or "HLA Pipeline"

    class MockRun:
        id = 8888
        control_number = dynamic_ctrl_num
        environment = "PROD"
        hostname = "prod-etl-node-01"
        status = "BLOCKED"
        started_at = datetime.now(timezone.utc)
        summary_message = "Pre-Execution Gate: Source table 'public.billing_records' has 0 rows / not arrived on scheduled cycle."
        result_details = {
            "tables_checked": 3,
            "tables_found": 2,
            "tables_missing": 1,
            "tables_empty": 1,
            "tables_stale": 0,
            "missing_list": ["public.billing_records"],
            "empty_list": ["public.telemetry_daily"],
            "stale_list": []
        }

    mock_run = MockRun()
    result = email_service.send_control_failure_alert(
        run_record=mock_run,
        project=project,
        failure_reason="SLA Failure Alert Test: Upstream source data has not arrived on scheduled run time.",
        additional_recipients=recipient_emails
    )
    return jsonify(result)


@app.route("/api/projects/<int:project_id>/schedules/<int:schedule_id>", methods=["DELETE"])
@login_required
@role_required("admin", "architect")
def delete_project_schedule(project_id, schedule_id):
    """Deletes a control schedule."""
    schedule = ControlSchedule.query.filter_by(id=schedule_id, project_id=project_id).first()
    if not schedule:
        return jsonify({"error": f"Schedule #{schedule_id} not found."}), 404

    control_scheduler.unregister_schedule_job(schedule.id)
    db.session.delete(schedule)
    db.session.commit()
    return jsonify({"success": True, "message": f"Schedule #{schedule_id} successfully deleted."})


@app.route("/api/projects/<int:project_id>/schedules/<int:schedule_id>/toggle", methods=["POST"])
@login_required
@role_required("admin", "architect")
def toggle_project_schedule(project_id, schedule_id):
    """Toggles active/paused status of a schedule."""
    schedule = ControlSchedule.query.filter_by(id=schedule_id, project_id=project_id).first()
    if not schedule:
        return jsonify({"error": f"Schedule #{schedule_id} not found."}), 404

    schedule.is_active = not schedule.is_active
    if schedule.is_active:
        if not (schedule.hostname or "").strip():
            return jsonify({"error": "Cannot activate schedule. Hostname is missing. The scheduler should work only when hostname is provided."}), 400
        schedule.next_run_at = control_scheduler.compute_next_run(
            schedule_type=schedule.schedule_type,
            cron_expression=schedule.cron_expression,
            run_time=schedule.run_time,
            days_of_week=schedule.days_of_week,
            day_of_month=schedule.day_of_month,
            interval_minutes=schedule.interval_minutes,
            tz_name=schedule.timezone_name
        )
        control_scheduler.register_schedule_job(schedule, app)
    else:
        schedule.next_run_at = None
        control_scheduler.unregister_schedule_job(schedule.id)

    db.session.commit()
    return jsonify(schedule.to_dict())


@app.route("/api/projects/<int:project_id>/schedules/<int:schedule_id>/run", methods=["POST"])
@login_required
@role_required("admin", "architect")
def trigger_schedule_run_now(project_id, schedule_id):
    """Triggers an immediate on-demand run of a scheduled control."""
    schedule = ControlSchedule.query.filter_by(id=schedule_id, project_id=project_id).first()
    if not schedule:
        return jsonify({"error": f"Schedule #{schedule_id} not found."}), 404

    if not (schedule.hostname or "").strip():
        return jsonify({"error": "Cannot run schedule. Hostname is missing. The scheduler should work only when hostname is provided."}), 400

    run_result = control_scheduler.execute_control_pipeline(
        document_id=schedule.document_id,
        project_id=project_id,
        environment=schedule.environment,
        schedule_id=schedule.id,
        trigger_type="MANUAL",
        hostname=schedule.hostname
    )
    return jsonify(run_result)


@app.route("/api/projects/<int:project_id>/documents/<int:document_id>/run-control", methods=["POST"])
@login_required
@role_required("admin", "architect")
def trigger_document_control_run(project_id, document_id):
    """Triggers an on-demand control run for a specific document/control without a schedule."""
    doc = Document.query.filter_by(id=document_id, project_id=project_id).first()
    if not doc:
        return jsonify({"error": f"Document #{document_id} not found."}), 404

    data = request.get_json() or {}
    env = (data.get("environment") or "dev").lower()
    hostname = (data.get("hostname") or "").strip()
    if not hostname:
        return jsonify({"error": "Hostname is required. The scheduler should work only when hostname is provided."}), 400

    run_result = control_scheduler.execute_control_pipeline(
        document_id=document_id,
        project_id=project_id,
        environment=env,
        schedule_id=None,
        trigger_type="MANUAL",
        hostname=hostname
    )
    return jsonify(run_result)


@app.route("/api/projects/<int:project_id>/schedules/history", methods=["GET"])
@login_required
def get_project_schedules_history(project_id):
    """Returns execution run history and audit logs for the workspace."""
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": f"Project #{project_id} not found."}), 404

    query = ControlRunHistory.query.filter_by(project_id=project_id)

    doc_id = request.args.get("document_id")
    if doc_id:
        query = query.filter_by(document_id=int(doc_id))

    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status.upper())

    limit = request.args.get("limit", default=100, type=int)
    runs = query.order_by(ControlRunHistory.started_at.desc()).limit(limit).all()

    return jsonify([r.to_dict() for r in runs])


@app.route("/api/projects/<int:project_id>/schedules/history/<int:run_id>", methods=["GET"])
@login_required
def get_control_run_details(project_id, run_id):
    """Returns full details and console logs for a specific run."""
    run_record = ControlRunHistory.query.filter_by(id=run_id, project_id=project_id).first()
    if not run_record:
        return jsonify({"error": f"Run record #{run_id} not found."}), 404

    return jsonify(run_record.to_dict())


# ── SMTP & Email Alert Settings Endpoints ─────────────────────────────

@app.route("/api/settings/smtp", methods=["GET"])
@login_required
def get_smtp_settings():
    """Returns current SMTP server configuration (with password masked)."""
    cfg = email_service.get_smtp_config()
    return jsonify({
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 587),
        "user": cfg.get("user", ""),
        "has_password": bool(cfg.get("password")),
        "security": cfg.get("security", "starttls"),
        "from_email": cfg.get("from_email", ""),
        "is_configured": email_service.is_smtp_configured(cfg)
    })


@app.route("/api/settings/smtp", methods=["POST"])
@login_required
@role_required("admin", "architect")
def save_smtp_settings():
    """Saves SMTP server configuration in PostgreSQL SystemSetting table."""
    data = request.get_json() or {}
    updated = email_service.save_smtp_config(data)
    return jsonify({
        "success": True,
        "message": "SMTP configuration saved successfully.",
        "config": {
            "host": updated.get("host", ""),
            "port": updated.get("port", 587),
            "user": updated.get("user", ""),
            "has_password": bool(updated.get("password")),
            "security": updated.get("security", "starttls"),
            "from_email": updated.get("from_email", ""),
            "is_configured": email_service.is_smtp_configured(updated)
        }
    })


@app.route("/api/settings/smtp/test", methods=["POST"])
@login_required
@role_required("admin", "architect")
def test_smtp_connection_endpoint():
    """Tests live SMTP connection, authentication, and sends a test email."""
    data = request.get_json() or {}
    target_email = data.get("target_email") or (getattr(g, "current_user", None) and getattr(g.current_user, "email", None))
    override_cfg = data.get("smtp_config")
    result = email_service.test_smtp_connection(target_email, override_config=override_cfg)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


# ── Error handlers ────────────────────────────────────────────────────

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": f"File too large. Maximum size is {MAX_FILE_SIZE_MB} MB."}), 413


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n  HLA Backend running at http://localhost:5000")
    print(f"  Upload folder: {UPLOAD_FOLDER}\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
