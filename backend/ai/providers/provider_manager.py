"""
AI Provider Manager for HLA Studio.
Coordinates provider lifecycle, secure configuration storage, health monitoring,
and routing requests to the configured provider without automatic cloud fallback.
"""

import os
import json
import base64
import logging
import threading
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from backend.ai.providers.base_provider import AIProvider
from backend.ai.providers.ollama_provider import OllamaProvider
from backend.ai.providers.api_provider import APIProvider

logger = logging.getLogger("hla_ai.manager")


def _get_encryption_key() -> bytes:
    """Derives a stable 32-byte encryption key for backend credential encryption."""
    secret = os.getenv("SECRET_KEY", "hla-studio-enterprise-encryption-secret-2026")
    salt = b"hla_ai_provider_salt_v1"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def encrypt_secret(secret_text: str) -> str:
    """Encrypts sensitive credentials for persistence in database."""
    if not secret_text:
        return ""
    try:
        f = Fernet(_get_encryption_key())
        return f.encrypt(secret_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"[AI] Failed to encrypt secret: {e}")
        return secret_text


def decrypt_secret(encrypted_text: str) -> str:
    """Decrypts persisted credentials."""
    if not encrypted_text:
        return ""
    try:
        f = Fernet(_get_encryption_key())
        return f.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return encrypted_text


class AIProviderManager:
    """
    Singleton AI Provider Manager.
    DEFAULT: Local Ollama + qwen3.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AIProviderManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._active_provider_type = os.getenv("AI_PROVIDER", "ollama").lower().strip()
        if self._active_provider_type not in ("ollama", "api"):
            self._active_provider_type = "ollama"

        # Initialize Default Ollama Provider
        self._ollama_provider = OllamaProvider(
            base_url=os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST"),
            model=os.getenv("OLLAMA_MODEL", "qwen3:latest"),
            auto_start=os.getenv("OLLAMA_AUTO_START", "true").lower() in ("true", "1", "yes"),
            auto_pull=os.getenv("OLLAMA_AUTO_PULL", "false").lower() in ("true", "1", "yes")
        )

        # Initialize API Provider (from env if present)
        env_api_key = os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self._api_provider = APIProvider(
            provider_type=os.getenv("API_PROVIDER_TYPE", "openai"),
            api_key=env_api_key,
            model=os.getenv("API_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("API_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        )

        self._initialized = True
        logger.info(f"[AI] AIProviderManager initialized. Active provider: '{self._active_provider_type}'")

    @property
    def active_provider_type(self) -> str:
        return self._active_provider_type

    def get_active_provider(self) -> AIProvider:
        if self._active_provider_type == "api":
            return self._api_provider
        return self._ollama_provider

    def get_ollama_provider(self) -> OllamaProvider:
        return self._ollama_provider

    def get_api_provider(self) -> APIProvider:
        return self._api_provider

    def switch_provider(self, provider_type: str) -> bool:
        p = (provider_type or "ollama").lower().strip()
        if p not in ("ollama", "api"):
            raise ValueError(f"Unknown AI provider type: {provider_type}")
        self._active_provider_type = p
        logger.info(f"[AI] Active AI provider switched to: '{self._active_provider_type}'")
        return True

    def configure_ollama(self, model: Optional[str] = None, base_url: Optional[str] = None):
        if model:
            self._ollama_provider.model = model.strip()
            self._ollama_provider._state["model"] = model.strip()
        if base_url:
            self._ollama_provider.base_url = base_url.rstrip("/")
            self._ollama_provider._state["host"] = base_url.rstrip("/")

    def configure_api(
        self,
        provider_type: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        if provider_type:
            self._api_provider.provider_type = provider_type.lower().strip()
        if api_key is not None and api_key.strip():
            self._api_provider.set_api_key(api_key.strip())
        if model:
            self._api_provider.model = model.strip()
        if base_url is not None:
            self._api_provider.base_url = base_url.rstrip("/") if base_url.strip() else None

    def get_status(self) -> Dict[str, Any]:
        provider = self.get_active_provider()
        health = provider.health_check()
        
        return {
            "active_provider": self._active_provider_type,
            "provider_name": provider.provider_name,
            "is_cloud": provider.is_cloud(),
            "model": provider.get_model(),
            "online": health.get("online", False),
            "available": health.get("available", False),
            "ready": health.get("available", False),
            "model_available": health.get("model_available", False),
            "status": health.get("status", "OFFLINE"),
            "error": health.get("error"),
            "privacy_notice": (
                "AI requests are being processed by the selected external provider."
                if provider.is_cloud()
                else "Prompts and HLA data remain strictly local on your machine."
            ),
            "ollama": {
                "online": self._ollama_provider.is_available(),
                "model": self._ollama_provider.get_model(),
                "status": self._ollama_provider.get_state().get("status", "OFFLINE")
            },
            "api": {
                "has_key": self._api_provider.is_available(),
                "provider_type": self._api_provider.provider_type,
                "model": self._api_provider.get_model(),
                "masked_key": self._api_provider.get_masked_api_key(),
                "endpoint": self._api_provider.base_url
            }
        }

    def get_config(self) -> Dict[str, Any]:
        return {
            "active_provider": self._active_provider_type,
            "ollama": {
                "model": self._ollama_provider.get_model(),
                "base_url": self._ollama_provider.base_url
            },
            "api": {
                "provider_type": self._api_provider.provider_type,
                "model": self._api_provider.get_model(),
                "base_url": self._api_provider.base_url or "",
                "has_api_key": self._api_provider.is_available(),
                "masked_api_key": self._api_provider.get_masked_api_key()
            }
        }

    def test_connection(self, provider_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        p_type = (provider_type or "ollama").lower().strip()
        if p_type == "ollama":
            test_ollama = OllamaProvider(
                base_url=config.get("base_url") or self._ollama_provider.base_url,
                model=config.get("model") or self._ollama_provider.model,
                timeout=10
            )
            health = test_ollama.health_check()
            return {
                "success": health.get("available", False),
                "status": health.get("status", "OFFLINE"),
                "model": test_ollama.get_model(),
                "error": health.get("error")
            }
        elif p_type == "api":
            api_key = config.get("api_key") or self._api_provider._api_key
            test_api = APIProvider(
                provider_type=config.get("provider_type", self._api_provider.provider_type),
                api_key=api_key,
                model=config.get("model", self._api_provider.model),
                base_url=config.get("base_url") or None,
                timeout=15
            )
            health = test_api.health_check()
            return {
                "success": health.get("available", False),
                "status": health.get("status", "OFFLINE"),
                "model": test_api.get_model(),
                "error": health.get("error")
            }
        else:
            return {"success": False, "error": f"Unknown provider '{provider_type}'"}

    def save_settings(self, settings_data: Dict[str, Any], db_session=None) -> Dict[str, Any]:
        provider_choice = settings_data.get("active_provider")
        if provider_choice in ("ollama", "api"):
            self.switch_provider(provider_choice)

        ollama_cfg = settings_data.get("ollama", {})
        if ollama_cfg:
            self.configure_ollama(
                model=ollama_cfg.get("model"),
                base_url=ollama_cfg.get("base_url")
            )

        api_cfg = settings_data.get("api", {})
        if api_cfg:
            new_key = api_cfg.get("api_key")
            if new_key and not new_key.startswith("••"):
                self.configure_api(
                    provider_type=api_cfg.get("provider_type"),
                    api_key=new_key,
                    model=api_cfg.get("model"),
                    base_url=api_cfg.get("base_url")
                )
            else:
                self.configure_api(
                    provider_type=api_cfg.get("provider_type"),
                    model=api_cfg.get("model"),
                    base_url=api_cfg.get("base_url")
                )

        if db_session:
            try:
                from models import SystemSetting
                payload_to_store = {
                    "active_provider": self._active_provider_type,
                    "ollama_model": self._ollama_provider.get_model(),
                    "ollama_base_url": self._ollama_provider.base_url,
                    "api_provider_type": self._api_provider.provider_type,
                    "api_model": self._api_provider.get_model(),
                    "api_base_url": self._api_provider.base_url,
                    "encrypted_api_key": encrypt_secret(self._api_provider._api_key) if self._api_provider._api_key else ""
                }
                
                setting = SystemSetting.query.filter_by(key="ai_provider_config").first()
                if not setting:
                    setting = SystemSetting(
                        key="ai_provider_config",
                        value=json.dumps(payload_to_store),
                        description="HLA Studio AI Provider Configuration"
                    )
                    db_session.add(setting)
                else:
                    setting.value = json.dumps(payload_to_store)
                db_session.commit()
                logger.info("[AI] Provider settings persisted to database successfully")
            except Exception as e:
                logger.error(f"[AI] Could not persist AI settings to DB: {e}")
                if db_session:
                    db_session.rollback()

        return self.get_config()

    def load_persisted_settings(self, db_session):
        if not db_session:
            return
        try:
            from models import SystemSetting
            setting = SystemSetting.query.filter_by(key="ai_provider_config").first()
            if setting and setting.value:
                data = json.loads(setting.value)
                if data.get("active_provider") in ("ollama", "api"):
                    self._active_provider_type = data["active_provider"]
                if data.get("ollama_model"):
                    self.configure_ollama(model=data["ollama_model"], base_url=data.get("ollama_base_url"))
                if data.get("encrypted_api_key"):
                    raw_key = decrypt_secret(data["encrypted_api_key"])
                    self.configure_api(
                        provider_type=data.get("api_provider_type"),
                        api_key=raw_key,
                        model=data.get("api_model"),
                        base_url=data.get("api_base_url")
                    )
                logger.info(f"[AI] Loaded persisted AI settings (Provider: {self._active_provider_type})")
        except Exception as e:
            logger.warning(f"[AI] Note: Could not load persisted AI settings on startup ({e})")


def get_provider_manager() -> AIProviderManager:
    return AIProviderManager()
