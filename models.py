import os
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="architect", nullable=False)  # admin, architect, viewer
    token_version = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    projects = db.relationship("Project", backref="creator", lazy=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "token_version": self.token_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User id={self.id} username='{self.username}' role='{self.role}'>"


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = db.Column(db.String(255), nullable=True)
    otp_hash = db.Column(db.String(255), nullable=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    max_attempts = db.Column(db.Integer, default=5, nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reset_token = db.Column(db.String(128), unique=True, nullable=True, index=True)
    reset_token_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref=db.backref("reset_tokens", cascade="all, delete-orphan", lazy=True))

    def set_otp(self, otp_plain: str):
        self.otp_hash = generate_password_hash(otp_plain)

    def check_otp(self, otp_plain: str) -> bool:
        if not self.otp_hash:
            return False
        return check_password_hash(self.otp_hash, otp_plain)

    def is_otp_valid(self) -> bool:
        if self.used or self.verified:
            return False
        if self.attempts >= self.max_attempts:
            return False
        exp = self.expires_at
        if not exp:
            return False
        if exp.tzinfo is None:
            return exp > datetime.now()
        return exp > datetime.now(timezone.utc)

    def is_reset_token_valid(self) -> bool:
        if self.used or not self.verified or not self.reset_token:
            return False
        exp = self.reset_token_expires_at or self.expires_at
        if not exp:
            return False
        if exp.tzinfo is None:
            return exp > datetime.now()
        return exp > datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "verified": self.verified,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "used": self.used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    folder_path = db.Column(db.String(500), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    documents = db.relationship("Document", backref="project", cascade="all, delete-orphan", lazy=True)
    db_connections = db.relationship("DBConnection", backref="project", cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_details=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "folder_path": self.folder_path,
            "created_by_id": self.created_by_id,
            "created_by": self.creator.username if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "document_count": len(self.documents),
            "connection_count": len(self.db_connections),
        }
        if include_details:
            data["documents"] = [d.to_dict() for d in self.documents]
            data["db_connections"] = [c.to_dict() for c in self.db_connections]
        return data

    def __repr__(self):
        return f"<Project id={self.id} name='{self.name}'>"


class DBConnection(db.Model):
    __tablename__ = "db_connections"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_db_name = db.Column(db.String(100), nullable=False)  # e.g. "24b", "24a", "RA Recon db", "Target Dev", "Target Prod"
    conn_role = db.Column(db.String(20), default="source", nullable=False)  # "source" or "target"
    target_env = db.Column(db.String(20), default="none", nullable=False)  # "none", "dev", "prod"
    schema_name = db.Column(db.String(100), default="public", nullable=True)
    db_type = db.Column(db.String(50), default="postgresql", nullable=False)  # postgresql, mysql, mssql, oracle, sqlite, sandbox, snowflake
    host = db.Column(db.String(255), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    database_name = db.Column(db.String(100), nullable=True)
    username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(255), nullable=True)
    connection_string = db.Column(db.String(500), nullable=True)
    vault_profile = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default="not_configured", nullable=False)
    last_tested = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "source_db_name": self.source_db_name,
            "conn_role": self.conn_role,
            "target_env": self.target_env,
            "schema_name": self.schema_name or "public",
            "db_type": self.db_type,
            "host": self.host,
            "port": self.port,
            "database_name": self.database_name,
            "username": self.username,
            "has_password": bool(self.password),
            "connection_string": self.connection_string,
            "vault_profile": self.vault_profile,
            "status": self.status,
            "last_tested": self.last_tested.isoformat() if self.last_tested else None,
        }

    def __repr__(self):
        return f"<DBConnection id={self.id} source_db='{self.source_db_name}' role='{self.conn_role}' env='{self.target_env}'>"


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False, default=0)
    file_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="uploaded")
    metadata_json = db.Column(db.JSON, nullable=True)
    analysis_data = db.Column(db.JSON, nullable=True)
    generated_doc_path = db.Column(db.String(500), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    target_artifacts = db.relationship("TargetArtifact", backref="document", cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "filename": self.filename,
            "original_name": self.original_name,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "file_path": self.file_path,
            "status": self.status,
            "metadata": self.metadata_json or {},
            "analysis": self.analysis_data,
            "has_generated_doc": bool(self.generated_doc_path and os.path.exists(self.generated_doc_path)),
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "target_artifact_count": len(self.target_artifacts),
        }

    def __repr__(self):
        return f"<Document id={self.id} filename='{self.filename}'>"


class TargetArtifact(db.Model):
    __tablename__ = "target_artifacts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    environment = db.Column(db.String(20), default="dev", nullable=False)  # 'dev' or 'prod'
    target_dialect = db.Column(db.String(50), default="postgresql", nullable=False)
    target_schema = db.Column(db.String(100), default="target_dev", nullable=False)
    source_tables_ddl = db.Column(db.Text, nullable=True)
    generated_ddl = db.Column(db.Text, nullable=True)
    generated_transformation_sql = db.Column(db.Text, nullable=True)
    generated_pyspark_code = db.Column(db.Text, nullable=True)
    target_schema_json = db.Column(db.JSON, nullable=True)
    llm_reasoning = db.Column(db.Text, nullable=True)
    deployment_status = db.Column(db.String(50), default="draft", nullable=False)  # 'draft', 'validated', 'deployed', 'failed'
    deployment_log = db.Column(db.Text, nullable=True)
    deployed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    project = db.relationship("Project", backref=db.backref("target_artifacts", cascade="all, delete-orphan", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "environment": self.environment,
            "target_dialect": self.target_dialect,
            "target_schema": self.target_schema,
            "source_tables_ddl": self.source_tables_ddl or "",
            "generated_ddl": self.generated_ddl or "",
            "generated_transformation_sql": self.generated_transformation_sql or "",
            "generated_pyspark_code": self.generated_pyspark_code or "",
            "target_schema_json": self.target_schema_json or {},
            "llm_reasoning": self.llm_reasoning or "",
            "deployment_status": self.deployment_status,
            "deployment_log": self.deployment_log or "",
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<TargetArtifact id={self.id} env='{self.environment}' status='{self.deployment_status}'>"


class ControlSchedule(db.Model):
    __tablename__ = "control_schedules"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    control_number = db.Column(db.String(100), nullable=True, default=None)
    environment = db.Column(db.String(20), default="dev", nullable=False)  # 'dev' or 'prod'
    schedule_type = db.Column(db.String(50), default="daily", nullable=False)  # 'hourly', 'daily', 'weekly', 'monthly', 'interval', 'custom_cron'
    cron_expression = db.Column(db.String(100), nullable=True)  # e.g. "0 2 * * *"
    run_time = db.Column(db.String(20), nullable=True, default="02:00")  # "02:00"
    days_of_week = db.Column(db.String(100), nullable=True, default="mon,tue,wed,thu,fri")
    day_of_month = db.Column(db.String(20), default="1", nullable=True)  # e.g. '1', '15', 'last'
    interval_minutes = db.Column(db.Integer, nullable=True)  # e.g. 60
    timezone_name = db.Column(db.String(50), default="UTC", nullable=False)
    hostname = db.Column(db.String(255), nullable=True)
    notification_emails = db.Column(db.Text, nullable=True)  # e.g. "alerts@org.com, oncall@org.com"
    notify_on_failure = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    next_run_at = db.Column(db.DateTime, nullable=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_run_status = db.Column(db.String(50), nullable=True)  # 'SUCCESS', 'BLOCKED', 'FAILED', 'RUNNING'
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    project = db.relationship("Project", backref=db.backref("schedules", cascade="all, delete-orphan", lazy=True))
    document = db.relationship("Document", backref=db.backref("schedules", cascade="all, delete-orphan", lazy=True))
    creator = db.relationship("User", backref="created_schedules", lazy=True)
    runs = db.relationship("ControlRunHistory", backref="schedule", cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        doc_name = self.document.original_name if self.document else (self.document.filename if self.document else None)
        ctrl_num = self.control_number
        if not ctrl_num and self.document and self.document.analysis_data:
            ctrl_num = self.document.analysis_data.get("control_overview", {}).get("identification", {}).get("control_number")
        return {
            "id": self.id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "document_name": doc_name,
            "name": self.name,
            "control_number": ctrl_num or "",
            "environment": self.environment,
            "schedule_type": self.schedule_type,
            "cron_expression": self.cron_expression,
            "run_time": self.run_time,
            "days_of_week": self.days_of_week,
            "day_of_month": self.day_of_month or "1",
            "interval_minutes": self.interval_minutes,
            "timezone": self.timezone_name,
            "hostname": self.hostname or "",
            "notification_emails": self.notification_emails or "",
            "notify_on_failure": self.notify_on_failure if self.notify_on_failure is not None else True,
            "is_active": self.is_active,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_status": self.last_run_status,
            "created_by": self.creator.username if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "total_runs": len(self.runs) if self.runs else 0,
        }

    def __repr__(self):
        return f"<ControlSchedule id={self.id} name='{self.name}' active={self.is_active}>"


class EmailNotificationLog(db.Model):
    __tablename__ = "email_notification_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("control_schedules.id", ondelete="SET NULL"), nullable=True)
    run_history_id = db.Column(db.Integer, db.ForeignKey("control_run_history.id", ondelete="SET NULL"), nullable=True)
    recipient_emails = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(500), nullable=False)
    body_text = db.Column(db.Text, nullable=False)
    body_html = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default="SENT", nullable=False)  # 'SENT', 'DISPATCHED (SIMULATED)', 'FAILED'
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "schedule_id": self.schedule_id,
            "run_history_id": self.run_history_id,
            "recipient_emails": self.recipient_emails,
            "subject": self.subject,
            "body_text": self.body_text,
            "body_html": self.body_html,
            "status": self.status,
            "error_message": self.error_message,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


class ControlRunHistory(db.Model):
    __tablename__ = "control_run_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("control_schedules.id", ondelete="SET NULL"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    control_number = db.Column(db.String(100), nullable=True, default=None)
    environment = db.Column(db.String(20), default="dev", nullable=False)
    hostname = db.Column(db.String(255), nullable=True)
    trigger_type = db.Column(db.String(50), default="SCHEDULED", nullable=False)  # 'SCHEDULED' or 'MANUAL'
    status = db.Column(db.String(50), default="RUNNING", nullable=False)  # 'RUNNING', 'SUCCESS', 'BLOCKED', 'FAILED'
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    tables_checked_count = db.Column(db.Integer, default=0, nullable=False)
    tables_found_count = db.Column(db.Integer, default=0, nullable=False)
    tables_missing_count = db.Column(db.Integer, default=0, nullable=False)
    summary_message = db.Column(db.Text, nullable=True)
    execution_log = db.Column(db.Text, nullable=True)
    result_details = db.Column(db.JSON, nullable=True)

    project = db.relationship("Project", backref=db.backref("control_runs", cascade="all, delete-orphan", lazy=True))
    document = db.relationship("Document", backref=db.backref("control_runs", cascade="all, delete-orphan", lazy=True))

    def to_dict(self):
        doc_name = self.document.original_name if self.document else (self.document.filename if self.document else None)
        return {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "schedule_name": self.schedule.name if self.schedule else None,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "document_name": doc_name,
            "control_number": self.control_number,
            "environment": self.environment,
            "hostname": self.hostname or "",
            "trigger_type": self.trigger_type,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 2) if self.duration_seconds is not None else None,
            "tables_checked_count": self.tables_checked_count,
            "tables_found_count": self.tables_found_count,
            "tables_missing_count": self.tables_missing_count,
            "summary_message": self.summary_message,
            "execution_log": self.execution_log or "",
            "result_details": self.result_details or {},
        }

    def __repr__(self):
        return f"<ControlRunHistory id={self.id} ctrl='{self.control_number}' status='{self.status}'>"


class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<SystemSetting key='{self.key}'>"


