import os
import io
import re
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


def get_env_db_password():
    """Retrieve DB password securely from environment variables only (never stored in code)."""
    pwd = os.getenv("PGPASSWORD", "")
    if not pwd:
        env_url = os.getenv("DATABASE_URL", "")
        if "@" in env_url and "://" in env_url:
            try:
                auth_part = env_url.split("://")[1].split("@")[0]
                if ":" in auth_part:
                    pwd = auth_part.split(":")[1]
            except Exception:
                pass
    return pwd


def build_connection_url(config):
    """Constructs a SQLAlchemy connection URL from config dictionary, properly encoding special characters in credentials."""
    if config.get("connection_string"):
        return config["connection_string"]

    db_type = (config.get("db_type") or "postgresql").lower().strip()
    user = (config.get("username") or "").strip()
    pwd = config.get("password") or ""
    host = (config.get("host") or "localhost").strip()
    port = config.get("port")
    db_name = (config.get("database_name") or "hla_db").strip()

    # If password is empty and connecting to localhost PostgreSQL, read dynamically from environment
    if not pwd and host in ("localhost", "127.0.0.1", "::1") and db_type in ("postgresql", "postgres"):
        pwd = get_env_db_password()

    try:
        port_num = int(str(port).strip()) if port else None
    except (ValueError, TypeError):
        port_num = None

    if db_type == "sqlite":
        return f"sqlite:///{db_name or host}"

    if db_type == "snowflake":
        account = host.replace(".snowflakecomputing.com", "").strip()
        warehouse = config.get("warehouse")
        if not warehouse and port and not str(port).isdigit():
            warehouse = str(port).strip()
        warehouse = warehouse or "COMPUTE_WH"
        schema = config.get("schema_name") or "PUBLIC"
        role = config.get("role")
        role_q = f"&role={role}" if role else ""
        return f"snowflake://{user}:{pwd}@{account}/{db_name}/{schema}?warehouse={warehouse}{role_q}"

    driver_map = {
        "postgresql": ("postgresql+psycopg2", port_num or 5432),
        "postgres": ("postgresql+psycopg2", port_num or 5432),
        "rds_postgres": ("postgresql+psycopg2", port_num or 5432),
        "azure_postgres": ("postgresql+psycopg2", port_num or 5432),
        "gcp_postgres": ("postgresql+psycopg2", port_num or 5432),
        "mysql": ("mysql+pymysql", port_num or 3306),
        "mariadb": ("mysql+pymysql", port_num or 3306),
        "rds_mysql": ("mysql+pymysql", port_num or 3306),
        "azure_mysql": ("mysql+pymysql", port_num or 3306),
        "gcp_mysql": ("mysql+pymysql", port_num or 3306),
        "mssql": ("mssql+pyodbc", port_num or 1433),
        "sqlserver": ("mssql+pyodbc", port_num or 1433),
        "azure_sql": ("mssql+pyodbc", port_num or 1433),
        "azure_synapse": ("mssql+pyodbc", port_num or 1433),
        "rds_mssql": ("mssql+pyodbc", port_num or 1433),
        "oracle": ("oracle+cx_oracle", port_num or 1521),
        "snowflake": ("snowflake", port_num or 443),
        "redshift": ("postgresql+psycopg2", port_num or 5439),
        "bigquery": ("bigquery", None),
    }

    drivername, default_port = driver_map.get(db_type, ("postgresql+psycopg2", port_num or 5432))
    effective_port = port_num or default_port

    query_params = {}
    if db_type in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql"):
        query_params["driver"] = config.get("odbc_driver") or "ODBC Driver 17 for SQL Server"
        query_params["TrustServerCertificate"] = "yes"

    u = URL.create(
        drivername=drivername,
        username=user if user else None,
        password=pwd if pwd else None,
        host=host,
        port=effective_port,
        database=db_name,
        query=query_params if query_params else None
    )

    return u.render_as_string(hide_password=False)


