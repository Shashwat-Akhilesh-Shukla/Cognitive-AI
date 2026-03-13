"""
AI Provider Abstraction Layer for CognitiveAI

Supports multiple LLM backends:
  - GeminiProvider  (default)  — Google Gemini via google-generativeai SDK
  - PerplexityProvider         — Perplexity AI via OpenAI-compatible REST API

The active provider is managed by AIProviderRegistry which is initialised
once at startup and can be switched at runtime via the /ai/provider endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class AIProviderBase(ABC):
    """Common interface that every LLM provider must implement."""

    name: str = "base"
    default_model: str = ""

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.default_model
        self._available: bool = bool(api_key)

    @property
    def is_available(self) -> bool:
        return self._available

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> str:
        """Return the full response string (non-streaming)."""

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Yield response chunks as they arrive."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "available": self.is_available,
        }


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------

class GeminiProvider(AIProviderBase):
    """Google Gemini provider using the google-generativeai SDK."""

    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self, api_key: str, model: Optional[str] = None):
        super().__init__(api_key, model)
        self._client = None
        if api_key:
            try:
                import google.generativeai as genai  # type: ignore

                genai.configure(api_key=api_key)
                self._genai = genai
                self._client = genai.GenerativeModel(self.model)
                self._available = True
                logger.info(f"GeminiProvider initialised with model={self.model}")
            except ImportError:
                logger.warning(
                    "google-generativeai package not installed. "
                    "Run: pip install google-generativeai"
                )
                self._available = False
            except Exception as exc:
                logger.warning(f"GeminiProvider init failed: {exc}")
                self._available = False
        else:
            logger.info("GEMINI_API_KEY not set — GeminiProvider unavailable")
            self._available = False

    def _convert_messages(self, messages: List[Dict[str, str]]) -> tuple[str, list]:
        """
        Convert OpenAI-style messages to Gemini format.
        Returns (system_instruction, history_parts) where history_parts are
        the non-system turns that can be fed into chat.
        """
        system_parts: List[str] = []
        history: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
            else:
                history.append({"role": "user", "parts": [content]})

        return "\n\n".join(system_parts), history

    async def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> str:
        if not self._available or self._client is None:
            raise RuntimeError("GeminiProvider is not available")

        system_instruction, history = self._convert_messages(messages)

        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            # Rebuild model with system instruction if present
            if system_instruction:
                import google.generativeai as genai  # type: ignore

                model = genai.GenerativeModel(
                    self.model,
                    system_instruction=system_instruction,
                    generation_config=generation_config,
                )
            else:
                import google.generativeai as genai  # type: ignore

                model = genai.GenerativeModel(
                    self.model,
                    generation_config=generation_config,
                )

            # Build the prompt from history
            if not history:
                raise ValueError("No user messages provided")

            # For multi-turn, use chat; for single turn, use generate_content
            if len(history) == 1:
                response = await asyncio.to_thread(
                    model.generate_content, history[0]["parts"][0]
                )
            else:
                chat = model.start_chat(history=history[:-1])
                last_user_msg = history[-1]["parts"][0]
                response = await asyncio.to_thread(chat.send_message, last_user_msg)

            return response.text.strip()

        except Exception as exc:
            logger.error(f"GeminiProvider.generate error: {exc}")
            raise

    async def stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        if not self._available or self._client is None:
            yield "Gemini provider is not available."
            return

        system_instruction, history = self._convert_messages(messages)
        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            import google.generativeai as genai  # type: ignore

            if system_instruction:
                model = genai.GenerativeModel(
                    self.model,
                    system_instruction=system_instruction,
                    generation_config=generation_config,
                )
            else:
                model = genai.GenerativeModel(
                    self.model, generation_config=generation_config
                )

            if not history:
                yield "No user message provided."
                return

            if len(history) == 1:
                prompt = history[0]["parts"][0]
            else:
                # Build a plain-text multi-turn representation for streaming
                prompt = "\n".join(
                    f"{h['role'].upper()}: {h['parts'][0]}" for h in history
                )

            # Gemini streaming is synchronous; run in thread and yield chunks
            def _stream_sync():
                return model.generate_content(prompt, stream=True)

            response = await asyncio.to_thread(_stream_sync)
            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as exc:
            logger.error(f"GeminiProvider.stream error: {exc}")
            yield "I'm having trouble generating a response right now. Please try again."


# ---------------------------------------------------------------------------
# Perplexity Provider
# ---------------------------------------------------------------------------

class PerplexityProvider(AIProviderBase):
    """Perplexity AI provider via its OpenAI-compatible REST API."""

    name = "perplexity"
    default_model = "sonar"

    def __init__(self, api_key: str, model: Optional[str] = None):
        super().__init__(api_key, model)
        self._base_url = "https://api.perplexity.ai/chat/completions"
        if not api_key:
            logger.info("PERPLEXITY_API_KEY not set — PerplexityProvider unavailable")
            self._available = False
        else:
            self._available = True
            logger.info(f"PerplexityProvider initialised with model={self.model}")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> str:
        if not self._available:
            raise RuntimeError("PerplexityProvider is not available")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        max_retries = 2
        attempt = 0
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                attempt += 1
                try:
                    resp = await client.post(
                        self._base_url, headers=self._headers(), json=payload
                    )
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = (
                            int(retry_after)
                            if retry_after and retry_after.isdigit()
                            else 2 ** attempt
                        )
                        if attempt <= max_retries:
                            await asyncio.sleep(wait)
                            continue
                        return "I'm being rate limited. Please try again later."

                    if 500 <= resp.status_code < 600:
                        if attempt <= max_retries:
                            await asyncio.sleep(1 + attempt)
                            continue
                        return "I'm having trouble contacting the knowledge service; please try again later."

                    resp.raise_for_status()
                    result = resp.json()
                    return (
                        result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )

                except httpx.RequestError as exc:
                    logger.warning(f"Perplexity request error (attempt {attempt}): {exc}")
                    if attempt <= max_retries:
                        await asyncio.sleep(1 + attempt)
                        continue
                    return "I apologize, but I'm having trouble generating a response right now. Please try again."
                except Exception as exc:
                    logger.error(f"PerplexityProvider.generate error: {exc}")
                    return "I apologize, but I'm having trouble generating a response right now. Please try again."

    async def stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        if not self._available:
            yield "Perplexity provider is not available."
            return

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        max_retries = 2
        attempt = 0
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                attempt += 1
                try:
                    async with client.stream(
                        "POST", self._base_url, headers=self._headers(), json=payload
                    ) as resp:
                        if resp.status_code == 429:
                            retry_after = resp.headers.get("Retry-After")
                            wait = (
                                int(retry_after)
                                if retry_after and retry_after.isdigit()
                                else 2 ** attempt
                            )
                            if attempt <= max_retries:
                                await asyncio.sleep(wait)
                                continue
                            yield "I'm being rate limited. Please try again later."
                            return

                        if 500 <= resp.status_code < 600:
                            if attempt <= max_retries:
                                await asyncio.sleep(1 + attempt)
                                continue
                            yield "I'm having trouble contacting the knowledge service; please try again later."
                            return

                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]
                                if data.strip() == "[DONE]":
                                    return
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue
                        return

                except httpx.RequestError as exc:
                    logger.warning(
                        f"Perplexity stream request error (attempt {attempt}): {exc}"
                    )
                    if attempt <= max_retries:
                        await asyncio.sleep(1 + attempt)
                        continue
                    yield "I apologize, but I'm having trouble generating a response right now. Please try again."
                    return
                except Exception as exc:
                    logger.error(f"PerplexityProvider.stream error: {exc}")
                    yield "I apologize, but I'm having trouble generating a response right now. Please try again."
                    return


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class AIProviderRegistry:
    """
    Singleton-style registry that holds all configured providers and tracks
    which one is currently active.

    Usage
    -----
    registry = AIProviderRegistry()
    registry.register(GeminiProvider(api_key="..."))
    registry.register(PerplexityProvider(api_key="..."))
    registry.set_active("gemini")          # or "perplexity"
    provider = registry.active_provider    # returns the active AIProviderBase
    """

    def __init__(self):
        self._providers: Dict[str, AIProviderBase] = {}
        self._active_name: Optional[str] = None

    def register(self, provider: AIProviderBase) -> None:
        """Register a provider. Unavailable providers are still registered."""
        self._providers[provider.name] = provider
        logger.info(
            f"Registered provider '{provider.name}' (available={provider.is_available})"
        )

    def set_active(self, name: str) -> bool:
        """
        Set the active provider by name.
        Returns True on success, False if provider is unknown or unavailable.
        """
        if name not in self._providers:
            logger.warning(f"Provider '{name}' is not registered")
            return False
        provider = self._providers[name]
        if not provider.is_available:
            logger.warning(f"Provider '{name}' is registered but not available (missing API key?)")
            return False
        self._active_name = name
        logger.info(f"Active AI provider switched to: {name}")
        return True

    def auto_select(self, preferred: str = "gemini") -> str:
        """
        Pick the active provider automatically:
        1. Try the preferred provider if available.
        2. Fall back to any other available provider.
        3. Return the chosen provider's name (or raise if none available).
        """
        if preferred in self._providers and self._providers[preferred].is_available:
            self._active_name = preferred
            logger.info(f"Auto-selected preferred provider: {preferred}")
            return preferred

        for name, provider in self._providers.items():
            if provider.is_available:
                self._active_name = name
                logger.info(
                    f"Preferred provider '{preferred}' unavailable. "
                    f"Auto-selected fallback: {name}"
                )
                return name

        raise RuntimeError(
            "No AI provider is available. "
            "Please set GEMINI_API_KEY or PERPLEXITY_API_KEY in your .env file."
        )

    @property
    def active_provider(self) -> AIProviderBase:
        """Return the currently active provider."""
        if self._active_name is None or self._active_name not in self._providers:
            raise RuntimeError("No active AI provider configured")
        return self._providers[self._active_name]

    @property
    def active_name(self) -> Optional[str]:
        return self._active_name

    def list_providers(self) -> List[Dict[str, Any]]:
        """Return info dict for every registered provider."""
        return [p.to_dict() for p in self._providers.values()]

    def get_provider(self, name: str) -> Optional[AIProviderBase]:
        return self._providers.get(name)


# ---------------------------------------------------------------------------
# Module-level registry instance (shared across the app)
# ---------------------------------------------------------------------------

_registry: Optional[AIProviderRegistry] = None


def get_registry() -> AIProviderRegistry:
    global _registry
    if _registry is None:
        _registry = AIProviderRegistry()
    return _registry


def init_providers(
    gemini_api_key: str = "",
    perplexity_api_key: str = "",
    preferred: str = "gemini",
    gemini_model: Optional[str] = None,
    perplexity_model: Optional[str] = None,
) -> AIProviderRegistry:
    """
    Convenience function called once at startup.
    Registers both providers and auto-selects the active one.
    """
    global _registry
    _registry = AIProviderRegistry()

    gemini = GeminiProvider(api_key=gemini_api_key, model=gemini_model)
    perplexity = PerplexityProvider(api_key=perplexity_api_key, model=perplexity_model)

    _registry.register(gemini)
    _registry.register(perplexity)
    _registry.auto_select(preferred)

    return _registry
