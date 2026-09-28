"""
Centralized Database Engine & Connection Lifecycle Manager for HLA Studio.
Ensures:
1. Exactly ONE application-scoped Engine per unique database URL/config with bounded pooling.
2. Controlled pool sizes (pool_size, max_overflow, pool_timeout, pool_recycle, pool_pre_ping).
3. Context-managed connection acquisition (with automatic release).
4. Full pool observability and PostgreSQL connection diagnostics.
5. Graceful shutdown / engine disposal.
"""

import os
import re
import sys
import atexit
import logging
import threading
from typing import Dict, Any, Optional, Generator, Tuple
from contextlib import contextmanager

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.pool import QueuePool, NullPool, StaticPool
from sqlalchemy.exc import OperationalError, SQLAlchemyError

logger = logging.getLogger("db_manager")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [DB_MGR] %(message)s")

# Global deployment concurrency limiter (default: max 2 concurrent deployment/loading pipelines)
MAX_CONCURRENT_DEPLOYMENTS = int(os.getenv("MAX_CONCURRENT_DEPLOYMENTS", "2"))
DEPLOYMENT_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_DEPLOYMENTS)


class DatabaseManager:
    """
    Centralized singleton registry for database engines and connection pooling.
    Guarantees that ad-hoc create_engine() calls are completely eliminated.
    """
    _lock = threading.Lock()
    _engines: Dict[str, Engine] = {}
    _engine_configs: Dict[str, dict] = {}

    # Pool Configuration Defaults
    DEFAULT_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    DEFAULT_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    DEFAULT_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DEFAULT_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "300"))  # 5 minutes

    @classmethod
    def _normalize_key(cls, config_or_url: Any) -> str:
        """Generates a canonical cache key for a database target without exposing secrets."""
        if isinstance(config_or_url, dict):
            url = cls.build_url_from_config(config_or_url)
        else:
            url = str(config_or_url).strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        # Mask password in cache key for logging safety
        return re.sub(r':([^/@]+)@', ':***@', url)

    @classmethod
    def build_url_from_config(cls, config: dict) -> str:
        """Builds a standard SQLAlchemy connection URL from a config dictionary."""
        if not config or not isinstance(config, dict):
            return os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hla_db")

        # Explicit connection_string takes precedence
        conn_str = config.get("connection_string") or config.get("conn_str")
        if conn_str and str(conn_str).strip():
            c_str = str(conn_str).strip()
            if c_str.startswith("postgres://"):
                c_str = "postgresql://" + c_str[len("postgres://"):]
            return c_str

        db_type = str(config.get("db_type") or config.get("connection_type") or "postgresql").lower().strip()
        host = config.get("host") or "localhost"
        port = str(config.get("port") or ("5432" if "postgres" in db_type else "3306"))
        database = config.get("database_name") or config.get("database") or config.get("source_db_name") or "hla_db"
        username = config.get("username") or config.get("user") or "postgres"
        password = config.get("password") or ""

        if not password and host in ("localhost", "127.0.0.1"):
            # Check environment fallback for local postgres
            env_url = os.getenv("DATABASE_URL", "")
            if env_url:
                m = re.search(r'://[^:]+:([^@]+)@', env_url)
                if m:
                    password = m.group(1)

        import urllib.parse
        encoded_user = urllib.parse.quote_plus(username) if username else ""
        encoded_pass = urllib.parse.quote_plus(password) if password else ""

        if "sqlite" in db_type:
            if database in (":memory:", ""):
                return "sqlite:///:memory:"
            db_path = database if database.endswith(".db") else f"{database}.db"
            return f"sqlite:///{db_path}"
        elif "postgres" in db_type:
            auth = f"{encoded_user}:{encoded_pass}@" if (encoded_user or encoded_pass) else ""
            return f"postgresql://{auth}{host}:{port}/{database}"
        elif "mysql" in db_type:
            auth = f"{encoded_user}:{encoded_pass}@" if (encoded_user or encoded_pass) else ""
            return f"mysql+pymysql://{auth}{host}:{port}/{database}"
        else:
            auth = f"{encoded_user}:{encoded_pass}@" if (encoded_user or encoded_pass) else ""
            return f"{db_type}://{auth}{host}:{port}/{database}"

    @classmethod
    def get_engine(cls, config_or_url: Any) -> Engine:
        """
        Retrieves or initializes a singleton SQLAlchemy Engine for the given database target.
        Applies strict bounded connection pooling.
        """
        if isinstance(config_or_url, dict):
            raw_url = cls.build_url_from_config(config_or_url)
        else:
            raw_url = str(config_or_url).strip()
            if raw_url.startswith("postgres://"):
                raw_url = "postgresql://" + raw_url[len("postgres://"):]

        norm_key = cls._normalize_key(raw_url)

        with cls._lock:
            if norm_key in cls._engines:
                return cls._engines[norm_key]

            # Configure Engine with bounded pooling
            is_sqlite = "sqlite" in raw_url.lower()
            connect_args = {}
            if not is_sqlite:
                connect_args = {
                    "connect_timeout": 15,
                    "application_name": "hla_studio_engine"
                }

            if is_sqlite:
                if ":memory:" in raw_url:
                    engine = create_engine(
                        raw_url,
                        poolclass=StaticPool,
                        connect_args={"check_same_thread": False}
                    )
                else:
                    engine = create_engine(
                        raw_url,
                        poolclass=QueuePool,
                        pool_size=cls.DEFAULT_POOL_SIZE,
                        max_overflow=cls.DEFAULT_MAX_OVERFLOW,
                        pool_timeout=cls.DEFAULT_POOL_TIMEOUT,
                        pool_recycle=cls.DEFAULT_POOL_RECYCLE,
                        pool_pre_ping=True,
                        connect_args={"check_same_thread": False}
                    )
            else:
                engine = create_engine(
                    raw_url,
                    poolclass=QueuePool,
                    pool_size=cls.DEFAULT_POOL_SIZE,
                    max_overflow=cls.DEFAULT_MAX_OVERFLOW,
                    pool_timeout=cls.DEFAULT_POOL_TIMEOUT,
                    pool_recycle=cls.DEFAULT_POOL_RECYCLE,
                    pool_pre_ping=True,
                    connect_args=connect_args
                )

            cls._engines[norm_key] = engine
            logger.info(f"Initialized application-scoped DB Engine [{norm_key}] (pool_size={cls.DEFAULT_POOL_SIZE}, max_overflow={cls.DEFAULT_MAX_OVERFLOW})")
            return engine

    @classmethod
    @contextmanager
    def connect(cls, config_or_url: Any) -> Generator[Connection, None, None]:
        """
        Safe context manager to acquire and guaranteed-release a connection from the pool.
        Usage:
            with DatabaseManager.connect(cfg) as conn:
                res = conn.execute(text("SELECT ..."))
        """
        engine = cls.get_engine(config_or_url)
        conn = None
        try:
            conn = engine.connect()
            yield conn
        except OperationalError as e:
            err_msg = str(e).lower()
            if "remaining connection slots" in err_msg or "too many clients" in err_msg:
                logger.error(f"DATABASE CONNECTION EXHAUSTED on {cls._normalize_key(config_or_url)}: {e}")
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as ex:
                    logger.warning(f"Error closing connection to {cls._normalize_key(config_or_url)}: {ex}")

    @classmethod
    @contextmanager
    def begin(cls, config_or_url: Any) -> Generator[Connection, None, None]:
        """
        Safe context manager to acquire a transactional connection that automatically commits or rolls back.
        Usage:
            with DatabaseManager.begin(cfg) as conn:
                conn.execute(text("INSERT ..."))
        """
        engine = cls.get_engine(config_or_url)
        conn = None
        try:
            conn = engine.connect()
            trans = conn.begin()
            try:
                yield conn
                trans.commit()
            except Exception:
                trans.rollback()
                raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as ex:
                    logger.warning(f"Error closing transactional connection to {cls._normalize_key(config_or_url)}: {ex}")

    @classmethod
    def get_pool_status(cls, config_or_url: Any = None) -> Dict[str, Any]:
        """Returns connection pool metrics for all or a specific engine."""
        with cls._lock:
            if config_or_url is not None:
                norm_key = cls._normalize_key(config_or_url)
                eng = cls._engines.get(norm_key)
                if not eng:
                    return {"status": "NOT_INITIALIZED", "key": norm_key}
                pool = getattr(eng, "pool", None)
                if pool:
                    return {
                        "key": norm_key,
                        "pool_size": getattr(pool, "size", lambda: None)(),
                        "checked_in": getattr(pool, "checkedin", lambda: None)(),
                        "checked_out": getattr(pool, "checkedout", lambda: None)(),
                        "overflow": getattr(pool, "overflow", lambda: None)(),
                        "timeout": getattr(pool, "_timeout", cls.DEFAULT_POOL_TIMEOUT)
                    }
                return {"status": "NO_POOL", "key": norm_key}

            # Return all active engine pools
            all_pools = {}
            for k, eng in cls._engines.items():
                pool = getattr(eng, "pool", None)
                if pool:
                    all_pools[k] = {
                        "pool_size": getattr(pool, "size", lambda: None)(),
                        "checked_in": getattr(pool, "checkedin", lambda: None)(),
                        "checked_out": getattr(pool, "checkedout", lambda: None)(),
                        "overflow": getattr(pool, "overflow", lambda: None)(),
                    }
            return all_pools

    @classmethod
    def log_pool_status(cls, stage: str, config_or_url: Any = None):
        """Logs structured DB POOL STATUS for observability and leak detection."""
        status = cls.get_pool_status(config_or_url)
        logger.info(f"[DB POOL STATUS] [{stage}] -> {status}")

    @classmethod
    def get_server_diagnostics(cls, config_or_url: Any) -> Dict[str, Any]:
        """
        Queries PostgreSQL catalog for real-time connection capacity and active/idle connections.
        Does NOT expose passwords or sensitive credentials.
        """
        diag = {
            "target": cls._normalize_key(config_or_url),
            "max_connections": None,
            "current_connections": None,
            "active_connections": None,
            "idle_connections": None,
            "available_connections": None,
            "app_pool_status": cls.get_pool_status(config_or_url),
            "status": "UNKNOWN"
        }
        try:
            with cls.connect(config_or_url) as conn:
                # 1. Max connections
                try:
                    max_c_res = conn.execute(text("SHOW max_connections;")).scalar()
                    diag["max_connections"] = int(max_c_res) if max_c_res else 100
                except Exception:
                    diag["max_connections"] = 100

                # 2. pg_stat_activity connection counts
                try:
                    stats_sql = text("""
                        SELECT 
                            count(*) as total,
                            count(*) FILTER (WHERE state = 'active') as active,
                            count(*) FILTER (WHERE state = 'idle') as idle,
                            count(*) FILTER (WHERE state LIKE 'idle in transaction%') as idle_in_trans
                        FROM pg_stat_activity
                        WHERE datname = current_database();
                    """)
                    row = conn.execute(stats_sql).fetchone()
                    if row:
                        diag["current_connections"] = row[0]
                        diag["active_connections"] = row[1]
                        diag["idle_connections"] = row[2]
                        diag["idle_in_transaction"] = row[3]
                        if diag["max_connections"]:
                            diag["available_connections"] = max(0, diag["max_connections"] - diag["current_connections"])
                except Exception as ex:
                    diag["error"] = str(ex)

                diag["status"] = "HEALTHY"
        except Exception as e:
            diag["status"] = "ERROR"
            diag["error"] = str(e)

        return diag

    @classmethod
    def dispose_engine(cls, config_or_url: Any):
        """Disposes a specific engine and frees all underlying pooled connections."""
        norm_key = cls._normalize_key(config_or_url)
        with cls._lock:
            eng = cls._engines.pop(norm_key, None)
            if eng:
                try:
                    eng.dispose()
                    logger.info(f"Disposed DB Engine and closed pool [{norm_key}]")
                except Exception as e:
                    logger.warning(f"Error disposing engine [{norm_key}]: {e}")

    @classmethod
    def dispose_all(cls):
        """Disposes all registered database engines and terminates connection pools."""
        with cls._lock:
            for k, eng in list(cls._engines.items()):
                try:
                    eng.dispose()
                    logger.info(f"Disposed DB Engine [{k}] on shutdown")
                except Exception as e:
                    logger.warning(f"Error disposing engine [{k}]: {e}")
            cls._engines.clear()


# Register cleanup at exit
atexit.register(DatabaseManager.dispose_all)
