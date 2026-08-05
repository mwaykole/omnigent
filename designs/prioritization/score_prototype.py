#!/usr/bin/env python3
"""Dry-run prototype for issue-prioritization-v2 scoring.

Reads a snapshot of all open issues and produces a BEFORE (current priority
label ordering) vs AFTER (composite score ordering) comparison, so we can
eyeball which issues move and tune the weights against real test cases.

The severity heuristic here is a *stand-in* for the production design, where
severity is graded by the triage classifier LLM (which reads full issue
content). Regex is used only so the dry-run is reproducible and inspectable.

Usage:
    # refresh the snapshot (external org -> ghx from gh-profiles)
    GH_HOST=github.com ghx api --paginate \
      "repos/omnigent-ai/omnigent/issues?state=all&per_page=100" > /tmp/all_issues_raw.json
    python3 designs/prioritization/score_prototype.py /tmp/all_issues_raw.json
    # priority-LABEL backfill preview (current vs regraded bucket, no scores):
    python3 designs/prioritization/score_prototype.py /tmp/all_issues_raw.json --regrade
"""

from __future__ import annotations

import datetime
import json
import math
import re
import sys

NOW = datetime.datetime.now(datetime.timezone.utc)

# ── Tunable weights ──────────────────────────────────────────────────────
# Severity tiers are checked most-severe first; first match wins. Kept narrow
# so a stray "credential" mention doesn't inflate everything to critical.
SEVERITY = {
    # NOTE: `severity()` lowercases the text before matching, so every pattern
    # here MUST be lowercase — an uppercase literal can never match.
    "critical": (
        100,
        [
            r"\bdata ?loss\b",
            r"\bvulnerab",
            r"\bcve-\d",
            r"\brce\b",
            r"\bexfiltrat",
            r"\bpolicy (?:gate|bypass)",
            r"\bsandbox (?:escape|bypass)",
            r"\bgates? (?:are )?bypass",
            r"\bcorrupt(?:s|ion|ed)\b",
            r"\bpat is offered",
            r"\bleak(?:s|ed) (?:the |a )?(?:secret|token|credential)",
        ],
    ),
    "high": (
        60,
        [
            r"\bcrash",
            r"\bdeadlock",
            r"\bhangs?\b",
            r"\bbricks?\b",
            r"\bpermanently\b",
            r"\bnever (?:recover|complete|exit|return)",
            r"\bcannot (?:install|start|log ?in|sign ?in|uninstall)",
            r"\bfails? to start\b",
            r"\bwedge",
            r"\binfinite\b",
            r"\bunbounded\b",
            r"\bstarv(?:e|ation)",
            r"\bevery (?:user|session|request)\b",
            r"\ball (?:users|sessions)\b",
        ],
    ),
    "medium": (
        30,
        [
            r"\berror",
            r"\bfails?\b",
            r"\btimeout|\btimes? out",
            r"\b(?:404|401|403|500)\b",
            r"\bwrong\b",
            r"\bignore[sd]?\b",
            r"\bmissing\b",
            r"\bincorrect",
            r"\bregression",
            r"\bswallow",
            r"\bsilent",
        ],
    ),
    "low": (
        10,
        [
            r"\bcosmetic",
            r"\bpolish",
            r"\btypo",
            r"\bnit\b",
            r"\bmisalign|\balignment\b",
            r"\btooltip",
            r"\brename\b",
            r"\bnice.to.have",
            r"\bminor\b",
            r"\brenders? und",
        ],
    ),
}

TIER1 = ["claude", "codex"]
TIER2 = ["cursor", "antigravity", "copilot", "gemini", "openai"]
PRIOS = ("P0-critical", "P1-high", "P2-medium", "P3-low")


def labels(i):
    return {lab["name"] for lab in i["labels"]}


