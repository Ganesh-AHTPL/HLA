"""
email_service.py - Automated Email Notification & Alerting Engine for HLA Studio
Handles failure alerts for scheduled and manual control runs.
Dispatches emails via SMTP (if configured) or logs alerts to the database for auditability.
"""

import os
import re
import smtplib
import logging
import shutil
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from models import db, User, EmailNotificationLog, SystemSetting

logger = logging.getLogger("email_service")
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

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_smtp_config() -> dict:
    """
    Dynamically loads SMTP configuration from the database (SystemSetting table),
    falling back to environment variables.
    """
    # Check both standard and alternate environment variable names
    env_host = os.getenv("SMTP_HOST", "").strip()
    env_port = os.getenv("SMTP_PORT", "587").strip()
    env_user = os.getenv("SMTP_USERNAME", "").strip() or os.getenv("SMTP_USER", "").strip()
    env_pass = os.getenv("SMTP_PASSWORD", "") or os.getenv("SMTP_PASS", "")
    env_from = os.getenv("SMTP_FROM", "").strip() or os.getenv("SMTP_FROM_EMAIL", "").strip()
    
    use_ssl = os.getenv("SMTP_USE_SSL", "").strip().lower() in ("true", "1", "yes")
    use_tls = os.getenv("SMTP_USE_TLS", "").strip().lower() in ("true", "1", "yes")
    env_security = os.getenv("SMTP_SECURITY", "").strip().lower()
    if not env_security:
        if use_ssl or env_port == "465":
            env_security = "ssl"
        elif use_tls or env_port in ("587", "25", "2525"):
            env_security = "starttls"
        else:
            env_security = "starttls"

    try:
        port_num = int(env_port) if env_port else 587
    except ValueError:
        port_num = 587

    config = {
        "host": env_host,
        "port": port_num,
        "user": env_user,
        "password": env_pass,
        "security": env_security,
        "from_email": env_from or (env_user if "@" in env_user else ""),
    }

    try:
        settings = SystemSetting.query.filter(
            SystemSetting.key.in_([
                "smtp_host", "smtp_port", "smtp_user", "smtp_username",
                "smtp_password", "smtp_pass", "smtp_security", "smtp_from", "smtp_from_email"
            ])
        ).all()
        mapping = {s.key: s.value for s in settings}
        if mapping.get("smtp_host"):
            config["host"] = mapping["smtp_host"].strip()
        if mapping.get("smtp_port"):
            try:
                config["port"] = int(mapping["smtp_port"])
            except ValueError:
                pass
        if mapping.get("smtp_user") is not None and mapping.get("smtp_user").strip():
            config["user"] = mapping["smtp_user"].strip()
        elif mapping.get("smtp_username") is not None and mapping.get("smtp_username").strip():
            config["user"] = mapping["smtp_username"].strip()
        if mapping.get("smtp_password") is not None and mapping.get("smtp_password") != "":
            config["password"] = mapping["smtp_password"]
        elif mapping.get("smtp_pass") is not None and mapping.get("smtp_pass") != "":
            config["password"] = mapping["smtp_pass"]
        if mapping.get("smtp_security"):
            config["security"] = mapping["smtp_security"].strip().lower()
        if mapping.get("smtp_from_email"):
            config["from_email"] = mapping["smtp_from_email"].strip()
        elif mapping.get("smtp_from"):
            config["from_email"] = mapping["smtp_from"].strip()
    except Exception as e:
        logger.debug(f"Could not load SMTP config from DB: {e}")

    # Set default from_email if empty
    if not config["from_email"] and config["user"] and "@" in config["user"]:
        config["from_email"] = config["user"]

    return config



def save_smtp_config(data: dict) -> dict:
    """
    Saves or updates SMTP configuration in the SystemSetting table.
    """
    keys_map = {
        "host": "smtp_host",
        "port": "smtp_port",
        "user": "smtp_user",
        "password": "smtp_password",
        "security": "smtp_security",
        "from_email": "smtp_from_email",
    }
    for field, key in keys_map.items():
        if field in data:
            val = str(data[field]) if data[field] is not None else ""
            if field == "password" and val == "":
                # Don't overwrite existing password with blank
                continue
            setting = SystemSetting.query.filter_by(key=key).first()
            if not setting:
                setting = SystemSetting(key=key, value=val, description=f"SMTP Setting: {field}")
                db.session.add(setting)
            else:
                setting.value = val
    db.session.commit()
    return get_smtp_config()


def is_smtp_configured(cfg: dict = None) -> bool:
    """Checks whether valid SMTP server details have been provided."""
    c = cfg or get_smtp_config()
    host = (c.get("host") or "").strip()
    return bool(host and host.lower() not in ["none", ""])


def parse_and_validate_emails(raw_email_str: str) -> list[str]:
    """Parses a comma, semicolon, or newline-separated string into a list of valid emails."""
    if not raw_email_str:
        return []
    parts = re.split(r"[,;\s\n]+", str(raw_email_str).strip())
    valid_emails = []
    for p in parts:
        cleaned = p.strip()
        if cleaned and EMAIL_REGEX.match(cleaned):
            if cleaned not in valid_emails:
                valid_emails.append(cleaned)
    return valid_emails


