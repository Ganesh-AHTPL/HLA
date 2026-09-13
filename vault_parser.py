"""
Universal Credential Vault & KDB File Parser
--------------------------------------------
Parses .kdb, .ini, .json, .yaml, .xml, and Key-Value configuration files
containing database connection credentials for upstream Source DBs
and Target Environments (Dev / Prod).
"""

import os
import re
import json
import configparser
import xml.etree.ElementTree as ET

def normalize_profile_name(name: str):
    """Cleans and standardizes profile names."""
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name).strip('_')


def parse_ini_kdb_text(content: str, default_role: str = "auto", target_env_hint: str = None):
    """Parses standard INI/KDB style configuration text."""
    parser = configparser.ConfigParser(interpolation=None)
    # INI requires a top section if headerless; check if headers exist
    has_sections = bool(re.search(r'^\s*\[.+\]', content, re.MULTILINE))
    if not has_sections:
        default_header = f"target.{target_env_hint or 'dev'}" if default_role == "target" else "default"
        content = f"[{default_header}]\n" + content

    parser.read_string(content)
    profiles = []
    sections = parser.sections()

    for section in sections:
        sec_clean = section.lower().strip()
        
        # Determine role and environment
        is_target = "target" in sec_clean or "dest" in sec_clean or "sink" in sec_clean
        if default_role == "target":
            is_target = True

        env = "none"
        if "prod" in sec_clean or "production" in sec_clean or "live" in sec_clean:
            env = "prod"
            if default_role == "target":
                is_target = True
        elif "dev" in sec_clean or "test" in sec_clean or "stage" in sec_clean or "staging" in sec_clean:
            env = "dev"
            if default_role == "target":
                is_target = True
        elif is_target:
            if target_env_hint in ("dev", "prod"):
                env = target_env_hint
            elif len(sections) == 1 and target_env_hint in ("dev", "prod"):
                env = target_env_hint
            else:
                env = "dev"

        # Determine display name
        display_name = section
        if "." in section:
            display_name = section.split(".", 1)[1].strip()
        elif "_" in section and (section.lower().startswith("source_") or section.lower().startswith("target_")):
            display_name = section.split("_", 1)[1].strip()

        # Extract fields
        items = dict(parser.items(section))
        db_type = items.get("db_type") or items.get("type") or items.get("engine") or items.get("dialect") or "postgresql"
        host = items.get("host") or items.get("hostname") or items.get("server") or items.get("endpoint") or "localhost"
        port_raw = items.get("port")
        try:
            port = int(port_raw) if port_raw else (5432 if "postgres" in db_type.lower() else (3306 if "mysql" in db_type.lower() else None))
        except ValueError:
            port = None

        db_name = items.get("database") or items.get("database_name") or items.get("db") or items.get("dbname") or "hla_db"
        user = items.get("username") or items.get("user") or items.get("uid") or "postgres"
        pwd = items.get("password") or items.get("pwd") or items.get("pass") or ""
        schema = items.get("schema") or items.get("schema_name") or (f"target_{env}" if is_target and env != "none" else "public")
        conn_str = items.get("connection_string") or items.get("conn_str") or items.get("url") or None

        profiles.append({
            "source_db_name": f"Target {env.upper()}" if is_target and env != "none" else display_name,
            "conn_role": "target" if is_target else "source",
            "target_env": env if is_target else "none",
            "schema_name": schema,
            "db_type": db_type.lower(),
            "host": host,
            "port": port,
            "database_name": db_name,
            "username": user,
            "password": pwd,
            "connection_string": conn_str,
            "vault_profile": section
        })

    return profiles


