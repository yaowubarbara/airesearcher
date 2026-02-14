"""Unified LLM router using LiteLLM with task-based routing and cost tracking."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from litellm import completion

from src.knowledge_base.db import Database
from src.knowledge_base.models import LLMUsageRecord

DEFAULT_CONFIG_PATH = Path("config/llm_routing.yaml")


class LLMRouter:
    """Routes LLM requests to optimal models based on task type with automatic fallback."""

    def __init__(
        self,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
        db: Optional[Database] = None,
    ):
        self.config_path = Path(config_path)
        self._config: Optional[dict] = None
        self.db = db

    @property
    def config(self) -> dict:
        if self._config is None:
            with open(self.config_path) as f:
                self._config = yaml.safe_load(f)
        return self._config

    def _get_provider_config(self, provider_name: str) -> dict:
        """Get provider-level config (api_base, api_key) by provider name."""
        providers = self.config.get("providers", {})
        provider = providers.get(provider_name, {})
        result = {}
        if "api_base" in provider:
            result["api_base"] = provider["api_base"]
        api_key_env = provider.get("api_key_env")
        if api_key_env:
            key = os.environ.get(api_key_env)
            if key:
                result["api_key"] = key
        if "api_key" in provider:
            result["api_key"] = provider["api_key"]
        return result

    def get_route(self, task_type: str) -> dict:
        """Get the routing config for a task type."""
        routes = self.config.get("routing", {})
        if task_type in routes:
            return routes[task_type]
        return self.config.get("defaults", {})

    def complete(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Send a completion request, routing to the optimal model for the task type.

        Attempts the primary model first, falling back to secondary on failure.
        Automatically tracks token usage and cost.
        """
        route = self.get_route(task_type)
        primary = route.get("primary", "openai/glm-4-plus")
        fallback = route.get("fallback")
        temp = temperature if temperature is not None else route.get("temperature", 0.3)
        max_tok = max_tokens if max_tokens is not None else route.get("max_tokens", 4000)

        # Get provider-level kwargs (api_base, api_key)
        provider_name = route.get("provider") or self.config.get("defaults", {}).get("provider")
        provider_kwargs = self._get_provider_config(provider_name) if provider_name else {}

        # Merge provider kwargs (caller kwargs take precedence)
        merged_kwargs = {**provider_kwargs, **kwargs}

        # Try primary model
        try:
            return self._call_model(
                model=primary,
                task_type=task_type,
                messages=messages,
                temperature=temp,
                max_tokens=max_tok,
                **merged_kwargs,
            )
        except Exception as e:
            if fallback:
                # Try fallback model
                return self._call_model(
                    model=fallback,
                    task_type=task_type,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tok,
                    **merged_kwargs,
                )
            raise e

    def _call_model(
        self,
        model: str,
        task_type: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Any:
        """Make a single LLM call with usage tracking."""
        start_time = time.time()
        success = True
        response = None
        try:
            response = completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response
        except Exception as e:
            success = False
            raise e
        finally:
            latency_ms = int((time.time() - start_time) * 1000)
            self._track_usage(
                model=model,
                task_type=task_type,
                response=response,
                messages=messages,
                latency_ms=latency_ms,
                success=success,
            )

    def _track_usage(
        self,
        model: str,
        task_type: str,
        response: Any,
        messages: list[dict[str, str]],
        latency_ms: int,
        success: bool,
    ) -> None:
        """Record LLM usage to the database for cost tracking."""
        if self.db is None:
            return

        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = 0.0

        if response and hasattr(response, "usage") and response.usage:
            prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0

        # Use litellm's cost tracking if available
        if response and hasattr(response, "_hidden_params"):
            hidden = response._hidden_params or {}
            if "response_cost" in hidden and hidden["response_cost"] is not None:
                cost_usd = hidden["response_cost"]

        record = LLMUsageRecord(
            model=model,
            task_type=task_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
        )

        try:
            self.db.insert_llm_usage(record)
        except Exception:
            pass  # Don't let tracking failures break the main flow

    def get_response_text(self, response: Any) -> str:
        """Extract text content from an LLM response."""
        if response and response.choices:
            return response.choices[0].message.content or ""
        return ""

    def get_usage_summary(self) -> dict:
        """Get accumulated usage/cost summary."""
        if self.db is None:
            return {}
        return self.db.get_llm_usage_summary()
