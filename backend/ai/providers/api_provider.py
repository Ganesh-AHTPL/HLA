"""
Configurable Cloud / API Provider for HLA Studio.
Enables switching to external models (OpenAI, Anthropic, Groq, custom OpenAI-compatible endpoints)
without changing any HLA business logic, NLU, database tools, or frontend functionality.
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
import requests

from backend.ai.providers.base_provider import AIProvider

logger = logging.getLogger("hla_ai.api")


class APIProvider(AIProvider):
    """
    Implements cloud/external AI model access via standard API endpoints.
    """

    def __init__(
        self,
        provider_type: str = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60
    ):
        self.provider_name = "api"
        self.provider_type = (provider_type or "openai").lower().strip()
        self._api_key = api_key or ""
        self.timeout = timeout
        
        # Determine model default
        if model:
            self.model = model.strip()
        elif self.provider_type == "anthropic":
            self.model = "claude-3-5-sonnet-20241022"
        elif self.provider_type == "groq":
            self.model = "llama-3.3-70b-versatile"
        else:
            self.model = "gpt-4o-mini"

        # Determine base_url default
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif self.provider_type == "anthropic":
            self.base_url = "https://api.anthropic.com/v1"
        elif self.provider_type == "groq":
            self.base_url = "https://api.groq.com/openai/v1"
        else:
            self.base_url = "https://api.openai.com/v1"

    def get_model(self) -> str:
        return self.model

    def is_cloud(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._api_key and len(self._api_key.strip()) > 5)

    def set_api_key(self, api_key: str):
        self._api_key = (api_key or "").strip()

    def get_masked_api_key(self) -> str:
        if not self._api_key:
            return ""
        if len(self._api_key) <= 8:
            return "••••••••"
        return f"{self._api_key[:3]}••••{self._api_key[-4:]}"

    def health_check(self) -> Dict[str, Any]:
        """Validates the API key and endpoint connectivity."""
        if not self._api_key:
            return {
                "available": False,
                "online": False,
                "model": self.model,
                "model_available": False,
                "status": "KEY_MISSING",
                "error": "API connection failed. Check the API key and provider settings."
            }

        try:
            test_resp = self.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0.0
            )
            if test_resp.get("confidence", 0) > 0 and not test_resp.get("text", "").startswith("Error:"):
                return {
                    "available": True,
                    "online": True,
                    "model": self.model,
                    "model_available": True,
                    "status": "READY",
                    "error": None
                }
            else:
                return {
                    "available": False,
                    "online": False,
                    "model": self.model,
                    "model_available": False,
                    "status": "AUTH_FAILED",
                    "error": "API connection failed. Check the API key and provider settings."
                }
        except Exception as e:
            logger.error(f"[AI] API health check failed: {type(e).__name__}")
            return {
                "available": False,
                "online": False,
                "model": self.model,
                "model_available": False,
                "status": "ERROR",
                "error": "API connection failed. Check the API key and provider settings."
            }

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Dispatches chat completion request to the configured API provider."""
        if not self._api_key:
            return self.format_standard_response(
                text="API connection failed. Check the API key and provider settings.",
                confidence=0.0,
                raw_response={"error": "API key not configured"}
            )

        temp = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 600)

        if self.provider_type == "anthropic":
            return self._call_anthropic(messages, temp=temp, max_tokens=max_tokens)
        else:
            return self._call_openai_compatible(messages, temp=temp, max_tokens=max_tokens)

    def _call_openai_compatible(self, messages: List[Dict[str, str]], temp: float, max_tokens: int) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens
        }

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    return self.format_standard_response(text=content, raw_response=data)
                return self.format_standard_response(text="", raw_response=data)
            elif res.status_code in (401, 403):
                logger.error(f"[AI] API Provider authentication failed (HTTP {res.status_code})")
                return self.format_standard_response(
                    text="API connection failed. Check the API key and provider settings.",
                    confidence=0.0,
                    raw_response={"status_code": res.status_code}
                )
            else:
                logger.error(f"[AI] API Provider returned HTTP {res.status_code}: {res.text[:200]}")
                return self.format_standard_response(
                    text="API connection failed. Check the API key and provider settings.",
                    confidence=0.0,
                    raw_response={"status_code": res.status_code, "text": res.text[:200]}
                )
        except requests.exceptions.Timeout:
            logger.error(f"[AI] API Provider request timed out after {self.timeout}s")
            return self.format_standard_response(
                text="API request timed out. Please try again later.",
                confidence=0.0,
                raw_response={"error": "timeout"}
            )
        except Exception as e:
            logger.error(f"[AI] Error calling API Provider: {type(e).__name__}")
            return self.format_standard_response(
                text="API connection failed. Check the API key and provider settings.",
                confidence=0.0,
                raw_response={"error": type(e).__name__}
            )

    def _call_anthropic(self, messages: List[Dict[str, str]], temp: float, max_tokens: int) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        system_text = ""
        user_assistant_msgs = []
        for m in messages:
            if m.get("role") == "system":
                system_text += f"\n{m.get('content', '')}"
            else:
                user_assistant_msgs.append({
                    "role": "user" if m.get("role") == "user" else "assistant",
                    "content": m.get("content", "")
                })

        payload = {
            "model": self.model,
            "messages": user_assistant_msgs,
            "temperature": temp,
            "max_tokens": max_tokens
        }
        if system_text.strip():
            payload["system"] = system_text.strip()

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
            if res.status_code == 200:
                data = res.json()
                content_blocks = data.get("content", [])
                text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                return self.format_standard_response(text="".join(text_parts).strip(), raw_response=data)
            else:
                logger.error(f"[AI] Anthropic API returned HTTP {res.status_code}: {res.text[:200]}")
                return self.format_standard_response(
                    text="API connection failed. Check the API key and provider settings.",
                    confidence=0.0,
                    raw_response={"status_code": res.status_code}
                )
        except Exception as e:
            logger.error(f"[AI] Error calling Anthropic API: {type(e).__name__}")
            return self.format_standard_response(
                text="API connection failed. Check the API key and provider settings.",
                confidence=0.0,
                raw_response={"error": type(e).__name__}
            )

    def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)