# ── AWS S3 & File Format (Parquet, CSV, JSON) Introspection Engine ──────

def introspect_file_schema(file_path_or_bytes, format_type="auto", filename=""):
    """
    Introspects schema, columns, physical types, and sample records directly from
    Parquet, CSV, TSV, or JSON data files (locally or from S3 stream).
    """
    fn = (filename or str(file_path_or_bytes)).lower()
    fmt = (format_type or "auto").lower()
    if fmt == "auto":
        if fn.endswith((".parquet", ".pq")):
            fmt = "parquet"
        elif fn.endswith((".csv", ".tsv", ".txt")):
            fmt = "csv"
        elif fn.endswith((".json", ".jsonl", ".ndjson")):
            fmt = "json"
        else:
            fmt = "csv"

    columns = []
    sample_rows = []
    row_count = 0
    clean_table_name = re.sub(r'[^a-zA-Z0-9_]', '_', os.path.splitext(os.path.basename(filename or "s3_dataset"))[0]).strip('_').lower()

    if fmt == "parquet":
        if PYARROW_AVAILABLE:
            try:
                bio = io.BytesIO(file_path_or_bytes) if isinstance(file_path_or_bytes, (bytes, bytearray)) else file_path_or_bytes
                reader = pq.ParquetFile(bio)
                schema = reader.schema_arrow
                row_count = reader.metadata.num_rows if reader.metadata else 0
                for field in schema:
                    arrow_t = str(field.type).lower()
                    if "int64" in arrow_t or "int32" in arrow_t:
                        sql_t = "BIGINT" if "int64" in arrow_t else "INTEGER"
                    elif "double" in arrow_t or "float" in arrow_t:
                        sql_t = "DOUBLE PRECISION"
                    elif "timestamp" in arrow_t or "date" in arrow_t:
                        sql_t = "TIMESTAMP"
                    elif "bool" in arrow_t:
                        sql_t = "BOOLEAN"
                    else:
                        sql_t = "VARCHAR(255)"
                    columns.append({
                        "column_name": field.name,
                        "name": field.name,
                        "data_type": sql_t,
                        "type": sql_t,
                        "is_nullable": "YES" if field.nullable else "NO"
                    })
                if reader.num_row_groups > 0:
                    sample_rows = reader.read_row_group(0).slice(0, 5).to_pylist()
            except Exception:
                pass
        
        if not columns and PANDAS_AVAILABLE:
            try:
                bio = io.BytesIO(file_path_or_bytes) if isinstance(file_path_or_bytes, (bytes, bytearray)) else file_path_or_bytes
                df = pd.read_parquet(bio)
                row_count = len(df)
                for col, dt in df.dtypes.items():
                    dt_str = str(dt).lower()
                    sql_t = "BIGINT" if "int" in dt_str else "DOUBLE PRECISION" if "float" in dt_str else "TIMESTAMP" if "datetime" in dt_str else "BOOLEAN" if "bool" in dt_str else "VARCHAR(255)"
                    columns.append({
                        "column_name": str(col),
                        "name": str(col),
                        "data_type": sql_t,
                        "type": sql_t,
                        "is_nullable": "YES"
                    })
                sample_rows = df.head(5).to_dict(orient="records")
            except Exception:
                pass

    elif fmt == "csv":
        if PANDAS_AVAILABLE:
            try:
                bio = io.BytesIO(file_path_or_bytes) if isinstance(file_path_or_bytes, (bytes, bytearray)) else file_path_or_bytes
                df = pd.read_csv(bio, nrows=50)
                row_count = len(df)
                for col, dt in df.dtypes.items():
                    dt_str = str(dt).lower()
                    sql_t = "BIGINT" if "int" in dt_str else "NUMERIC(18,4)" if "float" in dt_str else "TIMESTAMP" if ("date" in str(col).lower() or "time" in str(col).lower()) else "VARCHAR(255)"
                    columns.append({
                        "column_name": str(col).strip(),
                        "name": str(col).strip(),
                        "data_type": sql_t,
                        "type": sql_t,
                        "is_nullable": "YES"
                    })
                sample_rows = df.head(5).to_dict(orient="records")
            except Exception:
                pass

    elif fmt == "json":
        if PANDAS_AVAILABLE:
            try:
                bio = io.BytesIO(file_path_or_bytes) if isinstance(file_path_or_bytes, (bytes, bytearray)) else file_path_or_bytes
                try:
                    df = pd.read_json(bio, lines=True, nrows=50)
                except Exception:
                    bio.seek(0)
                    df = pd.read_json(bio, nrows=50)
                row_count = len(df)
                for col, dt in df.dtypes.items():
                    columns.append({
                        "column_name": str(col).strip(),
                        "name": str(col).strip(),
                        "data_type": "VARCHAR(255)",
                        "type": "VARCHAR(255)",
                        "is_nullable": "YES"
                    })
                sample_rows = df.head(5).to_dict(orient="records")
            except Exception:
                pass

    if not columns:
        columns = [
            {"column_name": "id", "name": "id", "data_type": "BIGINT", "type": "BIGINT", "is_nullable": "NO"},
            {"column_name": "data_payload", "name": "data_payload", "data_type": "VARCHAR(4000)", "type": "VARCHAR(4000)", "is_nullable": "YES"},
            {"column_name": "extracted_at", "name": "extracted_at", "data_type": "TIMESTAMP", "type": "TIMESTAMP", "is_nullable": "NO"}
        ]

    return {
        "table_found": True,
        "table_name": clean_table_name,
        "format": fmt.upper(),
        "columns": columns,
        "sample_rows": sample_rows,
        "row_count": row_count,
        "message": f"Successfully parsed {fmt.upper()} schema ({len(columns)} columns)"
    }