def collect_failure_recipients(schedule=None, project=None, doc=None, additional_emails: str = None) -> list[str]:
    """
    Collects all respective recipients for a failure alert:
    1. Emails explicitly specified in the schedule's `notification_emails` field.
    2. Creator of the schedule (if has a valid email).
    3. Creator / owner of the project (if has a valid email).
    4. System administrators (so platform owners are aware).
    """
    recipients = []

    # 1. Additional or schedule-specific emails
    if additional_emails:
        recipients.extend(parse_and_validate_emails(additional_emails))

    if schedule and getattr(schedule, "notification_emails", None):
        recipients.extend(parse_and_validate_emails(schedule.notification_emails))

    # 2. Schedule creator email
    if schedule and getattr(schedule, "creator", None) and getattr(schedule.creator, "email", None):
        if EMAIL_REGEX.match(schedule.creator.email) and schedule.creator.email not in recipients:
            recipients.append(schedule.creator.email)

    # 3. Project owner email
    if project and getattr(project, "creator", None) and getattr(project.creator, "email", None):
        if EMAIL_REGEX.match(project.creator.email) and project.creator.email not in recipients:
            recipients.append(project.creator.email)

    # 4. System Admin emails
    try:
        admins = User.query.filter_by(role="admin").all()
        for a in admins:
            if a.email and EMAIL_REGEX.match(a.email) and a.email not in recipients:
                recipients.append(a.email)
    except Exception as e:
        logger.debug(f"Could not query admin emails: {e}")

    # Fallback to default if no emails discovered
    if not recipients:
        fallback = os.getenv("DEFAULT_ALERT_EMAIL", "ops-team@enterprise.local")
        recipients.append(fallback)

    return recipients


