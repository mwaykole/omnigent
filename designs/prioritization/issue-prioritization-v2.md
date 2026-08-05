# Issue Prioritization v2 for omnigent

## Goal

Currently priorities used in issues are too coarse and sometimes misleading.
  - Bugs are sorted into P0, P1, P2, P3.
  - FRs are always P2.
  - Categories are broad.
  - Sorting by priority doesn't give a meaningful list when almost everything are P1 and P2.

We want better prioritization scheme. This is an attempt to come up with a subjectively better
scheme. It has automations part, a heuristic scoring rule, and it allows users to intervene.

This can be viewed as an important of the existing [triage pipeline](../issue-triage-proposal.md)
where we add:
  - More categories and sub-categories,
  - Separate severities from priorities (one is used for LLM scoring, another is used as final
    label.),
  - Add some details for sorting guideline and expose heuristic scores,
  - Also mention manual intervention.


This document only applies to community issues. Issues created by maintainer will be handled
separately since they are mostly backlogs or require coordination.

---

## Evidence: what the data says (snapshot Aug 2026)

We currently have: 725 issues (360 open / 365 closed).

**1. Issues are splited into `Bug` and `enhancement` (FRs).** This is good, we keep it as-is.

**2. Most issues are P1 / P2.**

| Priority | Open | Closed | Median days-to-close | Median age (open) |
|---|---|---|---|---|
| P0-critical | 3 | 12 | 2.7d | 25d |
| **P1-high** | **128** | 139 | 1.9d | 20.6d |
| **P2-medium** | **204** | 149 | 3.8d | 28.1d |
| P3-low | 16 | 19 | 3.4d | 30.8d |

- **125 (60%) are P1**. This is too bloat and making P1 less important.
- **P0 and P3 are only 19 issues combined**. These two are underused, especially P3.
- **Open-issue age is flat.** Median days-to-close are 20.6d for P1 and 28.1d for P2.

This reflects indifference between P1 and P2. To distinguish them, we have to re-prioritize so that
we have less P1. Aim (magic number) is 25%.

**Propose:** the final shape should have ~ 25% P1 to distinguish itself from P2. When everything is
P1, nothing is P1. 

**3. Priority is meaningful only to bugs today.** FRs are P2, so at first glance, all FRs are
treated equally. For example, ([#2125](https://github.com/omnigent-ai/omnigent/issues/2125), multi-host git
credentials): a real self-hoster blocker, labeled `P2-medium` purely because it's an FR.
There is no way today for it to outrank a weak P1.

**Propose:** Let's have priorities for FRs too. Since we might filter by `bug`/`enhancement` anyway,
this doesn't takeaway anything mentally.

**4. Buckets are too coarse.** 148 (41%) are `comp:harness`, 135 are `comp:server`, 109 are
`comp:runner`, etc. 

**Propose:** Let's have more fine-grained buckets. The benefit are two-fold; 1) it gives us a
better set of keys to filter on, 2) these keys can be feeded into the scoring function, so we have a
way to tune more important components. For harnesses specifically, we should make sure to
have tier-based labels. That will help with prioritization.


**5. Community inputs should be taken into account.** For example, if multiple issues are filed for
the same underlying issue, it is a sign that this issue is widespread. We plan to have automation to
link duplicates and similar issues. So those can be used for clustering and bumping scores. Factors
such as number of unique users contributed to issues and likes may also be considered.


---

## Design

We have the following mental model:
  1. Issues --> LLM + guideline --> Severity (low / medium / high / critical),
  2. Severity + metadata --> Score (heuristics, mixed between LLM and hand-tuned weights),
  3. Score --> Priority (deterministic),
  4. Priority can be re-adjusted by maintainers.

The core of this is still non-deterministic by nature. But it should give a reasoning as to why we
might prioritize one issue over another. Number scores give a total ordering. If one want to use
priorities, then it is also available as a group of scores (100+ = P0, 60+ = P1, 25+ = P2,
everything else P3.)

To make the adjustment scope narrows, we will try to adjust only weights of factors.

**Do not read too hard into it. This requires tuning over-time and can always be adjusted, but it
gives something to start with.** 

### Axis 1 - Type (unchanged)

`bug` / `enhancement` / `documentation`.

### Axis 2 - Severity (new; done by LLMs)

LLM should judge issues by contents and give grades. Grades can be:
  - Bugs:
    - **S0**: Should be fixed ASAP, today if possible. This can be widespread real bugs or some
      serious security bugs,
    - **S1**: Real bug affecting one or few narrow real use cases; no easy mitigation,
    - **S2**: Real bug, with easy mitigation,
    - **S3**: Not sure if it is real or not.

  - Feature Requests:
    - **S0**: Blocking (potentially) a lot of users from onboarding Omnigent,
    - **S1**: Must have soon / on our roadmap / will unblock a certain set of users,
    - **S2**: Nice to have, but won't matter in terms of functionality,
    - **S3**: Unclear if it's good or not or a very nit papercut.

This grade, together with other metadata, will produce scores.
Issues will be graded once filed. They can be regraded on changes, but regrading will be done
semi-manually (comments/labels added).

The LLM prompt maybe tuned. Mentally, these are severities from LLM, so we will take it with a grain
of salt, but should still give some directional opinions.

Soft nudge (prompt, not a hard rule): a real claude / codex bug is rarely S3 —
lean S1–S2. We don't force ≥ S1: the 1.4 component weight (Axis 3) already lifts
their S0/S1 bugs to P0/P1, so a hard floor would double-count and re-inflate P1.


### Axis 3 - Component weight

Some components matter more than others. Each area in `areas.json` carries a
`weight` (used by the scoring function) and a `weight_source` (metadata: how we
picked it). Bands: **1.4 / 1.2 / 1.1 / 1.0 / 0.9**.

- **Harness weights are telemetry** (`weight_source: telemetry`) — from *LJ
  Sessions by Harness* (usage, last week), not issue counts. This is where
  harness "tiering" lives. Subject to change as usage shifts.
- **Non-harness weights are editorial** (`weight_source: editorial`) — no
  per-component usage signal (every session hits the server), so maintainers set
  these by judgment.

**Combining:** an issue with multiple `comp:` labels takes the **max** weight
(most-important area wins). Harness issues resolve to the specific harness area.

| Component | Weight | Source | Why |
|---|---|---|---|
| `comp:harnesses` — claude, codex | 1.4 | telemetry | Top usage. |
| `comp:harnesses` — cursor, antigravity, hermes, opencode, pi, copilot | 1.1 | telemetry | Mid usage. |
| `comp:harnesses` — goose, kimi, kiro, qwen | 0.9 | telemetry | Less usage. |
| `comp:harnesses` — inner, llms, tools (shared) | 1.1 | editorial | Underpins all harnesses. |
| `comp:server` — server, host, db | 1.2 | editorial | Core path; failures block everything. |
| `comp:runner` — runner, runtime, sandbox | 1.2 | editorial | Core execution path. |
| `comp:server` — resources, sdks | 1.0 | editorial | Supporting. |
| `comp:web-ui`, `comp:policies`, `comp:tui` | 1.0 | editorial | Mainline surfaces. |
| `comp:repr`, `comp:infra`, tui/repl | 0.9 | editorial | Lower blast radius. |

Open follow-up (review): confirm the harness bands (Pi/opencode) and the
editorial weights in the team channel.

#### More / finer labels

Today's 8 `comp:` labels are coarse — a few are mega-buckets:

| Label | Open |
|---|---|
| `comp:harnesses` | 148 |
| `comp:server` | 135 |
| `comp:runner` | 109 |
| `comp:web-ui` | 99 |
| `comp:tui` / `comp:infra` / `comp:policies` / `comp:repr` | 40 / 34 / 21 / 13 |

We add granularity two ways (both, deliberately):

- **New top-level `comp:` label** when a slice is something you'd *filter and
  prioritize on* (e.g. `comp:sandbox` is security-grade).
- **A `sub_area` tag** for the rest. `areas.json` already models sub-areas; the
  classifier emits the matched one as a second-level tag — granularity without
  minting a GH label per slice (the repo has no label-sync, so the label set
  stays small).

**New labels to add:**

| New label | Carved from | Weight | Why |
|---|---|---|---|
| `comp:harness-t1/-t2/-t3` | `comp:harnesses` | 1.4 / 1.1 / 0.9 (telemetry) | Tier is the harness view of the weight; future-proof (add/re-tier = `areas.json` edit, not a new label). `sub_area` also tags SDK vs native. |
| `comp:sandbox` | `comp:runner` | 1.1 (editorial) | ~29 issues, security-grade, home of P0 #3557. Inherits runner's 1.1; the *security* lift is in the P0 rubric (Axis 2), not the weight — so it isn't double-counted. |
| `comp:mobile` | `comp:web-ui` | 1.0 (editorial) | ~23 issues; device sub-tags desktop / mobile-iOS / mobile-Android. Inherits web-ui's 1.0. |
| `comp:auth` | `comp:server` | 1.1 (editorial) | Distinct surface; types local / multi-user / OIDC / OAuth / Databricks. Inherits server-core's 1.1 (a broken login blocks everything). |



### Axis 5 — Duplicate issue

The dedup labeler ([#4037](https://github.com/omnigent-ai/omnigent/pull/4037))
links and labels duplicates without auto-closing. That gives us a reach signal
for free: **N confirmed duplicates means N reporters hit the same issue.**
`dup_reach` bumps the score +15% per confirmed duplicate, capped at +50%, so a
frequently-reduplicated bug rises without letting a pile-on dominate severity.
The scoring job reads the dup count from the labeler's linked issues; the
dry-run stubs it (`duplicate_count`, default 0) since the snapshot JSON doesn't
carry dup links.

### Axis 6 — Readiness

A ticket you can *start on now* is worth surfacing above an equally-severe but vague one.
`readiness` is a small multiplier: 1.1 for a bug with a repro section and a ≥400-char body
(or any substantive FR), 1.0 otherwise. Gentle — it breaks near-ties, never overrides severity.

**`needs-info` is separate. If it's genuinely incomprehensible, we give *no score*, meaning P3 by
default. However, if information are partially presented and is comprehensible, then 1.0.

### Axis 7 - Community demand

Unique user engagement and comments and thumb-up will be counted additively. So they will bump the
issue but won't have too much weight. Existing issues get at most 15 pts today.

### Axis 8 - Age factor

Recent issues (0 - 5 days): 1.0
5 - 21 days: 1.2 - bump lightly to provide more visibility.
21+ days: 0.8 - Since they are ignored for awhile. chances are, they are less important. If not, the
maintainer should bump priority (since priority gives more scores).



### Scoring function (the ordering primitive)
```
base  = severity_weight              # LLM grade, reach folded in (S0/S1/S2/S3 = 100/60/30/10)
      × component_weight             # areas.json per-area weight 1.4/1.2/1.1/1.0/0.9 (Axis 3)
      × dup_reach                    # +15% per confirmed duplicate, capped +50% (Axis 5)
      × readiness                    # ready-to-work 1.1 · normal 1.0 (Axis 6)

score = apply_demand(base, type)     # additive, ≤15 pts (Axis 7)
      × age_factor                   # 0-5d 1.0 · 5-21d 1.2 · 21d+ 0.8 (Axis 8)
```

Every weight is a named constant; the priority label is the band the score lands in
(`≥100 P0 · ≥60 P1 · ≥25 P2 · else P3`).

**Worked example — one issue, data points → score.** Take
[#3265](https://github.com/omnigent-ai/omnigent/issues/3265) ("claude-sdk agent
with linux_bwrap dies at spawn"):

| Factor | Value | Why |
|---|---|---|
| severity | 60 (S1) | spawn death, no workaround; not widespread enough for S0 |
| × component_weight | × 1.4 | `claude-sdk` → `harness-claude`, weight 1.4 (Axis 3) |
| × dup_reach | × 1.0 | no confirmed duplicates |
| × readiness | × 1.0 | no repro section matched |
| + demand (bug) | + 0 | 0 reactions |
| × age | × 1.2 | 10 days old → mid-life visibility bump |
| **= score** | **101** | 60 × 1.4 × 1.2 → **≥ 100 → P0**; rank **#17** of 360 (was rank #37 by label) |

Contrast a vague, low-weight ticket: severity 30 (S2) × component_weight 0.9
(e.g. `comp:repr`) × age 0.8 (stale) ≈ **22** → **P3**, near the bottom. Same
factors, opposite ends of the queue — that's the score→label derivation working.

### Determinism - same inputs, same score

The score is a **pure arithmetic function** of its inputs (multiply/add, no
randomness), so given identical inputs it is byte-for-byte reproducible across
runs. Two nuances worth stating plainly:

- **Persisted severity is what guarantees it.** since severity is the only LLM-generated label.
- **The score still moves over time — by design.** `dup_reach` / `demand` read
  *current* counts, and `age_factor` (Axis 8) changes as an issue progress. This is intended.

Note: There is no tie-breaking today.

### Updates
We will have a schedule job to regrade tickets periodically since metadata can change.

### Maintainer Intervention

Since severity is LLM judgement, maintainer may decide to override priority in the issues.
That's fine and expected. Putting a note here that if there are too many adjustments, we should
revisit some weights. Bot shouldn't overwrite human judgement.


The goal is a ranking good enough that **hand-correction is needed for ≤10% of issues touched**.
If you're correcting more than that, we should fix prompts or weights.


| Symptom | Action |
|---|---|
| Grader misread severity (a real P1 sitting at P2, or vice versa) | Change the priority label. Done — it sticks. |
| Right severity, wrong reach (e.g. "affects all users" missed) | Same: bump the label; reach feeds severity's bucket. |
| A security/sandbox/policy **bypass** graded as ordinary | Set `P0-critical` — bypass is top severity regardless of reach (Axis 2). |
| Truly incomprehensible | Add `needs-info` and leave priority unset (don't prioritize what we can't understand). Partial-but-serious info: keep prioritizing, skip the label. |


---

## Dry-run: LLM grader vs. regex, on real issues

`score_prototype.py` grades severity with regex so a dry-run is reproducible.
But regex only keyword-matches — to check the *design*, an LLM (this one) read
**the 100 oldest open issues**, graded S0–S3 by content, and ran the grades
through the same scoring machinery (weight × dup × readiness + demand × age).
**Priority flipped on 49 of 100** — the argument for grading severity with the
classifier in production.

**Distribution (100 issues):**

| Priority | regex | LLM |
|---|--:|--:|
| P0 | 2 | 1 |
| P1 | 13 | 13 |
| P2 | 43 | 65 |
| P3 | 42 | 21 |

**Confusion — regex (row) → LLM (col):**

| regex ↓ \ LLM → | P0 | P1 | P2 | P3 |
|---|--:|--:|--:|--:|
| **P0** (2) | 1 | 0 | 1 | 0 |
| **P1** (13) | 0 | 6 | 6 | 1 |
| **P2** (43) | 0 | 7 | 30 | 6 |
| **P3** (42) | 0 | 0 | 28 | 14 |

**Agree 51 / 100. Of the 49 flips: 35 regex-too-low, 14 regex-too-high.** The
skew is the tell — regex parks anything without a strong keyword in P3 (and
defaults FRs low), so **28 of its 42 P3s are really P2** on reading: real
feature work or bugs-with-a-workaround it couldn't distinguish from noise.
Agreement concentrates where regex can keyword-match (P2→P2 30, P1→P1 6); it
mis-parks the extremes.

A few concrete flips show *why*, in both directions:

**Regex over-grades (keyword false positives) → LLM corrects down:**

| Issue | regex | LLM | Why regex was wrong |
|---|---|---|---|
| #2057 Codex Auto mode (FR) | P0 | **P2** | FR *proposing* a mode; "sandbox bypass" is what it avoids, not a report. |
| #2054 dedup Codex modes (FR) | P0 | **P3** | Config tidying; same false keyword. |
| #61 bot "Code Audit" (bug) | P1 | **P3** | Auto-generated list, "verify before acting" — not a confirmed bug. |
| #2125 multi-host git creds (FR) | P0 | **P1** | Real blocker, but regex hit the literal phrase "PAT is offered", not the risk. |

**Regex under-grades (no way to read impact) → LLM corrects up:**

| Issue | regex | LLM | Why |
|---|---|---|---|
| #1021 Copilot provider (FR) | P2 | **P1** | Wanted new provider (10 👍); regex graded the FR "medium". |
| #2429 server CPU-spin (bug) | P2 | **P1** | 10h spin, no watchdog; "medium" keyword undersold a real reliability bug. |
| #3790 force_sandbox no-op (bug) | P2 | **P1** | A safety policy silently disabled — security-adjacent; regex saw only "evaluated". |

**Regex already right (no flip):** #3557 (P0 policy bypass), #16 (P0, whole
platform), #3981 (P2, has workaround), #377 (P2, trivial mitigation). Regex is
fine when the keyword *happens* to match the real severity.

**Takeaway:** once severity is graded honestly, the machinery carries it to a
sensible priority with no extra tuning (e.g. #2429 crosses P1 on the 1.2 server
weight). The grader must be the LLM; the weights are a defensible start.

---

## Intake: what more to collect

Today's bug template has Version + OS, both optional → sparse. Add optional
dropdowns (cheap for the reporter, better signal than free text):

- **Harness + mode** (claude / codex / … + SDK / native) → component weight + `sub_area`.
- **Platform / device** (macOS / Linux / Windows / desktop / mobile-iOS / mobile-Android / Docker) → `comp:mobile` sub-tag + reach.
- **Impact / reach** (all / most / some / edge) → feeds severity (Axis 2).
- **Auth type** (local / multi-user / OIDC / OAuth / Databricks) → `comp:auth`.

---

## Rollout

Nothing here is built yet except the `areas.json` weights (+ test). Action items,
each its own PR:

- [ ] **Tune the classifier prompt** (`.github/triage/config.yaml`) — S0–S3 rubric,
  FRs graded, tier-1 nudge, P0 list; emit + **persist** `severity`, `readiness`,
  `sub_area` (persisted severity is what keeps re-scoring deterministic).
- [ ] **Create the cron job** — scheduled Databricks notebook: read
  `github_issues_bronze`, compute score once, write `issue_scores`, apply labels
  back (with the human-override guard). See "Surfacing the score".
- [ ] **Add labels** — `severity S0–S3`, `comp:harness-t1/-t2/-t3`, `comp:sandbox`,
  `comp:mobile`, `comp:auth`; wire the classifier allowlist.
- [ ] **Add template dropdowns** — Harness+mode / Platform-device / Impact / Auth-type.
- [ ] **Backfill** — regrade open issues (`--regrade`; preview lands ~23% P1 bugs),
  filling only bot-owned priorities.
- [ ] **Plumb scores to the dashboard** — `issue_scores` → a ranked Lakeview tile.

## Metrics

- **P1 share of open bugs** — target ~25% (today 60%).
- **Priority age separation** — P1 median age should drop below P2's (equal today).
- **Prioritization efficiency** — `sum(score of k resolved) / sum(score of top-k)`;
  near 1.0 = we're working the highest-scored issues.
- **Re-grade rate** — how often maintainers change a label post-triage (high = tune the grader).

---

## Appendix A — Splitting `comp:harnesses`: tier labels vs per-harness labels

`comp:harnesses` is 41% of open issues and needs splitting. Two options:

- **Per-harness** (`comp:harness-claude`, `comp:harness-codex`, …) — one label
  per harness (~11 today). Maximally granular, but every new harness needs a
  new label, and re-tiering means re-teaching everyone which harnesses are
  "important."
- **Tier** (`comp:harness-t1/-t2/-t3`) — three stable labels; the harness→tier
  mapping lives in `areas.json`. **Chosen.** Future-proof: shipping a harness or
  re-tiering one is an `areas.json` edit + backfill, no new label. Per-harness
  *filtering* is still possible through area routing when someone needs it.

Both need the same one-time backfill of existing `comp:harnesses` issues; tier
adds three labels instead of eleven and doesn't grow with the harness count.

## Appendix B — Rejected alternatives

- **Keep priority as the only axis.** Can't express a high-severity item stuck
  in a low bucket (#2125), and a single bucket label can't encode ordering
  within a bucket. The score exists to order within and across buckets.
- **A separate `pin:high` / `pin:low` override** (in an earlier draft). Dropped:
  it's a second knob that means the same thing as changing severity but sits out
  of band from it. Maintainers re-grade severity to bump — one knob, the one
  they already use.
- **Auto-closing duplicates.** The dedup labeler
  ([#4037](https://github.com/omnigent-ai/omnigent/pull/4037)) links without
  closing; we keep dupes open and use their *count* as a reach signal (Axis 5).

## Appendix C — Full ranking snapshot (top 200 of 360 open)

Generated from the snapshot with `score_prototype.py --markdown 200` (regex
severity grader — the same stand-in used throughout; production uses the LLM
grader). Columns: **Score** = composite score; **Sev** = re-graded severity;
**Now** = current priority label; **Derived** = the priority the score→label
thresholds (Axis 2) assign, with **⚑** marking a change from today's label;
**Δrank** = movement vs the current priority-label ordering (positive = moved
up). The Now→Derived column is the per-issue view of the backfill: the ⚑ rows
are the relabels the one-time regrade would apply.

**Illustrative, not actionable.** This is the *mechanism* running on a
deliberately-weak grader, so its own failures are visible on purpose: ranks 2–5
(#2125/#2057/#2054) are FRs that hit a critical-regex keyword — they sit above
the real P0 (#3557, rank 14), so **the very top is backwards**; #61 (rank 33) is
a *bot* audit issue riding a "security" keyword. That's the doc's thesis made
concrete: regex can't grade severity. Strip those artifacts and the genuine
high-weight harness bugs cluster correctly near the top. Scores *tie* in coarse
bands (many share 84/67/…), so within-band order is arbitrary — read this as a
handful of tiers, not 200 true ranks. With the LLM grader plus ≤10%
hand-correction (see the maintainer guide), this is the shape the production
ranking takes.

| # | Score | Sev | Now | Derived | Δrank | Issue |
|--:|--:|---|---|---|--:|---|
| 1 | 158 | critical | P1 | P0 ⚑ | +34 | [#3270](https://github.com/omnigent-ai/omnigent/issues/3270) [Bug] sys_session_create children are absent from both sys_session_lis |
| 2 | 143 | critical | P2 | P0 ⚑ | +230 | [#2125](https://github.com/omnigent-ai/omnigent/issues/2125) [Feature] Multi-host git credentials for managed sandboxes (GitHub + s |
| 3 | 132 | critical | P1 | P0 ⚑ | +1 | [#3983](https://github.com/omnigent-ai/omnigent/issues/3983) [Bug] Smart-routed turns render out of order: reply streams above the  |
| 4 | 123 | critical | P2 | P0 ⚑ | +232 | [#2057](https://github.com/omnigent-ai/omnigent/issues/2057) [Feature] Add Codex Auto mode using auto_review instead of jumping to  |
| 5 | 123 | critical | P2 | P0 ⚑ | +233 | [#2054](https://github.com/omnigent-ai/omnigent/issues/2054) [Feature] Remove duplicate Codex Full access mode and keep Sandbox Byp |
| 6 | 111 | high | P1 | P0 ⚑ | +27 | [#3299](https://github.com/omnigent-ai/omnigent/issues/3299) [Bug] Harness-credential route times out with a misleading 504 against |
| 7 | 111 | high | P2 | P0 ⚑ | +159 | [#3284](https://github.com/omnigent-ai/omnigent/issues/3284) [Crash] DuplicateOptionError: While reading from PosixPath('/Users/*** |
| 8 | 111 | high | P1 | P0 ⚑ | +33 | [#3180](https://github.com/omnigent-ai/omnigent/issues/3180) codex-native: runner never exits on idle timeout — cancelled delta-coa |
| 9 | 111 | high | P2 | P0 ⚑ | +175 | [#3070](https://github.com/omnigent-ai/omnigent/issues/3070) No progress signal on a stuck or interactive harness install |
| 10 | 111 | high | P1 | P0 ⚑ | +45 | [#2967](https://github.com/omnigent-ai/omnigent/issues/2967) [Bug] A full context window bricks a session with "Prompt is too long" |
| 11 | 111 | high | P1 | P0 ⚑ | +45 | [#2920](https://github.com/omnigent-ai/omnigent/issues/2920) Omnigent server fails to start on native Windows: os.getuid() at impor |
| 12 | 111 | high | P1 | P0 ⚑ | +45 | [#2919](https://github.com/omnigent-ai/omnigent/issues/2919) omni setup crashes on Windows: ModuleNotFoundError: No module named 't |
| 13 | 111 | high | P2 | P0 ⚑ | +195 | [#2714](https://github.com/omnigent-ai/omnigent/issues/2714) Upgrade openai-agents and remove the temporary openai<2.45 cap |
| 14 | 110 | critical | P0 | P0 | -13 | [#3557](https://github.com/omnigent-ai/omnigent/issues/3557) [Bug] Shell-surface policy gates are bypassed by option-taking command |
| 15 | 108 | high | P2 | P0 ⚑ | +319 | [#16](https://github.com/omnigent-ai/omnigent/issues/16) Is native Windows support in scope, or should docs recommend WSL2? |
| 16 | 106 | critical | P2 | P0 ⚑ | +299 | [#659](https://github.com/omnigent-ai/omnigent/issues/659) [Feature] add a microvm backend for sandbox |
| 17 | 101 | high | P1 | P0 ⚑ | +20 | [#3265](https://github.com/omnigent-ai/omnigent/issues/3265) claude-sdk agent with linux_bwrap dies at spawn on a runtime bwrap bin |
| 18 | 101 | high | P1 | P0 ⚑ | +35 | [#3000](https://github.com/omnigent-ai/omnigent/issues/3000) claude-native transcript forwarder polls at 4 Hz per session with no i |
| 19 | 101 | high | P1 | P0 ⚑ | +43 | [#2748](https://github.com/omnigent-ai/omnigent/issues/2748) Runner idle-shutdown deadlocks forever: codex-forwarder close()/flush( |
| 20 | 101 | high | P1 | P0 ⚑ | +45 | [#2629](https://github.com/omnigent-ai/omnigent/issues/2629) web_fetch sub-agent spawn fails with unknown harness 'omnigent' — bare |
| 21 | 101 | high | P1 | P0 ⚑ | +46 | [#2575](https://github.com/omnigent-ai/omnigent/issues/2575) pi-native: non-Claude Databricks models (GLM, Gemini, …) hang — provid |
| 22 | 100 | high | P1 | P1 | +16 | [#3261](https://github.com/omnigent-ai/omnigent/issues/3261) [Crash] AttributeError: module 'os' has no attribute 'WNOHANG' |
| 23 | 95 | high | P1 | P1 | +5 | [#3482](https://github.com/omnigent-ai/omnigent/issues/3482) [Crash] ServerError: |
| 24 | 95 | high | P1 | P1 | +6 | [#3458](https://github.com/omnigent-ai/omnigent/issues/3458) session-updates stream crashes with KeyError when a client watches a c |
| 25 | 95 | high | P2 | P1 ⚑ | +139 | [#3363](https://github.com/omnigent-ai/omnigent/issues/3363) [Feature] Per-project custom instructions (project-scoped context) |
| 26 | 95 | high | P2 | P1 ⚑ | +141 | [#3271](https://github.com/omnigent-ai/omnigent/issues/3271) [Feature] Expose per-session context size + last-turn timestamp to age |
| 27 | 95 | high | P2 | P1 ⚑ | +146 | [#3231](https://github.com/omnigent-ai/omnigent/issues/3231) [Crash] OmnigentError: {'error_code': 403, 'message': 'Invalid access  |
| 28 | 86 | high | P1 | P1 | +6 | [#3274](https://github.com/omnigent-ai/omnigent/issues/3274) Sub-agent terminal status rejected with missing_parent_inbox and retri |
| 29 | 86 | high | P1 | P1 | +18 | [#3016](https://github.com/omnigent-ai/omnigent/issues/3016) [Bug] A transient session-snapshot failure permanently pins a session  |
| 30 | 86 | high | P1 | P1 | +18 | [#3012](https://github.com/omnigent-ai/omnigent/issues/3012) Hosts authenticated via `omnigent login` permanently 403 on first reco |
| 31 | 86 | high | P1 | P1 | +21 | [#3001](https://github.com/omnigent-ai/omnigent/issues/3001) [Performance] GET /v1/sessions pre-fetches every accessible conversati |
| 32 | 84 | high | P2 | P1 ⚑ | +122 | [#3558](https://github.com/omnigent-ai/omnigent/issues/3558) claude-sdk: cached client does not rebuild on framework-instruction ch |
| 33 | 80 | critical | P3 | P1 ⚑ | +316 | [#61](https://github.com/omnigent-ai/omnigent/issues/61) 🤖 Code Audit: 21 potential issue(s) found |
| 34 | 79 | high | P2 | P1 ⚑ | +102 | [#3976](https://github.com/omnigent-ai/omnigent/issues/3976) [Feature] OAuth2 client-credentials grant so a headless process can au |
| 35 | 79 | high | P1 | P1 | -6 | [#3469](https://github.com/omnigent-ai/omnigent/issues/3469) [Bug] Post-completion compaction spiral: merge-commit diff output trig |
| 36 | 79 | high | P1 | P1 | -4 | [#3359](https://github.com/omnigent-ai/omnigent/issues/3359) [Crash] ModuleNotFoundError: No module named 'termios' |
| 37 | 79 | high | P1 | P1 | +2 | [#3251](https://github.com/omnigent-ai/omnigent/issues/3251) [Crash] ModuleNotFoundError: No module named 'termios' |
| 38 | 79 | high | P1 | P1 | +7 | [#3052](https://github.com/omnigent-ai/omnigent/issues/3052) [Crash] ModuleNotFoundError: No module named 'termios' |
| 39 | 79 | high | P1 | P1 | +7 | [#3023](https://github.com/omnigent-ai/omnigent/issues/3023) [Crash] ModuleNotFoundError: No module named 'termios' |
| 40 | 79 | high | P1 | P1 | +14 | [#2993](https://github.com/omnigent-ai/omnigent/issues/2993) [Crash] ModuleNotFoundError: No module named 'termios' |
| 41 | 79 | high | P3 | P1 ⚑ | +296 | [#2887](https://github.com/omnigent-ai/omnigent/issues/2887) [Bug] web/package-lock.json is out of sync with package.json; plain `n |
| 42 | 79 | high | P1 | P1 | +26 | [#2559](https://github.com/omnigent-ai/omnigent/issues/2559) Conversation bricked: Page fails to load when opening markdown file af |
| 43 | 74 | high | P1 | P1 | +36 | [#2422](https://github.com/omnigent-ai/omnigent/issues/2422) Windows: five chained defects break the documented degraded-mode subse |
| 44 | 74 | high | P1 | P1 | +38 | [#2373](https://github.com/omnigent-ai/omnigent/issues/2373) [Bug] claude-native: pasted web-UI message loses its Enter, stuck draf |
| 45 | 74 | high | P1 | P1 | +45 | [#2245](https://github.com/omnigent-ai/omnigent/issues/2245) [Bug] openai-agents harness turn wedges permanently after policy-verdi |
| 46 | 74 | high | P1 | P1 | +48 | [#2060](https://github.com/omnigent-ai/omnigent/issues/2060) [Bug] claude-native: first web-UI message silently dropped when Claude |
| 47 | 74 | high | P1 | P1 | +56 | [#1898](https://github.com/omnigent-ai/omnigent/issues/1898) [Bug] codex-native: cancelling a task awaiting flush() poisons the del |
| 48 | 74 | high | P2 | P1 ⚑ | +222 | [#1528](https://github.com/omnigent-ai/omnigent/issues/1528) Idle-session lifecycle UX: reap gracefully, resume seamlessly, surface |
| 49 | 74 | high | P2 | P1 ⚑ | +246 | [#1051](https://github.com/omnigent-ai/omnigent/issues/1051) [Feature] Forward OTel exporter knobs to executor subprocess env |
| 50 | 74 | high | P2 | P1 ⚑ | +260 | [#762](https://github.com/omnigent-ai/omnigent/issues/762) [Bug] sub agent terminal crashes when cli starts with prompt for input |
| 51 | 74 | high | P2 | P1 ⚑ | +265 | [#654](https://github.com/omnigent-ai/omnigent/issues/654) [Bug] Streaming with codex is hanging and paragraphs are not split. |
| 52 | 74 | high | P1 | P1 | +75 | [#542](https://github.com/omnigent-ai/omnigent/issues/542) [Bug] AttributeError: 'SubprocessCLITransport' object has no attribute |
| 53 | 74 | high | P2 | P1 ⚑ | +187 | [#2038](https://github.com/omnigent-ai/omnigent/issues/2038) [Feature] No way to deregister/delete an external self-registered host |
| 54 | 72 | high | P1 | P1 | -46 | [#3971](https://github.com/omnigent-ai/omnigent/issues/3971) Host runners inherit the daemon's cwd; a deleted launch dir breaks eve |
| 55 | 72 | high | P2 | P1 ⚑ | +117 | [#3235](https://github.com/omnigent-ai/omnigent/issues/3235) Flaky E2E UI: test_scheduled_task_create_edit_modal_and_time_picker[ch |
| 56 | 71 | high | P2 | P1 ⚑ | +121 | [#3164](https://github.com/omnigent-ai/omnigent/issues/3164) [Feature] Optional runtimeClassName on the kubernetes sandbox provider |
| 57 | 71 | high | P1 | P1 | -8 | [#3011](https://github.com/omnigent-ai/omnigent/issues/3011) kiro-native harness: interactive sessions never respond with kiro-cli  |
| 58 | 67 | high | P1 | P1 | +14 | [#2454](https://github.com/omnigent-ai/omnigent/issues/2454) [Bug] Unbounded ~/.omnigent growth: per-session native-harness dirs ar |
| 59 | 67 | high | P1 | P1 | +21 | [#2421](https://github.com/omnigent-ai/omnigent/issues/2421) [Bug] codex app-server + MCP bridge children leak on ANY unclean runne |
| 60 | 67 | high | P1 | P1 | +68 | [#523](https://github.com/omnigent-ai/omnigent/issues/523) REPL pexpect e2e tests starve on boot under full shard load (60s _wait |
| 61 | 67 | high | P2 | P1 ⚑ | +268 | [#151](https://github.com/omnigent-ai/omnigent/issues/151) Native claude_code worker hangs on the one-time Bypass Permissions acc |
| 62 | 66 | high | P2 | P1 ⚑ | +243 | [#888](https://github.com/omnigent-ai/omnigent/issues/888) [Feature] Side-by-side multi-session view |
| 63 | 66 | high | P2 | P1 ⚑ | +74 | [#3970](https://github.com/omnigent-ai/omnigent/issues/3970) pi-native: every turn fails with "Pi model error: 401 Invalid Token" w |
| 64 | 66 | high | P1 | P1 | -47 | [#3799](https://github.com/omnigent-ai/omnigent/issues/3799) Android shell cannot sign in to servers behind a front-door auth proxy |
| 65 | 66 | high | P2 | P1 ⚑ | +81 | [#3750](https://github.com/omnigent-ai/omnigent/issues/3750) [Crash] PermissionError: [Errno 1] Operation not permitted |
| 66 | 66 | high | P1 | P1 | -46 | [#3730](https://github.com/omnigent-ai/omnigent/issues/3730) [Bug] Android: renderer death terminates the app — OmnigentWebViewClie |
| 67 | 66 | high | P1 | P1 | -45 | [#3701](https://github.com/omnigent-ai/omnigent/issues/3701) [Bug] Desktop app never completes Okta security key / biometric MFA du |
| 68 | 63 | high | P2 | P1 ⚑ | +148 | [#2480](https://github.com/omnigent-ai/omnigent/issues/2480) [Bug] Postgres-backed local server: bare `No module named 'psycopg'` + |
| 69 | 63 | high | P0 | P1 ⚑ | -67 | [#2355](https://github.com/omnigent-ai/omnigent/issues/2355) [Bug] workspace_id PK-widening migration crashes on populated Postgres |
| 70 | 63 | high | P3 | P1 ⚑ | +271 | [#2224](https://github.com/omnigent-ai/omnigent/issues/2224) [Bug] get_client model-change check fails for harness="any" |
| 71 | 63 | high | P1 | P1 | +27 | [#1985](https://github.com/omnigent-ai/omnigent/issues/1985) Headless `omnigent run -p` intermittently hangs forever despite the tu |
| 72 | 63 | high | P1 | P1 | +27 | [#1953](https://github.com/omnigent-ai/omnigent/issues/1953) `omni host` dies permanently when the OIDC session JWT expires — no re |
| 73 | 63 | high | P2 | P1 ⚑ | +171 | [#1907](https://github.com/omnigent-ai/omnigent/issues/1907) Sub-agent model_override triggers an unnecessary first-turn harness re |
| 74 | 63 | high | P2 | P1 ⚑ | +179 | [#1804](https://github.com/omnigent-ai/omnigent/issues/1804) spec parser crashes with TypeError on a null tools.builtins key (and s |
| 75 | 63 | high | P2 | P1 ⚑ | +201 | [#1388](https://github.com/omnigent-ai/omnigent/issues/1388) Make agents a first-class CRUD entity with a dedicated sidebar UI (dec |
| 76 | 63 | high | P2 | P1 ⚑ | +213 | [#1076](https://github.com/omnigent-ai/omnigent/issues/1076) Runner-layer Tier-2 escalation: release an unresponsive per-conversati |
| 77 | 63 | high | P1 | P1 | +44 | [#1026](https://github.com/omnigent-ai/omnigent/issues/1026) Runner orphans tool callbacks with "no active turn context" after mid- |
| 78 | 61 | high | P2 | P1 ⚑ | +220 | [#1022](https://github.com/omnigent-ai/omnigent/issues/1022) Behind a corporate proxy, the host daemon can't reach the model backen |
| 79 | 60 | medium | P2 | P1 ⚑ | +125 | [#2744](https://github.com/omnigent-ai/omnigent/issues/2744) [Bug] codex-native: custom agents time out at launch — native provider |
| 80 | 60 | high | P2 | P1 ⚑ | +64 | [#3798](https://github.com/omnigent-ai/omnigent/issues/3798) Android shell shows the SPA as if signed in while native login runs in |
| 81 | 58 | high | P2 | P2 | +186 | [#1600](https://github.com/omnigent-ai/omnigent/issues/1600) Epic: 12-feature contribution (one issue + one PR per feature) |
| 82 | 58 | high | P2 | P2 | +136 | [#2428](https://github.com/omnigent-ai/omnigent/issues/2428) sys_session_send to a completed session hangs to ReadTimeout and is si |
| 83 | 58 | high | P1 | P2 ⚑ | +8 | [#2241](https://github.com/omnigent-ai/omnigent/issues/2241) Flaky on main: test_interrupt_forwards_to_harness_before_cancelling ti |
| 84 | 58 | high | P1 | P2 ⚑ | +12 | [#2051](https://github.com/omnigent-ai/omnigent/issues/2051) [Bug] sys_session_send(session_id=…) completions never drain to sys_re |
| 85 | 58 | high | P0 | P2 ⚑ | -82 | [#1657](https://github.com/omnigent-ai/omnigent/issues/1657) hermes-native forwarder advances last_id per item, dropping a row's la |
| 86 | 58 | high | P2 | P2 | +228 | [#678](https://github.com/omnigent-ai/omnigent/issues/678) e2e: sub-agent supervisor routing / named-sub-agent auto-wake flakes ( |
| 87 | 55 | medium | P1 | P2 ⚑ | -62 | [#3536](https://github.com/omnigent-ai/omnigent/issues/3536) [Bug] A session's `reasoning_effort` never reaches in-process harnesse |
| 88 | 55 | medium | P2 | P2 | +73 | [#3369](https://github.com/omnigent-ai/omnigent/issues/3369) Feature: a policy that fences a spawned type: agent worker read-only ( |
| 89 | 55 | medium | P2 | P2 | +79 | [#3254](https://github.com/omnigent-ai/omnigent/issues/3254) Sub-agent silently stalls after repeated context compactions during re |
| 90 | 55 | medium | P2 | P2 | +95 | [#3069](https://github.com/omnigent-ai/omnigent/issues/3069) Harness install surfaces opaque failure reasons (npm stderr not captur |
| 91 | 55 | medium | P2 | P2 | +100 | [#2984](https://github.com/omnigent-ai/omnigent/issues/2984) [Bug] Codex incorrectly reports `needs-auth` with an authenticated cus |
| 92 | 55 | medium | P1 | P2 ⚑ | -34 | [#2904](https://github.com/omnigent-ai/omnigent/issues/2904) [Bug] claude-native: web-UI chat input fails with "tmux command failed |
| 93 | 55 | medium | P2 | P2 | +101 | [#2880](https://github.com/omnigent-ai/omnigent/issues/2880) [Feature] Add in-session revert mechanism for all interfaces  |
| 94 | 55 | medium | P3 | P2 ⚑ | +244 | [#2853](https://github.com/omnigent-ai/omnigent/issues/2853) [Bug] Native harnesses silently drop the agent spec `prompt:` at runti |
| 95 | 55 | medium | P2 | P2 | +105 | [#2815](https://github.com/omnigent-ai/omnigent/issues/2815) [Feature] Distinguish human waits from machine-liveness deadlines |
| 96 | 55 | medium | P1 | P2 ⚑ | -35 | [#2812](https://github.com/omnigent-ai/omnigent/issues/2812) [Bug] serve-mcp stops answering stdio requests during a slow tool call |
| 97 | 55 | medium | P2 | P2 | +110 | [#2719](https://github.com/omnigent-ai/omnigent/issues/2719) [Bug] |
| 98 | 55 | medium | P2 | P2 | +113 | [#2644](https://github.com/omnigent-ai/omnigent/issues/2644) Design discussion: deterministic verification gates (a PASS/FAIL quali |
| 99 | 53 | high | P1 | P2 ⚑ | -11 | [#2270](https://github.com/omnigent-ai/omnigent/issues/2270) Windows: config list crashes — UnicodeEncodeError on cp1252 (non-UTF8) |
| 100 | 53 | high | P1 | P2 ⚑ | -11 | [#2269](https://github.com/omnigent-ai/omnigent/issues/2269) Windows: omnigent setup crashes — ModuleNotFoundError: No module named |
| 101 | 53 | high | P1 | P2 ⚑ | +3 | [#1888](https://github.com/omnigent-ai/omnigent/issues/1888) ansi-to-react default import resolves to the CJS exports object under  |
| 102 | 53 | high | P1 | P2 ⚑ | +3 | [#1881](https://github.com/omnigent-ai/omnigent/issues/1881) [Bug] `omnigent setup` crashes with `ValueError: select() requires at  |
| 103 | 53 | high | P2 | P2 | +152 | [#1778](https://github.com/omnigent-ai/omnigent/issues/1778) opencode-native forwarder loses session content across SSE reconnects  |
| 104 | 52 | medium | P1 | P2 ⚑ | -62 | [#3101](https://github.com/omnigent-ai/omnigent/issues/3101) Docker/Kubernetes entrypoint never wires project_store — first-class P |
| 105 | 51 | high | P1 | P2 ⚑ | +26 | [#108](https://github.com/omnigent-ai/omnigent/issues/108) Cannot install on Linux aarch64 — cel-expr-python has no aarch64 wheel |
| 106 | 50 | medium | P1 | P2 ⚑ | -66 | [#3236](https://github.com/omnigent-ai/omnigent/issues/3236) web_search: bare executor.model strings are inferred as provider 'open |
| 107 | 50 | medium | P1 | P2 ⚑ | -43 | [#2630](https://github.com/omnigent-ai/omnigent/issues/2630) Tool-spawn failure is swallowed — agent answers from training knowledg |
| 108 | 49 | medium | P2 | P2 | +160 | [#1596](https://github.com/omnigent-ai/omnigent/issues/1596) Native-CLI harness (claude-native/codex-native) as a named agent's own |
| 109 | 48 | high | P1 | P2 ⚑ | -7 | [#1901](https://github.com/omnigent-ai/omnigent/issues/1901) [Bug] kimi/qwen/goose/kiro forwarders blind-retry failed conversation- |
| 110 | 48 | high | P1 | P2 ⚑ | -2 | [#1827](https://github.com/omnigent-ai/omnigent/issues/1827) [Bug] kimi-native: torn UTF-8 wire read crashes the forwarder; supervi |
| 111 | 48 | medium | P2 | P2 | +46 | [#3531](https://github.com/omnigent-ai/omnigent/issues/3531) SSH_AUTH_SOCK dropped at the host→runner env boundary, breaking ssh-ag |
| 112 | 48 | medium | P2 | P2 | +48 | [#3435](https://github.com/omnigent-ai/omnigent/issues/3435) [Feature] Admin server-wide usage report (per-user and per-model cost) |
| 113 | 48 | medium | P2 | P2 | +49 | [#3368](https://github.com/omnigent-ai/omnigent/issues/3368) Feature: first-class async write-safety (freeze → approve → apply) pri |
| 114 | 48 | medium | P2 | P2 | +51 | [#3352](https://github.com/omnigent-ai/omnigent/issues/3352) [Feature] OpenClaw onboarding — Option B: chat import (SQLite session  |
| 115 | 48 | medium | P2 | P2 | +55 | [#3247](https://github.com/omnigent-ai/omnigent/issues/3247) credential_proxy: re-resolve the source on 401 / expiry (short-lived t |
| 116 | 48 | medium | P1 | P2 ⚑ | -56 | [#2854](https://github.com/omnigent-ai/omnigent/issues/2854) [Bug] Cross-harness `harness_override` is ignored on the `initial_item |
| 117 | 48 | medium | P2 | P2 | +79 | [#2851](https://github.com/omnigent-ai/omnigent/issues/2851) Policy-supplied targets for ASK approval cards |
| 118 | 48 | medium | P2 | P2 | +84 | [#2756](https://github.com/omnigent-ai/omnigent/issues/2756) Expose atomic session-event admission to integrations |
| 119 | 48 | medium | P2 | P2 | +93 | [#2577](https://github.com/omnigent-ai/omnigent/issues/2577) [Feature] Manage OIDC/SSO admins from an id_token claim (IdP group/rol |
| 120 | 48 | medium | P2 | P2 | +94 | [#2542](https://github.com/omnigent-ai/omnigent/issues/2542) [Feature] Ambient-detect a local llama-server, mirroring Ollama detect |
| 121 | 48 | medium | P1 | P2 ⚑ | -51 | [#2539](https://github.com/omnigent-ai/omnigent/issues/2539) Named sys_session_send returns 404 after first child from a bundled se |
| 122 | 46 | medium | P1 | P2 ⚑ | -112 | [#3952](https://github.com/omnigent-ai/omnigent/issues/3952) A stale terminal exit removes the newer Codex resources of the same se |
| 123 | 46 | medium | P2 | P2 | +27 | [#3592](https://github.com/omnigent-ai/omnigent/issues/3592) [Feature] Deterministic long-term memory (automatic recall/retain) — f |
| 124 | 46 | medium | P1 | P2 ⚑ | -98 | [#3530](https://github.com/omnigent-ai/omnigent/issues/3530) [Bug] An agent spec's `instructions:` has no effect on 13 of 24 harnes |
| 125 | 46 | medium | P1 | P2 ⚑ | -98 | [#3525](https://github.com/omnigent-ai/omnigent/issues/3525) Sub-agent sessions are launched from the parent agent's bundle root, e |
| 126 | 46 | medium | P1 | P2 ⚑ | -82 | [#3076](https://github.com/omnigent-ai/omnigent/issues/3076) [Bug] claude-sdk omits ToolSearch, eagerly loading every MCP schema |
| 127 | 46 | medium | P3 | P2 ⚑ | +212 | [#2800](https://github.com/omnigent-ai/omnigent/issues/2800) [Bug] Top-level custom codex-native agents drop reasoning effort and y |
| 128 | 45 | medium | P2 | P2 | +171 | [#1021](https://github.com/omnigent-ai/omnigent/issues/1021) [Feature] GitHub Copilot as provider |
| 129 | 43 | medium | P2 | P2 | +195 | [#377](https://github.com/omnigent-ai/omnigent/issues/377) gpt sub-agent fails on startup with missing databricks-sdk dependency |
| 130 | 43 | medium | P2 | P2 | +68 | [#2848](https://github.com/omnigent-ai/omnigent/issues/2848) Server logs an expected offline-runner resource 503 as ERROR + full tr |
| 131 | 43 | medium | P2 | P2 | +70 | [#2767](https://github.com/omnigent-ai/omnigent/issues/2767) [Bug] SQLite pool (default 5+10) not sized to the 200-thread limiter → |
| 132 | 42 | medium | P2 | P2 | +6 | [#3969](https://github.com/omnigent-ai/omnigent/issues/3969) Databricks gateway sessions default to a stale model (opus-4-7) while  |
| 133 | 42 | medium | P1 | P2 ⚑ | -115 | [#3790](https://github.com/omnigent-ai/omnigent/issues/3790) force_sandbox policy is evaluated but structurally unreachable from cl |
| 134 | 42 | medium | P1 | P2 ⚑ | -71 | [#2702](https://github.com/omnigent-ai/omnigent/issues/2702) Native idle-detection fork+exec's tmux capture-pane at 5 Hz per termin |
| 135 | 40 | medium | P2 | P2 | -1 | [#4009](https://github.com/omnigent-ai/omnigent/issues/4009) [Feature] No Go client for the session API, so every Go caller hand-ro |
| 136 | 40 | medium | P1 | P2 ⚑ | -123 | [#3898](https://github.com/omnigent-ai/omnigent/issues/3898) [Bug] Pack function policies fail server-side input evaluation unless  |
| 137 | 40 | medium | P1 | P2 ⚑ | -123 | [#3870](https://github.com/omnigent-ai/omnigent/issues/3870) child-session creation returns 500 internal_error, breaking Polly/Debb |
| 138 | 40 | medium | P2 | P2 | +4 | [#3864](https://github.com/omnigent-ai/omnigent/issues/3864) [Bug] to_api_dict() drops ConversationItem.created_at, so flat items A |
| 139 | 40 | medium | P1 | P2 ⚑ | -124 | [#3863](https://github.com/omnigent-ai/omnigent/issues/3863) [Bug] Databricks Apps entrypoint never wires project_store — Projects  |
| 140 | 40 | medium | P2 | P2 | +12 | [#3563](https://github.com/omnigent-ai/omnigent/issues/3563) [Bug] Host-bound resume into a deleted workspace: host computes the ex |
| 141 | 40 | medium | P2 | P2 | +14 | [#3550](https://github.com/omnigent-ai/omnigent/issues/3550) [Bug] Missing signing alg's prevent using some OIDC providers |
| 142 | 40 | medium | P2 | P2 | +16 | [#3449](https://github.com/omnigent-ai/omnigent/issues/3449) [Bug] Item pagination cursor can't use the index, so scroll-back scans |
| 143 | 40 | medium | none | P2 | +210 | [#3402](https://github.com/omnigent-ai/omnigent/issues/3402) [Bug] Label seeding and session-state writes race under concurrent upd |
| 144 | 40 | medium | none | P2 | +210 | [#3392](https://github.com/omnigent-ai/omnigent/issues/3392) [Bug] Linux desktop app missing Icon |
| 145 | 40 | medium | P2 | P2 | +31 | [#3219](https://github.com/omnigent-ai/omnigent/issues/3219) [Bug] Cmd/Ctrl+Up/Down session traversal stops in an empty focused com |
| 146 | 40 | medium | P1 | P2 ⚑ | -103 | [#3095](https://github.com/omnigent-ai/omnigent/issues/3095) [Bug] Can't uninstall |
| 147 | 40 | medium | P2 | P2 | +40 | [#3064](https://github.com/omnigent-ai/omnigent/issues/3064) [Bug] Created file links are inaccessible from remote sessions |
| 148 | 40 | medium | P2 | P2 | +44 | [#2921](https://github.com/omnigent-ai/omnigent/issues/2921) Font settings: selected font (incl. Nerd Fonts) never loads — no webfo |
| 149 | 40 | medium | P1 | P2 ⚑ | -90 | [#2866](https://github.com/omnigent-ai/omnigent/issues/2866) iOS app: Google OIDC fails with 403 disallowed_useragent in embedded w |
| 150 | 40 | medium | P1 | P2 ⚑ | -81 | [#2549](https://github.com/omnigent-ai/omnigent/issues/2549) [Bug] iOS Google OIDC fails with disallowed_useragent in WKWebView |
| 151 | 38 | medium | P2 | P2 | -12 | [#3950](https://github.com/omnigent-ai/omnigent/issues/3950) An agent switch keeps the previous agent's comment-tool relay |
| 152 | 38 | medium | P1 | P2 ⚑ | -136 | [#3852](https://github.com/omnigent-ai/omnigent/issues/3852) [Bug] Built-in write policies miss Claude Code's `MultiEdit` / `Notebo |
| 153 | 37 | feature | P2 | P2 | +25 | [#3150](https://github.com/omnigent-ai/omnigent/issues/3150) [Feature] CLI: cross-harness fork — continue an existing session in a  |
| 154 | 37 | medium | P1 | P2 ⚑ | -73 | [#2397](https://github.com/omnigent-ai/omnigent/issues/2397) [Bug] Codex-native intelligent routing ignores live effort capabilitie |
| 155 | 37 | medium | P1 | P2 ⚑ | -68 | [#2272](https://github.com/omnigent-ai/omnigent/issues/2272) [Bug] Codex runner can't find OpenRouter secret that exists in keyring |
| 156 | 37 | medium | P1 | P2 ⚑ | -64 | [#2184](https://github.com/omnigent-ai/omnigent/issues/2184) [Bug] Codex plugin skills are exposed with inconsistent names (`plugin |
| 157 | 37 | medium | P1 | P2 ⚑ | -64 | [#2071](https://github.com/omnigent-ai/omnigent/issues/2071) [Bug] web_search never advertised to claude-sdk sessions: unprefixed m |
| 158 | 37 | medium | P2 | P2 | +77 | [#2062](https://github.com/omnigent-ai/omnigent/issues/2062) [Bug] claude-native: per-session model override silently lost when wra |
| 159 | 37 | medium | P1 | P2 ⚑ | -52 | [#1831](https://github.com/omnigent-ai/omnigent/issues/1831) claude-native workers ignore executor.model pin and per-dispatch args. |
| 160 | 37 | medium | P2 | P2 | +94 | [#1789](https://github.com/omnigent-ai/omnigent/issues/1789) Feature: Canvas — agent-authored artifact panel (#2) |
| 161 | 37 | medium | P1 | P2 ⚑ | -51 | [#1781](https://github.com/omnigent-ai/omnigent/issues/1781) codex harness: ambient DATABRICKS_BEARER/DATABRICKS_TOKEN overrides pr |
| 162 | 37 | medium | P2 | P2 | +107 | [#1594](https://github.com/omnigent-ai/omnigent/issues/1594) Server-side idempotency for external_conversation_item (safe dedup on  |
| 163 | 37 | medium | P2 | P2 | +118 | [#1230](https://github.com/omnigent-ai/omnigent/issues/1230) [Feature] Migrate remaining native forwarders to the shared post_sessi |
| 164 | 37 | medium | P1 | P2 ⚑ | -45 | [#1128](https://github.com/omnigent-ai/omnigent/issues/1128) [Bug] Claude SDK Appears to Use Opus Instead of Selected Model |
| 165 | 37 | medium | P2 | P2 | +139 | [#890](https://github.com/omnigent-ai/omnigent/issues/890) [Bug] omnigent setup fails with npm EACCES when installing the Claude  |
| 166 | 37 | medium | P1 | P2 ⚑ | -41 | [#668](https://github.com/omnigent-ai/omnigent/issues/668) [Bug] BUG？omni claude times out (60s) on macOS with native Claude Code |
| 167 | 37 | medium | P2 | P2 | +150 | [#548](https://github.com/omnigent-ai/omnigent/issues/548) Recommend missing dependency install suggestions more gracefully in UI |
| 168 | 37 | medium | P1 | P2 ⚑ | -38 | [#241](https://github.com/omnigent-ai/omnigent/issues/241) pi harness: GPT and Gemini dispatches 404 on the Databricks ucode gate |
| 169 | 37 | medium | P3 | P2 ⚑ | +178 | [#147](https://github.com/omnigent-ai/omnigent/issues/147) Tracking: gradual decomposition of monolith modules (cli.py 9.1KLOC, c |
| 170 | 37 | medium | P1 | P2 ⚑ | -50 | [#1113](https://github.com/omnigent-ai/omnigent/issues/1113) Native sub-agent/runner failures surface as bare "failed" with no reas |
| 171 | 36 | medium | P2 | P2 | +11 | [#3083](https://github.com/omnigent-ai/omnigent/issues/3083) [Bug] Cursor sessions launched from Omnigent Web is losing MCPs |
| 172 | 36 | medium | P1 | P2 ⚑ | -141 | [#3424](https://github.com/omnigent-ai/omnigent/issues/3424) [Bug] Per-request pool checkout + pre-ping overhead: ~11 checkouts/req |
| 173 | 36 | medium | none | P2 | +178 | [#3408](https://github.com/omnigent-ai/omnigent/issues/3408) [Bug] Mac app start locally fails with no such command start |
| 174 | 36 | medium | P2 | P2 | -5 | [#3250](https://github.com/omnigent-ai/omnigent/issues/3250) flaky e2e_ui: test_scheduled_task_create_edit_modal_and_time_picker ti |
| 175 | 36 | medium | P1 | P2 ⚑ | -125 | [#3004](https://github.com/omnigent-ai/omnigent/issues/3004) [Performance] Every streamed event re-loads conversation + ACL: 16 que |
| 176 | 36 | medium | P1 | P2 ⚑ | -125 | [#3003](https://github.com/omnigent-ai/omnigent/issues/3003) [Performance] Policy engine rebuilt per evaluation: 32 queries + two f |
| 177 | 36 | medium | P2 | P2 | +20 | [#2849](https://github.com/omnigent-ai/omnigent/issues/2849) [Performance] Session switch re-runs a full eager transcript backfill  |
| 178 | 36 | medium | P2 | P2 | +32 | [#2703](https://github.com/omnigent-ai/omnigent/issues/2703) Runner re-parses agent-bundle YAML per session with pure-Python SafeLo |
| 179 | 36 | medium | P1 | P2 ⚑ | -113 | [#2592](https://github.com/omnigent-ai/omnigent/issues/2592) [Bug] omni update wipes extras installs: VCS reinstall spec rebuilt fr |
| 180 | 36 | medium | P2 | P2 | +33 | [#2558](https://github.com/omnigent-ai/omnigent/issues/2558) Distribution / Installation / Enterprise Readiness |
| 181 | 34 | medium | P1 | P2 ⚑ | -72 | [#1794](https://github.com/omnigent-ai/omnigent/issues/1794) Bundled Polly: claude-sdk brain "Not logged in" + runaway spawn loop o |
| 182 | 34 | medium | P2 | P2 | +76 | [#1724](https://github.com/omnigent-ai/omnigent/issues/1724) codex-native harness times out on WSL2 ("Codex TUI never started a thr |
| 183 | 34 | medium | P1 | P2 ⚑ | -72 | [#1694](https://github.com/omnigent-ai/omnigent/issues/1694) Reliability: parallel code-fix missions fail silently (5s tmux timeout |
| 184 | 34 | medium | P1 | P2 ⚑ | -69 | [#1533](https://github.com/omnigent-ai/omnigent/issues/1533) Context-occupancy meter (context_tokens) freezes on failed turns — onl |
| 185 | 34 | medium | P2 | P2 | +143 | [#152](https://github.com/omnigent-ai/omnigent/issues/152) Harness availability is reported from binary presence, not from config |
| 186 | 33 | medium | P1 | P2 ⚑ | -181 | [#3982](https://github.com/omnigent-ai/omnigent/issues/3982) [Bug] electron-build.yml pnpm filter matches no package: desktop packa |
| 187 | 33 | medium | P1 | P2 ⚑ | -181 | [#3981](https://github.com/omnigent-ai/omnigent/issues/3981) [Bug] Desktop: Workspace rail resize is unusable on the Browser tab; a |
| 188 | 33 | medium | P1 | P2 ⚑ | -179 | [#3967](https://github.com/omnigent-ai/omnigent/issues/3967) Daemon registry records and host identity should be scoped to the data |
| 189 | 33 | medium | P1 | P2 ⚑ | -178 | [#3951](https://github.com/omnigent-ai/omnigent/issues/3951) The runner-wide agent spec cache can publish a superseded tool spec |
| 190 | 33 | medium | P1 | P2 ⚑ | -178 | [#3949](https://github.com/omnigent-ai/omnigent/issues/3949) Session reset does not fence in-flight terminal publication |
| 191 | 33 | medium | P2 | P2 | -48 | [#3861](https://github.com/omnigent-ai/omnigent/issues/3861) [Bug] omni host status renders URLs so terminals link the whole status |
| 192 | 33 | medium | P3 | P2 ⚑ | +144 | [#3733](https://github.com/omnigent-ai/omnigent/issues/3733) [Bug] Android: hardcoded 25px switcher height makes the chat scroll-fa |
| 193 | 33 | medium | P2 | P2 | -46 | [#3732](https://github.com/omnigent-ai/omnigent/issues/3732) [Bug] Android: a Display-size change leaves the server-switcher pill's |
| 194 | 33 | medium | P2 | P2 | -43 | [#3586](https://github.com/omnigent-ai/omnigent/issues/3586) [Bug] Android: native server-picker pill overlaps the sidebar header c |
| 195 | 33 | medium | P1 | P2 ⚑ | -171 | [#3578](https://github.com/omnigent-ai/omnigent/issues/3578) [Bug] MacOS Start Locally - "Error: No such command 'start'" |
| 196 | 33 | medium | P2 | P2 | -43 | [#3561](https://github.com/omnigent-ai/omnigent/issues/3561) [Bug] `prompt_policy` never sends `_CLASSIFIER_SCHEMA` to the LLM — st |
| 197 | 33 | medium | P2 | P2 | -17 | [#3127](https://github.com/omnigent-ai/omnigent/issues/3127) Desktop app: closed sub-agents stay in the Agents panel with no 'close |
| 198 | 33 | medium | P2 | P2 | -8 | [#2988](https://github.com/omnigent-ai/omnigent/issues/2988) [Bug] Arrow keys don't work in `omni setup` menus |
| 199 | 32 | medium | P1 | P2 ⚑ | -121 | [#2429](https://github.com/omnigent-ai/omnigent/issues/2429) Server (python -m omnigent.cli server) CPU-spins indefinitely with no  |
| 200 | 32 | medium | P1 | P2 ⚑ | -129 | [#2524](https://github.com/omnigent-ai/omnigent/issues/2524) [Bug] Registering remote host fails |