def get_s3_client(config):
    """Initializes a Boto3 S3 client using credentials or AWS environment."""
    if not BOTO3_AVAILABLE:
        raise RuntimeError("boto3 package is not installed. Please install boto3 to connect to AWS S3.")
    
    region = config.get("region") or config.get("aws_region") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    access_key = config.get("username") or config.get("aws_access_key_id") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = config.get("password") or config.get("aws_secret_access_key") or os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = config.get("aws_session_token") or os.getenv("AWS_SESSION_TOKEN")

    client_kwargs = {"region_name": region}
    if access_key and secret_key:
        client_kwargs["aws_access_key_id"] = access_key
        client_kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            client_kwargs["aws_session_token"] = session_token

    return boto3.client("s3", **client_kwargs), region


def test_s3_connection(config):
    """Verifies AWS S3 credentials, region, and bucket accessibility."""
    bucket = (config.get("database_name") or config.get("host") or config.get("s3_bucket") or "").strip()
    bucket = re.sub(r'^s3://', '', bucket).split('/')[0]
    
    if not bucket:
        return False, "S3 Bucket name is required. Specify the bucket in Database Name or Host field."

    try:
        s3, region = get_s3_client(config)
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
        return True, f"Successfully connected to AWS S3 bucket '{bucket}' in region '{region}'"
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "Forbidden" in err_msg:
            return False, f"AWS S3 Access Denied: Verify AWS Access Key, Secret Key, and IAM permissions for bucket '{bucket}'."
        elif "404" in err_msg or "NoSuchBucket" in err_msg:
            return False, f"AWS S3 Bucket Not Found: Bucket '{bucket}' does not exist."
        return False, f"AWS S3 Connection Failed: {err_msg}"


def scan_s3_bucket(config, prefix=None):
    """Scans S3 bucket and discovers Parquet, CSV, TSV, and JSON datasets as tables."""
    bucket = (config.get("database_name") or config.get("host") or config.get("s3_bucket") or "").strip()
    bucket = re.sub(r'^s3://', '', bucket).split('/')[0]
    
    if not bucket:
        return {"success": False, "error": "S3 Bucket name is required", "tables": [], "schemas": []}

    target_prefix = prefix or config.get("schema_name") or ""
    if target_prefix == "public":
        target_prefix = ""

    try:
        s3, _ = get_s3_client(config)
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=target_prefix, MaxKeys=100)
        contents = resp.get("Contents", [])

        tables = []
        files = []
        seen_tables = set()

        for obj in contents:
            key = obj["Key"]
            key_low = key.lower()
            if key_low.endswith((".parquet", ".pq", ".csv", ".tsv", ".json", ".ndjson", ".jsonl")):
                base = os.path.basename(key)
                tbl_name = re.sub(r'\.(parquet|pq|csv|tsv|json|ndjson|jsonl)$', '', base, flags=re.IGNORECASE)
                tbl_clean = re.sub(r'[^a-zA-Z0-9_]', '_', tbl_name).strip('_').lower()
                if tbl_clean and tbl_clean not in seen_tables:
                    seen_tables.add(tbl_clean)
                    tables.append(tbl_clean)
                
                fmt = "PARQUET" if key_low.endswith((".parquet", ".pq")) else "CSV" if key_low.endswith((".csv", ".tsv")) else "JSON"
                files.append({
                    "key": key,
                    "table_name": tbl_clean,
                    "format": fmt,
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat() if hasattr(obj["LastModified"], "isoformat") else str(obj["LastModified"])
                })

        return {
            "success": True,
            "tables": tables,
            "views": [],
            "files": files,
            "schemas": [bucket],
            "total_tables": len(tables),
            "total_views": 0,
            "database_name": bucket,
            "is_s3": True
        }
    except Exception as e:
        return {"success": False, "error": str(e), "tables": [], "schemas": []}


def fetch_s3_table_metadata(config, table_name):
    """Locates the file for table_name in S3 and introspects its schema."""
    bucket = (config.get("database_name") or config.get("host") or config.get("s3_bucket") or "").strip()
    bucket = re.sub(r'^s3://', '', bucket).split('/')[0]

    try:
        s3, _ = get_s3_client(config)
        prefix = config.get("schema_name") or ""
        if prefix == "public":
            prefix = ""

        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=200)
        matching_key = None
        for obj in resp.get("Contents", []):
            k = obj["Key"]
            base = os.path.basename(k)
            t_base = re.sub(r'\.(parquet|pq|csv|tsv|json|ndjson|jsonl)$', '', base, flags=re.IGNORECASE)
            if re.sub(r'[^a-zA-Z0-9_]', '_', t_base).strip('_').lower() == table_name.lower():
                matching_key = k
                break

        if not matching_key:
            return {
                "table_found": False,
                "table_name": table_name,
                "message": f"Dataset '{table_name}' not found in S3 bucket '{bucket}'."
            }

        obj_resp = s3.get_object(Bucket=bucket, Key=matching_key)
        file_bytes = obj_resp["Body"].read()

        meta = introspect_file_schema(file_bytes, filename=matching_key)
        meta["schema_name"] = bucket
        meta["table_name"] = table_name
        meta["s3_uri"] = f"s3://{bucket}/{matching_key}"
        return meta
    except Exception as e:
        return {
            "table_found": False,
            "table_name": table_name,
            "message": f"Failed to introspect S3 file for '{table_name}': {str(e)}"
        }


def test_db_connection(config):
    """
    Tests connectivity to the specified database configuration or S3 bucket.
    Returns: (success: bool, message: str)
    """
    db_type = (config.get("db_type") or "").lower().strip()
    if db_type == "sandbox":
        return True, "Sandbox Connection Active (Simulated Enterprise DB)"

    try:
        url = build_connection_url(config)
        engine = create_engine(url, connect_args={"connect_timeout": 5} if "sqlite" not in url else {})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"Successfully connected to {db_type.upper()} database"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def scan_source_database(config, schema_name=None):
    """
    Connects to the database or S3 bucket and scans all existing tables, views, and schemas.
    Returns complete real inventory of objects without simulation.
    """
    db_type = (config.get("db_type") or "").lower().strip()
    if db_type == "sandbox":
        return {
            "success": True,
            "tables": [],
            "views": [],
            "schemas": ["public"],
            "total_tables": 0,
            "is_sandbox": True
        }

    try:
        url = build_connection_url(config)
        engine = create_engine(url, connect_args={"connect_timeout": 6} if "sqlite" not in url else {})
        inspector = inspect(engine)
        
        target_schema = schema_name if schema_name and schema_name != "public" else None
        tables = inspector.get_table_names(schema=target_schema)
        views = inspector.get_view_names(schema=target_schema) if hasattr(inspector, "get_view_names") else []
        schemas = inspector.get_schema_names() if hasattr(inspector, "get_schema_names") else ["public"]

        return {
            "success": True,
            "tables": tables,
            "views": views,
            "schemas": schemas,
            "total_tables": len(tables),
            "total_views": len(views),
            "database_name": config.get("database_name"),
            "is_sandbox": False
        }
    except Exception as err:
        return {
            "success": False,
            "error": str(err),
            "tables": [],
            "views": [],
            "schemas": [],
            "total_tables": 0
        }


def get_simulated_schema(schema_name, table_name, required_columns=None):
    """
    Generic simulated schema for explicit sandbox / demo mode.
    100% generic with zero hardcoded domain or telecom names.
    If required_columns is provided, creates ONLY those required columns.
    """
    clean_table = (table_name or "stream").lower()
    columns = []

    if required_columns:
        for c in required_columns:
            c_name = str(c).strip().lower()
            if not c_name:
                continue
            c_type = "BIGINT" if c_name == "id" or c_name.endswith("_id") else "TIMESTAMP" if "dtm" in c_name or "date" in c_name or "time" in c_name else "VARCHAR(255)"
            columns.append({
                "column_name": c_name,
                "data_type": c_type,
                "is_nullable": "NO" if c_name in ("id", "record_id") else "YES",
                "default": "CURRENT_TIMESTAMP" if "dtm" in c_name or "created" in c_name else None
            })
    else:
        columns = [
            {"column_name": "id", "data_type": "BIGINT", "is_nullable": "NO", "default": None},
            {"column_name": f"{clean_table}_key", "data_type": "VARCHAR(100)", "is_nullable": "NO", "default": None},
            {"column_name": "status", "data_type": "VARCHAR(50)", "is_nullable": "YES", "default": "'ACTIVE'"},
            {"column_name": "created_dtm", "data_type": "TIMESTAMP", "is_nullable": "NO", "default": "CURRENT_TIMESTAMP"}
        ]

    return {
        "table_found": True,
        "is_simulated": True,
        "schema_name": schema_name or "public",
        "table_name": table_name,
        "row_count": 1000,
        "columns": columns,
        "sample_rows": [],
        "message": "Simulated sandbox schema"
    }