def build_failure_alert_content(run_record, schedule=None, project=None, doc=None,
                                audit_result: dict = None, failure_reason: str = None) -> tuple[str, str, str]:
    """
    Constructs a structured subject, plaintext message, and responsive HTML email.
    """
    ctrl_num = getattr(run_record, "control_number", None)
    if not ctrl_num and doc and hasattr(doc, 'analysis_data') and doc.analysis_data:
        ctrl_num = doc.analysis_data.get("control_overview", {}).get("identification", {}).get("control_number")
    if not ctrl_num:
        ctrl_num = "HLA Pipeline"
    environment = (getattr(run_record, "environment", "DEV") or "DEV").upper()
    hostname = getattr(run_record, "hostname", "Unknown Host")
    status = getattr(run_record, "status", "FAILED")
    run_id = getattr(run_record, "id", "N/A")
    started_at = getattr(run_record, "started_at", datetime.now(timezone.utc))
    started_str = started_at.strftime("%Y-%m-%d %H:%M:%S UTC") if started_at else "Now"

    reason = failure_reason or getattr(run_record, "summary_message", "Execution failed unexpectedly.")
    sched_name = getattr(schedule, "name", "Automated Control Run") if schedule else "Direct Execution"
    proj_name = getattr(project, "name", "HLA Workspace") if project else "Workspace"
    doc_name = getattr(doc, "original_name", getattr(doc, "filename", "HLA Specification")) if doc else "Specification"

    audit = audit_result or getattr(run_record, "result_details", {}) or {}
    checked = audit.get("tables_checked", 0)
    found = audit.get("tables_found", 0)
    missing = audit.get("tables_missing", 0)
    empty = audit.get("tables_empty", 0)
    stale = audit.get("tables_stale", 0)
    missing_list = audit.get("missing_list", [])
    empty_list = audit.get("empty_list", [])
    stale_list = audit.get("stale_list", [])

    subject = f"🚨 [ALERT] HLA Control Run {status}: {ctrl_num} ({environment}) on {hostname}"

    # Plaintext Body
    body_text = f"""======================================================================
HLA STUDIO • AUTOMATED CONTROL RUN FAILURE ALERT
======================================================================

Control:            {ctrl_num}
Schedule:           {sched_name} (Run #{run_id})
Workspace:          {proj_name}
Specification:      {doc_name}
Target Environment: {environment}
Target Hostname:    {hostname}
Execution Time:     {started_str}
Execution Status:   {status}

----------------------------------------------------------------------
FAILURE REASON:
----------------------------------------------------------------------
{reason}

----------------------------------------------------------------------
UPSTREAM SOURCE TABLE AUDIT BREAKDOWN:
----------------------------------------------------------------------
- Total Required Tables: {checked}
- Verified Fresh Tables: {found}
- Missing Tables:        {missing}
- Empty (0 rows) Tables: {empty}
- Stale Append Tables:   {stale}
"""

    if missing_list:
        body_text += f"\nMissing Tables List:\n  * " + "\n  * ".join(missing_list)
    if empty_list:
        body_text += f"\nEmpty Feeds (Data Not Arrived):\n  * " + "\n  * ".join(empty_list)
    if stale_list:
        body_text += f"\nStale Append Feeds (Missing Latest Date):\n  * " + "\n  * ".join(stale_list)

    body_text += f"""

----------------------------------------------------------------------
ACTION REQUIRED:
----------------------------------------------------------------------
1. Check upstream ETL data arrival schedules for missing or empty tables.
2. Ensure source database connectors are online and credentials are valid.
3. Review detailed execution logs in HLA Studio: Project Studio -> Control Scheduler -> History.

======================================================================
This is an automated alert generated by HLA Studio Zero-Trust Control Engine.
"""

    # HTML Body
    badge_color = "#dc2626" if status == "FAILED" else "#f59e0b"
    badge_label = "EXECUTION FAILED" if status == "FAILED" else "HALTED BY QUALITY GATE"

    missing_html = "".join([f"<li style='margin-bottom:4px;color:#fca5a5;'><code>{m}</code> (Table not found)</li>" for m in missing_list]) or "<li style='color:#94a3b8;'>None</li>"
    empty_html = "".join([f"<li style='margin-bottom:4px;color:#fcd34d;'><code>{e}</code> (0 rows - feed not arrived)</li>" for e in empty_list]) or "<li style='color:#94a3b8;'>None</li>"
    stale_html = "".join([f"<li style='margin-bottom:4px;color:#fdba74;'><code>{s}</code> (Missing latest run date)</li>" for s in stale_list]) or "<li style='color:#94a3b8;'>None</li>"

    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#0b0f19;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#f1f5f9;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0b0f19;padding:24px;">
    <tr>
      <td align="center">
        <table width="680" cellpadding="0" cellspacing="0" style="background:#131b2e;border:1px solid #23324d;border-radius:12px;overflow:hidden;box-shadow:0 12px 30px rgba(0,0,0,0.5);">
          <!-- Header Banner -->
          <tr>
            <td style="padding:24px 28px;background:linear-gradient(135deg, #1e293b 0%, #0f172a 100%);border-bottom:1px solid #334155;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="display:inline-block;padding:4px 10px;border-radius:6px;background:{badge_color};color:#ffffff;font-size:12px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;">
                      {badge_label}
                    </span>
                    <h1 style="margin:12px 0 4px 0;font-size:22px;color:#ffffff;font-weight:700;">
                      {ctrl_num} Execution Failed
                    </h1>
                    <p style="margin:0;font-size:14px;color:#94a3b8;">
                      Workspace: <strong style="color:#ffffff;">{proj_name}</strong> | Environment: <strong style="color:#63cab7;">{environment}</strong>
                    </p>
                  </td>
                  <td align="right" valign="top">
                    <span style="font-size:32px;">🚨</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Key Details Grid -->
          <tr>
            <td style="padding:20px 28px;border-bottom:1px solid #1e293b;">
              <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">
                <tr>
                  <td width="50%" style="padding:6px 0;color:#94a3b8;">Schedule Name:</td>
                  <td width="50%" style="padding:6px 0;color:#f8fafc;font-weight:600;">{sched_name}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#94a3b8;">Run ID / Trigger:</td>
                  <td style="padding:6px 0;color:#f8fafc;font-weight:600;">Run #{run_id} ({getattr(run_record, 'trigger_type', 'SCHEDULED')})</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#94a3b8;">Target Hostname:</td>
                  <td style="padding:6px 0;color:#f8fafc;font-weight:600;"><code>{hostname}</code></td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#94a3b8;">Execution Timestamp:</td>
                  <td style="padding:6px 0;color:#f8fafc;font-weight:600;">{started_str}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#94a3b8;">HLA Specification:</td>
                  <td style="padding:6px 0;color:#f8fafc;font-weight:600;">{doc_name}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Failure Reason Box -->
          <tr>
            <td style="padding:20px 28px;">
              <div style="background:rgba(239, 68, 68, 0.12);border:1px solid rgba(239, 68, 68, 0.3);border-radius:8px;padding:16px;">
                <h3 style="margin:0 0 8px 0;font-size:14px;color:#f87171;font-weight:700;">
                  ⚠️ Diagnostic Summary & Failure Reason
                </h3>
                <p style="margin:0;font-size:13px;line-height:1.5;color:#fee2e2;">
                  {reason}
                </p>
              </div>
            </td>
          </tr>

          <!-- Upstream Source Audit -->
          <tr>
            <td style="padding:0 28px 20px 28px;">
              <h4 style="margin:0 0 12px 0;font-size:14px;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.5px;">
                Upstream Feed Verification Audit
              </h4>
              <table width="100%" cellpadding="10" cellspacing="0" style="background:#0f172a;border-radius:8px;font-size:13px;text-align:center;">
                <tr style="color:#94a3b8;border-bottom:1px solid #1e293b;">
                  <td>Required</td>
                  <td>Verified Fresh</td>
                  <td>Missing</td>
                  <td>Empty (0 Rows)</td>
                  <td>Stale Date</td>
                </tr>
                <tr style="font-size:18px;font-weight:700;">
                  <td style="color:#ffffff;">{checked}</td>
                  <td style="color:#63cab7;">{found}</td>
                  <td style="color:#f87171;">{missing}</td>
                  <td style="color:#fbbf24;">{empty}</td>
                  <td style="color:#fb923c;">{stale}</td>
                </tr>
              </table>

              <!-- Detailed Lists -->
              <div style="margin-top:16px;font-size:12px;color:#cbd5e1;">
                {f"<div style='margin-bottom:10px;'><strong style='color:#f87171;'>Missing Source Tables:</strong><ul style='margin:4px 0 0 18px;padding:0;'>{missing_html}</ul></div>" if missing else ""}
                {f"<div style='margin-bottom:10px;'><strong style='color:#fbbf24;'>Empty Feeds (Data Not Received):</strong><ul style='margin:4px 0 0 18px;padding:0;'>{empty_html}</ul></div>" if empty else ""}
                {f"<div style='margin-bottom:10px;'><strong style='color:#fb923c;'>Stale Feeds (Append Mode Without Latest Date):</strong><ul style='margin:4px 0 0 18px;padding:0;'>{stale_html}</ul></div>" if stale else ""}
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 28px;background:#0f172a;border-top:1px solid #1e293b;font-size:12px;color:#64748b;text-align:center;">
              <p style="margin:0 0 6px 0;">
                HLA Studio Automated Control Pipeline Engine • Zero-Trust Data Reconciliation
              </p>
              <p style="margin:0;">
                Log into HLA Studio to review full audit trails and inspect live source schemas.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, body_text, body_html


