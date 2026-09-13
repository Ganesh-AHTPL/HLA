import os
from datetime import datetime, timezone, timedelta
from functools import wraps
import jwt
from flask import request, jsonify, g
from models import db, User

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "hla-enterprise-production-jwt-security-key-2026-secure-32bytes")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRATION_HOURS = 1
REFRESH_TOKEN_EXPIRATION_DAYS = 7


def generate_token(user: User, expires_in_hours: int = ACCESS_TOKEN_EXPIRATION_HOURS, token_type: str = "access") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(hours=expires_in_hours)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def generate_tokens(user: User) -> dict:
    now = datetime.now(timezone.utc)
    access_payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRATION_HOURS)
    }
    refresh_payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
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

        logger.info(f"[AUTH] {path} request received")
        logger.info(f"[AUTH] Authorization header present: {has_auth_header}")
        logger.info(f"[AUTH] Token validation: {'success' if user_resolved else 'failure'}")
        logger.info(f"[AUTH] User resolved: {user_resolved}")
        if user_role:
            logger.info(f"[AUTH] User role: {user_role}")
        logger.info(f"[AUTH] Authorization result: {'allowed' if user_resolved else 'denied'}")

        if not user:
            return jsonify({"error": error or "Authentication required."}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    """
    Enforces that the authenticated user possesses one of the allowed roles.
    Example: @role_required('admin', 'architect') or @role_required(['admin', 'architect'])
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
            path = request.path
            auth_header = request.headers.get("Authorization", "")
            has_auth_header = bool(auth_header)
            user, error = get_current_user()
            user_resolved = bool(user)
            user_role = user.role if user else None

            logger.info(f"[AUTH] {path} request received")
            logger.info(f"[AUTH] Authorization header present: {has_auth_header}")
            logger.info(f"[AUTH] Token validation: {'success' if user_resolved else 'failure'}")
            logger.info(f"[AUTH] User resolved: {user_resolved}")
            if user_role:
                logger.info(f"[AUTH] User role: {user_role}")

            if not user:
                logger.info(f"[AUTH] Authorization result: denied (unauthenticated)")
                return jsonify({"error": error or "Authentication required."}), 401
            if user.role.lower() not in normalized_roles:
                logger.info(f"[AUTH] Authorization result: denied (insufficient permissions)")
                return jsonify({
                    "error": f"Access denied. Required role: {', '.join(allowed_roles)}. Your current role is '{user.role}'."
                }), 403
            logger.info(f"[AUTH] Authorization result: allowed")
            g.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator
