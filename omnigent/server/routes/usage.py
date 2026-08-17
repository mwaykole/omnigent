"""API route for the per-user LLM cost report (``omni usage``)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from omnigent._wrapper_labels import WRAPPER_LABEL_KEY
from omnigent.entities import Conversation
from omnigent.runtime.policies.builder import load_session_usage
from omnigent.server.auth import RESERVED_USER_LOCAL, AuthProvider
from omnigent.server.routes._auth_helpers import require_user
from omnigent.server.routes._sessions.helpers import (
    _resolve_harness_impl,
    _resolve_llm_model,
)
from omnigent.server.schemas import DailyCost, SessionUsage, UsageReport
from omnigent.stores import ConversationStore

# The daily rollup floor for an "all-time" sum: earlier than any real row, so
# ``sum_daily_cost`` with this lower bound totals every recorded day.
_EPOCH_DAY = "0000-00-00"


def _utc_today() -> str:
    """Return the current UTC calendar day as ``"YYYY-MM-DD"``."""
    from omnigent.db.utils import now_epoch

    return datetime.fromtimestamp(now_epoch(), tz=timezone.utc).date().isoformat()


def _day_offset(day_utc: str, *, days: int) -> str:
    """Return the UTC day *days* before *day_utc*, as ``"YYYY-MM-DD"``."""
    base = datetime.strptime(day_utc, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (base - timedelta(days=days)).date().isoformat()


def _session_models(usage: dict[str, Any]) -> dict[str, float]:
    """
    Project a session's ``by_model`` map into a ``{model_id: cost_usd}`` dict.

    Mirrors the web session sidebar's per-model list: each model's recorded
    cost, keyed by the raw harness model id, shown faithfully. Models with no
    recorded cost are omitted. NOT guaranteed to sum to the session's
    ``total_cost_usd`` — see :class:`SessionUsage`.

    :param usage: A subtree-summed ``session_usage`` dict.
    :returns: Per-model cost map (empty when no per-model cost was recorded).
    """
    by_model = usage.get("by_model")
    if not isinstance(by_model, dict):
        return {}
    models: dict[str, float] = {}
    for name, bucket in by_model.items():
        if not isinstance(bucket, dict) or "total_cost_usd" not in bucket:
            continue
        try:
            models[str(name)] = float(bucket["total_cost_usd"])
        except (TypeError, ValueError):
            continue
    return models


def _resolve_session_harness(conv: Conversation) -> str | None:
    """
    Best-effort harness resolution for the usage report.

    Checks, in order: (1) per-session harness override, (2) the
    ``omnigent.wrapper`` label stamped at creation by native wrappers,
    (3) agent-spec resolution via the runtime (works when the server has
    a live agent cache). Returns a display-friendly name or ``None``.
    """
    if conv.harness_override:
        return conv.harness_override
    wrapper = conv.labels.get(WRAPPER_LABEL_KEY)
    if wrapper:
        # Strip the "-ui" suffix for display: "claude-code-native-ui" → "claude-code-native"
        return wrapper.removesuffix("-ui") if wrapper.endswith("-ui") else wrapper
    return _resolve_harness_impl(conv)


def _parse_token_saver_stats(
    conv: Conversation,
    conversation_store: ConversationStore,
) -> dict[str, Any] | None:
    """Return token saver stats for a session.

    First checks the ``omnigent.token_saver_stats`` label (written by the
    runner).  If absent and token saver is enabled, computes stats from
    the session's stored ``function_call_output`` items.
    """
    import json

    raw = conv.labels.get("omnigent.token_saver_stats")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("compressions", 0) > 0:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    ts_mode = conv.labels.get("omnigent.token_saver", "")
    if not ts_mode or ts_mode == "off":
        return None

    return _compute_token_saver_stats(conv.id, conversation_store)


def _compute_token_saver_stats(
    session_id: str,
    conversation_store: ConversationStore,
) -> dict[str, Any] | None:
    """Compute token saver stats from stored items."""
    from omnigent.runner.tool_output_compressor import (
        compress_tool_output,
        parse_algo_label,
    )

    algos = parse_algo_label("all")
    total_original = 0
    total_compressed = 0
    compressions = 0

    # Build call_id → tool_name map and collect outputs in one pass.
    call_names: dict[str, str] = {}
    outputs: list[tuple[str, str]] = []  # (tool_name, output)

    after: str | None = None
    while True:
        page = conversation_store.list_items(
            session_id, limit=200, after=after, order="asc",
        )
        for item in page.data:
            if item.type == "function_call":
                call_id = getattr(item.data, "call_id", "")
                name = getattr(item.data, "name", "")
                if call_id and name:
                    call_names[call_id] = name
            elif item.type == "function_call_output":
                call_id = getattr(item.data, "call_id", "")
                output = getattr(item.data, "output", "") or ""
                if isinstance(output, str) and len(output) >= 500:
                    outputs.append((call_id, output))
        if not page.has_more:
            break
        after = page.last_id

    for call_id, output in outputs:
        tool_name = call_names.get(call_id, "")
        compressed = compress_tool_output(
            output, tool_name, enabled_algos=algos,
        )
        saved = len(output) - len(compressed)
        if saved > 0:
            total_original += len(output)
            total_compressed += len(compressed)
            compressions += 1

    if compressions == 0:
        return None

    chars_saved = total_original - total_compressed
    tokens_saved = int(chars_saved / 3.5)
    cost_saved = round(tokens_saved / 1000 * 0.003, 4)
    return {
        "chars_saved": chars_saved,
        "original_chars": total_original,
        "compressions": compressions,
        "tokens_saved": tokens_saved,
        "cost_saved_usd": cost_saved,
    }


def _session_cost(usage: dict[str, Any]) -> float:
    """
    Read a session's authoritative cumulative cost, or ``0.0`` when unpriced.

    ``total_cost_usd`` is present only on priced sessions (the "priced ⟺ key
    present" contract); an absent or malformed value reads as ``0.0``.
    """
    if "total_cost_usd" not in usage:
        return 0.0
    try:
        return float(usage["total_cost_usd"])
    except (TypeError, ValueError):
        return 0.0


def _build_usage_report(
    conversation_store: ConversationStore,
    user_id: str | None,
) -> UsageReport:
    """
    Build the usage report: a daily-rollup cost summary plus session detail.

    The summary (today / last 7 days / last 30 days / all-time) is summed
    from the per-user daily-cost rollup (``user_daily_cost``), which
    attributes spend to the UTC day it occurred on — so the windows reflect
    when spend actually happened, not merely a session's last-activity time.

    The per-session detail is a separate view over each top-level session's
    cumulative ``session_usage`` (rolled up across its sub-agent subtree via
    :func:`load_session_usage`), newest activity first, carrying the
    authoritative session cost and the per-model breakdown.

    :param conversation_store: Store to read the rollup and sessions from.
    :param user_id: The caller / ACL scope. ``None`` in single-user mode maps
        to the reserved local owner the daily rollup and grants are keyed by.
    :returns: The populated :class:`UsageReport`.
    """
    # The daily rollup and session-permission grants key spend by the resolved
    # owner, which is the reserved local sentinel in single-user mode (where
    # require_user yields None). Map None -> "local" so the summary reads the
    # same rows the write path recorded.
    rollup_user = user_id if user_id is not None else RESERVED_USER_LOCAL

    today = _utc_today()
    cost_today = conversation_store.sum_daily_cost(rollup_user, today)
    cost_7d = conversation_store.sum_daily_cost(rollup_user, _day_offset(today, days=6))
    cost_30d = conversation_store.sum_daily_cost(rollup_user, _day_offset(today, days=29))
    total = conversation_store.sum_daily_cost(rollup_user, _EPOCH_DAY)

    sessions: list[SessionUsage] = []
    agg_tokens_saved = 0
    agg_cost_saved = 0.0
    after: str | None = None
    while True:
        page = conversation_store.list_conversations(
            limit=200,
            after=after,
            accessible_by=user_id,
            has_agent_id=True,
            kind="default",
            order="desc",
            sort_by="updated_at",
        )
        for conv in page.data:
            if conv.agent_id is None:
                continue
            usage = load_session_usage(conv.id, conversation_store)
            ts_stats = _parse_token_saver_stats(conv, conversation_store)
            if ts_stats:
                agg_tokens_saved += ts_stats.get("tokens_saved", 0)
                agg_cost_saved += ts_stats.get("cost_saved_usd", 0.0)
            sessions.append(
                SessionUsage(
                    id=conv.id,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    title=conv.title,
                    cost_usd=_session_cost(usage),
                    models=_session_models(usage),
                    harness=_resolve_session_harness(conv),
                    llm_model=conv.model_override or _resolve_llm_model(conv),
                    agent_name=conv.sub_agent_name,
                    token_saver_stats=ts_stats,
                )
            )
        if not page.has_more:
            break
        after = page.last_id

    daily_costs_raw = conversation_store.list_daily_costs(rollup_user, _EPOCH_DAY)

    return UsageReport(
        cost_today=cost_today,
        cost_last_7d=cost_7d,
        cost_last_30d=cost_30d,
        total_cost_usd=total,
        total_tokens_saved=agg_tokens_saved,
        total_cost_saved_usd=round(agg_cost_saved, 4),
        daily_costs=[DailyCost(day=d, cost_usd=c) for d, c in daily_costs_raw],
        sessions=sessions,
    )


def create_usage_router(
    conversation_store: ConversationStore,
    *,
    auth_provider: AuthProvider | None = None,
) -> APIRouter:
    """
    Create the per-user usage-report router.

    The report is user-scoped, not session-scoped, so it lives in its own
    router rather than under the sessions router.

    :param conversation_store: Store for the daily rollup and session reads.
    :param auth_provider: Auth provider for user identity. ``None`` disables
        auth (single-user / local mode).
    :returns: The configured router (mounted under ``/v1``).
    """
    router = APIRouter()

    @router.get("/usage", response_model=UsageReport)
    async def get_usage(request: Request) -> UsageReport:
        """
        Aggregate the calling user's LLM spend across their sessions.

        require_user, not get_user_id: the aggregation scopes to the caller,
        so a request slipping through as ``None`` in multi-user mode would
        read another scope. Fail closed with 401 instead (``user_id`` is
        ``None`` only when auth is disabled — the single-user / local case).
        """
        user_id = require_user(request, auth_provider)
        return await asyncio.to_thread(_build_usage_report, conversation_store, user_id)

    return router