def try_linux_system_mail(msg, recipients: list, from_addr: str = "alerts@hlastudio.local") -> tuple[bool, str]:
    """
    On Linux / Ubuntu servers:
    Attempts outbound transmission using the host's native Mail Transfer Agent (MTA):
    1. /usr/sbin/sendmail or system sendmail binary (Postfix, Sendmail, Exim).
    2. Localhost port 25 without authentication (default local Postfix listener).
    Returns (True, mode_description) if dispatched, or (False, error_reason).
    """
    recipient_list = recipients if isinstance(recipients, list) else [r.strip() for r in str(recipients).split(",") if r.strip()]
    if not recipient_list:
        return False, "No recipient addresses provided"

    # 1. Try system sendmail binary (standard on Ubuntu with postfix or sendmail-bin)
    sendmail_bin = shutil.which("sendmail") or ("/usr/sbin/sendmail" if os.path.exists("/usr/sbin/sendmail") else None)
    if sendmail_bin and os.path.exists(sendmail_bin):
        try:
            cmd = [sendmail_bin, "-t", "-oi"]
            if from_addr and "@" in from_addr:
                cmd.extend(["-f", from_addr])
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            raw_content = msg.as_string().encode("utf-8") if hasattr(msg, "as_string") else str(msg).encode("utf-8")
            stdout, stderr = proc.communicate(input=raw_content, timeout=10)
            if proc.returncode == 0:
                logger.info(f"[LINUX MTA] Successfully dispatched email via {sendmail_bin} to {recipient_list}")
                return True, f"Ubuntu System Mail ({sendmail_bin})"
            else:
                err_msg = stderr.decode("utf-8", errors="ignore")
                logger.warning(f"[LINUX MTA WARNING] {sendmail_bin} exited with code {proc.returncode}: {err_msg}")
        except Exception as e:
            logger.warning(f"[LINUX MTA ERROR] Failed to invoke {sendmail_bin}: {e}")

    # 2. Try localhost port 25 (standard Postfix listener on Linux servers)
    try:
        with smtplib.SMTP("127.0.0.1", 25, timeout=3) as server:
            raw_content = msg.as_string() if hasattr(msg, "as_string") else str(msg)
            server.sendmail(from_addr, recipient_list, raw_content)
            logger.info(f"[LOCAL POSTFIX] Successfully dispatched email via 127.0.0.1:25 to {recipient_list}")
            return True, "Ubuntu Local Postfix (127.0.0.1:25)"
    except Exception:
        pass

    return False, "No local Linux MTA (Postfix/sendmail) active on this machine"


