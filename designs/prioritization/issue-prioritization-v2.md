# Issue Prioritization v2 for omnigent

## Goal

Make the open-issue queue **orderable by real severity**, not by a label that
has lost its meaning. Today priority is a single collapsed axis (P1 vs P2 as a
de-facto binary); it neither reflects how bad an issue is nor how many users it
hits, and it doesn't move over time. This proposal keeps the working
[triage pipeline](../issue-triage-proposal.md) and adds: a re-calibrated
priority rubric, independent scoring axes (severity × reach × harness-tier +
demand), a maintainer-facing ranked view, and a lightweight way to nudge
ranking over time.

This is an evolution of, not a replacement for,
[issue-triage-proposal.md](../issue-triage-proposal.md). The intake, the
tool-less classifier, and the trusted-step label application all stay.

---

## Evidence: what the data says (snapshot Aug 2026)

725 issues (360 open / 365 closed), PRs excluded. The triage *pipeline* works —
only 7 open issues are un-triaged, `needs-triage` is effectively empty. The
problems are all in the *taxonomy and prioritization*, not the plumbing.

**1. Type split is clean — leave it alone.** 0 open issues carry both `Bug` and
`enhancement`; the template auto-labels and the classifier confirms. This axis
is healthy.

**2. Priority has collapsed into a P1/P2 binary.**

| Priority | Open | Closed | Median days-to-close | Median age (open) |
|---|---|---|---|---|
| P0-critical | 3 | 12 | 2.7d | 25d |
| **P1-high** | **128** | 139 | 1.9d | 20.6d |
| **P2-medium** | **204** | 149 | 3.8d | 28.1d |
| P3-low | 16 | 19 | 3.4d | 30.8d |

- **125 of 207 open bugs (60%) are P1-high.** "Major feature broken, no
  workaround" cannot describe 60% of bugs — P1 is inflated to the point of
  being noise.
- **P0 (3) and P3 (16) are vestigial.** Four buckets, two used.
- **Open-issue age is flat across priorities** (P1 20.6d ≈ P2 28d ≈ P3 30d).
  If P1 were respected as urgent, P1 age would be far lower than P2. It isn't:
  priority is *not* pulling issues to the front. Close-time looks fine only
  because the team turns the whole backlog over in days when it engages —
  attention/recency orders the queue today, not priority.

**3. Severity is orthogonal to the type-default — and the current label hides
it.** Feature requests default to P2 by rule, so a high-value capability gap is
indistinguishable from a trivial nice-to-have. Grounding example
([#2125](https://github.com/omnigent-ai/omnigent/issues/2125), multi-host git
credentials): a real self-hoster blocker, labeled `P2-medium` purely because
it's an FR. There is no way today for it to outrank a weak P1.

**4. `comp:harnesses` is a mega-bucket.** 148 of 360 open (41%). The next
components are `comp:server` (135), `comp:runner` (109), `comp:web-ui` (99).
`areas.json` *already* models per-harness areas (`harness-claude`,
`harness-codex`, …) but they all collapse to the single `comp:harnesses` label,
so routing knows the sub-area while the label throws it away. Within harnesses,
title mentions skew hard to **claude (32) and codex (24)**, then kimi /
antigravity / openai (~6 each) — a natural tier boundary.

**5. Contributor + dedup funnels are unused vs. the design.**
`good first issue` is on **0** open issues; only **5** issues ever closed as
duplicate (0 currently labeled) — yet the triage design calls dedup the
"highest-ROI automation." Both are latent, not wired.

**6. "Community volume" is mostly internal dogfood.** 320 of 360 open issues
are NONE/CONTRIBUTOR-authored, but the bug titles read like insider reports
("antigravity-native: TUI-typed turns never mirror"). Reactions are sparse —
only **25 of 360** open issues have any 👍. Implication: **severity must lead
the score; external demand is at most a tiebreak**, or the queue will look
empty of signal.

---

## Design

### Axis 1 — Type (unchanged)

`bug` / `enhancement` / `documentation`. Clean today; no change.

### Axis 2 — Re-calibrated priority rubric

Priority stays a 4-bucket label but gets a **rubric that forces separation**,
enforced in the classifier prompt (`.github/triage/config.yaml`) and by a
one-time backfill. The key change: **priority is a function of severity × reach,
graded from content — not a type-default.**

| Priority | Definition (must satisfy BOTH severity and reach) |
|---|---|
| **P0-critical** | Security/policy bypass, data loss, or all-users-down. Rare by construction. |
| **P1-high** | High severity (crash / hang / permanent breakage / no workaround) **AND** broad reach (default config, all/most users, or a tier-1 harness). Not "a bug I care about." |
| **P2-medium** | Real bug with a workaround, OR a substantive capability/feature. **Default for FRs**, but a P2 can outrank a P1 in the *score* (below) when its severity/demand is high — the label is a bucket, the score is the order. |
| **P3-low** | Genuinely minor: cosmetic, polish, trivial convenience, narrow nice-to-have. |

Calibration guardrail added to the prompt: **"P1 is a scarcity signal. If more
than ~20% of open bugs are P1, you are over-grading. A bug affecting one harness
on one platform with a workaround is P2, not P1."**

### Axis 3 — Harness tier (new, derived)

Harnesses are not equal in strategic weight. Tier is **derived from the
existing `areas.json` harness areas** (no new hand-labeling):

- **Tier 1** — `claude`, `codex` (flagship; ~38% of harness issues).
- **Tier 2** — `cursor`, `antigravity`, `copilot`, `gemini`/`openai`.
- **Tier 3** — everything else (goose, hermes, kimi, kiro, opencode, pi, qwen).

Tier is a **score multiplier**, not a visible label, so it can be re-weighted
without relabeling. Optionally surface as `tier:1|2|3` labels later if
maintainers want to filter on it.

**Recommended, not required:** split `comp:harnesses` into per-harness labels
so the 41% bucket becomes filterable. This is a bigger change (new labels + a
label-sync step, which the repo deliberately avoids today) — see Appendix A. If
we don't split, tier-as-multiplier still recovers most of the value.

### Axis 4 — The composite score (the ordering primitive)

```
base  = severity_weight              # LLM-graded from content (P0/P1/P2/P3-ish, 0–100)
      × reach_multiplier             # all-users/default 1.5 · normal 1.0 · single-platform 0.9
      × harness_tier_multiplier      # T1 1.4 · T2 1.1 · T3 0.9 · non-harness 1.0

score = apply_demand(base, type)     # type-dependent — see "Community demand" below
      × recency_factor               # 1.0 fresh; gentle decay past ~30d (tunable)
      + manual_pin                   # maintainer override (see "eyeball" below)
```

Every weight is a named constant in one place. The score is **advisory
ordering** layered on top of the labels; labels stay authoritative for
filtering, the score decides *what to look at first*.

**Why severity is LLM-graded, not label-derived:** the dry-run
(`score_prototype.py`) grades severity with regex for reproducibility, and it
demonstrates *why regex isn't enough in production* — "sandbox **bypass**" in an
FR title falsely scored two Codex-mode FRs (#2057, #2054) as critical, and a bot
"Code Audit" issue (#61) too. The production grader is the triage classifier,
which reads full content and already runs per issue at zero extra cost.

### Community demand — used, but type-dependent and bounded

Should 👍 / engagement feed the score? **Yes, but carefully**, because of what
the reaction distribution actually looks like on this repo:

- **93% of open issues (335/360) have zero reactions**; 51 reactions total
  across the whole backlog, with a tiny head (one issue at 10, one at 6, a
  handful at 2–4).
- **Reactions skew hard to feature requests** — 9 of the top 10 reacted issues
  are FRs — and are almost entirely external (50 of 51 from NONE/CONTRIBUTOR,
  ~0 from maintainers). So reactions are a **demand** signal (a wanted
  capability), not a **severity** signal (bugs are reported once, rarely
  upvoted).

Consequences baked into the model:

1. **Type-dependent.** For **feature requests**, demand is a bounded
   *multiplier* (up to +60%), so a well-liked FR climbs above unwanted ones.
   For **bugs**, demand is only a small additive *tiebreak* (≤15 pts), so a
   0-reaction crash still outranks a lightly-liked cosmetic FR. Severity always
   leads for bugs.
2. **Log-scaled and capped.** With a backlog max of ~10 reactions, a linear
   term would let one popular FR swamp severity; `log1p` + a hard cap keeps
   demand a nudge, not a driver.
3. **Comments are excluded.** On this repo, bug comment volume is mostly repro
   back-and-forth — a bug with more comments is often *harder*, not more wanted
   — so comments would reward contentious issues rather than important ones.

**Caveat this guards against:** because reactions are 93%-zero and tilt toward
external FRs, over-weighting demand would systematically bias a
dogfood-bug-heavy backlog toward features. Bounding it (and splitting by type)
keeps severity as the driver.

### Ongoing adjustment — the "eyeball / upgrade over time" mechanism

Prioritization is not a one-shot classification. Three cheap levers:

1. **Periodic re-score.** A scheduled job (weekly) recomputes the score for all
   open issues and posts/updates a single **ranked view** (a pinned issue or a
   generated `PRIORITY-QUEUE.md`), so demand/age changes are reflected without
   re-triaging. Cheap: no LLM call needed for re-score if severity is cached as
   a label/field at triage time.
2. **Manual pin / nudge.** Maintainers add `pin:high` / `pin:low` (or 👍 on a
   tracking comment) to force an issue up or down; `manual_pin` in the score
   honors it. This is the direct answer to "#2125 is a high-severity P2" — a
   maintainer bumps it once and it sticks.
3. **Severity is re-gradable.** Because severity is a field, not baked into the
   priority bucket, re-triage (`/retriage` slash command or label toggle) can
   revise it as understanding of an issue evolves.

---

## Dry-run: before → after (methodical, on real issues)

`designs/prioritization/score_prototype.py` reads a snapshot of all open issues
and prints **current-priority ordering vs composite-score ordering**, with a
rank delta per issue, so we tune weights against real test cases.

Selected results (360 open issues; rank out of 360, lower = higher priority):

**Severity surfaces real bugs the label buried:**

| Issue | Before | After | Δ | Note |
|---|---|---|---|---|
| #3557 policy-gate bypass (P0) | 1 | 6 | −5 | Real P0 stays near top ✅ |
| #3265 claude-sdk bwrap spawn death (P1) | 37 | 3 | +34 | High-sev, tier-1 harness ✅ |
| #3270 sub-agent sessions absent (P1) | 35 | 7 | +28 | ✅ |
| #2421 codex MCP bridge child leak (P1) | 80 | 20 | +60 | Resource leak, tier-1 ✅ |
| #2454 unbounded ~/.omnigent growth (P1) | 72 | 19 | +53 | ✅ |

**Community demand lifts wanted FRs — bounded, so bugs stay on top:**

| Issue | 👍 | Before | After | Δ | Note |
|---|---|---|---|---|---|
| #1021 GitHub Copilot as provider (FR) | 10 | 299 | 93 | +206 | Most-wanted FR climbs; demand pushed score 31→48 ✅ |
| #16 native Windows support (FR) | 6 | 334 | 32 | +302 | High demand + broad reach ✅ |
| #888 side-by-side multi-session (FR) | 2 | 305 | 29 | +276 | ✅ |

**Dry-run limits — the evidence that severity must be LLM-graded, not regex:**

| Issue | Before | After | Note |
|---|---|---|---|
| #2057 / #2054 Codex-mode FRs | 236/238 | 1/2 | **False positive** — "sandbox bypass" tripped the critical regex. LLM grader avoids. |
| #61 bot "Code Audit" (P3) | 349 | 12 | **False positive** — audit issue mentioning security. LLM grader avoids. |
| #2125 multi-host git creds (P2, FR) | 232 | 324 | **False negative** — a real capability gap, but no severity keyword and only 1 👍, so it *sinks*. The LLM grader (or a `pin:high`) is exactly what rescues it. |

#2125 is the clearest case for the whole design: a regex/label view can't see
it's important, so it needs either content-grading (LLM) or the manual-pin
lever — which is why both are in the model.

**Takeaways for the real build:**
- The score *mechanics* order the queue far better than the priority label.
- The severity *grader* must be the LLM, not regex — the dry-run's own false
  positives are the proof.
- Weights are defensible starting points; tune against this before→after table.

---

## Intake: what more to collect

The bug template asks Version + OS but both optional → sparse. Add structured,
**dropdown** fields (dropdowns beat free-text for scoring signal):

- **Harness** (dropdown: claude / codex / cursor / … / n/a) — the #1 component,
  currently buried in prose. Feeds tier directly.
- **Platform / device** (dropdown: macOS / Linux / Windows / iOS / Android /
  Docker) — a whole class of bugs is platform-specific (Windows setup crashes,
  iOS/Android OIDC, Linux aarch64). Feeds reach.
- **Impact / reach** (dropdown: all users / most / some / edge) — the reach axis
  the reporter can often answer better than the grader.

Keep them optional (the pipeline already triages from description alone) but
dropdowns cost the reporter nothing and sharpen severity × reach.

---

## Rollout

1. **Prompt re-calibration** (`.github/triage/config.yaml`) — new priority
   rubric + the "P1 scarcity" guardrail + emit a `severity` field. Low risk,
   affects new issues immediately.
2. **Template fields** — add Harness / Platform / Impact dropdowns.
3. **Scoring job** — productionize `score_prototype.py` into a scheduled action
   that reads the LLM-graded severity and publishes the ranked view.
4. **One-time backfill** — re-run triage over the 128 open P1s to demote the
   mislabeled ones (target: P1 back under ~20% of open bugs).
5. **Wire the latent funnels** — actually apply `good first issue`; revisit why
   dedup fires so rarely.

## Metrics

- **P1 share of open bugs** — target < 20% (today 60%).
- **Priority age separation** — P1 median age should drop well below P2's
  (today they're equal — the tell that priority is ignored).
- **Score→action correlation** — are top-scored issues the ones getting closed?
- **Manual-pin rate** — how often maintainers override the score (high = weights
  need tuning).

---

## Appendix A — Should we split `comp:harnesses`?

**For:** it's 41% of open issues; `areas.json` already knows the sub-area;
per-harness labels make the biggest bucket filterable and feed tier without
title-keyword guessing.

**Against:** the repo intentionally has *no label-sync* (`areas.json` notes
`gh` can't add a nonexistent label), and 8 areas share `comp:harnesses` today.
Splitting means ~11 new `harness:*` labels + a sync step + updating the
classifier allowlist.

**Recommendation:** defer the label split; ship tier-as-multiplier first (gets
most of the value with no new labels). Split only if maintainers want to *filter*
by harness, not just *order* by it.

## Appendix B — Rejected: keep priority as the only axis

Considered leaving priority as the single lever and just re-calibrating the
rubric. Rejected because it can't express "high-severity P2" (#2125) — a bucket
label can't encode within-bucket ordering, and maintainers demonstrably need to
re-rank over time. The score exists precisely to order *within and across*
buckets.
