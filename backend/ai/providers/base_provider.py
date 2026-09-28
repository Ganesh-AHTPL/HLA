"""
Base interface for AI Providers in HLA Studio.
Ensures provider independence across Local Ollama and Cloud/API providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class AIProvider(ABC):
    """
    Abstract AI Provider Interface.
    All providers must adhere to this contract and return standardized internal response dictionaries.
    """

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Executes a chat completion request with conversation history.
        """
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Executes a single prompt completion request.
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Checks connectivity, availability, and model readiness.
        """
        pass

    @abstractmethod
    def get_model(self) -> str:
        """Returns the configured model name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is fully ready for inference."""
        pass

    @abstractmethod
    def is_cloud(self) -> bool:
        """Returns True if this is an external cloud/API provider."""
        pass

    def format_standard_response(
        self,
        text: str,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        confidence: float = 1.0,
        raw_response: Any = None
    ) -> Dict[str, Any]:
        """
        Constructs a consistent standard response object across all providers.
        """
        return {
            "text": text or "",
            "intent": intent,
            "entities": entities or {},
            "tool_calls": tool_calls or [],
            "provider": getattr(self, "provider_name", "unknown"),
            "model": self.get_model(),
            "confidence": confidence,
            "raw_response": raw_response
        }
