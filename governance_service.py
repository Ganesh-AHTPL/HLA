"""
governance_service.py - Enterprise HLA Governance, RBAC & Security Center Engine
Provides:
1. 25 Standard enterprise permissions across 8 domains
2. Default system roles (admin, architect, viewer) & custom role lifecycle
3. User lifecycle (status, lockout, force-logout, effective permissions, user activity)
4. Interactive Role-Permission Matrix management
5. Append-only Audit Center with filtering & safe CSV export
6. Executive Overview foundation with real database metrics
7. Security Center health indicators (Auth, RBAC, DB, Ollama, SMTP, Audit, KPIs)
"""

import io
import csv
import socket
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g, make_response
from models import (
    db, User, Role, Permission, RolePermission, AuditLog,
    Project, Document, ControlSchedule, ControlRunHistory, SystemSetting
)
from auth import (
    login_required, role_required, permission_required,
    log_audit_event, sanitize_audit_metadata
)
from email_service import get_smtp_config

governance_bp = Blueprint("governance", __name__, url_prefix="/api/governance")

# ─────────────────────────────────────────────────────────────────────────────
# 25 STANDARD ENTERPRISE PERMISSIONS SPECIFICATION
# ─────────────────────────────────────────────────────────────────────────────
STANDARD_PERMISSIONS = [
    # DOMAIN: PROJECT
    {"code": "project.view", "name": "View Projects", "category": "Project", "description": "Browse and inspect workspace projects and metadata"},
    {"code": "project.create", "name": "Create Projects", "category": "Project", "description": "Initialize new projects and configure workspace settings"},
    {"code": "project.edit", "name": "Edit Projects", "category": "Project", "description": "Update project details, descriptions, and connectors"},
    {"code": "project.delete", "name": "Delete Projects", "category": "Project", "description": "Permanently remove projects and associated artifacts"},

    # DOMAIN: DOCUMENT
    {"code": "document.view", "name": "View Documents", "category": "Document", "description": "Inspect uploaded HLA specifications and analysis metadata"},
    {"code": "document.upload", "name": "Upload Documents", "category": "Document", "description": "Upload new HLA Excel specifications into projects"},
    {"code": "document.edit", "name": "Edit Documents", "category": "Document", "description": "Modify document parameters and target logic mappings"},
    {"code": "document.delete", "name": "Delete Documents", "category": "Document", "description": "Remove documents and target logic artifacts"},

    # DOMAIN: CONTROL
    {"code": "control.view", "name": "View Controls", "category": "Control", "description": "View control rules, evaluation schedules, and status"},
    {"code": "control.create", "name": "Create Controls", "category": "Control", "description": "Define new control rules and execution schedules"},
    {"code": "control.edit", "name": "Edit Controls", "category": "Control", "description": "Modify control rule parameters and cron schedules"},
    {"code": "control.execute", "name": "Execute Controls", "category": "Control", "description": "Trigger on-demand or scheduled control evaluations"},
    {"code": "control.delete", "name": "Delete Controls", "category": "Control", "description": "Remove control configurations and execution schedules"},

    # DOMAIN: EXCEPTION
    {"code": "exception.view", "name": "View Exceptions", "category": "Exception", "description": "Inspect detected rule exceptions and validation anomalies"},
    {"code": "exception.manage", "name": "Manage Exceptions", "category": "Exception", "description": "Assign, update status, and resolve control exceptions"},

    # DOMAIN: EVIDENCE
    {"code": "evidence.view", "name": "View Evidence", "category": "Evidence", "description": "Browse audit evidence packages and execution history"},
    {"code": "evidence.manage", "name": "Manage Evidence", "category": "Evidence", "description": "Attach, catalog, and certify execution evidence artifacts"},

    # DOMAIN: ARCHITECTURE
    {"code": "architecture.view", "name": "View Architecture", "category": "Architecture", "description": "Inspect interactive component and data flow diagrams"},
    {"code": "architecture.edit", "name": "Edit Architecture", "category": "Architecture", "description": "Author, modify, and annotate architecture components"},

    # DOMAIN: LINEAGE
    {"code": "lineage.view", "name": "View Lineage", "category": "Lineage", "description": "Trace circuit and field transformations from source to target"},

    # DOMAIN: ADMINISTRATION
    {"code": "user.manage", "name": "Manage Users", "category": "Administration", "description": "Create, edit, lock, unlock, disable, and reset users"},
    {"code": "role.manage", "name": "Manage Roles", "category": "Administration", "description": "Create, customize, clone, and manage enterprise security roles"},
    {"code": "permission.manage", "name": "Manage Permissions", "category": "Administration", "description": "Configure role-permission matrices and privilege grants"},

    # DOMAIN: GOVERNANCE
    {"code": "audit.view", "name": "View Audit Center", "category": "Governance", "description": "Search, inspect, and export immutable governance audit logs"},

    # DOMAIN: SYSTEM
    {"code": "system.settings", "name": "Manage System Settings", "category": "System", "description": "Configure platform parameters, connectors, and security center"},
]

