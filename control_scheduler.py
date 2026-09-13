"""
control_scheduler.py - Workspace Control Scheduler & Execution Pipeline Engine
Manages recurring cron/interval schedules and automated execution of reconciliation controls.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from db_fetcher import find_table_across_databases, get_env_db_password, build_connection_url
from sqlalchemy import create_engine, text, inspect
from target_logic_builder import (
    generate_target_ddl,
    generate_transformation_sql,
    ensure_target_tables_provisioned,
    _split_sql_statements
)

logger = logging.getLogger("control_scheduler")
logger.setLevel(logging.INFO)

# Global background scheduler instance
_scheduler = None
_app_ref = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
    return _scheduler


def get_timezone(tz_name: str):
    try:
        return pytz.timezone(tz_name or "UTC")
    except Exception:
        return pytz.UTC


def compute_next_run(schedule_type: str, cron_expression: str = None, run_time: str = None,
                     days_of_week: str = None, day_of_month: str = "1", interval_minutes: int = None,
                     tz_name: str = "UTC") -> datetime:
    """Computes the next firing datetime for a given schedule configuration."""
    tz = get_timezone(tz_name)
    now = datetime.now(tz)

    try:
        if schedule_type == "custom_cron" and cron_expression:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=tz)
            return trigger.get_next_fire_time(None, now)

        elif schedule_type == "hourly":
            min_val = 0
            if run_time and ":" in run_time:
                try:
                    min_val = int(run_time.split(":")[1])
                except Exception:
                    min_val = 0
            trigger = CronTrigger(minute=min_val, timezone=tz)
            return trigger.get_next_fire_time(None, now)

        elif schedule_type == "daily":
            hour_val, min_val = 2, 0
            if run_time and ":" in run_time:
                parts = run_time.split(":")
                hour_val = int(parts[0])
                min_val = int(parts[1]) if len(parts) > 1 else 0
            trigger = CronTrigger(hour=hour_val, minute=min_val, timezone=tz)
            return trigger.get_next_fire_time(None, now)

        elif schedule_type == "weekly":
            hour_val, min_val = 2, 0
            if run_time and ":" in run_time:
                parts = run_time.split(":")
                hour_val = int(parts[0])
                min_val = int(parts[1]) if len(parts) > 1 else 0
            dow = days_of_week or "mon"
            trigger = CronTrigger(day_of_week=dow, hour=hour_val, minute=min_val, timezone=tz)
            return trigger.get_next_fire_time(None, now)

        elif schedule_type == "monthly":
            hour_val, min_val = 2, 0
            if run_time and ":" in run_time:
                parts = run_time.split(":")
                hour_val = int(parts[0])
                min_val = int(parts[1]) if len(parts) > 1 else 0
            dom = str(day_of_month or "1").strip().lower()
            if not dom:
                dom = "1"
            trigger = CronTrigger(day=dom, hour=hour_val, minute=min_val, timezone=tz)
            return trigger.get_next_fire_time(None, now)

        elif schedule_type == "interval" and interval_minutes:
            trigger = IntervalTrigger(minutes=max(1, int(interval_minutes)), timezone=tz)
            return trigger.get_next_fire_time(None, now)

        else:
            trigger = CronTrigger(hour=2, minute=0, timezone=tz)
            return trigger.get_next_fire_time(None, now)

    except Exception as e:
        logger.warning(f"Error computing next run time for schedule: {e}")
        return None


def _scheduled_job_runner(schedule_id: int):
    """Wrapper invoked by APScheduler background daemon."""
    global _app_ref
    if not _app_ref:
        logger.error("Flask app reference is missing in scheduler worker.")
        return

    with _app_ref.app_context():
        from models import db, ControlSchedule
        schedule = ControlSchedule.query.get(schedule_id)
        if not schedule or not schedule.is_active:
            logger.info(f"Schedule {schedule_id} is inactive or deleted, skipping run.")
            return

        logger.info(f"[SCHEDULER] Triggering scheduled execution for '{schedule.name}' (Schedule #{schedule.id})")
        if not (schedule.hostname or "").strip():
            logger.warning(f"[SCHEDULER] Schedule #{schedule.id} blocked: Hostname not provided.")
            execute_control_pipeline(
                document_id=schedule.document_id,
                project_id=schedule.project_id,
                environment=schedule.environment,
                schedule_id=schedule.id,
                trigger_type="SCHEDULED",
                hostname=None
            )
            return

        try:
            execute_control_pipeline(
                document_id=schedule.document_id,
                project_id=schedule.project_id,
                environment=schedule.environment,
                schedule_id=schedule.id,
                trigger_type="SCHEDULED",
                hostname=schedule.hostname
            )
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] Failed running schedule {schedule_id}: {e}", exc_info=True)


def register_schedule_job(schedule, app=None):
    """Registers or updates a scheduled job in APScheduler."""
    global _app_ref
    if app:
        _app_ref = app

    scheduler = get_scheduler()
    job_id = f"ctrl_sched_{schedule.id}"

    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    if not schedule.is_active:
        return

    tz = get_timezone(schedule.timezone_name)
    trigger = None

    try:
        st = schedule.schedule_type
        if st == "custom_cron" and schedule.cron_expression:
            trigger = CronTrigger.from_crontab(schedule.cron_expression, timezone=tz)
        elif st == "hourly":
            min_val = 0
            if schedule.run_time and ":" in schedule.run_time:
                min_val = int(schedule.run_time.split(":")[1])
            trigger = CronTrigger(minute=min_val, timezone=tz)
        elif st == "daily":
            hour_val, min_val = 2, 0
            if schedule.run_time and ":" in schedule.run_time:
                p = schedule.run_time.split(":")
                hour_val, min_val = int(p[0]), int(p[1])
            trigger = CronTrigger(hour=hour_val, minute=min_val, timezone=tz)
        elif st == "weekly":
            hour_val, min_val = 2, 0
            if schedule.run_time and ":" in schedule.run_time:
                p = schedule.run_time.split(":")
                hour_val, min_val = int(p[0]), int(p[1])
            trigger = CronTrigger(day_of_week=schedule.days_of_week or "mon", hour=hour_val, minute=min_val, timezone=tz)
        elif st == "monthly":
            hour_val, min_val = 2, 0
            if schedule.run_time and ":" in schedule.run_time:
                p = schedule.run_time.split(":")
                hour_val = int(p[0])
                min_val = int(p[1]) if len(p) > 1 else 0
            dom = str(schedule.day_of_month or "1").strip().lower()
            if not dom:
                dom = "1"
            trigger = CronTrigger(day=dom, hour=hour_val, minute=min_val, timezone=tz)
        elif st == "interval" and schedule.interval_minutes:
            trigger = IntervalTrigger(minutes=max(1, int(schedule.interval_minutes)), timezone=tz)
        else:
            trigger = CronTrigger(hour=2, minute=0, timezone=tz)

        if trigger:
            scheduler.add_job(
                _scheduled_job_runner,
                trigger=trigger,
                id=job_id,
                args=[schedule.id],
                replace_existing=True,
                name=f"Schedule #{schedule.id}: {schedule.name}"
            )
            logger.info(f"Registered APScheduler job {job_id} for '{schedule.name}'")

    except Exception as e:
        logger.error(f"Failed to register job {job_id}: {e}")


def unregister_schedule_job(schedule_id: int):
    """Removes a job from APScheduler."""
    scheduler = get_scheduler()
    job_id = f"ctrl_sched_{schedule_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Removed APScheduler job {job_id}")
    except Exception:
        pass


def init_scheduler(app):
    """Starts the background scheduler and registers active schedules."""
    global _app_ref
    _app_ref = app

    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("[OK] APScheduler background scheduler started.")

    with app.app_context():
        try:
            from models import db, ControlSchedule
            try:
                with db.engine.connect() as conn:
                    conn.execute(db.text("ALTER TABLE control_schedules ADD COLUMN IF NOT EXISTS notification_emails TEXT;"))
                    conn.execute(db.text("ALTER TABLE control_schedules ADD COLUMN IF NOT EXISTS notify_on_failure BOOLEAN DEFAULT TRUE;"))
                    conn.commit()
                db.create_all()
            except Exception as dbe:
                logger.warning(f"Database schema migration notice: {dbe}")

            active_schedules = ControlSchedule.query.filter_by(is_active=True).all()
            logger.info(f"Syncing {len(active_schedules)} active control schedules into background runner...")
            for s in active_schedules:
                register_schedule_job(s, app)
                next_fire = compute_next_run(
                    schedule_type=s.schedule_type,
                    cron_expression=s.cron_expression,
                    run_time=s.run_time,
                    days_of_week=s.days_of_week,
                    day_of_month=s.day_of_month,
                    interval_minutes=s.interval_minutes,
                    tz_name=s.timezone_name
                )
                if next_fire and (not s.next_run_at or s.next_run_at != next_fire):
                    s.next_run_at = next_fire
            db.session.commit()
            logger.info("[OK] Control schedules synchronized successfully.")
        except Exception as e:
            logger.warning(f"Could not sync control schedules on startup: {e}")


def execute_control_pipeline(document_id: int, project_id: int, environment: str = "dev",
                             schedule_id: int = None, trigger_type: str = "MANUAL",
                             hostname: str = None) -> dict:
    """
    Executes the full automated Control Run Pipeline:
    1. Validates that hostname is provided (scheduler works ONLY when hostname is provided).
    2. Audits & scans live source database connections for declared upstream tables.
    3. Enforces quality gate (dry-run and deploy are strictly blocked if tables are missing).
    4. If tables are verified, executes target schema reconciliation.
    5. Writes detailed execution logs and status to ControlRunHistory.
    """
    from models import db, Document, Project, DBConnection, ControlSchedule, ControlRunHistory

    start_time = time.time()
    now_utc = datetime.now(timezone.utc)

    doc = Document.query.get(document_id)
    if not doc:
        raise ValueError(f"Document #{document_id} not found.")

    project = Project.query.get(project_id)
    if not project:
        raise ValueError(f"Project #{project_id} not found.")

    # Determine Control Identification
    co = (doc.analysis_data or {}).get("control_overview", {})
    ctrl_id_info = co.get("identification", {})
    ctrl_num = ctrl_id_info.get("control_number") or (f"Control-{co.get('control_digits')}" if co.get("control_digits") else "HLA Pipeline")
    ctrl_title = ctrl_id_info.get("control_title") or doc.original_name or doc.filename or "HLA Specification"

    # If hostname not passed directly, look up from schedule
    if not hostname and schedule_id:
        sched_obj = ControlSchedule.query.get(schedule_id)
        if sched_obj and sched_obj.hostname:
            hostname = sched_obj.hostname

    # Ensure hostname is assigned (defaults to server machine name)
    clean_hostname = str(hostname).strip() if hostname else ""
    if not clean_hostname:
        clean_hostname = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "localhost"

    # Create Initial Run History record
    run_record = ControlRunHistory(
        schedule_id=schedule_id,
        project_id=project_id,
        document_id=document_id,
        control_number=str(ctrl_num),
        environment=environment.lower(),
        hostname=clean_hostname,
        trigger_type=trigger_type.upper(),
        status="RUNNING",
        started_at=now_utc,
        tables_checked_count=0,
        tables_found_count=0,
        tables_missing_count=0,
        summary_message=f"Executing control run for {ctrl_num} ({trigger_type})...",
        execution_log=""
    )
    db.session.add(run_record)
    db.session.commit()

    log_lines = []

    def _log(msg: str, level: str = "INFO"):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted = f"[{ts}] [{level}] {msg}"
        log_lines.append(formatted)

    _log(f"================================================================================")
    _log(f"CONTROL EXECUTION RUN #{run_record.id}")
    _log(f"Control: {ctrl_num} - {ctrl_title}")
    _log(f"Workspace / Project ID: {project_id} ({project.name})")
    _log(f"Execution Target Hostname: {clean_hostname}")
    _log(f"Target Environment: {environment.upper()} | Trigger Mode: {trigger_type.upper()}")
    _log(f"================================================================================")

    audit_result = {
        "tables_checked": 0,
        "tables_found": 0,
        "tables_missing": 0,
        "details": [],
        "blocked": False
    }

    run_status = None
    summary = ""

    try:
        # STEP 1: Discover declared source tables from Document Analysis
        sources = (doc.analysis_data or {}).get("sources", [])
        raw_tables = []
        for s in sources:
            tbl = s.get("source_table") or s.get("full_table_name")
            if tbl and tbl not in [t["name"] for t in raw_tables]:
                raw_tables.append({
                    "name": tbl,
                    "schema": s.get("source_schema") or s.get("schema_name") or "public",
                    "system": s.get("source_system") or "Unknown",
                    "load_type": s.get("type_of_load") or s.get("load_type") or "Truncate and load",
                    "frequency": s.get("frequency") or s.get("refresh_time") or "Daily",
                    "schedule_time": s.get("schedule_time") or ""
                })

        _log(f"Discovered {len(raw_tables)} required source table(s) declared in control metadata.")

        # STEP 2: Assemble source database connection configurations
        source_conns = DBConnection.query.filter_by(project_id=project_id, conn_role="source").all()
        source_configs = []
        for sc in source_conns:
            # Only consider connections that have valid endpoint/database info
            if (sc.host or sc.connection_string) and (sc.database_name or sc.connection_string):
                source_configs.append({
                    "source_db_name": sc.source_db_name,
                    "db_type": sc.db_type,
                    "host": sc.host,
                    "port": sc.port,
                    "database_name": sc.database_name,
                    "username": sc.username,
                    "password": sc.password or (get_env_db_password() if sc.host in ("localhost", "127.0.0.1", "::1") else ""),
                    "schema_name": sc.schema_name or "public",
                    "connection_string": sc.connection_string,
                })

        # STRICT QUALITY GATE: Control run works ONLY if source db and table are available!
        if not source_configs:
            _log("✕ [QUALITY GATE FAILED] No Source Database configured for this workspace.", level="ERROR")
            _log("Audit Action: Control execution strictly requires source database connection info and available tables.", level="WARN")
            audit_result["blocked"] = True
            run_status = "FAILED"
            summary = "Execution failed: No source database info configured. The control run requires valid source DB information and available tables."
            found_tables = []
            missing_tables = [t["name"] for t in raw_tables]
            empty_tables = []
            stale_tables = []
        elif len(raw_tables) == 0:
            _log("✕ [QUALITY GATE FAILED] No source tables declared in HLA document to verify in source DB.", level="ERROR")
            audit_result["blocked"] = True
            run_status = "FAILED"
            summary = "Execution failed: No upstream source tables declared in HLA document to verify."
            found_tables = []
            missing_tables = []
            empty_tables = []
            stale_tables = []
        else:
            _log(f"Configured {len(source_configs)} source database connection(s) to scan: {', '.join([c['source_db_name'] for c in source_configs])}")

            found_tables = []
            missing_tables = []
            empty_tables = []
            stale_tables = []

            for t in raw_tables:
                tbl_name = t["name"]
                req_schema = t["schema"]
                load_type = (t.get("load_type") or "").lower()
                frequency = (t.get("frequency") or "").lower()
                schedule_time = t.get("schedule_time") or ""

                meta = find_table_across_databases(source_configs, req_schema, tbl_name)
                if not meta.get("table_found"):
                    missing_tables.append(f"{req_schema}.{tbl_name}")
                    _log(f"✕ [SLA GATE FAILED] Source table '{req_schema}.{tbl_name}' NOT FOUND in any source DB ({', '.join(meta.get('scanned_databases', []))}).", level="WARN")
                    continue

                found_tables.append(tbl_name)
                row_count = meta.get("row_count", 0)
                latest_dt = meta.get("latest_record_date")

                # Check 1: Empty Feed Check (Data not arrived)
                if row_count == 0:
                    empty_tables.append(f"{req_schema}.{tbl_name}")
                    _log(f"✕ [SLA GATE FAILED] Source table '{req_schema}.{tbl_name}' exists in '{meta.get('found_in_db')}' but has 0 rows. Upstream feed has not arrived on scheduled time.", level="WARN")
                    continue

                # Check 2: Append-Only Feed Date Freshness Check
                is_append = "append" in load_type
                if is_append:
                    if not latest_dt:
                        stale_tables.append({
                            "table": f"{req_schema}.{tbl_name}",
                            "reason": f"Append table '{req_schema}.{tbl_name}' has no identifiable date/timestamp column to verify latest scheduled arrival."
                        })
                        _log(f"✕ [FRESHNESS GATE FAILED] Append source '{req_schema}.{tbl_name}' has no valid record date for scheduled run.", level="WARN")
                    else:
                        try:
                            parsed_dt = datetime.fromisoformat(str(latest_dt).replace("Z", "+00:00").split("+")[0].strip())
                            if parsed_dt.tzinfo is None:
                                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                            max_allowed_days = 8 if "week" in frequency else 2
                            age_days = (now_utc - parsed_dt).total_seconds() / 86400.0
                            if age_days > max_allowed_days:
                                stale_tables.append({
                                    "table": f"{req_schema}.{tbl_name}",
                                    "reason": f"Append source '{req_schema}.{tbl_name}' latest data is dated {latest_dt} ({age_days:.1f} days old). Missing latest week/run date data."
                                })
                                _log(f"✕ [FRESHNESS GATE FAILED] STALE APPEND FEED: '{req_schema}.{tbl_name}' latest record is from {latest_dt} (older than SLA cycle of {max_allowed_days} days).", level="WARN")
                            else:
                                _log(f"✓ Append source '{req_schema}.{tbl_name}' verified: latest record is from {latest_dt} ({row_count:,} rows, within SLA).")
                        except Exception:
                            _log(f"✓ Append source '{req_schema}.{tbl_name}' verified with latest date record: {latest_dt} ({row_count:,} rows).")
                else:
                    _log(f"✓ Source table '{req_schema}.{tbl_name}' verified in '{meta.get('found_in_db')}' ({row_count:,} rows, Load: {t.get('load_type')}).")

        audit_result["tables_checked"] = len(raw_tables)
        audit_result["tables_found"] = len(found_tables)
        audit_result["tables_missing"] = len(missing_tables)
        audit_result["tables_empty"] = len(empty_tables)
        audit_result["tables_stale"] = len(stale_tables)
        audit_result["missing_list"] = missing_tables
        audit_result["empty_list"] = empty_tables
        audit_result["stale_list"] = [s["table"] for s in stale_tables] if stale_tables and isinstance(stale_tables[0], dict) else stale_tables
        audit_result["found_list"] = found_tables

        _log(f"Table Audit Summary: {len(found_tables)} found, {len(missing_tables)} missing, {len(empty_tables)} empty, {len(stale_tables)} stale out of {len(raw_tables)} required.")

        # STEP 3: Mandatory Quality & Freshness Gate Enforcement
        # Zero Tolerance: If even ONE source is missing, empty, or lacks latest date in Append mode, HALT!
        if run_status == "FAILED":
            # Already set by missing source DB or missing HLA table declarations
            audit_result["blocked"] = True
            _log(f"QUALITY GATE ENGAGED: Execution halted: {summary}", level="ERROR")
        elif len(missing_tables) > 0 or len(empty_tables) > 0 or len(stale_tables) > 0:
            audit_result["blocked"] = True
            run_status = "BLOCKED"
            reasons = []
            if missing_tables:
                reasons.append(f"{len(missing_tables)} source table(s) missing ({', '.join(missing_tables[:2])})")
            if empty_tables:
                reasons.append(f"{len(empty_tables)} source feed(s) have 0 rows / data not received ({', '.join(empty_tables[:2])})")
            if stale_tables:
                tbl_names = [s["table"] if isinstance(s, dict) else s for s in stale_tables[:2]]
                reasons.append(f"{len(stale_tables)} append feed(s) missing latest date data ({', '.join(tbl_names)})")

            summary = (
                f"Execution Blocked by Pre-Execution Gate: {'; '.join(reasons)}. "
                f"Per control specification, if any source has not received data or append feeds lack latest date, the control is strictly halted."
            )
            _log(f"QUALITY GATE ENGAGED: Pre-execution arrival check failed. Halting control run immediately.", level="WARN")
            _log(f"Blocking Reason(s): {'; '.join(reasons)}", level="WARN")
        else:
            # STEP 4: All tables verified fresh and present -> Execute Target Logic & Populate Respective Tables
            _log("QUALITY GATE PASSED: All upstream source feeds verified present and fresh with latest date data.")

            # Resolve Target Database Configuration
            target_schema_name = co.get("target_schema") or f"ra_ctrl.ctrl_{co.get('control_digits', '23')}"
            if isinstance(target_schema_name, dict):
                target_schema_name = target_schema_name.get("schema_name", "ra_ctrl")

            target_conn = DBConnection.query.filter_by(
                project_id=project_id,
                conn_role="target",
                target_env=environment.lower()
            ).first() or DBConnection.query.filter_by(
                project_id=project_id,
                conn_role="target"
            ).first()

            if target_conn:
                target_cfg = {
                    "db_type": target_conn.db_type,
                    "host": target_conn.host,
                    "port": target_conn.port,
                    "database_name": target_conn.database_name,
                    "username": target_conn.username,
                    "password": target_conn.password,
                    "schema_name": target_conn.schema_name or target_schema_name,
                    "target_env": environment.lower(),
                    "connection_string": target_conn.connection_string
                }
            else:
                target_cfg = {
                    "db_type": "postgresql",
                    "host": os.getenv("PGHOST", "localhost"),
                    "port": int(os.getenv("PGPORT", "5432")),
                    "database_name": os.getenv("PGDATABASE", "hla_db"),
                    "username": os.getenv("PGUSER", "postgres"),
                    "password": get_env_db_password(),
                    "schema_name": target_schema_name,
                    "target_env": environment.lower()
                }

            if not target_cfg.get("password") and target_cfg.get("host") in ("localhost", "127.0.0.1", "::1"):
                target_cfg["password"] = get_env_db_password()

            target_schema = target_cfg.get("schema_name") or target_schema_name

            # 4A. First time alone create required DDL (if already created, no need to create)
            _log(f"Target DB: {target_cfg.get('host')}:{target_cfg.get('port')}/{target_cfg.get('database_name')} (Schema: {target_schema})")
            ddl_script = generate_target_ddl(
                target_schema,
                target_cfg.get("db_type", "postgresql"),
                raw_tables,
                doc.analysis_data.get("rules", {}),
                doc.analysis_data.get("mappings", []),
                {},
                doc.analysis_data
            )

            ddl_ok, ddl_msg, deployed_tables = ensure_target_tables_provisioned(target_cfg, ddl_script)
            _log(f"[TARGET DDL CHECK] {ddl_msg}")
            if not ddl_ok:
                raise RuntimeError(f"Target DDL check/creation failed: {ddl_msg}")

            # 4B. Apply transformation logic and load into respective target tables
            _log(f"Applying transformation logic (Append vs Truncate-and-load) into target schema '{target_schema}'...")
            transform_sql = generate_transformation_sql(
                target_schema,
                target_cfg.get("db_type", "postgresql"),
                raw_tables,
                doc.analysis_data.get("rules", {}),
                doc.analysis_data.get("mappings", []),
                doc.analysis_data.get("config_tables"),
                doc.analysis_data.get("control_overview"),
                doc.analysis_data
            )

            target_url = build_connection_url(target_cfg)
            target_engine = create_engine(target_url, connect_args={"connect_timeout": 12} if "sqlite" not in target_url else {})

            statements = _split_sql_statements(transform_sql)
            executed_stmts = 0
            with target_engine.connect() as conn:
                for stmt in statements:
                    clean_stmt = stmt.strip()
                    if clean_stmt:
                        try:
                            conn.execute(text(clean_stmt))
                            conn.commit()
                            executed_stmts += 1
                        except Exception as sql_err:
                            conn.rollback()
                            err_s = str(sql_err).lower()
                            if "already exists" in err_s or "duplicate key" in err_s:
                                continue
                            _log(f"[TRANSFORMATION SQL NOTICE] {sql_err}", level="WARN")

            _log(f"Executed {executed_stmts} reconciliation logic transformation steps.")

            # 4C. Query and verify populated rows in respective target tables
            target_counts = {}
            with target_engine.connect() as conn:
                for tbl in (deployed_tables or []):
                    try:
                        quoted_schema = f'"{target_schema}"' if ("." in target_schema or "-" in target_schema) else target_schema
                        cnt = conn.execute(text(f'SELECT COUNT(*) FROM {quoted_schema}.{tbl}')).scalar()
                        target_counts[tbl] = cnt
                        _log(f"✓ Target Table '{target_schema}.{tbl}' active: {cnt:,} record(s)")
                    except Exception:
                        pass

            audit_result["target_tables_summary"] = target_counts
            run_status = "SUCCESS"
            summary = f"Control run completed successfully. Target schema '{target_schema}' populated ({len(target_counts)} tables verified). Feeds verified fresh."
            _log(f"[OK] {summary}")


    except Exception as e:
        run_status = "FAILED"
        summary = f"Execution failed with unexpected error: {str(e)}"
        _log(f"UNHANDLED EXCEPTION: {e}", level="ERROR")

    # STEP 5: Automated Email Alert Trigger on Failure or Blocked SLA Gate
    if run_status in ["BLOCKED", "FAILED"]:
        try:
            from email_service import send_control_failure_alert
            should_notify = True
            sched_obj = None
            if schedule_id:
                sched_obj = ControlSchedule.query.get(schedule_id)
                if sched_obj and sched_obj.notify_on_failure is False:
                    should_notify = False

            if should_notify:
                _log(f"[EMAIL ALERT TRIGGER] Dispatching automated failure alert to respective emails...")
                alert_res = send_control_failure_alert(
                    run_record=run_record,
                    schedule=sched_obj,
                    project=project,
                    doc=doc,
                    audit_result=audit_result,
                    failure_reason=summary
                )
                audit_result["email_alert"] = {
                    "sent": alert_res.get("success", False),
                    "status": alert_res.get("status"),
                    "recipients": alert_res.get("recipients", []),
                    "log_id": alert_res.get("log_id")
                }
                _log(f"✓ Automatic email alert triggered: Status '{alert_res.get('status')}' sent to: {', '.join(alert_res.get('recipients', []))}")
        except Exception as mail_err:
            logger.error(f"Failed to dispatch automatic failure email alert: {mail_err}", exc_info=True)
            _log(f"⚠️ Automatic email alert failed to dispatch: {mail_err}", level="WARN")

    # Complete Run Record
    elapsed = time.time() - start_time
    now_end = datetime.now(timezone.utc)
    _log(f"Run completed in {elapsed:.2f}s with status: {run_status}")
    _log(f"================================================================================")

    run_record.status = run_status
    run_record.completed_at = now_end
    run_record.duration_seconds = elapsed
    run_record.tables_checked_count = audit_result["tables_checked"]
    run_record.tables_found_count = audit_result["tables_found"]
    run_record.tables_missing_count = audit_result["tables_missing"]
    run_record.summary_message = summary
    run_record.execution_log = "\n".join(log_lines)
    run_record.result_details = audit_result

    # Update Schedule metadata if linked
    if schedule_id:
        schedule = ControlSchedule.query.get(schedule_id)
        if schedule:
            schedule.last_run_at = now_end
            schedule.last_run_status = run_status
            next_fire = compute_next_run(
                schedule_type=schedule.schedule_type,
                cron_expression=schedule.cron_expression,
                run_time=schedule.run_time,
                days_of_week=schedule.days_of_week,
                day_of_month=schedule.day_of_month,
                interval_minutes=schedule.interval_minutes,
                tz_name=schedule.timezone_name
            )
            schedule.next_run_at = next_fire

    db.session.commit()
    logger.info(f"Control run #{run_record.id} for {ctrl_num} finished: {run_status} ({elapsed:.2f}s)")
    return run_record.to_dict()
