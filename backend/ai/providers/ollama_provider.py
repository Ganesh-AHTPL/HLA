"""
Local Ollama AI Provider for HLA Studio.
Default AI provider maintaining local-first privacy and offline capability.
"""

import os
import re
import time
import logging
import threading
from typing import Dict, Any, List, Optional
import requests

from backend.ai.providers.base_provider import AIProvider

logger = logging.getLogger("hla_ai.ollama")


class OllamaProvider(AIProvider):
    """
    Implements local Ollama integration for qwen3 (or configured local model).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 180,
        auto_start: bool = True,
        auto_pull: bool = False
    ):
        self.provider_name = "ollama"
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
        self.model = (model or os.getenv("OLLAMA_MODEL") or "qwen3:latest").strip()
        self.timeout = timeout
        self.auto_start = auto_start
        self.auto_pull = auto_pull
        self._lock = threading.Lock()
        self._state = {
            "enabled": True,
            "online": False,
            "model": self.model,
            "model_available": False,
            "ready": False,
            "status": "STARTING",
            "host": self.base_url,
            "error": None
        }

    def get_model(self) -> str:
        return self.model

    def is_cloud(self) -> bool:
        return False

    def is_available(self) -> bool:
        with self._lock:
            return bool(self._state.get("ready", False))

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _update_state(self, **kwargs):
        with self._lock:
            self._state.update(kwargs)

    def _is_model_installed(self, available_models: list, configured_model: str) -> bool:
        cfg = configured_model.lower()
        cfg_base = cfg.split(":")[0]
        for m in available_models:
            if not m:
                continue
            m_lower = m.lower()
            m_base = m_lower.split(":")[0]
            if m_lower == cfg:
                return True
            if m_base == cfg_base and (":" not in cfg or cfg.endswith(":latest")):
                return True
            if m_lower == cfg_base:
                return True
        return False

    def health_check(self) -> Dict[str, Any]:
        """Performs a live health check against the local Ollama API."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if res.status_code == 200:
                data = res.json()
                installed_models = [m.get("name", "") for m in data.get("models", [])]
                model_found = self._is_model_installed(installed_models, self.model)
                
                if model_found:
                    self._update_state(
                        online=True,
                        model_available=True,
                        ready=True,
                        status="READY",
                        error=None
                    )
                    return {
                        "available": True,
                        "online": True,
                        "model": self.model,
                        "model_available": True,
                        "status": "READY",
                        "error": None
                    }
                else:
                    self._update_state(
                        online=True,
                        model_available=False,
                        ready=False,
                        status="MODEL_MISSING",
                        error=f"Configured AI model '{self.model}' is not installed in local Ollama. Run: ollama pull {self.model}"
                    )
                    return {
                        "available": False,
                        "online": True,
                        "model": self.model,
                        "model_available": False,
                        "status": "MODEL_MISSING",
                        "error": f"Configured AI model '{self.model}' is not installed in local Ollama. Run: ollama pull {self.model}"
                    }
        except Exception:
            self._update_state(
                online=False,
                model_available=False,
                ready=False,
                status="OFFLINE",
                error="Local Ollama is unavailable. Start Ollama or select an API provider."
            )
            return {
                "available": False,
                "online": False,
                "model": self.model,
                "model_available": False,
                "status": "OFFLINE",
                "error": "Local Ollama is unavailable. Start Ollama or select an API provider."
            }

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Dispatches chat request to Ollama /api/chat with /api/generate fallback."""
        if not self.is_available():
            health = self.health_check()
            if not health.get("available"):
                err_msg = health.get("error") or "Local Ollama is unavailable. Start Ollama or select an API provider."
                return self.format_standard_response(
                    text=f"Error: {err_msg}",
                    confidence=0.0,
                    raw_response={"error": err_msg}
                )

        temp = kwargs.get("temperature", 0.2)
        top_p = kwargs.get("top_p", 0.9)
        num_predict = kwargs.get("num_predict", kwargs.get("max_tokens", 450))

        chat_url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temp,
                "top_p": top_p,
                "num_predict": num_predict
            }
        }

        try:
            res = requests.post(chat_url, json=payload, timeout=self.timeout)
            if res.status_code == 404:
                generate_url = f"{self.base_url}/api/generate"
                combined_prompt = "\n\n".join([f"{m.get('role', 'user').upper()}:\n{m.get('content', '')}" for m in messages])
                gen_payload = {
                    "model": self.model,
                    "prompt": combined_prompt,
                    "stream": False,
                    "options": {
                        "temperature": temp,
                        "top_p": top_p,
                        "num_predict": num_predict
                    }
                }
                res = requests.post(generate_url, json=gen_payload, timeout=self.timeout)

            if res.status_code == 200:
                data = res.json()
                raw_text = (
                    data.get("message", {}).get("content") or
                    data.get("response") or
                    ""
                ).strip()
                return self.format_standard_response(
                    text=raw_text,
                    raw_response=data
                )
            else:
                logger.error(f"[AI] Ollama returned HTTP {res.status_code}: {res.text[:200]}")
                return self.format_standard_response(
                    text="Local Ollama is unavailable. Start Ollama or select an API provider.",
                    confidence=0.0,
                    raw_response={"status_code": res.status_code, "text": res.text}
                )
        except requests.exceptions.Timeout:
            logger.error(f"[AI] Ollama inference timed out after {self.timeout}s")
            return self.format_standard_response(
                text="AI request timed out. Please try again or optimize your prompt.",
                confidence=0.0,
                raw_response={"error": "timeout"}
            )
        except requests.exceptions.ConnectionError:
            logger.error(f"[AI] Connection refused to Ollama at {self.base_url}")
            return self.format_standard_response(
                text="Local Ollama is unavailable. Start Ollama or select an API provider.",
                confidence=0.0,
                raw_response={"error": "connection_error"}
            )
        except Exception as e:
            logger.error(f"[AI] Unexpected error in OllamaProvider: {e}")
            return self.format_standard_response(
                text="An unexpected error occurred while communicating with Ollama.",
                confidence=0.0,
                raw_response={"error": str(e)}
            )

    def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)
