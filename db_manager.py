"""
Root alias for DatabaseManager
"""
from backend.services.db_manager import DatabaseManager, DEPLOYMENT_SEMAPHORE

__all__ = ["DatabaseManager", "DEPLOYMENT_SEMAPHORE"]