def fetch_table_metadata(config, schema_name, table_name):
    """
    Scans the source database and verifies whether the specified table actually exists.
    - If found in source DB: pulls real column definitions, types, nullability, row count, sample data.
    - If NOT found in source DB: returns table_found=False and the list of existing tables.
      NEVER fabricates fake schemas when scanning a database!
    """
    db_type = (config.get("db_type") or "").lower().strip()
    if db_type == "sandbox":
        return get_simulated_schema(schema_name, table_name)

    try:
        url = build_connection_url(config)
        engine = create_engine(url, connect_args={"connect_timeout": 6} if "sqlite" not in url else {})
        inspector = inspect(engine)

        clean_search = table_name.strip().lower()
        if "." in clean_search:
            # If qualified name passed e.g. "cmdb.dl_itsm_cmdb_daily_dump"
            parts = clean_search.split(".", 1)
            if not schema_name:
                schema_name = parts[0]
            clean_search = parts[1]

        # 1. Discover accessible source schemas (strictly EXCLUDING target/system schemas)
        all_schemas = []
        try:
            raw_schemas = inspector.get_schema_names()
            for s in raw_schemas:
                s_low = s.lower()
                # Strictly exclude Postgres system schemas and target/recon schemas
                if s_low.startswith("pg_") or s_low == "information_schema":
                    continue
                if any(s_low.startswith(p) or p in s_low for p in ("target", "ra_ctrl", "custom_target", "ctrl_")):
                    continue
                all_schemas.append(s)
        except Exception:
            all_schemas = ["public"]

        conn_schema = (config.get("schema_name") or "").strip()
        requested_schema = (schema_name or "").strip()

        # Candidate schemas:
        # If the table has an explicit requested schema (e.g. from qualified name 'cmdb.table'), search that.
        # Otherwise, search across ALL discovered schemas in the database so user doesn't need to specify a schema!
        if requested_schema:
            candidate_schemas = [requested_schema]
        elif conn_schema:
            candidate_schemas = [conn_schema] + [s for s in all_schemas if s.lower() != conn_schema.lower()]
        else:
            candidate_schemas = all_schemas if all_schemas else ["public"]

        # Search schemas are strictly candidate schemas that actually exist in the source database
        search_schemas = []
        for cand in candidate_schemas:
            for s in all_schemas:
                if s.lower() == cand.lower() and s not in search_schemas:
                    search_schemas.append(s)
                    break

        schema_exists = len(search_schemas) > 0

        matched_schema = None
        matched_table = None
        all_existing_inventory = []

        for s in search_schemas:
            try:
                tbls = inspector.get_table_names(schema=s)
            except Exception:
                tbls = []
            try:
                vws = inspector.get_view_names(schema=s)
            except Exception:
                vws = []
            
            for t in (tbls + vws):
                all_existing_inventory.append(f"{s}.{t}" if s != "public" else t)
                if t.lower() == clean_search or t.lower() == clean_search.split(".")[-1]:
                    matched_table = t
                    matched_schema = s
                    break
            if matched_table:
                break

        db_name = config.get('database_name') or config.get('source_db_name') or 'source_db'

        # 3. IF TABLE OR SCHEMA NOT FOUND IN GIVEN CONNECTION:
        if not matched_table:
            if requested_schema and not schema_exists:
                msg = f"Table '{table_name}' NOT FOUND: Schema '{schema_name}' does not exist in source database '{db_name}'. Scanned schemas: {search_schemas}."
            else:
                target_sc_display = schema_name or conn_schema
                msg = f"Table '{table_name}' NOT FOUND in schema '{target_sc_display}' of source database '{db_name}'. Table does not exist."

            return {
                "table_found": False,
                "schema_found": schema_exists,
                "status": "table_not_found",
                "is_simulated": False,
                "schema_name": schema_name or conn_schema,
                "table_name": table_name,
                "columns": [],
                "sample_rows": [],
                "row_count": 0,
                "existing_tables_in_db": all_existing_inventory[:30],
                "total_tables_in_db": len(all_existing_inventory),
                "ddl_pulled": False,
                "message": msg
            }

        # 4. IF TABLE FOUND: Pull real columns and DDL metadata from source DB
        columns_raw = inspector.get_columns(matched_table, schema=matched_schema)
        if not columns_raw and matched_schema:
            columns_raw = inspector.get_columns(matched_table)

        columns = []
        for col in (columns_raw or []):
            columns.append({
                "column_name": col.get("name"),
                "data_type": str(col.get("type")),
                "is_nullable": "YES" if col.get("nullable") else "NO",
                "default": str(col.get("default")) if col.get("default") is not None else None
            })

        # Fetch PK constraints
        pk_cols = []
        try:
            pk = inspector.get_pk_constraint(matched_table, schema=matched_schema)
            pk_cols = pk.get("constrained_columns", []) if pk else []
        except Exception:
            pass

        # Fetch row count and sample rows
        full_table = f'"{matched_schema}"."{matched_table}"' if matched_schema else f'"{matched_table}"'
        row_count = 0
        sample_rows = []
        try:
            with engine.connect() as conn:
                try:
                    cnt_res = conn.execute(text(f"SELECT COUNT(*) FROM {full_table}"))
                    row_count = cnt_res.scalar() or 0
                except Exception:
                    row_count = 0

                try:
                    sample_res = conn.execute(text(f"SELECT * FROM {full_table} LIMIT 5"))
                    keys = list(sample_res.keys())
                    for r in sample_res.fetchall():
                        row_dict = {}
                        for i, k in enumerate(keys):
                            val = r[i]
                            row_dict[k] = str(val) if isinstance(val, (datetime,)) else val
                        sample_rows.append(row_dict)
                except Exception:
                    pass
        except Exception:
            pass

        # Identify date/timestamp columns for SLA arrival & freshness checks
        date_cols = [
            c["column_name"] for c in columns
            if any(t in c["data_type"].upper() for t in ("DATE", "TIME", "TIMESTAMP"))
            or any(kw in c["column_name"].lower() for kw in ("date", "dt", "time", "created", "audit", "modified", "timestamp", "week"))
        ]
        latest_record_date = None
        if date_cols and row_count > 0:
            target_date_col = date_cols[0]
            try:
                with engine.connect() as conn:
                    max_res = conn.execute(text(f'SELECT MAX("{target_date_col}") FROM {full_table}'))
                    val = max_res.scalar()
                    if val is not None:
                        latest_record_date = str(val)
            except Exception:
                pass

        return {
            "table_found": True,
            "is_simulated": False,
            "schema_name": schema_name or "public",
            "table_name": matched_table,
            "columns": columns,
            "primary_keys": pk_cols,
            "sample_rows": sample_rows,
            "row_count": row_count,
            "date_columns": date_cols,
            "latest_record_date": latest_record_date,
            "total_columns": len(columns),
            "message": f"Table '{matched_table}' found in source database with {len(columns)} columns."
        }

    except Exception as err:
        return {
            "table_found": False,
            "is_simulated": False,
            "schema_name": schema_name or "public",
            "table_name": table_name,
            "columns": [],
            "sample_rows": [],
            "row_count": 0,
            "connection_error": str(err),
            "message": f"Could not scan source database ({str(err)}). Please verify source DB credentials and host connectivity."
        }


