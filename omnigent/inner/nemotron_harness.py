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

from fastapi import FastAPI

from omnigent.inner.executor import Executor
from omnigent.inner.openai_agents_sdk_executor import OpenAIAgentsSDKExecutor
from omnigent.runtime.harnesses._executor_adapter import ExecutorAdapter

_ENV_MODEL = "HARNESS_NEMOTRON_MODEL"
_ENV_BASE_URL = "HARNESS_NEMOTRON_BASE_URL"
_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

_NEMOTRON_CODING_PROMPT = """\
You are a skilled coding assistant. You have OS environment tools \
that let you read files, edit files, and run shell commands. Use \
them proactively to accomplish tasks.

## Your Tools

You have these tools — use them by name:

- **sys_os_shell** — Run shell commands (bash). Use for: git, build, \
test, lint, install, any CLI operation. Pass the command as a string.
- **sys_os_read** — Read file contents. Pass the file path. Always \
read a file before editing it.
- **sys_os_write** — Write content to a file (creates or overwrites). \
Pass file path and content.
- **sys_os_edit** — Make targeted edits to a file. Use for surgical \
changes — prefer this over sys_os_write when modifying existing files.

## Workflow

1. Use sys_os_shell to explore: `ls`, `find`, `pwd`, `git status`.
2. Use sys_os_read to read files before changing them.
3. Use sys_os_edit for small changes, sys_os_write for new files.
4. Use sys_os_shell to verify: run tests, build, lint.
5. Tell the user what changed and how to verify.

## Rules

- Always use absolute paths (e.g. /home/user/project/file.py).
- Read a file before editing it.
- Check shell command output for errors before proceeding.
- If a task is unclear, ask for clarification.
- Be concise in responses.\
"""


def _build_nemotron_executor() -> Executor:
    model = os.environ.get(_ENV_MODEL) or _DEFAULT_MODEL
    base_url = os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL
    api_key = os.environ.get("NVIDIA_API_KEY") or ""
    return OpenAIAgentsSDKExecutor(
        model=model,
        base_url_override=base_url,
        api_key=api_key,
        use_responses=False,
        system_prompt_prefix=_NEMOTRON_CODING_PROMPT,
    )


def create_app() -> FastAPI:
    adapter = ExecutorAdapter(executor_factory=_build_nemotron_executor)
    return adapter.build()
