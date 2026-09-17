import os
from datetime import datetime, timezone, timedelta
from functools import wraps
import jwt
from flask import request, jsonify, g
from models import db, User, AuditLog

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "hla-enterprise-production-jwt-security-key-2026-secure-32bytes")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRATION_HOURS = 1
REFRESH_TOKEN_EXPIRATION_DAYS = 7


def generate_token(user: User, expires_in_hours: int = ACCESS_TOKEN_EXPIRATION_HOURS, token_type: str = "access") -> str:
    now = datetime.now(timezone.utc)
    role_code = user.assigned_role.code if user.assigned_role else user.role
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": role_code,
        "tv": user.token_version or 1,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(hours=expires_in_hours)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def generate_tokens(user: User) -> dict:
    now = datetime.now(timezone.utc)
    role_code = user.assigned_role.code if user.assigned_role else user.role
    tv = user.token_version or 1
    access_payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": role_code,
        "tv": tv,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRATION_HOURS)
    }
    refresh_payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": role_code,
        "tv": tv,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS)
    }
    return {
        "access_token": jwt.encode(access_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
        "refresh_token": jwt.encode(refresh_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    }


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired. Please log in again.")
    except jwt.InvalidTokenError as ite:
        raise ValueError(f"Invalid authentication token: {str(ite)}")


def verify_refresh_token(refresh_token: str):
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            return None, "Invalid token type: expected a refresh token."
        sub_id = payload.get("sub")
        user_id = int(sub_id) if sub_id is not None else None
        user = db.session.get(User, user_id) if user_id else None
        if not user:
            return None, "User account associated with this token was not found."

        # Token version invalidation check (force logout)
        tv = payload.get("tv")
        if tv is not None and user.token_version is not None and tv != user.token_version:
            return None, "Session has been terminated by administrator. Please log in again."

        if user.is_currently_locked():
            return None, "Account is currently locked. Please contact an administrator."
        if user.status == "DISABLED":
            return None, "Account is disabled. Please contact an administrator."

        return user, None
    except Exception as e:
        return None, str(e)


def get_current_user():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None, "Authorization header is missing."

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None, "Authorization header must be formatted as 'Bearer <token>'."

    token = parts[1]
    try:
        payload = decode_token(token)
        if payload.get("type") and payload.get("type") != "access":
            return None, "Invalid token type: cannot use refresh token for API access."
        sub_id = payload.get("sub")
        user_id = int(sub_id) if sub_id is not None else None
        user = db.session.get(User, user_id) if user_id else None
        if not user:
            return None, "User account not found."

        # Token version invalidation check (force logout)
        tv = payload.get("tv")
        if tv is not None and user.token_version is not None and tv != user.token_version:
            return None, "Session has been invalidated (force logout). Please log in again."

        # Account status enforcement
        if user.is_currently_locked():
            return None, "Account is currently locked. Please contact an administrator."
        if user.status == "DISABLED":
            return None, "Account is disabled. Please contact an administrator."

        # Update last_activity_at safely
        try:
            user.last_activity_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return user, None
    except Exception as e:
        return None, str(e)


import logging
import sys

logger = logging.getLogger("auth")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
logger.propagate = False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        path = request.path
        auth_header = request.headers.get("Authorization", "")
        has_auth_header = bool(auth_header)
        user, error = get_current_user()
        user_resolved = bool(user)
        user_role = user.role if user else None

        logger.info(f"[AUTH] {path} request received | AuthHeader: {has_auth_header} | Resolved: {user_resolved} | Role: {user_role}")

        if not user:
            return jsonify({"error": error or "Authentication required."}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    """
    Enforces that the authenticated user possesses one of the allowed roles.
    Example: @role_required('admin', 'architect')
    """
    flat_roles = []
    for r in allowed_roles:
        if isinstance(r, (list, tuple, set)):
            flat_roles.extend(r)
        else:
            flat_roles.append(r)
    normalized_roles = {str(r).lower() for r in flat_roles}

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user, error = get_current_user()
            if not user:
                return jsonify({"error": error or "Authentication required."}), 401

            user_role = (user.assigned_role.code if user.assigned_role else user.role or "").lower()
            if user_role not in normalized_roles:
                log_audit_event(
                    action="auth.access_denied",
                    resource_type="endpoint",
                    resource_id=request.path,
                    status="FAILURE",
                    metadata={"required_roles": list(normalized_roles), "user_role": user_role},
                    user=user
                )
                return jsonify({
                    "error": f"Access denied. Required role: {', '.join(allowed_roles)}. Your current role is '{user_role}'."
                }), 403

            g.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


def permission_required(*required_permissions):
    """
    Enforces that the authenticated user possesses ALL specified permissions.
    Administrators possess all permissions unconditionally.
    Example: @permission_required('project.view', 'project.edit')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user, error = get_current_user()
            if not user:
                return jsonify({"error": error or "Authentication required."}), 401

            user_role = (user.assigned_role.code if user.assigned_role else user.role or "").lower()
            # Admin role has superuser rights
            if user_role != "admin":
                missing = [p for p in required_permissions if not user.has_permission(p)]
                if missing:
                    log_audit_event(
                        action="auth.permission_denied",
                        resource_type="endpoint",
                        resource_id=request.path,
                        status="FAILURE",
                        metadata={"missing_permissions": missing, "user_role": user_role},
                        user=user
                    )
                    return jsonify({
                        "error": f"Access denied. Required permission(s): {', '.join(missing)}."
                    }), 403

            g.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


SENSITIVE_METADATA_KEYS = (
    "password", "passwd", "pwd", "hash", "secret", "token", "jwt",
    "otp", "key", "auth", "credential", "conn_str", "connection_string"
)


def sanitize_audit_metadata(data):
    """Recursively redacts sensitive credentials, tokens, and secrets from audit payloads."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if any(s in k_str for s in SENSITIVE_METADATA_KEYS):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_audit_metadata(v)
        return cleaned
    elif isinstance(data, (list, tuple, set)):
        return [sanitize_audit_metadata(item) for item in data]
    return data


def log_audit_event(action: str, resource_type: str, resource_id=None, project_id=None,
                    status: str = "SUCCESS", metadata: dict = None,
                    user: User = None, ip_address: str = None, username: str = None) -> AuditLog:
    """
    Appends an immutable event to the audit_logs table.
    Ensures zero sensitive passwords, tokens, or credentials are saved.
    """
    try:
        resolved_user = user or getattr(g, "current_user", None)
        user_id = resolved_user.id if resolved_user else None
        resolved_username = username or (resolved_user.username if resolved_user else "system")

        resolved_ip = ip_address
        if not resolved_ip:
            try:
                resolved_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
                if resolved_ip and "," in resolved_ip:
                    resolved_ip = resolved_ip.split(",")[0].strip()
            except Exception:
                resolved_ip = "127.0.0.1"

        cleaned_metadata = sanitize_audit_metadata(metadata or {})

        entry = AuditLog(
            user_id=user_id,
            username=resolved_username,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            project_id=project_id,
            status=status,
            ip_address=resolved_ip,
            metadata_json=cleaned_metadata,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(entry)
        db.session.commit()
        return entry
    except Exception as e:
        logger.error(f"[AUDIT] Failed to record audit event '{action}': {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return None