def parse_json_kdb_text(content: str, default_role: str = "auto", target_env_hint: str = None):
    """Parses JSON-structured database credential vaults."""
    data = json.loads(content)
    profiles = []

    # Case A: {"sources": [...], "targets": {"dev": {...}, "prod": {...}}}
    if isinstance(data, dict):
        # 1. Targets dict (checked first if default_role == 'target')
        targets_raw = data.get("targets") or data.get("target_databases") or {}
        if isinstance(targets_raw, dict) and targets_raw:
            for env in ["dev", "prod"]:
                t = targets_raw.get(env)
                if t:
                    profiles.append({
                        "source_db_name": f"Target {env.upper()}",
                        "conn_role": "target",
                        "target_env": env,
                        "schema_name": t.get("schema") or t.get("schema_name") or f"target_{env}",
                        "db_type": (t.get("db_type") or "postgresql").lower(),
                        "host": t.get("host") or "localhost",
                        "port": int(t.get("port")) if t.get("port") else 5432,
                        "database_name": t.get("database_name") or t.get("database") or "hla_db",
                        "username": t.get("username") or t.get("user") or "postgres",
                        "password": t.get("password") or "",
                        "connection_string": t.get("connection_string"),
                        "vault_profile": f"target.{env}"
                    })

        # 2. Sources array or dict
        sources_raw = data.get("sources") or data.get("source_databases") or []
        if isinstance(sources_raw, list):
            for s in sources_raw:
                name = s.get("name") or s.get("source_db_name") or "Source_DB"
                profiles.append({
                    "source_db_name": name,
                    "conn_role": "source",
                    "target_env": "none",
                    "schema_name": s.get("schema") or s.get("schema_name") or "public",
                    "db_type": (s.get("db_type") or "postgresql").lower(),
                    "host": s.get("host") or "localhost",
                    "port": int(s.get("port")) if s.get("port") else 5432,
                    "database_name": s.get("database_name") or s.get("database") or "hla_db",
                    "username": s.get("username") or s.get("user") or "postgres",
                    "password": s.get("password") or "",
                    "connection_string": s.get("connection_string"),
                    "vault_profile": f"source.{name}"
                })
        elif isinstance(sources_raw, dict):
            for k, s in sources_raw.items():
                profiles.append({
                    "source_db_name": k,
                    "conn_role": "source",
                    "target_env": "none",
                    "schema_name": s.get("schema") or s.get("schema_name") or "public",
                    "db_type": (s.get("db_type") or "postgresql").lower(),
                    "host": s.get("host") or "localhost",
                    "port": int(s.get("port")) if s.get("port") else 5432,
                    "database_name": s.get("database_name") or s.get("database") or "hla_db",
                    "username": s.get("username") or s.get("user") or "postgres",
                    "password": s.get("password") or "",
                    "connection_string": s.get("connection_string"),
                    "vault_profile": f"source.{k}"
                })

        # 3. Direct single object for target DB
        if not profiles and ("host" in data or "hostname" in data or "database" in data or "database_name" in data):
            env = target_env_hint or "dev"
            db_type = (data.get("db_type") or data.get("type") or "postgresql").lower()
            profiles.append({
                "source_db_name": f"Target {env.upper()}",
                "conn_role": "target" if default_role == "target" else "source",
                "target_env": env if default_role == "target" else "none",
                "schema_name": data.get("schema") or data.get("schema_name") or (f"target_{env}" if default_role == "target" else "public"),
                "db_type": db_type,
                "host": data.get("host") or data.get("hostname") or "localhost",
                "port": int(data.get("port")) if data.get("port") else 5432,
                "database_name": data.get("database_name") or data.get("database") or "hla_db",
                "username": data.get("username") or data.get("user") or "postgres",
                "password": data.get("password") or "",
                "connection_string": data.get("connection_string"),
                "vault_profile": f"target.{env}" if default_role == "target" else "default"
            })

        # 4. Flat dictionary profiles if no explicit "sources" or "targets" keys
        if not profiles:
            for k, v in data.items():
                if isinstance(v, dict):
                    is_target = "target" in k.lower() or default_role == "target"
                    env = "prod" if "prod" in k.lower() else ("dev" if "dev" in k.lower() else (target_env_hint or "dev" if is_target else "none"))
                    profiles.append({
                        "source_db_name": f"Target {env.upper()}" if is_target and env != "none" else k,
                        "conn_role": "target" if is_target else "source",
                        "target_env": env,
                        "schema_name": v.get("schema") or v.get("schema_name") or (f"target_{env}" if is_target and env != "none" else "public"),
                        "db_type": (v.get("db_type") or "postgresql").lower(),
                        "host": v.get("host") or "localhost",
                        "port": int(v.get("port")) if v.get("port") else 5432,
                        "database_name": v.get("database_name") or v.get("database") or "hla_db",
                        "username": v.get("username") or v.get("user") or "postgres",
                        "password": v.get("password") or "",
                        "connection_string": v.get("connection_string"),
                        "vault_profile": k
                    })

    return profiles


def parse_xml_keepass(content: str):
    """Parses KeePass XML / KDB export entries."""
    profiles = []
    root = ET.fromstring(content)
    
    # Locate all <Entry> elements
    for entry in root.findall(".//Entry"):
        entry_data = {}
        for s in entry.findall("String"):
            k = s.find("Key")
            v = s.find("Value")
            if k is not None and v is not None and k.text:
                entry_data[k.text.strip()] = v.text.strip() if v.text else ""

        title = entry_data.get("Title", "DB_Entry")
        is_target = "target" in title.lower()
        env = "prod" if "prod" in title.lower() else ("dev" if "dev" in title.lower() else ("dev" if is_target else "none"))
        url = entry_data.get("URL", "")

        profiles.append({
            "source_db_name": f"Target {env.upper()}" if is_target else title,
            "conn_role": "target" if is_target else "source",
            "target_env": env,
            "schema_name": f"target_{env}" if is_target else "public",
            "db_type": "postgresql",
            "host": url or "localhost",
            "port": 5432,
            "database_name": "hla_db",
            "username": entry_data.get("UserName", "postgres"),
            "password": entry_data.get("Password", ""),
            "connection_string": url if url.startswith("postgres") else None,
            "vault_profile": title
        })

    return profiles


def parse_credential_vault(raw_content: str, filename: str = "", default_role: str = "auto", target_env_hint: str = None):
    """
    Main entry point: detects format and returns list of parsed connection profiles.
    Returns:
        {
            "success": bool,
            "profiles": list of dict,
            "source_profiles": list of dict,
            "target_profiles": {"dev": dict, "prod": dict},
            "format_detected": str,
            "message": str
        }
    """
    text = raw_content.strip()
    if not text:
        return {"success": False, "profiles": [], "message": "Empty file or content."}

    ext = os.path.splitext(filename)[1].lower() if filename else ""
    profiles = []
    format_detected = "Unknown"

    # 1. Try JSON
    if ext in (".json",) or text.startswith("{"):
        try:
            profiles = parse_json_kdb_text(text, default_role=default_role, target_env_hint=target_env_hint)
            format_detected = "JSON Credential Vault"
        except Exception:
            pass

    # 2. Try XML (KeePass)
    if not profiles and (ext in (".xml", ".kdbx") or text.startswith("<")):
        try:
            profiles = parse_xml_keepass(text)
            format_detected = "KeePass XML Vault"
        except Exception:
            pass

    # 3. Try INI / .kdb format
    if not profiles:
        try:
            profiles = parse_ini_kdb_text(text, default_role=default_role, target_env_hint=target_env_hint)
            format_detected = "KDB / INI Profile Config"
        except Exception as err:
            return {"success": False, "profiles": [], "message": f"Failed to parse credential file: {str(err)}"}

    source_profiles = [p for p in profiles if p["conn_role"] == "source"]
    target_dev = next((p for p in profiles if p["conn_role"] == "target" and p["target_env"] == "dev"), None)
    target_prod = next((p for p in profiles if p["conn_role"] == "target" and p["target_env"] == "prod"), None)

    return {
        "success": True,
        "format_detected": format_detected,
        "profiles": profiles,
        "total_count": len(profiles),
        "source_profiles": source_profiles,
        "target_dev": target_dev,
        "target_prod": target_prod,
        "message": f"Successfully parsed {len(profiles)} database connection profile(s) from {format_detected}."
    }