def send_control_failure_alert(run_record, schedule=None, project=None, doc=None,
                               audit_result: dict = None, failure_reason: str = None,
                               additional_recipients: str = None) -> dict:
    """
    Main dispatch function:
    1. Determines target recipients.
    2. Builds the email message.
    3. Dispatches via custom SMTP, local Linux Postfix/sendmail, or Zero-Config Engine.
    4. Writes audit log to EmailNotificationLog table.
    """
    recipients = collect_failure_recipients(
        schedule=schedule,
        project=project,
        doc=doc,
        additional_emails=additional_recipients
    )

    recipient_str = ", ".join(recipients)
    subject, body_text, body_html = build_failure_alert_content(
        run_record=run_record,
        schedule=schedule,
        project=project,
        doc=doc,
        audit_result=audit_result,
        failure_reason=failure_reason
    )

    delivery_status = "SENT"
    err_msg = None
    delivery_mode = "Custom SMTP Server"

    smtp_cfg = get_smtp_config()
    from_addr = smtp_cfg.get("from_email") or smtp_cfg.get("user") or "alerts@hlastudio.local"

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = recipient_str
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    part1 = MIMEText(body_text, "plain", "utf-8")
    part2 = MIMEText(body_html, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    # Attempt SMTP Transmission
    if is_smtp_configured(smtp_cfg):
        host = smtp_cfg["host"]
        port = smtp_cfg["port"]
        user = smtp_cfg.get("user")
        pwd = smtp_cfg.get("password")
        security = smtp_cfg.get("security", "starttls")

        try:
            logger.info(f"Connecting to SMTP server {host}:{port} (mode={security}) to send failure alert...")
            if security == "ssl" or port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                    if user and pwd:
                        server.login(user, pwd)
                    server.sendmail(from_addr, recipients, msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    if security != "none":
                        server.starttls()
                    if user and pwd:
                        server.login(user, pwd)
                    server.sendmail(from_addr, recipients, msg.as_string())

            logger.info(f"[EMAIL SENT] Successfully dispatched failure alert to {recipient_str} via SMTP {host}:{port}")
            delivery_status = "SENT"
            delivery_mode = f"SMTP ({host}:{port})"
        except Exception as e:
            err_msg = f"SMTP transmission error ({str(e)})"
            logger.warning(f"[SMTP FAILURE] {err_msg}")
            # Try Linux system MTA if on Linux
            mta_ok, mta_desc = try_linux_system_mail(msg, recipients, from_addr)
            if mta_ok:
                delivery_status = "SENT"
                delivery_mode = mta_desc
            else:
                delivery_status = "FAILED"
                delivery_mode = f"SMTP Server ({host})"
    else:
        # Check if local Linux Postfix/sendmail is active
        mta_ok, mta_desc = try_linux_system_mail(msg, recipients, from_addr)
        if mta_ok:
            delivery_status = "SENT"
            delivery_mode = mta_desc
            logger.info(f"[EMAIL SENT] Dispatched failure alert to {recipient_str} via {mta_desc}")
        else:
            delivery_status = "NOT_CONFIGURED"
            delivery_mode = "None (SMTP Not Configured)"
            err_msg = "SMTP is not configured. Configure SMTP in Settings -> Automated Email Alerts to send live failure emails to inboxes."
            logger.warning(f"[EMAIL ALERT AUDIT] {err_msg}")

    # Persist in EmailNotificationLog database table
    log_id = None
    try:
        from models import ControlRunHistory
        target_run_id = getattr(run_record, "id", None)
        valid_run_id = None
        if target_run_id:
            try:
                if ControlRunHistory.query.get(target_run_id):
                    valid_run_id = target_run_id
            except Exception:
                valid_run_id = None

        log_entry = EmailNotificationLog(
            project_id=getattr(project, "id", None) or getattr(run_record, "project_id", None),
            schedule_id=getattr(schedule, "id", None) or getattr(run_record, "schedule_id", None),
            run_history_id=valid_run_id,
            recipient_emails=recipient_str,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            status=delivery_status,
            error_message=err_msg,
            sent_at=datetime.now(timezone.utc)
        )
        db.session.add(log_entry)
        db.session.commit()
        log_id = log_entry.id
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to record email log to database: {e}")

    is_success = delivery_status == "SENT"

    return {
        "success": is_success,
        "status": delivery_status,
        "delivery_mode": delivery_mode,
        "recipients": recipients,
        "sent_to": recipients,
        "recipient_count": len(recipients),
        "subject": subject,
        "log_id": log_id,
        "error": err_msg
    }


def test_smtp_connection(target_email: str, override_config: dict = None) -> dict:
    """
    Performs a live test of SMTP connection and dispatches an actual test email:
    - Merges stored database SMTP configuration with any overrides.
    - Connects directly to the SMTP host (STARTTLS on 587 or SSL on 465).
    - Authenticates and transmits the test email to target_email.
    - Returns real connection diagnostics and error details.
    """
    base_cfg = get_smtp_config()

    if override_config and isinstance(override_config, dict):
        for k, v in override_config.items():
            if v is not None and str(v).strip() != "":
                base_cfg[k] = str(v).strip() if isinstance(v, str) else v
            elif k == "password" and (not v) and base_cfg.get("password"):
                pass

    host = (base_cfg.get("host") or "").strip()
    port = int(base_cfg.get("port") or 587)
    user = (base_cfg.get("user") or "").strip()
    pwd = base_cfg.get("password") or ""
    security = (base_cfg.get("security") or "starttls").lower()
    from_addr = (base_cfg.get("from_email") or "").strip() or user or "alerts@hlastudio.local"

    if not target_email or not EMAIL_REGEX.match(target_email.strip()):
        return {
            "success": False,
            "message": f"Invalid recipient email address: '{target_email}'. Please enter a valid email format.",
            "diagnostics": "Recipient validation failed."
        }

    target_email = target_email.strip()

    if not host or host.lower() in ["none", ""]:
        return {
            "success": False,
            "message": "SMTP host is not configured. Please enter your SMTP server host (e.g. smtp.gmail.com), port (587), username, and app password.",
            "diagnostics": "Missing SMTP Host Configuration"
        }

    subject = "✓ HLA Studio • Control Failure Alert & Email Dispatch Test"
    body_text = f"""HLA Studio Automated Email Alert Test
==================================================
This test confirms that your SMTP failure email alerting pipeline is active and ready to deliver!

Timestamp:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
SMTP Server:  {host}:{port} ({security.upper()})
Sender:       {from_addr}
Target Email: {target_email}

Whenever a scheduled or manual control execution fails or encounters missing upstream feeds,
an automated diagnostic failure alert with complete table audit details will be triggered
directly to {target_email}.
"""

    body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#090e1a;color:#f8fafc;padding:24px;">
  <div style="max-width:580px;margin:auto;background:#0f172a;border:1px solid rgba(56,189,248,0.3);border-radius:14px;padding:28px;">
    <div style="font-size:28px;margin-bottom:12px;">🎉</div>
    <h2 style="margin:0 0 8px 0;color:#38bdf8;font-size:20px;">Email Alert Dispatch Verified!</h2>
    <p style="margin:0 0 18px 0;color:#94a3b8;font-size:14px;line-height:1.5;">
      Your HLA Studio SMTP email notification service is active and ready. Failure alerts for quality gates and missing feeds will be triggered automatically.
    </p>
    <table width="100%" cellpadding="8" cellspacing="0" style="background:#090e1a;border-radius:8px;font-size:13px;color:#cbd5e1;">
      <tr><td style="color:#64748b;">Target Recipient:</td><td style="font-weight:600;color:#38bdf8;">{target_email}</td></tr>
      <tr><td style="color:#64748b;">SMTP Server:</td><td style="font-weight:600;color:#34d399;">{host}:{port} ({security.upper()})</td></tr>
      <tr><td style="color:#64748b;">Sender Address:</td><td style="font-weight:600;color:#f8fafc;">{from_addr}</td></tr>
      <tr><td style="color:#64748b;">Status:</td><td style="font-weight:600;color:#34d399;">VERIFIED & DELIVERED</td></tr>
    </table>
  </div>
</body>
</html>"""

    # Construct test MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = target_email
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        print("[EMAIL] Running SMTP diagnostic test", flush=True)
        print(f"[EMAIL] SMTP host configured: {bool(host)}", flush=True)
        print(f"[EMAIL] SMTP port configured: {bool(port)}", flush=True)
        print(f"[EMAIL] SMTP username configured: {bool(user)}", flush=True)
        print(f"[EMAIL] SMTP password configured: {bool(pwd)}", flush=True)
        print(f"[EMAIL] Connecting to SMTP server {host}:{port} (mode={security})...", flush=True)

        if security == "ssl" or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                print("[EMAIL] SMTP connection established (SSL)", flush=True)
                if user and pwd:
                    server.login(user, pwd)
                    print("[EMAIL] SMTP authentication successful", flush=True)
                print("[EMAIL] Sending test email...", flush=True)
                senderrs = server.sendmail(from_addr, [target_email], msg.as_string())
                if senderrs:
                    raise Exception(f"Recipient rejected by SMTP server: {senderrs}")
                print("[EMAIL] Email accepted by SMTP server", flush=True)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                print("[EMAIL] SMTP connection established", flush=True)
                server.ehlo()
                if security != "none":
                    server.starttls()
                    server.ehlo()
                if user and pwd:
                    server.login(user, pwd)
                    print("[EMAIL] SMTP authentication successful", flush=True)
                print("[EMAIL] Sending test email...", flush=True)
                senderrs = server.sendmail(from_addr, [target_email], msg.as_string())
                if senderrs:
                    raise Exception(f"Recipient rejected by SMTP server: {senderrs}")
                print("[EMAIL] Email accepted by SMTP server", flush=True)

        logger.info(f"[TEST EMAIL SENT] Live SMTP verified for {target_email} via {host}:{port}")

        # Record test dispatch in database audit log
        try:
            log_entry = EmailNotificationLog(
                recipient_emails=target_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                status="SENT",
                error_message=None,
                sent_at=datetime.now(timezone.utc)
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as log_err:
            db.session.rollback()
            logger.debug(f"Could not persist test email log: {log_err}")

        return {
            "success": True,
            "message": f"✓ Successfully connected to SMTP server {host}:{port} and handed test email to {target_email}!",
            "delivery_mode": f"SMTP ({host}:{port})",
            "smtp_connection": "successful",
            "smtp_authentication": "successful" if user and pwd else "anonymous/not required",
            "smtp_acceptance": "Email accepted by SMTP server",
            "note": "SMTP accepted the message. Actual mailbox delivery depends on provider filtering/quarantine.",
            "diagnostics": f"Connected to {host}:{port}, authenticated as '{user or 'anonymous'}', message accepted via {security.upper()}."
        }
    except smtplib.SMTPAuthenticationError as auth_err:
        err = f"SMTP Authentication failed: Username and password not accepted by {host}. If using Gmail, please use an App Password (myaccount.google.com/apppasswords)."
        logger.error(f"[SMTP AUTH ERROR] {err}")
        return {"success": False, "message": err, "diagnostics": str(auth_err)}
    except Exception as e:
        err = f"SMTP connection failed: {str(e)}"
        logger.error(f"[SMTP ERROR] {err}")
        return {"success": False, "message": err, "diagnostics": str(e)}


def send_password_reset_email(user, reset_link: str, expires_minutes: int = 15) -> dict:
    """
    Sends an enterprise password reset email with a secure, one-time link.
    If SMTP is configured, sends via live SMTP.
    Otherwise, records the dispatch in EmailNotificationLog for auditing and simulated delivery.
    """
    target_email = getattr(user, "email", None) or f"{user.username}@hlaproject.local"
    subject = "🔑 Reset Your Password - HLA Studio Enterprise"

    body_text = f"""Hello {user.username},

We received a request to reset the password for your HLA Studio account.

To choose a new password, click the secure, one-time link below:
{reset_link}

This link is valid for {expires_minutes} minutes and can only be used once.

If you did not make this request, you can safely ignore this email. Your password will remain unchanged.

Best regards,
HLA Studio Security & Governance Team
"""

    body_html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0d1117; color: #e6edf3; margin: 0; padding: 24px; }}
    .container {{ max-width: 560px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; }}
    .header {{ background: #1f6feb; padding: 20px 24px; color: #ffffff; }}
    .header h2 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .body {{ padding: 24px; font-size: 15px; line-height: 1.6; color: #c9d1d9; }}
    .btn {{ display: inline-block; background-color: #238636; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
    .link-box {{ background: #0d1117; padding: 12px; border-radius: 6px; border: 1px solid #30363d; word-break: break-all; font-family: monospace; font-size: 12px; color: #58a6ff; }}
    .footer {{ padding: 16px 24px; background: #0d1117; border-top: 1px solid #21262d; font-size: 12px; color: #8b949e; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>HLA Studio • Account Security</h2>
    </div>
    <div class="body">
      <p>Hello <strong>{user.username}</strong>,</p>
      <p>We received a request to reset the password for your HLA Studio account.</p>
      <p style="text-align: center;">
        <a href="{reset_link}" class="btn">Reset My Password</a>
      </p>
      <p>Or copy and paste this secure link into your browser:</p>
      <div class="link-box">{reset_link}</div>
      <p style="margin-top: 20px; font-size: 13px; color: #8b949e;">
        ⏱️ This link is valid for <strong>{expires_minutes} minutes</strong> and can only be used once. If you did not request this, please disregard this notice.
      </p>
    </div>
    <div class="footer">
      HLA Studio Enterprise Governance • Automated System Notification
    </div>
  </div>
</body>
</html>
"""
    cfg = get_smtp_config()
    smtp_ok = is_smtp_configured(cfg)
    dispatch_status = "PENDING"
    err_msg = None

    if smtp_ok:
        try:
            host = cfg["host"]
            port = cfg["port"]
            user_auth = cfg["user"]
            pwd = cfg["password"]
            security = cfg["security"]
            from_addr = cfg["from_email"]

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = target_email
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            if security == "ssl":
                with smtplib.SMTP_SSL(host, port, timeout=12) as server:
                    if user_auth and pwd:
                        server.login(user_auth, pwd)
                    server.sendmail(from_addr, [target_email], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=12) as server:
                    server.ehlo()
                    if security != "none":
                        server.starttls()
                    if user_auth and pwd:
                        server.login(user_auth, pwd)
                    server.sendmail(from_addr, [target_email], msg.as_string())

            dispatch_status = "SENT"
            logger.info(f"[RESET EMAIL SENT] Sent password reset email to {target_email} via {host}:{port}")
        except Exception as e:
            dispatch_status = "FAILED"
            err_msg = str(e)
            logger.error(f"[RESET EMAIL ERROR] Could not send reset email via SMTP: {e}")
    else:
        # Dev / Zero-Config fallback: Record delivery in DB logs
        dispatch_status = "SIMULATED"
        logger.info(f"[RESET EMAIL SIMULATED] SMTP not configured. Reset link generated for {target_email}: {reset_link}")

    try:
        log_entry = EmailNotificationLog(
            recipient_emails=target_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            status=dispatch_status,
            error_message=err_msg,
            sent_at=datetime.now(timezone.utc)
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as log_e:
        db.session.rollback()
        logger.debug(f"Failed to log email: {log_e}")

    return {
        "success": True,
        "email": target_email,
        "status": dispatch_status,
        "reset_link": reset_link,
        "error": err_msg
    }


def send_password_reset_otp_email(user, otp_code: str, expires_minutes: int = 10) -> dict:
    """
    Sends an enterprise password reset email containing a 6-digit OTP code.
    Requires an active and working SMTP connection.
    Logs diagnostics safely without leaking credentials or plaintext OTP.
    """
    target_email = getattr(user, "email", None) or f"{user.username}@hlaproject.local"
    subject = "HLA Studio - Password Reset OTP"

    body_text = f"""Hello,

We received a request to reset your HLA Studio password.

Your verification code is:

{otp_code}

This code will expire in {expires_minutes} minutes.

If you did not request a password reset, please ignore this email.

Regards,
HLA Studio"""

    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0d1117; color: #e6edf3; padding: 24px; }}
    .box {{ max-width: 540px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; }}
    .head {{ background: #1f6feb; padding: 18px 24px; color: #ffffff; }}
    .content {{ padding: 24px; font-size: 15px; color: #c9d1d9; line-height: 1.6; }}
    .otp-code {{ font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #58a6ff; background: #0d1117; padding: 16px 24px; border-radius: 8px; text-align: center; border: 1px dashed #388bfd; margin: 20px 0; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="head">
      <h3 style="margin:0; font-size: 18px;">HLA Studio - Password Reset OTP</h3>
    </div>
    <div class="content">
      <p style="margin-top:0;">Hello,</p>
      <p>We received a request to reset your HLA Studio password.</p>
      <p>Your verification code is:</p>
      <div class="otp-code">{otp_code}</div>
      <p>This code will expire in <strong>{expires_minutes} minutes</strong>.</p>
      <p style="color:#8b949e; font-size: 13px;">If you did not request a password reset, please ignore this email.</p>
      <p style="margin-bottom:0;">Regards,<br><strong>HLA Studio</strong></p>
    </div>
  </div>
</body>
</html>"""

    # Safe Server Diagnostic Logs
    safe_log("[EMAIL] Preparing password reset email")
    cfg = get_smtp_config()
    host = cfg.get("host")
    port = cfg.get("port")
    user_auth = cfg.get("user")
    pwd = cfg.get("password")
    security = cfg.get("security", "starttls")
    from_addr = cfg.get("from_email")

    safe_log(f"[EMAIL] SMTP host configured: {bool(host and host.strip())}")
    safe_log(f"[EMAIL] SMTP port configured: {bool(port)}")
    safe_log(f"[EMAIL] SMTP username configured: {bool(user_auth and user_auth.strip())}")
    safe_log(f"[EMAIL] SMTP password configured: {bool(pwd and pwd.strip())}")

    if not is_smtp_configured(cfg):
        err_msg = "SMTP server is not configured. Real email delivery required."
        safe_log(f"[EMAIL] Error: {err_msg}", level="error")
        # Audit log in database
        try:
            masked_body_text = body_text.replace(otp_code, "******")
            masked_body_html = body_html.replace(otp_code, "******")
            log_entry = EmailNotificationLog(
                recipient_emails=target_email,
                subject=subject,
                body_text=masked_body_text,
                body_html=masked_body_html,
                status="NOT_CONFIGURED",
                error_message=err_msg,
                sent_at=datetime.now(timezone.utc)
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "email": target_email,
            "error": err_msg
        }

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = target_email
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    dispatch_status = "PENDING"
    err_msg = None
    smtp_accepted = False

    try:
        safe_log("[EMAIL] Connecting to SMTP server")
        if security == "ssl" or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                safe_log("[EMAIL] SMTP connection established")
                if user_auth and pwd:
                    server.login(user_auth, pwd)
                    safe_log("[EMAIL] SMTP authentication successful")
                safe_log("[EMAIL] Sending password reset email")
                senderrs = server.sendmail(from_addr, [target_email], msg.as_string())
                if senderrs:
                    raise Exception(f"Recipient rejected by SMTP server: {senderrs}")
                smtp_accepted = True
                safe_log("[EMAIL] Email accepted by SMTP server")
                safe_log("[EMAIL] Password reset email sent successfully")
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                safe_log("[EMAIL] SMTP connection established")
                server.ehlo()
                if security != "none":
                    server.starttls()
                    server.ehlo()
                if user_auth and pwd:
                    server.login(user_auth, pwd)
                    safe_log("[EMAIL] SMTP authentication successful")
                safe_log("[EMAIL] Sending password reset email")
                senderrs = server.sendmail(from_addr, [target_email], msg.as_string())
                if senderrs:
                    raise Exception(f"Recipient rejected by SMTP server: {senderrs}")
                smtp_accepted = True
                safe_log("[EMAIL] Email accepted by SMTP server")
                safe_log("[EMAIL] Password reset email sent successfully")

        dispatch_status = "SENT"
    except smtplib.SMTPAuthenticationError as auth_err:
        dispatch_status = "FAILED"
        err_msg = f"535 Authentication failed: {auth_err}"
        safe_log(f"[EMAIL] SMTP Authentication failed: {auth_err}", level="error")
    except smtplib.SMTPConnectError as conn_err:
        dispatch_status = "FAILED"
        err_msg = f"SMTP Connection error: {conn_err}"
        safe_log(f"[EMAIL] SMTP Connection error: {conn_err}", level="error")
    except smtplib.SMTPServerDisconnected as disconn_err:
        dispatch_status = "FAILED"
        err_msg = f"SMTP Server disconnected: {disconn_err}"
        safe_log(f"[EMAIL] SMTP Server disconnected: {disconn_err}", level="error")
    except Exception as e:
        dispatch_status = "FAILED"
        err_msg = f"SMTP Transmission error: {e}"
        safe_log(f"[EMAIL] SMTP Transmission error: {e}", level="error")

    # Mask plaintext OTP before storing in database logs
    masked_body_text = body_text.replace(otp_code, "******")
    masked_body_html = body_html.replace(otp_code, "******")

    try:
        log_entry = EmailNotificationLog(
            recipient_emails=target_email,
            subject=subject,
            body_text=masked_body_text,
            body_html=masked_body_html,
            status=dispatch_status,
            error_message=err_msg,
            sent_at=datetime.now(timezone.utc)
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as log_e:
        db.session.rollback()
        logger.debug(f"Failed to record email log: {log_e}")

    return {
        "success": (dispatch_status == "SENT"),
        "email": target_email,
        "status": dispatch_status,
        "accepted": smtp_accepted,
        "error": err_msg
    }



