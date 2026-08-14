"""``harness: ollama`` wrap.

In-process harness for local Ollama models. Reuses
:class:`OpenAIAgentsSDKExecutor` pointed at Ollama's OpenAI-compatible
endpoint (``http://localhost:11434/v1``). Ollama only supports
``/chat/completions`` (not the ``/responses`` wire), so
``use_responses`` is forced to ``False``.

Env vars read at startup:

- ``HARNESS_OLLAMA_MODEL``: model identifier, e.g. ``"gemma4:12b"``.
- ``HARNESS_OLLAMA_BASE_URL``: Ollama base URL override; defaults to
  ``http://localhost:11434/v1``.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from omnigent.inner.executor import Executor
from omnigent.inner.openai_agents_sdk_executor import OpenAIAgentsSDKExecutor
from omnigent.runtime.harnesses._executor_adapter import ExecutorAdapter

_ENV_MODEL = "HARNESS_OLLAMA_MODEL"
_ENV_BASE_URL = "HARNESS_OLLAMA_BASE_URL"
_DEFAULT_BASE_URL = "http://localhost:11434/v1"


def _build_ollama_executor() -> Executor:
    model = os.environ.get(_ENV_MODEL) or None
    base_url = os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL
    return OpenAIAgentsSDKExecutor(
        model=model,
        base_url_override=base_url,
        api_key="ollama",
        use_responses=False,
    )


def create_app() -> FastAPI:
    adapter = ExecutorAdapter(executor_factory=_build_ollama_executor)
    return adapter.build()