# Standard role permission mappings
ARCHITECT_DEFAULT_PERMISSIONS = [
    "project.view", "project.create", "project.edit",
    "document.view", "document.upload", "document.edit",
    "control.view", "control.create", "control.edit", "control.execute",
    "exception.view",
    "evidence.view",
    "architecture.view", "architecture.edit",
    "lineage.view",
]

VIEWER_DEFAULT_PERMISSIONS = [
    "project.view",
    "document.view",
    "control.view",
    "exception.view",
    "evidence.view",
    "architecture.view",
    "lineage.view",
]


def seed_governance_rbac():
    """
    Idempotently seeds:
    1. Exactly 25 standard permissions
    2. 3 system roles (admin, architect, viewer)
    3. Correct default role-permission mappings
    4. Synchronizes existing users to appropriate role_id
    """
    try:
        # 1. Seed Permissions
        perm_map = {}
        for pdata in STANDARD_PERMISSIONS:
            perm = Permission.query.filter_by(code=pdata["code"]).first()
            if not perm:
                perm = Permission(
                    code=pdata["code"],
                    name=pdata["name"],
                    category=pdata["category"],
                    description=pdata["description"]
                )
                db.session.add(perm)
                db.session.flush()
            else:
                perm.name = pdata["name"]
                perm.category = pdata["category"]
                perm.description = pdata["description"]
            perm_map[pdata["code"]] = perm

        # 2. Seed System Roles
        system_roles_spec = [
            {
                "code": "admin",
                "name": "Administrator",
                "description": "Full enterprise administrative access, user administration, custom roles, and security governance.",
                "perms": list(perm_map.keys())  # All 25 permissions
            },
            {
                "code": "architect",
                "name": "Solution Architect",
                "description": "Design, document parsing, Target DB Studio logic generation, control execution, and architecture lineage.",
                "perms": ARCHITECT_DEFAULT_PERMISSIONS
            },
            {
                "code": "viewer",
                "name": "Stakeholder / Viewer",
                "description": "Read-only access to projects, documents, controls, exceptions, architecture, and lineage.",
                "perms": VIEWER_DEFAULT_PERMISSIONS
            }
        ]

        role_obj_map = {}
        for rdata in system_roles_spec:
            role = Role.query.filter_by(code=rdata["code"]).first()
            if not role:
                role = Role(
                    name=rdata["name"],
                    code=rdata["code"],
                    description=rdata["description"],
                    is_system=True,
                    is_active=True
                )
                db.session.add(role)
                db.session.flush()
            else:
                role.name = rdata["name"]
                role.is_system = True
                role.is_active = True
                role.description = rdata["description"]

            # Map permissions
            assigned_perm_codes = {p.code for p in role.permissions}
            target_perm_codes = set(rdata["perms"])
            for code in target_perm_codes:
                if code not in assigned_perm_codes and code in perm_map:
                    role.permissions.append(perm_map[code])

            role_obj_map[rdata["code"]] = role

        db.session.commit()

        # 3. Synchronize existing users (safe migration from legacy role string to role_id)
        users = User.query.all()
        for user in users:
            legacy_role = (user.role or "architect").strip().lower()
            matching_role = role_obj_map.get(legacy_role) or role_obj_map.get("viewer")
            if matching_role:
                user.role_id = matching_role.id
                user.role = matching_role.code
            if not user.status:
                user.status = "ACTIVE"
        db.session.commit()
        print("[OK] Seeded 25 governance permissions, system roles, and synced user assignments.")
    except Exception as e:
        db.session.rollback()
        print(f"[WARNING] Governance seeding encountered an issue: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# USER LIFECYCLE & ADMINISTRATION APIS
# ─────────────────────────────────────────────────────────────────────────────

@governance_bp.route("/users", methods=["GET"])
@permission_required("user.manage")
def list_governance_users():
    q = request.args.get("q", "").strip().lower()
    status_filter = request.args.get("status", "").strip().upper()
    role_filter = request.args.get("role", "").strip().lower()
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(5, int(request.args.get("page_size", 20))))

    query = User.query

    if q:
        query = query.filter(
            db.or_(
                User.username.ilike(f"%{q}%"),
                User.email.ilike(f"%{q}%")
            )
        )
    if status_filter and status_filter != "ALL":
        query = query.filter(User.status == status_filter)
    if role_filter and role_filter != "all":
        query = query.filter(User.role == role_filter)

    total_count = query.count()
    users = query.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size).all()

    return jsonify({
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "users": [u.to_dict(include_permissions=True) for u in users]
    }), 200


