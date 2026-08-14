"""``harness: nemotron`` wrap.

In-process harness for NVIDIA Nemotron models via NVIDIA API.
Reuses :class:`OpenAIAgentsSDKExecutor` pointed at NVIDIA's
OpenAI-compatible endpoint (``https://integrate.api.nvidia.com/v1``).
NVIDIA API only supports ``/chat/completions`` (not the ``/responses``
wire), so ``use_responses`` is forced to ``False``.

Env vars read at startup:

- ``HARNESS_NEMOTRON_MODEL``: model identifier, e.g.
  ``"nvidia/nemotron-3-ultra-550b-a55b"``.
- ``HARNESS_NEMOTRON_BASE_URL``: NVIDIA API base URL override; defaults
  to ``https://integrate.api.nvidia.com/v1``.
- ``NVIDIA_API_KEY``: NVIDIA API key (``nvapi-…``) for authentication.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from omnigent.inner.executor import Executor
from omnigent.inner.openai_agents_sdk_executor import OpenAIAgentsSDKExecutor
from omnigent.runtime.harnesses._executor_adapter import ExecutorAdapter

_ENV_MODEL = "HARNESS_NEMOTRON_MODEL"
_ENV_BASE_URL = "HARNESS_NEMOTRON_BASE_URL"
_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# NVIDIA Nemotron models stream reasoning_content instead of content
# by default. Disable thinking so the SDK receives standard content deltas.
_NVIDIA_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


class _NvidiaCompletions:
    """Injects ``chat_template_kwargs`` into every chat completions call."""

    def __init__(self, completions: Any) -> None:
        self._completions = completions

    async def create(self, **kwargs: Any) -> Any:
        extra = kwargs.pop("extra_body", None) or {}
        kwargs["extra_body"] = {**_NVIDIA_EXTRA_BODY, **extra}
        return await self._completions.create(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _NvidiaChat:
    """Wraps ``AsyncOpenAI.chat`` to inject NVIDIA-specific params."""

    def __init__(self, chat: Any) -> None:
        self._chat = chat
        self.completions = _NvidiaCompletions(chat.completions)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


def _build_nemotron_executor() -> Executor:
    model = os.environ.get(_ENV_MODEL) or _DEFAULT_MODEL
    base_url = os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL
    api_key = os.environ.get("NVIDIA_API_KEY") or ""
    executor = OpenAIAgentsSDKExecutor(
        model=model,
        base_url_override=base_url,
        api_key=api_key,
        use_responses=False,
    )
    # Patch the client to inject NVIDIA-specific body params on every call.
    object.__setattr__(executor._client, "chat", _NvidiaChat(executor._client.chat))
    return executor


def create_app() -> FastAPI:
    adapter = ExecutorAdapter(executor_factory=_build_nemotron_executor)
    return adapter.build()