def parse(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def severity(i):
    text = (i["title"] + " " + (i.get("body") or ""))[:2000].lower()
    for name, (w, pats) in SEVERITY.items():
        if any(re.search(p, text) for p in pats):
            return name, w
    # Fallbacks for issues that hit no keyword. An un-keyworded bug scores 25 —
    # just below an explicit "medium" (30) so known-medium bugs sort above
    # unknown ones; an un-keyworded FR scores 20 (see FR grading note in doc).
    return ("medium", 25) if "Bug" in labels(i) else ("feature", 20)


_BROAD_REACH = re.compile(
    r"\ball (?:users|sessions|platforms)|every (?:user|session|request)"
    r"|any harness|default config"
)


def reach(i):
    text = (i["title"] + " " + (i.get("body") or ""))[:1500].lower()
    if _BROAD_REACH.search(text):
        return 1.5
    if re.search(
        r"\bwindows|\bios\b|\bandroid|\blinux|\baarch64|\bmacos|\belectron|\bself.host", text
    ):
        return 0.9  # platform-specific: real, but narrower blast radius
    return 1.0


def tier_mult(i):
    if "comp:harnesses" not in labels(i):
        return 1.0
    t = i["title"].lower()
    if any(k in t for k in TIER1):
        return 1.4
    if any(k in t for k in TIER2):
        return 1.1
    return 0.9


# Demand handling is type-dependent, grounded in the reaction distribution:
# 93% of open issues have 0 reactions, and the reacted ones skew heavily to
# feature requests. So reactions are a *demand* signal (a wanted capability),
# not a *severity* signal — a bug's importance comes from content, not upvotes.
#   - Feature requests: demand is a bounded MULTIPLIER, so a well-liked FR
#     climbs above unwanted ones.
#   - Bugs: demand is a small additive TIEBREAK only, so a 0-reaction crash
#     still outranks a lightly-liked cosmetic FR.
# Comments are deliberately excluded: on this repo they're mostly repro
# back-and-forth (a bug with more comments is often harder, not more wanted).
DEMAND_CAP = 12  # log input cap so one popular FR can't swamp severity
FR_DEMAND_MAX = 0.6  # +60% at most for the most-wanted FR
BUG_DEMAND_MAX = 15  # small flat additive tiebreak for bugs


def _demand_signal(i):
    """0..1 normalized, log-scaled reaction intensity."""
    r = min(i.get("reactions", {}).get("total_count", 0), DEMAND_CAP)
    return math.log1p(r) / math.log1p(DEMAND_CAP)


def age_days(i):
    return (NOW - parse(i["created_at"])).total_seconds() / 86400


# Readiness: an actionable ticket (repro steps, a real body) is worth surfacing
# above a vague one at the same severity — you can start on it now. A small
# multiplier so it only breaks near-ties, never overrides severity.
_REPRO = re.compile(r"steps to reproduce|reproduc|to reproduce", re.I)
READINESS_MIN, READINESS_MAX = 0.85, 1.1


def readiness(i):
    if "needs-info" in labels(i):
        return READINESS_MIN  # explicitly blocked on the reporter
    body = i.get("body") or ""
    ready = len(body) >= 400 and (_REPRO.search(body) or "enhancement" in labels(i))
    return READINESS_MAX if ready else 1.0


# Duplicate blast-radius: N confirmed duplicates of an issue means N reporters
# hit it — a reach signal. Snapshot JSON doesn't carry dup links, so this reads
# an optional `duplicate_count` the production job would populate from the
# dedup labeler (see PR #4037). Defaults to no-op on the dry-run data.
def dup_reach(i):
    n = i.get("duplicate_count", 0)
    return 1.0 + min(0.5, 0.15 * n)  # +15% per dup, capped at +50%


# Age is NEUTRAL by default (design review: an unfixed old bug isn't less
# important — if anything it should escalate, not decay). Set DECAY_OLD=True
# only to reproduce the earlier decaying variant for comparison.
DECAY_OLD = False


def age_factor(i):
    if not DECAY_OLD:
        return 1.0
    a = age_days(i)
    return 1.0 if a < 30 else max(0.7, 1.0 - (a - 30) / 200)


def score(i):
    sname, sw = severity(i)
    s = sw * reach(i) * tier_mult(i) * dup_reach(i) * readiness(i)
    d = _demand_signal(i)
    if "enhancement" in labels(i):
        s *= 1.0 + FR_DEMAND_MAX * d  # demand LEADS for feature requests
    else:
        s += BUG_DEMAND_MAX * d  # demand is only a tiebreak for bugs
    s *= age_factor(i)
    return s, sname


def current_rank_key(i):
    """BEFORE ordering: priority label, then recency (how the queue reads today)."""
    lab = labels(i)
    p = next((n for n, name in enumerate(PRIOS) if name in lab), len(PRIOS))
    return (p, -parse(i["created_at"]).timestamp())


# Score → priority label: a single derivation (design decision). The cut-points
# sit at the severity band values (100 = critical, 60 = high, 25 ≈ medium), so a
# multiplier (tier/reach/dup/readiness/demand) is what lets an issue cross UP a
# band — e.g. a "high" (60) bug in a tier-1 harness (×1.4 = 84) clears P1, while
# the same bug on a niche harness (×0.9 = 54) stays P2. On today's snapshot this
# yields P0 9 / P1 58 / P2 206 / P3 87, and a 24% P1 share of open bugs.
P0_MIN, P1_MIN, P2_MIN = 100, 60, 25


def priority_from_score(i):
    """The priority LABEL, derived from the final score (one system, no parallel
    rubric). This is both the backfill output and how the classifier's grade
    becomes a bucket in production."""
    s = score(i)[0]
    if s >= P0_MIN:
        return "P0-critical"
    if s >= P1_MIN:
        return "P1-high"
    if s >= P2_MIN:
        return "P2-medium"
    return "P3-low"


# Back-compat alias for the --regrade path / any external callers.
regrade = priority_from_score


def current_prio(i):
    return next((p for p in PRIOS if p in labels(i)), "none")


def print_score_ranking(opn):
    before = sorted(opn, key=current_rank_key)
    after = sorted(opn, key=lambda i: score(i)[0], reverse=True)
    before_rank = {i["number"]: n for n, i in enumerate(before)}

    print(f"# {len(opn)} open issues — BEFORE (priority label) vs AFTER (composite score)\n")
    print(f"{'AFTER':>5} {'BEFORE':>6} {'Δ':>5}  {'score':>6} {'severity':9} {'prio':11} issue")
    for n, i in enumerate(after):
        sc, sn = score(i)
        pr = current_prio(i)
        b = before_rank[i["number"]]
        delta = b - n  # positive = moved UP vs current ordering
        arrow = f"+{delta}" if delta > 0 else str(delta)
        title = i["title"][:48]
        print(f"{n + 1:>5} {b + 1:>6} {arrow:>5}  {sc:6.0f} {sn:9} {pr:11} #{i['number']} {title}")


def print_regrade(opn):
    """Backfill preview: current priority LABEL vs regraded label (no scores)."""
    import collections

    cur = collections.Counter(current_prio(i) for i in opn)
    new = collections.Counter(regrade(i) for i in opn)
    print(f"# {len(opn)} open issues — priority LABEL regrade (backfill preview)\n")
    print(f"{'priority':12} {'now':>5} {'regraded':>9}")
    for p in (*PRIOS, "none"):
        print(f"{p:12} {cur.get(p, 0):>5} {new.get(p, 0):>9}")

    bugs = [i for i in opn if "Bug" in labels(i)]
    p1_now = sum(current_prio(i) == "P1-high" for i in bugs)
    p1_new = sum(regrade(i) == "P1-high" for i in bugs)
    print(f"\nP1 share of open bugs: {p1_now}/{len(bugs)} -> {p1_new}/{len(bugs)}")

    moves = collections.Counter(
        f"{current_prio(i)} -> {regrade(i)}" for i in opn if current_prio(i) != regrade(i)
    )
    print("\nchanged labels (count):")
    for k, v in moves.most_common():
        print(f"  {v:>4}  {k}")


def print_markdown(opn, limit=200):
    """Emit a GitHub-markdown ranking table (for the design-doc appendix)."""
    before = sorted(opn, key=current_rank_key)
    after = sorted(opn, key=lambda i: score(i)[0], reverse=True)
    before_rank = {i["number"]: n for n, i in enumerate(before)}

    print("| # | Score | Sev | Now | Derived | Δrank | Issue |")
    print("|--:|--:|---|---|---|--:|---|")
    for n, i in enumerate(after[:limit]):
        sc, sn = score(i)
        b = before_rank[i["number"]]
        delta = b - n
        arrow = f"+{delta}" if delta > 0 else str(delta)
        title = i["title"].replace("|", "\\|")[:70]
        num = i["number"]
        link = f"[#{num}](https://github.com/omnigent-ai/omnigent/issues/{num})"
        derived = priority_from_score(i).replace("-critical", "").replace("-high", "")
        derived = derived.replace("-medium", "").replace("-low", "")
        now = current_prio(i).replace("-critical", "").replace("-high", "")
        now = now.replace("-medium", "").replace("-low", "")
        moved = " ⚑" if now != derived and now != "none" else ""
        print(
            f"| {n + 1} | {sc:.0f} | {sn} | {now} | {derived}{moved} | {arrow} | {link} {title} |"
        )


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    path = args[0] if args else "/tmp/all_issues_raw.json"
    with open(path) as f:
        data = json.load(f)
    opn = [i for i in data if i.get("pull_request") is None and i["state"] == "open"]

    if "--regrade" in flags:
        print_regrade(opn)  # priority-label backfill preview
    elif "--markdown" in flags:
        limit = next((int(a) for a in args[1:] if a.isdigit()), 200)
        print_markdown(opn, limit)  # markdown table for the doc appendix
    else:
        print_score_ranking(opn)  # composite-score before->after (default)


if __name__ == "__main__":
    main()