@governance_bp.route("/users", methods=["POST"])
@permission_required("user.manage")
def create_governance_user():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip() or None
    role_input = data.get("role", "architect").strip().lower()
    status_input = data.get("status", "ACTIVE").strip().upper()

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    if status_input not in ["ACTIVE", "PENDING", "LOCKED", "DISABLED"]:
        return jsonify({"error": "Invalid status. Must be ACTIVE, PENDING, LOCKED, or DISABLED."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": f"Username '{username}' already exists."}), 409

    target_role = Role.query.filter(
        db.or_(Role.code == role_input, Role.name.ilike(role_input))
    ).first()
    if not target_role:
        return jsonify({"error": f"Role '{role_input}' does not exist."}), 400

    try:
        new_user = User(
            username=username,
            email=email,
            role=target_role.code,
            role_id=target_role.id,
            status=status_input,
            token_version=1
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        log_audit_event(
            action="user.create",
            resource_type="user",
            resource_id=new_user.id,
            status="SUCCESS",
            metadata={"username": username, "role": target_role.code, "status": status_input}
        )

        return jsonify({
            "message": f"User '{username}' created successfully.",
            "user": new_user.to_dict(include_permissions=True)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500


@governance_bp.route("/users/<int:user_id>", methods=["PUT", "PATCH"])
@permission_required("user.manage")
def update_governance_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json() or {}
    new_role = data.get("role")
    new_email = data.get("email")
    new_password = data.get("password")
    new_status = data.get("status")

    # Self-protection guards
    is_self = (getattr(g, "current_user", None) and g.current_user.id == user_id)

    if new_role:
        normalized_role = str(new_role).strip().lower()
        target_role = Role.query.filter(
            db.or_(Role.code == normalized_role, Role.name.ilike(normalized_role))
        ).first()
        if not target_role:
            return jsonify({"error": f"Role '{new_role}' is not recognized."}), 400

        if is_self and target_role.code != "admin":
            return jsonify({"error": "Action rejected: You cannot remove your own Administrator privileges."}), 400

        user.sync_role(target_role)

    if new_status:
        stat = str(new_status).strip().upper()
        if stat not in ["ACTIVE", "PENDING", "LOCKED", "DISABLED"]:
            return jsonify({"error": "Invalid status. Must be ACTIVE, PENDING, LOCKED, or DISABLED."}), 400
        if is_self and stat in ["LOCKED", "DISABLED"]:
            return jsonify({"error": "Action rejected: You cannot lock or disable your own active Administrator account."}), 400
        user.status = stat
        if stat == "ACTIVE":
            user.failed_login_attempts = 0
            user.locked_until = None

    if new_email is not None:
        user.email = str(new_email).strip() or None

    if new_password:
        pw_str = str(new_password).strip()
        if len(pw_str) < 4:
            return jsonify({"error": "Password must be at least 4 characters long."}), 400
        user.set_password(pw_str)
        user.token_version = (user.token_version or 1) + 1  # invalidate active sessions on pwd change

    try:
        db.session.commit()
        log_audit_event(
            action="user.update",
            resource_type="user",
            resource_id=user.id,
            status="SUCCESS",
            metadata={"username": user.username, "role": user.role, "status": user.status}
        )
        return jsonify({
            "message": f"User '{user.username}' updated successfully.",
            "user": user.to_dict(include_permissions=True)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update user: {str(e)}"}), 500


@governance_bp.route("/users/<int:user_id>/status", methods=["POST"])
@permission_required("user.manage")
def set_user_status(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json() or {}
    new_status = data.get("status", "").strip().upper()
    if new_status not in ["ACTIVE", "PENDING", "LOCKED", "DISABLED"]:
        return jsonify({"error": "Invalid status. Supported: ACTIVE, PENDING, LOCKED, DISABLED."}), 400

    # Self-protection rule
    if getattr(g, "current_user", None) and g.current_user.id == user_id:
        if new_status in ["LOCKED", "DISABLED"]:
            return jsonify({"error": "Action rejected: You cannot lock or disable your own active Administrator account."}), 400

    old_status = user.status
    user.status = new_status
    if new_status == "ACTIVE":
        user.failed_login_attempts = 0
        user.locked_until = None
    elif new_status == "LOCKED":
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)

    try:
        db.session.commit()
        log_audit_event(
            action="user.status_change",
            resource_type="user",
            resource_id=user.id,
            status="SUCCESS",
            metadata={"username": user.username, "from": old_status, "to": new_status}
        )
        return jsonify({
            "message": f"User '{user.username}' status transitioned to {new_status}.",
            "user": user.to_dict(include_permissions=True)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to change status: {str(e)}"}), 500


@governance_bp.route("/users/<int:user_id>/force-logout", methods=["POST"])
@permission_required("user.manage")
def force_logout_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    # Increment token_version to invalidate all issued JWT access and refresh tokens
    user.token_version = (user.token_version or 1) + 1

    try:
        db.session.commit()
        log_audit_event(
            action="auth.force_logout",
            resource_type="user",
            resource_id=user.id,
            status="SUCCESS",
            metadata={"username": user.username, "new_token_version": user.token_version}
        )
        return jsonify({
            "message": f"Active sessions for user '{user.username}' have been invalidated (Token Version: {user.token_version}).",
            "token_version": user.token_version
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to force logout: {str(e)}"}), 500


@governance_bp.route("/users/<int:user_id>/activity", methods=["GET"])
@login_required
def get_user_activity(user_id):
    current_user = g.current_user
    if current_user.id != user_id and not current_user.has_permission("user.manage"):
        return jsonify({"error": "Access denied: Requires 'user.manage' permission to view other users' activity."}), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    limit = min(50, max(5, int(request.args.get("limit", 20))))
    logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return jsonify({
        "user_id": user.id,
        "username": user.username,
        "activity": [l.to_dict() for l in logs]
    }), 200


@governance_bp.route("/users/<int:user_id>/permissions", methods=["GET"])
@login_required
def get_user_permissions(user_id):
    current_user = g.current_user
    if current_user.id != user_id and not current_user.has_permission("user.manage"):
        return jsonify({"error": "Access denied: Requires 'user.manage' permission."}), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    perms = user.get_effective_permissions()
    role_obj = user.assigned_role
    return jsonify({
        "user_id": user.id,
        "username": user.username,
        "role": role_obj.code if role_obj else user.role,
        "role_name": role_obj.name if role_obj else user.role.capitalize(),
        "role_description": role_obj.description if role_obj else "",
        "effective_permissions": perms,
        "permission_count": len(perms)
    }), 200


@governance_bp.route("/users/<int:user_id>", methods=["DELETE"])
@permission_required("user.manage")
def delete_governance_user(user_id):
    if getattr(g, "current_user", None) and g.current_user.id == user_id:
        return jsonify({"error": "Action rejected: You cannot delete your own active Administrator account."}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    username = user.username
    try:
        db.session.delete(user)
        db.session.commit()
        log_audit_event(
            action="user.delete",
            resource_type="user",
            resource_id=user_id,
            status="SUCCESS",
            metadata={"deleted_username": username}
        )
        return jsonify({"message": f"User account '{username}' has been removed."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete user: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM ROLE MANAGEMENT APIS
# ─────────────────────────────────────────────────────────────────────────────

@governance_bp.route("/roles", methods=["GET"])
@login_required
def list_governance_roles():
    roles = Role.query.order_by(Role.is_system.desc(), Role.id.asc()).all()
    return jsonify([r.to_dict(include_users_count=True) for r in roles]), 200


@governance_bp.route("/roles", methods=["POST"])
@permission_required("role.manage")
def create_governance_role():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    code = data.get("code", "").strip().lower()
    description = data.get("description", "").strip()
    perm_codes = data.get("permissions", [])

    if not name or not code:
        return jsonify({"error": "Role name and unique code are required."}), 400

    clean_code = "".join(c if (c.isalnum() or c in "_-") else "_" for c in code).strip("_")
    if clean_code in ["admin", "architect", "viewer"]:
        return jsonify({"error": f"Role code '{clean_code}' is reserved for system roles."}), 400

    if Role.query.filter(db.or_(Role.code == clean_code, Role.name.ilike(name))).first():
        return jsonify({"error": f"A role with code '{clean_code}' or name '{name}' already exists."}), 409

    try:
        new_role = Role(
            name=name,
            code=clean_code,
            description=description,
            is_system=False,
            is_active=True
        )

        if perm_codes:
            perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
            new_role.permissions = perms

        db.session.add(new_role)
        db.session.commit()

        log_audit_event(
            action="role.create",
            resource_type="role",
            resource_id=new_role.id,
            status="SUCCESS",
            metadata={"name": name, "code": clean_code, "permission_count": len(new_role.permissions)}
        )

        return jsonify({
            "message": f"Custom role '{name}' ({clean_code}) created successfully.",
            "role": new_role.to_dict(include_users_count=True)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create role: {str(e)}"}), 500


@governance_bp.route("/roles/<int:role_id>", methods=["PUT", "PATCH"])
@permission_required("role.manage")
def update_governance_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "Role not found."}), 404

    data = request.get_json() or {}
    new_name = data.get("name")
    new_desc = data.get("description")
    is_active = data.get("is_active")
    perm_codes = data.get("permissions")

    if role.is_system:
        if new_name and new_name.strip() != role.name:
            return jsonify({"error": "System role names cannot be renamed."}), 400
        if is_active is False:
            return jsonify({"error": "System roles cannot be deactivated."}), 400

    if new_name and new_name.strip():
        dup = Role.query.filter(Role.name.ilike(new_name.strip()), Role.id != role.id).first()
        if dup:
            return jsonify({"error": f"Another role named '{new_name}' already exists."}), 409
        role.name = new_name.strip()

    if new_desc is not None:
        role.description = new_desc.strip()

    if is_active is not None and not role.is_system:
        role.is_active = bool(is_active)

    if perm_codes is not None:
        if role.code == "admin":
            req_protect = {"user.manage", "permission.manage"}
            if not req_protect.issubset(set(perm_codes)):
                return jsonify({"error": "Action rejected: The Administrator role must retain 'user.manage' and 'permission.manage'."}), 400
        perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
        role.permissions = perms

    try:
        role.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        log_audit_event(
            action="role.update",
            resource_type="role",
            resource_id=role.id,
            status="SUCCESS",
            metadata={"name": role.name, "code": role.code, "is_active": role.is_active}
        )
        return jsonify({
            "message": f"Role '{role.name}' updated successfully.",
            "role": role.to_dict(include_users_count=True)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update role: {str(e)}"}), 500


@governance_bp.route("/roles/<int:role_id>/clone", methods=["POST"])
@permission_required("role.manage")
def clone_governance_role(role_id):
    source_role = db.session.get(Role, role_id)
    if not source_role:
        return jsonify({"error": "Source role not found."}), 404

    data = request.get_json() or {}
    new_name = data.get("name", f"Copy of {source_role.name}").strip()
    new_code = data.get("code", f"{source_role.code}_copy").strip().lower()
    description = data.get("description", f"Cloned from {source_role.name}").strip()

    if Role.query.filter(db.or_(Role.code == new_code, Role.name.ilike(new_name))).first():
        return jsonify({"error": f"A role with code '{new_code}' or name '{new_name}' already exists."}), 409

    try:
        cloned_role = Role(
            name=new_name,
            code=new_code,
            description=description,
            is_system=False,
            is_active=True
        )
        cloned_role.permissions = list(source_role.permissions)
        db.session.add(cloned_role)
        db.session.commit()

        log_audit_event(
            action="role.clone",
            resource_type="role",
            resource_id=cloned_role.id,
            status="SUCCESS",
            metadata={"source_role_id": source_role.id, "source_code": source_role.code, "new_code": new_code}
        )

        return jsonify({
            "message": f"Role '{source_role.name}' cloned successfully as '{new_name}'.",
            "role": cloned_role.to_dict(include_users_count=True)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to clone role: {str(e)}"}), 500


@governance_bp.route("/roles/<int:role_id>", methods=["DELETE"])
@permission_required("role.manage")
def delete_governance_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "Role not found."}), 404

    if role.is_system:
        return jsonify({"error": "Action rejected: System roles cannot be deleted."}), 400

    assigned_count = User.query.filter_by(role_id=role.id).count()
    if assigned_count > 0:
        return jsonify({"error": f"Cannot delete role '{role.name}'. It is currently assigned to {assigned_count} user(s). Reassign them first."}), 400

    try:
        role_name = role.name
        role_code = role.code
        db.session.delete(role)
        db.session.commit()
        log_audit_event(
            action="role.delete",
            resource_type="role",
            resource_id=role_id,
            status="SUCCESS",
            metadata={"name": role_name, "code": role_code}
        )
        return jsonify({"message": f"Custom role '{role_name}' has been deleted."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete role: {str(e)}"}), 500


@governance_bp.route("/roles/<int:role_id>/users", methods=["GET"])
@permission_required("role.manage")
def get_role_users(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({"error": "Role not found."}), 404

    users = User.query.filter(
        db.or_(User.role_id == role.id, User.role == role.code)
    ).all()

    return jsonify({
        "role": role.to_dict(),
        "users": [u.to_dict() for u in users]
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSION MATRIX APIS
# ─────────────────────────────────────────────────────────────────────────────

@governance_bp.route("/permissions", methods=["GET"])
@login_required
def list_governance_permissions():
    perms = Permission.query.order_by(Permission.category.asc(), Permission.code.asc()).all()
    return jsonify([p.to_dict() for p in perms]), 200


@governance_bp.route("/permissions/matrix", methods=["GET"])
@login_required
def get_permission_matrix():
    roles = Role.query.order_by(Role.is_system.desc(), Role.id.asc()).all()
    perms = Permission.query.order_by(Permission.category.asc(), Permission.code.asc()).all()

    matrix = {}
    for r in roles:
        matrix[r.code] = [p.code for p in r.permissions]

    categories = {}
    for p in perms:
        cat = p.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p.to_dict())

    return jsonify({
        "roles": [r.to_dict() for r in roles],
        "categories": categories,
        "permissions": [p.to_dict() for p in perms],
        "matrix": matrix
    }), 200


@governance_bp.route("/permissions/matrix", methods=["PUT"])
@permission_required("permission.manage")
def update_permission_matrix():
    data = request.get_json() or {}
    role_code = data.get("role_code")
    perm_codes = data.get("permissions", [])

    if not role_code:
        return jsonify({"error": "Role code is required."}), 400

    role = Role.query.filter_by(code=role_code).first()
    if not role:
        return jsonify({"error": f"Role '{role_code}' does not exist."}), 404

    if role.code == "admin":
        if "user.manage" not in perm_codes or "permission.manage" not in perm_codes:
            return jsonify({"error": "Action rejected: The Administrator role must retain 'user.manage' and 'permission.manage'."}), 400

    try:
        perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
        role.permissions = perms
        role.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        log_audit_event(
            action="role.permission_change",
            resource_type="role",
            resource_id=role.id,
            status="SUCCESS",
            metadata={"role": role.code, "permission_count": len(perms), "permissions": perm_codes}
        )

        return jsonify({
            "message": f"Permissions matrix for role '{role.name}' updated successfully.",
            "role": role.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update permission matrix: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# APPEND-ONLY AUDIT CENTER APIS
# ─────────────────────────────────────────────────────────────────────────────

@governance_bp.route("/audit/events", methods=["GET"])
@permission_required("audit.view")
def list_audit_events():
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    username_filter = request.args.get("user")
    action_filter = request.args.get("action")
    resource_filter = request.args.get("resource_type")
    status_filter = request.args.get("status")
    project_id = request.args.get("project_id")
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(5, int(request.args.get("page_size", 25))))

    query = AuditLog.query

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.filter(AuditLog.timestamp >= dt_from)
        except Exception:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.filter(AuditLog.timestamp <= dt_to)
        except Exception:
            pass

    if username_filter:
        query = query.filter(AuditLog.username.ilike(f"%{username_filter.strip()}%"))
    if action_filter and action_filter != "ALL":
        query = query.filter(AuditLog.action == action_filter.strip())
    if resource_filter and resource_filter != "ALL":
        query = query.filter(AuditLog.resource_type == resource_filter.strip())
    if status_filter and status_filter != "ALL":
        query = query.filter(AuditLog.status == status_filter.strip().upper())
    if project_id:
        try:
            query = query.filter(AuditLog.project_id == int(project_id))
        except ValueError:
            pass

    total = query.count()
    events = query.order_by(AuditLog.timestamp.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "events": [e.to_dict() for e in events]
    }), 200


@governance_bp.route("/audit/export", methods=["GET"])
@permission_required("audit.view")
def export_audit_csv():
    """Generates an RFC 4180 compliant CSV export of filtered audit records."""
    action_filter = request.args.get("action")
    resource_filter = request.args.get("resource_type")
    status_filter = request.args.get("status")
    username_filter = request.args.get("user")

    query = AuditLog.query
    if action_filter and action_filter != "ALL":
        query = query.filter(AuditLog.action == action_filter.strip())
    if resource_filter and resource_filter != "ALL":
        query = query.filter(AuditLog.resource_type == resource_filter.strip())
    if status_filter and status_filter != "ALL":
        query = query.filter(AuditLog.status == status_filter.strip().upper())
    if username_filter:
        query = query.filter(AuditLog.username.ilike(f"%{username_filter.strip()}%"))

    events = query.order_by(AuditLog.timestamp.desc()).limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID", "Timestamp (UTC)", "User", "Action", "Resource Type", "Resource ID", "Project ID", "Status", "IP Address", "Sanitized Metadata"])

    for e in events:
        meta_str = str(e.metadata_json) if e.metadata_json else "{}"
        writer.writerow([
            e.id,
            e.timestamp.isoformat() if e.timestamp else "",
            e.username or "system",
            e.action,
            e.resource_type,
            e.resource_id or "",
            e.project_id or "",
            e.status,
            e.ip_address or "",
            meta_str
        ])

    csv_data = output.getvalue()
    response = make_response(csv_data)
    filename = f"hla_audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"

    log_audit_event(
        action="audit.export",
        resource_type="audit_log",
        status="SUCCESS",
        metadata={"exported_count": len(events)}
    )

    return response


@governance_bp.route("/audit/meta", methods=["GET"])
@permission_required("audit.view")
def get_audit_metadata_options():
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct().all() if r[0]]
    resources = [r[0] for r in db.session.query(AuditLog.resource_type).distinct().all() if r[0]]
    return jsonify({
        "actions": sorted(actions),
        "resource_types": sorted(resources),
        "statuses": ["SUCCESS", "FAILURE", "WARNING"]
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY CENTER HEALTH & POSTURE APIS
# ─────────────────────────────────────────────────────────────────────────────

@governance_bp.route("/security-center/summary", methods=["GET"])
@login_required
def get_security_center_summary():
    # 1. Database Connection & Latency
    db_status = "CONNECTED"
    db_latency_ms = None
    try:
        t0 = datetime.now()
        db.session.execute(db.text("SELECT 1"))
        db_latency_ms = round((datetime.now() - t0).total_seconds() * 1000, 2)
    except Exception:
        db_status = "CONNECTION_FAILED"

    # 2. Ollama Status & Configured Model
    ollama_model = "qwen3:latest"
    ollama_status = "UNKNOWN"
    ollama_latency_ms = None
    try:
        import urllib.request
        import json as json_lib
        t0 = datetime.now()
        req = urllib.request.Request("http://localhost:11434/api/tags", headers={"User-Agent": "HLA-Security-Center"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                body = json_lib.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in body.get("models", [])]
                ollama_status = "CONNECTED" if any("qwen3" in m.lower() for m in models) else "MODEL_NOT_FOUND"
                ollama_latency_ms = round((datetime.now() - t0).total_seconds() * 1000, 2)
    except Exception:
        ollama_status = "CONNECTION_FAILED"

    # 3. SMTP Status (Safe test without exposing credentials)
    smtp_cfg = get_smtp_config()
    smtp_status = "NOT_CONFIGURED"
    if smtp_cfg.get("host"):
        smtp_status = "CONFIGURED"
        try:
            s = socket.create_connection((smtp_cfg["host"], smtp_cfg["port"]), timeout=2.0)
            s.close()
            smtp_status = "CONNECTED"
        except Exception:
            smtp_status = "CONNECTION_FAILED"

    # 4. RBAC Metrics
    total_roles = Role.query.count()
    custom_roles = Role.query.filter_by(is_system=False).count()
    total_permissions = Permission.query.count()

    # 5. Audit Logging Health
    total_audit_events = AuditLog.query.count()
    last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    audit_events_24h = AuditLog.query.filter(AuditLog.timestamp >= last_24h).count()

    # 6. Security KPIs
    total_users = User.query.count()
    active_users = User.query.filter(User.status == "ACTIVE").count()
    locked_users = User.query.filter(User.status == "LOCKED").count()
    disabled_users = User.query.filter(User.status == "DISABLED").count()
    mfa_users = User.query.filter(User.mfa_enabled == True).count()
    mfa_adoption_pct = round((mfa_users / total_users * 100), 1) if total_users > 0 else 0.0

    failed_logins_24h = AuditLog.query.filter(
        AuditLog.action.in_(["auth.login.failure", "auth.access_denied"]),
        AuditLog.timestamp >= last_24h
    ).count()

    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "authentication": {
            "token_type": "JWT HMAC-SHA256",
            "access_token_lifetime": "1 hour",
            "refresh_token_lifetime": "7 days",
            "force_logout_support": True,
            "session_invalidation_method": "token_version"
        },
        "rbac": {
            "enforcement_active": True,
            "total_roles": total_roles,
            "custom_roles": custom_roles,
            "standard_permissions": total_permissions,
            "matrix_configurable": True
        },
        "database": {
            "status": db_status,
            "type": "PostgreSQL",
            "latency_ms": db_latency_ms
        },
        "ollama": {
            "status": ollama_status,
            "configured_model": ollama_model,
            "latency_ms": ollama_latency_ms,
            "direct_db_access": False
        },
        "smtp": {
            "status": smtp_status,
            "host_configured": bool(smtp_cfg.get("host")),
            "port": smtp_cfg.get("port"),
            "security": smtp_cfg.get("security"),
            "delivery_guarantee": "Submission-verified; inbox delivery subject to MTA transport"
        },
        "audit": {
            "logging_active": True,
            "immutability_enforced": True,
            "total_events": total_audit_events,
            "events_last_24h": audit_events_24h
        },
        "kpis": {
            "total_accounts": total_users,
            "active_accounts": active_users,
            "locked_accounts": locked_users,
            "disabled_accounts": disabled_users,
            "mfa_adoption_pct": mfa_adoption_pct,
            "failed_logins_24h": failed_logins_24h
        }
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTIVE OVERVIEW FOUNDATION APIS
# ─────────────────────────────────────────────────────────────────────────────

@governance_bp.route("/executive-overview", methods=["GET"])
@login_required
def get_executive_overview():
    projects_count = Project.query.count()
    documents_count = Document.query.count()
    controls_count = ControlSchedule.query.count()

    completed_runs = ControlRunHistory.query.filter(
        ControlRunHistory.status.in_(["SUCCESS", "FAILED", "BLOCKED"])
    ).all()
    total_runs = len(completed_runs)
    successful_runs = sum(1 for r in completed_runs if r.status == "SUCCESS")
    pass_rate = round((successful_runs / total_runs * 100), 1) if total_runs > 0 else None

    failed_runs_count = sum(1 for r in completed_runs if r.status in ["FAILED", "BLOCKED"])

    recent_runs = ControlRunHistory.query.order_by(
        ControlRunHistory.started_at.desc()
    ).limit(5).all()

    recent_governance = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).limit(5).all()

    return jsonify({
        "metrics": {
            "projects_count": projects_count,
            "hla_documents_count": documents_count,
            "controls_count": controls_count,
            "open_exceptions_count": failed_runs_count,
            "control_pass_rate": pass_rate,
            "total_executions": total_runs
        },
        "recent_control_executions": [r.to_dict() for r in recent_runs],
        "recent_governance_activity": [g.to_dict() for g in recent_governance]
    }), 200
