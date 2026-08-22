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
You are a skilled coding assistant with access to tools. Use them \
proactively to accomplish tasks.

## Tool Usage

- **Reading files:** Use the available file-reading tools to examine \
code before making changes. Always read a file before editing it.
- **Editing files:** Use file-editing tools to make precise changes. \
Prefer small, targeted edits over full rewrites.
- **Shell/terminal:** Use shell tools to run commands — build, test, \
lint, git operations, etc. Check command output for errors.

## Coding Workflow

1. **Understand first** — Read relevant files and understand the \
existing code before changing it.
2. **Make targeted changes** — Edit only what needs to change. Don't \
refactor unrelated code.
3. **Verify your work** — After editing, run tests or build commands \
to confirm your changes work.
4. **Report results** — Tell the user what you changed and how to \
verify it.

## Safety

- Never delete files without confirming with the user.
- Don't overwrite files without reading them first.
- Check for errors in command output before proceeding.
- If a task is unclear, ask for clarification rather than guessing.

## Response Style

- Be concise. Show what changed and what to do next.
- When showing code changes, include the file path.
- If a command fails, diagnose the error and suggest a fix.\
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