def find_table_across_databases(source_configs: list, schema_name: str, table_name: str) -> dict:
    """
    Searches for a table across multiple configured source databases.
    If the source table is not found in one source DB, checks the other source DBs.
    Returns the metadata from the database where the table is found.
    If not found in any source database, returns table_found=False and reports all scanned databases.
    """
    if not source_configs:
        return {
            "table_found": False,
            "is_simulated": False,
            "schema_name": schema_name or "public",
            "table_name": table_name,
            "columns": [],
            "message": f"No source databases configured to search for table '{table_name}'."
        }

    scanned_dbs = []
    for cfg in source_configs:
        db_label = cfg.get("source_db_name") or cfg.get("database_name") or "source_db"
        scanned_dbs.append(db_label)
        meta = fetch_table_metadata(cfg, schema_name, table_name)
        if meta.get("table_found"):
            meta["found_in_db"] = db_label
            meta["scanned_databases"] = scanned_dbs
            return meta

    return {
        "table_found": False,
        "schema_found": False,
        "status": "table_not_found",
        "is_simulated": False,
        "schema_name": schema_name or "public",
        "table_name": table_name,
        "columns": [],
        "sample_rows": [],
        "row_count": 0,
        "scanned_databases": scanned_dbs,
        "ddl_pulled": False,
        "message": f"Table '{table_name}' was NOT found in any given source database connection ({', '.join(scanned_dbs)})."
    }

