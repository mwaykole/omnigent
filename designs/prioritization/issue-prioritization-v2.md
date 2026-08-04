# Issue Prioritization v2 for omnigent

## Goal

Make the open-issue queue **orderable by real severity**, not by a label that
has lost its meaning. Today priority is a single collapsed axis (P1 vs P2 as a
de-facto binary); it neither reflects how bad an issue is nor how many users it
hits, and it doesn't move over time. This proposal keeps the working
[triage pipeline](../issue-triage-proposal.md) and adds: a re-calibrated
priority rubric (severity graded across all buckets, for FRs too), independent
scoring axes (severity × reach × harness-tier × readiness + demand, with
duplicate count as a reach signal), a maintainer-facing ranked view, and
re-gradable severity as the mechanism to nudge ranking over time.

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

- **125 of 207 open *bugs* (60%) are P1-high** (128 open P1 in total, incl. 3
  non-bugs). "Major feature broken, no workaround" cannot describe 60% of bugs
  — P1 is inflated to the point of being noise.
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

**5. Contributor funnel is unused; dedup is now landing.** `good first issue`
is on **0** open issues. Dedup was previously latent (only 5 ever closed as
duplicate), but the dedup labeler in
[#4037](https://github.com/omnigent-ai/omnigent/pull/4037) is putting it in
place — link + label, closure gated off by default. That changes the plan: we
should **use duplicate *count* as a scoring signal** (N confirmed dupes = N
reporters hit it = bigger blast radius), not auto-close — see Axis 5.

**6. Most issues are dogfood, by the MAINTAINER file.** Of 360 open issues,
**36 are authored by a name in `.github/MAINTAINER`** → 324 "community." (The
`author_association` field is a poor proxy: it marks 4 as MEMBER that aren't
maintainers, so we key off the MAINTAINER file, which the triage pipeline
already reads.) Even the 324 read like insider reports ("antigravity-native:
TUI-typed turns never mirror"). Reactions are sparse — only **25 of 360** open
issues have any 👍. Implication: **severity must lead the score; external
demand is at most a tiebreak**, or the queue will look empty of signal.

---

## Design

### Axis 1 — Type (unchanged)

`bug` / `enhancement` / `documentation`. Clean today; no change.

### Axis 2 — Re-calibrated priority rubric

Priority stays a 4-bucket label but gets a **rubric that forces separation**,
enforced in the classifier prompt (`.github/triage/config.yaml`) and by a
one-time backfill. The key change: **priority is a function of severity × reach,
graded from content — not a type-default.**

| Priority | Definition (severity × reach — applies to bugs AND FRs) |
|---|---|
| **P0-critical** | Security/policy/sandbox bypass, data loss, or all-users-down. Rare by construction. |
| **P1-high** | High severity (bug: crash / hang / permanent breakage, no workaround. FR: a capability whose *absence* blocks a common workflow) **AND** broad reach (default config, all/most users, or a tier-1 harness). Not "a thing I care about." |
| **P2-medium** | Real bug with a workaround, OR a substantive capability/feature with a moderate reach. |
| **P3-low** | Genuinely minor: cosmetic, polish, trivial convenience, narrow nice-to-have — bug or FR. |

**FRs are graded, not defaulted.** The old prompt defaulted every FR to P2;
that's the "all FRs are equal" trap. An FR gets P1 when its *absence* is a
high-severity, broad-reach gap (e.g. [#16](https://github.com/omnigent-ai/omnigent/issues/16)
native Windows — a whole platform can't run; [#2125](https://github.com/omnigent-ai/omnigent/issues/2125)
multi-host git creds — blocks the common self-hoster setup), and P3 when it's a
narrow nice-to-have. Bug-vs-FR is the *type* axis; it does not cap priority.
(Practically, FR reach is still usually narrower than a crash's, so most FRs
land P2/P3 — but by grading, not by rule.)

Calibration guardrail added to the prompt: **"P1 is a scarcity signal. If more
than ~20% of open bugs are P1, you are over-grading. A bug affecting one harness
on one platform with a workaround is P2, not P1."**

#### How regrading works

Regrading maps an issue to a priority *bucket* from `severity × reach` — a
pure label change, independent of the score. It runs in two situations:

1. **One-time backfill.** Re-run the classifier over the existing open issues
   once, so the backlog reflects the new rubric on day one. This is a labels-only
   pass — same tool-less classifier, same trusted label-application steps as
   [Stage 2 triage](../issue-triage-proposal.md); nothing new to build.
2. **Ongoing, on demand.** A maintainer who disagrees just changes the label
   (P2 → P1, or the reverse). That *is* the bump mechanism — no separate pin
   lever (see "Ongoing adjustment"). The scheduled re-score reads the updated
   label the next time it runs.

The mapping is mechanical once severity and reach are graded:

| Graded severity | + reach | → priority |
|---|---|---|
| critical (security / data-loss / all-users-down) | any | **P0** |
| high (crash / hang / no-workaround; FR: blocks common workflow) | broad / normal | **P1** |
| high | single-platform | **P2** |
| medium | broad | **P1** |
| medium | normal / narrow | **P2** |
| low / narrow FR | — | **P3** |

**Backfill preview** (`score_prototype.py --regrade`, regex grader over the 360
open issues — the production backfill uses the LLM grader):

| Priority | Now | Regraded |
|---|---|---|
| P0-critical | 3 | 8 |
| **P1-high** | **128** | **65** |
| P2-medium | 203 | 273 |
| P3-low | 15 | 14 |
| (no priority) | 11 | 0 |

**P1 share of open bugs: 60% → 25%** — the inflation drained, the P1/P2 binary
un-collapsed. What moves, and why:

| Change | Count | Example |
|---|---|---|
| P1 → P2 | 87 | #3980 desktop dialog paint-over — medium severity, single-platform (not "all users, no workaround") |
| P2 → P1 | 24 | #3976 headless OAuth2 grant — high-severity FR, broad reach (was defaulted to P2) |
| P2 → P3 | 10 | #3074 OS-native directory picker — narrow nice-to-have FR |
| P3 → P2 | 12 | under-graded items pulled up |
| P2 → P0 | 4 | #659 microvm sandbox backend — security-tier |

*Caveat:* these per-issue moves use the regex grader, so they inherit its known
false positives (e.g. #2057/#2054 "sandbox bypass" FRs wrongly reach P0). Read
the **aggregate shape** (60% → 25%) as the reliable signal and individual rows
as illustrative; the LLM backfill corrects the outliers.

### Axis 3 — Harness tier (new, derived)

Harnesses are not equal in strategic weight. Tier is **derived from the
existing `areas.json` harness areas** (no new hand-labeling):

- **Tier 1** — `claude`, `codex` (flagship; ~38% of harness issues).
- **Tier 2** — `cursor`, `antigravity`, `copilot`, `gemini`/`openai`.
- **Tier 3** — everything else (goose, hermes, kimi, kiro, opencode, pi, qwen).

Tier is a **score multiplier**, and we split the `comp:harnesses` mega-bucket
(41% of open) with **tier labels — `comp:harness-t1` / `-t2` / `-t3`** — rather
than per-harness labels (`comp:harness-claude`, …). Tier labels are more
future-proof: adding a harness or re-tiering one edits `areas.json` (which
already maps each harness area) and re-runs a backfill, without inventing a new
label each time a harness ships. The mapping (area → tier) lives in
`areas.json`, so the tier label and the score multiplier share one source of
truth. Per-harness *filtering* is still available via the area routing if a
maintainer wants it, without a label per harness. (Alternative considered and
rejected in Appendix A.)

### Component taxonomy — which `comp:` labels to add

There are 8 `comp:` labels today, and several are mega-buckets because each
merges multiple `areas.json` areas. The bar for a new label is deliberately
high: **split only when you'd actually filter on it, or when it changes how the
issue is graded** — every split costs new labels + an `areas.json` mapping + a
classifier-allowlist update + a one-time backfill, and the repo has *no
label-sync* by design. By that test:

| Label | Open | Recommendation |
|---|---|---|
| `comp:harnesses` | 148 | Split by **tier** — `-t1/-t2/-t3` (Axis 3). |
| `comp:runner` | 109 | **Carve out `comp:sandbox`** (~29 of the 109 are sandbox/isolation: bwrap/seatbelt/egress). Distinct discipline, security-grade severity, home of the top P0 (#3557). Makes the security surface *filterable*, not just score-boosted. |
| `comp:web-ui` | 99 | **Add `comp:mobile`** (~23: iOS/Android OIDC, renderer death, iPad layout) — a different failure domain and reporter set from browser-web (~55). Defer `comp:desktop`/electron (~11): borderline, revisit if it grows. |
| `comp:server` | 135 | **Leave as-is.** Its sub-buckets (host 55, db 36, sdk 65) overlap heavily on the same session/API issues; splitting would just multi-label without aiding prioritization. |
| `comp:tui` · `comp:infra` · `comp:repr` · `comp:policies` | 40 / 34 / 13 / 21 | **Leave as-is** — small enough to prioritize within; splitting adds labels without payoff. `comp:policies` already isolates the guardrail surface. |

Net new labels: **`comp:sandbox`** and **`comp:mobile`** (plus the three harness
tier labels). Everything else stays. `sandbox` and `policies` remain
first-class (see Sandbox / security below); we're promoting `sandbox` from an
area that collapses into `comp:runner` to its own label, not inventing a new
concept.

Naming note: `comp:sandbox` (narrow) is preferred over a broad `comp:security`
umbrella — "security" would pull in the 120 credential/auth issues that mostly
belong to `comp:server`/onboarding, re-creating a mega-bucket. Sandbox/policy
*bypass* severity is handled by the rubric (Axis 2), not by an umbrella label.

### Axis 4 — The composite score (the ordering primitive)

```
base  = severity_weight              # LLM-graded from content (P0/P1/P2/P3-ish, 0–100)
      × reach_multiplier             # all-users/default 1.5 · normal 1.0 · single-platform 0.9
      × harness_tier_multiplier      # T1 1.4 · T2 1.1 · T3 0.9 · non-harness 1.0
      × dup_reach                    # +15% per confirmed duplicate, capped +50% (Axis 5)
      × readiness                    # ready-to-work 1.1 · normal 1.0 · needs-info 0.85 (Axis 6)

score = apply_demand(base, type)     # type-dependent — see "Community demand" below
      × recency_factor               # 1.0 fresh; gentle decay past ~30d (tunable)
```

Every weight is a named constant in one place. The score is **advisory
ordering** layered on top of the labels; labels stay authoritative for
filtering, the score decides *what to look at first*.

**Worked example — one issue, data points → score.** Take
[#3265](https://github.com/omnigent-ai/omnigent/issues/3265) ("claude-sdk agent
with linux_bwrap dies at spawn"):

| Factor | Value | Why |
|---|---|---|
| severity | 60 (high) | body matches "cannot start" / spawn death — a hard failure, no workaround |
| × reach | × 1.0 | affects the linux_bwrap sandbox config, not literally all users |
| × harness_tier | × 1.4 | title says `claude-sdk` → tier-1 |
| × dup_reach | × 1.0 | no confirmed duplicates (yet) |
| × readiness | × 1.1 | 400+ char body with repro steps → ready to work |
| = base | **92.4** | |
| × demand (bug) | + 0 | 0 reactions; bugs get only the additive tiebreak |
| × recency | × 1.0 | 10 days old, under the 30-day decay threshold |
| **= score** | **≈ 92** | ranks **#3** of 360 (was #37 by priority label) |

Contrast a vague, low-tier ticket: severity 30 (medium) × reach 0.9
(single-platform) × tier 0.9 (tier-3 harness) × readiness 1.0 ≈ **24** — an
order of magnitude lower, so it sits deep in the queue. That gap is the point:
the score turns four cheap data points into an order.

**Why severity is LLM-graded, not label-derived:** the dry-run
(`score_prototype.py`) grades severity with regex for reproducibility, and it
demonstrates *why regex isn't enough in production* — "sandbox **bypass**" in an
FR title falsely scored two Codex-mode FRs (#2057, #2054) as critical, and a bot
"Code Audit" issue (#61) too. The production grader is the triage classifier,
which reads full content and already runs per issue at zero extra cost.

### Community demand — used, but type-dependent and bounded

Should 👍 feed the score? **Yes, but bounded** — the reaction distribution
forces it. 93% of open issues (335/360) have zero reactions; the 51 total skew
hard to FRs (9 of the top 10 reacted are FRs) and are almost all external. So
reactions are a **demand** signal (a wanted capability), not a **severity** one.
The model reflects that:

- **Type-dependent.** FRs: a bounded *multiplier* (up to +60%), so a well-liked
  FR climbs. Bugs: a small additive *tiebreak* (≤15 pts), so a 0-reaction crash
  still outranks a lightly-liked cosmetic FR. Severity always leads for bugs.
- **Log-scaled and capped** (`log1p` + hard cap), so one popular FR can't swamp
  severity. **Comments excluded** — here they're mostly repro back-and-forth, a
  sign a bug is *harder*, not more wanted.

Without these bounds, a 93%-zero, FR-skewed signal would tilt a dogfood-heavy
backlog toward features — the exact failure the type-split guards against.

### Axis 5 — Duplicate reach

The dedup labeler ([#4037](https://github.com/omnigent-ai/omnigent/pull/4037))
links and labels duplicates without auto-closing. That gives us a reach signal
for free: **N confirmed duplicates means N reporters hit the same issue.**
`dup_reach` bumps the score +15% per confirmed duplicate, capped at +50%, so a
frequently-reduplicated bug rises without letting a pile-on dominate severity.
The scoring job reads the dup count from the labeler's linked issues; the
dry-run stubs it (`duplicate_count`, default 0) since the snapshot JSON doesn't
carry dup links.

### Axis 6 — Readiness

A ticket you can *start on now* — repro steps, a real body — is worth surfacing
above an equally-severe but vague one. `readiness` is a small multiplier: 1.1
for a bug with a repro section and a ≥400-char body (or any substantive FR),
0.85 for anything labeled `needs-info` (explicitly blocked on the reporter),
1.0 otherwise. It's deliberately gentle — it breaks near-ties, it never
overrides severity. On the current backlog it bumps 272 issues, penalizes only
the 4 `needs-info` ones (today `needs-info` is applied to **0** open bugs, so
this also gives the classifier a reason to use it). Cheap to compute from
existing fields; the production grader can set it directly.

### Ongoing adjustment — re-grade severity, don't add a pin lever

Prioritization is not a one-shot classification, but the adjustment lever is
just **re-grading severity** — the same field the classifier already sets:

1. **Periodic re-score.** A scheduled (weekly) job recomputes the score and
   posts/updates a single **ranked view** (a pinned issue or generated
   `PRIORITY-QUEUE.md`), reflecting demand/age/dup changes without re-triaging.
   No LLM call needed if severity is cached as a field at triage time.
2. **Re-grade severity to bump.** To move an issue, a maintainer changes its
   label (P2 → P1) — the one knob they already use. There is deliberately no
   separate `pin:high`/`pin:low`: it would mean the same thing as changing
   severity but out of band from it. The real fix for a mis-ranked issue (e.g.
   #2125) is upstream — grade severity honestly (Axis 2); the score reads
   severity, so fixing severity fixes the order.

#### Maintainer guide — hand-correcting the ranking

The goal is a ranking good enough that **hand-correction is the exception, not
the process** — a working target is **≤10% of issues touched**. If you're
correcting more than that, the fix isn't more editing, it's tuning the prompt or
weights (below). Two properties make correction cheap and safe:

- **Corrections are sticky.** Triage runs `on: issues [opened]` only — it never
  re-fires on edits, so a label you change by hand is never overwritten by the
  bot. (The weekly re-score only *reads* labels; it doesn't re-grade.)
- **One knob.** You change the **priority label** (the field the classifier
  emits). The score is a pure function of it plus mechanical factors — no
  separate override to learn.

**When to correct** — reach for it only when the *grade* is wrong, not when you
merely disagree with a neighbor in a tie:

| Symptom | Action |
|---|---|
| Grader misread severity (a real P1 sitting at P2, or vice versa) | Change the priority label. Done — it sticks. |
| Right severity, wrong reach (e.g. "affects all users" missed) | Same: bump the label; reach feeds severity's bucket. |
| A security/sandbox/policy **bypass** graded as ordinary | Set `P0-critical` — bypass is top severity regardless of reach (Axis 2). |
| Blocked on the reporter | Add `needs-info` (drops readiness ×0.85); don't fight the score. |
| You just prefer a different order *within the same grade* | **Don't.** Ties are arbitrary by design; re-grading here is noise. |

**When NOT to correct — fix the system instead.** A hand-edit fixes one issue; a
prompt fix fixes the class. Escalate from editing to tuning when:

- The **same misgrade recurs** (e.g. every "sandbox bypass" *feature request*
  gets graded critical — the #2057/#2054 class). Fix the classifier prompt in
  `.github/triage/config.yaml`, not the issues one by one.
- You cross the **~10% correction rate** in a re-score cycle. That's the signal
  the weights (tier multipliers, demand cap, readiness) or the rubric need
  tuning — re-run `score_prototype.py` against the new weights and eyeball the
  before→after before shipping.
- The **`Re-grade rate` metric** (below) trends up. It's the quantitative
  version of the same signal.

**What this is not:** there is no per-issue score override, no manual score
number, no pin. Everything flows through the priority label so the ranking stays
explainable — anyone can re-derive an issue's position from its label + factors,
and there's no hidden hand-tuning to reverse-engineer later.

---

## Dry-run: before → after (methodical, on real issues)

`designs/prioritization/score_prototype.py` reads a snapshot of all open issues
and prints **current-priority ordering vs composite-score ordering**, with a
rank delta per issue, so we tune weights against real test cases. (Pass
`--regrade` for the priority-*label* backfill preview shown in Axis 2 instead of
the score ranking.)

**Is severity re-graded in these examples?** Yes — the dry-run ignores the
existing priority label entirely and *re-grades severity from content* (regex
stand-in for the LLM), so the "After" column is a fresh grade, not a re-sort of
the old labels. The regex grade distribution across the 360 open issues:

| Grade | critical | high | medium | low | (FR default) |
|---|---|---|---|---|---|
| Count | 8 | 85 | 183 | 3 | 81 |

That shape is itself a sanity check: **critical is scarce (8)**, most bugs are
medium, and `low` is under-detected by regex (only 3) — a real grader would find
more genuinely-minor issues. It's the inverse of today's inflated-P1 label
distribution, which is the goal.

Selected results (360 open issues; rank out of 360, lower = higher priority):

**Severity surfaces real bugs the label buried:**

| Issue | Before | After | Δ | Note |
|---|---|---|---|---|
| #3557 policy-gate bypass (P0) | 1 | 6 | −5 | Real P0 stays near top ✅ |
| #3265 claude-sdk bwrap spawn death (P1) | 37 | 3 | +34 | High-sev, tier-1 harness, has repro ✅ |
| #3270 sub-agent sessions absent (P1) | 35 | 7 | +28 | ✅ |
| #2421 codex MCP bridge child leak (P1) | 80 | 27 | +53 | Resource leak, tier-1 ✅ |
| #2454 unbounded ~/.omnigent growth (P1) | 72 | 26 | +46 | ✅ |

**Community demand lifts wanted FRs — bounded, so bugs stay on top:**

| Issue | 👍 | Before | After | Δ | Note |
|---|---|---|---|---|---|
| #1021 GitHub Copilot as provider (FR) | 10 | 299 | 92 | +207 | Most-wanted FR climbs; demand alone pushed it up ✅ |
| #16 native Windows support (FR) | 6 | 334 | 32 | +302 | High demand + graded P1 (whole platform) ✅ |
| #888 side-by-side multi-session (FR) | 2 | 305 | 30 | +275 | ✅ |

**Dry-run limits — the evidence that severity must be LLM-graded, not regex:**

| Issue | Before | After | Note |
|---|---|---|---|
| #2057 / #2054 Codex-mode FRs | 236/238 | 1/2 | **False positive** — "sandbox bypass" in the FR body tripped the critical regex. An LLM reads that it's *proposing* a mode, not reporting a bypass. |
| #61 bot "Code Audit" (P3) | 349 | 19 | **False positive** — a bot audit issue mentioning "security". LLM grader avoids. |
| #2125 multi-host git creds (P2, FR) | 232 | 8 | **Lucky match** — the body literally says "your GitHub PAT is offered to the self-hosted remote", so the regex hits a credential-leak pattern and scores it critical. Right answer, wrong reason: it's an exact-phrase fluke, not comprehension. An LLM would grade it high because it *understands* the credential-crossing risk. |

#2125 makes the point either way: the earlier draft's regex *missed* it (false
negative); a one-word regex tweak now *over-*hits it. Both are the same lesson —
regex can't reason about severity, so production must grade with the LLM.

**Takeaways for the real build:**
- The score *mechanics* order the queue far better than the priority label.
- The severity *grader* must be the LLM, not regex — the dry-run's false
  positives *and* its lucky matches are both the proof.
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

### Sandbox / security deserves its own treatment

You flagged sandboxing as its own category — the data agrees. Across open
issues: **63 mention sandbox** (bwrap/seatbelt/egress), **70 policy/guardrail**,
**120 credential/secret**. The top P0
([#3557](https://github.com/omnigent-ai/omnigent/issues/3557)) is a
shell-surface policy-gate *bypass*; #2125 is a credential-crossing risk. These
aren't ordinary bugs — a sandbox escape or policy bypass is a **security
severity**, not a functional one.

Two concrete changes:

- **Component:** promote `sandbox` to its own `comp:sandbox` label (today it
  collapses into `comp:runner`); `policies` already has `comp:policies`. See
  "Component taxonomy" above for the full rationale.
- **Severity:** the rubric's P0 row explicitly names "security/policy/sandbox
  bypass," and the grader should treat *escape / bypass / credential-crossing*
  as top-tier severity regardless of reach — a one-user sandbox escape is still
  P0. This is the one place reach does **not** gate priority.

---

## Rollout

1. **Prompt re-calibration** (`.github/triage/config.yaml`) — new priority
   rubric (grade FRs across buckets; security/sandbox → P0) + the "P1 scarcity"
   guardrail + emit `severity` and `readiness` fields. Low risk, affects new
   issues immediately.
2. **Component labels** — add `comp:harness-t1/-t2/-t3` (map each harness area
   in `areas.json` to a tier), plus `comp:sandbox` and `comp:mobile`; update the
   classifier allowlist and backfill existing `comp:harnesses` / `comp:runner` /
   `comp:web-ui` issues into the new labels. See "Component taxonomy."
3. **Template fields** — add Harness / Platform / Impact dropdowns.
4. **Scoring job** — productionize `score_prototype.py` into a scheduled action
   that reads LLM-graded severity + readiness + dup count and publishes the
   ranked view.
5. **One-time backfill (regrade)** — re-run the classifier over open issues to
   relabel under the new rubric (see "How regrading works"); preview with
   `score_prototype.py --regrade`. Target: P1 back under ~20% of open bugs
   (regex preview lands it at 25%; the LLM pass should do better).
6. **Consume dedup output** — once [#4037](https://github.com/omnigent-ai/omnigent/pull/4037)
   lands, feed duplicate count into `dup_reach`; wire the unused `good first
   issue` funnel.

## Metrics

- **P1 share of open bugs** — target < 20% (today 60%).
- **Priority age separation** — P1 median age should drop well below P2's
  (today they're equal — the tell that priority is ignored).
- **Prioritization efficiency** — of the k issues actually resolved in a period,
  what fraction of the *achievable* score did we capture? Compute
  `sum(score of the k resolved) / sum(score of the top-k by score)`. A ratio
  near 1.0 means the team is working the highest-scored issues; a low ratio
  means high-score issues are being skipped (either the score is wrong, or
  attention is going elsewhere). This is the single best signal that the score
  is *ordering real work*, not just producing a list.
- **Re-grade rate** — how often maintainers change a severity/priority label
  after triage (high = the classifier's grading needs tuning).

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

Generated from today's snapshot with `score_prototype.py --markdown 200`
(regex severity grader — the same stand-in used throughout; production uses
the LLM grader). Columns: **Score** = composite score; **Sev** = re-graded
severity; **Now** = current priority label; **Δrank** = movement vs the
current priority-label ordering (positive = moved up).

**Illustrative, not actionable.** This is the *mechanism* running on a
deliberately-weak grader, so its own failures are visible on purpose: ranks 1–2
(#2057/#2054) are FRs that merely *mention* "sandbox bypass" and are graded
critical — they sit above the real P0 (#3557, rank 6), so **the very top is
backwards**; #61 (rank 19) is a *bot* audit issue. That's the doc's thesis made
concrete: regex can't grade severity. The scaffold is sound — strip those
artifacts and the genuine tier-1 bugs (#3265, #3557, #3270, #3180, #2373)
cluster correctly in the top 15. Scores also *tie* in coarse bands (nine issues
share 99/92), so within-band order is arbitrary — read this as ~8 tiers, not 200
ranks. With the LLM grader plus ≤10% hand-correction (see the maintainer guide),
this is the shape the production ranking takes.

| # | Score | Sev | Now | Δrank | Issue |
|--:|--:|---|---|--:|---|
| 1 | 154 | critical | P2-medium | +235 | [#2057](https://github.com/omnigent-ai/omnigent/issues/2057) [Feature] Add Codex Auto mode using auto_review instead of jumping to  |
| 2 | 154 | critical | P2-medium | +236 | [#2054](https://github.com/omnigent-ai/omnigent/issues/2054) [Feature] Remove duplicate Codex Full access mode and keep Sandbox Byp |
| 3 | 126 | high | P1-high | +34 | [#3265](https://github.com/omnigent-ai/omnigent/issues/3265) claude-sdk agent with linux_bwrap dies at spawn on a runtime bwrap bin |
| 4 | 115 | high | P2-medium | +236 | [#2038](https://github.com/omnigent-ai/omnigent/issues/2038) [Feature] No way to deregister/delete an external self-registered host |
| 5 | 110 | critical | P1-high | -1 | [#3983](https://github.com/omnigent-ai/omnigent/issues/3983) [Bug] Smart-routed turns render out of order: reply streams above the  |
| 6 | 110 | critical | P0-critical | -5 | [#3557](https://github.com/omnigent-ai/omnigent/issues/3557) [Bug] Shell-surface policy gates are bypassed by option-taking command |
| 7 | 110 | critical | P1-high | +28 | [#3270](https://github.com/omnigent-ai/omnigent/issues/3270) [Bug] sys_session_create children are absent from both sys_session_lis |
| 8 | 104 | critical | P2-medium | +224 | [#2125](https://github.com/omnigent-ai/omnigent/issues/2125) [Feature] Multi-host git credentials for managed sandboxes (GitHub + s |
| 9 | 99 | high | P2-medium | +127 | [#3976](https://github.com/omnigent-ai/omnigent/issues/3976) [Feature] OAuth2 client-credentials grant so a headless process can au |
| 10 | 99 | high | P2-medium | +154 | [#3363](https://github.com/omnigent-ai/omnigent/issues/3363) [Feature] Per-project custom instructions (project-scoped context) |
| 11 | 99 | high | P2-medium | +166 | [#3164](https://github.com/omnigent-ai/omnigent/issues/3164) [Feature] Optional runtimeClassName on the kubernetes sandbox provider |
| 12 | 95 | high | P2-medium | +264 | [#1388](https://github.com/omnigent-ai/omnigent/issues/1388) Make agents a first-class CRUD entity with a dedicated sidebar UI (dec |
| 13 | 92 | high | P1-high | +28 | [#3180](https://github.com/omnigent-ai/omnigent/issues/3180) codex-native: runner never exits on idle timeout — cancelled delta-coa |
| 14 | 92 | high | P1-high | +68 | [#2373](https://github.com/omnigent-ai/omnigent/issues/2373) [Bug] claude-native: pasted web-UI message loses its Enter, stuck draf |
| 15 | 92 | high | P1-high | +79 | [#2060](https://github.com/omnigent-ai/omnigent/issues/2060) [Bug] claude-native: first web-UI message silently dropped when Claude |
| 16 | 91 | high | P1-high | +87 | [#1898](https://github.com/omnigent-ai/omnigent/issues/1898) [Bug] codex-native: cancelling a task awaiting flush() poisons the del |
| 17 | 91 | critical | P2-medium | +298 | [#659](https://github.com/omnigent-ai/omnigent/issues/659) [Feature] add a microvm backend for sandbox |
| 18 | 90 | high | P1-high | +34 | [#3001](https://github.com/omnigent-ai/omnigent/issues/3001) [Performance] GET /v1/sessions pre-fetches every accessible conversati |
| 19 | 90 | critical | P3-low | +330 | [#61](https://github.com/omnigent-ai/omnigent/issues/61) 🤖 Code Audit: 21 potential issue(s) found |
| 20 | 85 | high | P2-medium | +296 | [#654](https://github.com/omnigent-ai/omnigent/issues/654) [Bug] Streaming with codex is hanging and paragraphs are not split. |
| 21 | 84 | high | P1-high | +106 | [#542](https://github.com/omnigent-ai/omnigent/issues/542) [Bug] AttributeError: 'SubprocessCLITransport' object has no attribute |
| 22 | 84 | high | P2-medium | +132 | [#3558](https://github.com/omnigent-ai/omnigent/issues/3558) claude-sdk: cached client does not rebuild on framework-instruction ch |
| 23 | 84 | high | P1-high | +30 | [#3000](https://github.com/omnigent-ai/omnigent/issues/3000) claude-native transcript forwarder polls at 4 Hz per session with no i |
| 24 | 84 | high | P1-high | +38 | [#2748](https://github.com/omnigent-ai/omnigent/issues/2748) Runner idle-shutdown deadlocks forever: codex-forwarder close()/flush( |
| 25 | 84 | high | P1-high | +42 | [#2575](https://github.com/omnigent-ai/omnigent/issues/2575) pi-native: non-Claude Databricks models (GLM, Gemini, …) hang — provid |
| 26 | 84 | high | P1-high | +46 | [#2454](https://github.com/omnigent-ai/omnigent/issues/2454) [Bug] Unbounded ~/.omnigent growth: per-session native-harness dirs ar |
| 27 | 84 | high | P1-high | +53 | [#2421](https://github.com/omnigent-ai/omnigent/issues/2421) [Bug] codex app-server + MCP bridge children leak on ANY unclean runne |
| 28 | 84 | high | P2-medium | +267 | [#1051](https://github.com/omnigent-ai/omnigent/issues/1051) [Feature] Forward OTel exporter knobs to executor subprocess env |
| 29 | 81 | high | P2-medium | +108 | [#3970](https://github.com/omnigent-ai/omnigent/issues/3970) pi-native: every turn fails with "Pi model error: 401 Invalid Token" w |
| 30 | 77 | high | P2-medium | +275 | [#888](https://github.com/omnigent-ai/omnigent/issues/888) [Feature] Side-by-side multi-session view |
| 31 | 70 | high | P1-high | +7 | [#3261](https://github.com/omnigent-ai/omnigent/issues/3261) [Crash] AttributeError: module 'os' has no attribute 'WNOHANG' |
| 32 | 69 | high | P2-medium | +302 | [#16](https://github.com/omnigent-ai/omnigent/issues/16) Is native Windows support in scope, or should docs recommend WSL2? |
| 33 | 68 | high | P2-medium | +296 | [#151](https://github.com/omnigent-ai/omnigent/issues/151) Native claude_code worker hangs on the one-time Bypass Permissions acc |
| 34 | 66 | high | P2-medium | +112 | [#3750](https://github.com/omnigent-ai/omnigent/issues/3750) [Crash] PermissionError: [Errno 1] Operation not permitted |
| 35 | 66 | high | P1-high | -7 | [#3482](https://github.com/omnigent-ai/omnigent/issues/3482) [Crash] ServerError: |
| 36 | 66 | high | P1-high | -6 | [#3458](https://github.com/omnigent-ai/omnigent/issues/3458) session-updates stream crashes with KeyError when a client watches a c |
| 37 | 66 | high | P1-high | -5 | [#3359](https://github.com/omnigent-ai/omnigent/issues/3359) [Crash] ModuleNotFoundError: No module named 'termios' |
| 38 | 66 | high | P2-medium | +129 | [#3271](https://github.com/omnigent-ai/omnigent/issues/3271) [Feature] Expose per-session context size + last-turn timestamp to age |
| 39 | 66 | high | P1-high | 0 | [#3251](https://github.com/omnigent-ai/omnigent/issues/3251) [Crash] ModuleNotFoundError: No module named 'termios' |
| 40 | 66 | high | P2-medium | +133 | [#3231](https://github.com/omnigent-ai/omnigent/issues/3231) [Crash] OmnigentError: {'error_code': 403, 'message': 'Invalid access  |
| 41 | 66 | high | P1-high | +4 | [#3052](https://github.com/omnigent-ai/omnigent/issues/3052) [Crash] ModuleNotFoundError: No module named 'termios' |
| 42 | 66 | high | P1-high | +4 | [#3023](https://github.com/omnigent-ai/omnigent/issues/3023) [Crash] ModuleNotFoundError: No module named 'termios' |
| 43 | 66 | high | P1-high | +11 | [#2993](https://github.com/omnigent-ai/omnigent/issues/2993) [Crash] ModuleNotFoundError: No module named 'termios' |
| 44 | 66 | high | P3-low | +293 | [#2887](https://github.com/omnigent-ai/omnigent/issues/2887) [Bug] web/package-lock.json is out of sync with package.json; plain `n |
| 45 | 66 | high | P1-high | +23 | [#2559](https://github.com/omnigent-ai/omnigent/issues/2559) Conversation bricked: Page fails to load when opening markdown file af |
| 46 | 66 | high | P0-critical | -44 | [#2355](https://github.com/omnigent-ai/omnigent/issues/2355) [Bug] workspace_id PK-widening migration crashes on populated Postgres |
| 47 | 66 | high | P3-low | +294 | [#2224](https://github.com/omnigent-ai/omnigent/issues/2224) [Bug] get_client model-change check fails for harness="any" |
| 48 | 66 | high | P1-high | +50 | [#1985](https://github.com/omnigent-ai/omnigent/issues/1985) Headless `omnigent run -p` intermittently hangs forever despite the tu |
| 49 | 65 | high | P2-medium | +159 | [#2714](https://github.com/omnigent-ai/omnigent/issues/2714) Upgrade openai-agents and remove the temporary openai<2.45 cap |
| 50 | 65 | high | P1-high | +40 | [#2245](https://github.com/omnigent-ai/omnigent/issues/2245) [Bug] openai-agents harness turn wedges permanently after policy-verdi |
| 51 | 65 | high | P2-medium | +193 | [#1907](https://github.com/omnigent-ai/omnigent/issues/1907) Sub-agent model_override triggers an unnecessary first-turn harness re |
| 52 | 65 | high | P1-high | +52 | [#1888](https://github.com/omnigent-ai/omnigent/issues/1888) ansi-to-react default import resolves to the CJS exports object under  |
| 53 | 65 | high | P2-medium | +200 | [#1804](https://github.com/omnigent-ai/omnigent/issues/1804) spec parser crashes with TypeError on a null tools.builtins key (and s |
| 54 | 62 | high | P2-medium | +235 | [#1076](https://github.com/omnigent-ai/omnigent/issues/1076) Runner-layer Tier-2 escalation: release an unresponsive per-conversati |
| 55 | 62 | high | P1-high | +66 | [#1026](https://github.com/omnigent-ai/omnigent/issues/1026) Runner orphans tool callbacks with "no active turn context" after mid- |
| 56 | 60 | high | P1-high | -48 | [#3971](https://github.com/omnigent-ai/omnigent/issues/3971) Host runners inherit the daemon's cwd; a deleted launch dir breaks eve |
| 57 | 60 | high | P1-high | -23 | [#3274](https://github.com/omnigent-ai/omnigent/issues/3274) Sub-agent terminal status rejected with missing_parent_inbox and retri |
| 58 | 60 | high | P2-medium | +114 | [#3235](https://github.com/omnigent-ai/omnigent/issues/3235) Flaky E2E UI: test_scheduled_task_create_edit_modal_and_time_picker[ch |
| 59 | 60 | high | P1-high | -12 | [#3016](https://github.com/omnigent-ai/omnigent/issues/3016) [Bug] A transient session-snapshot failure permanently pins a session  |
| 60 | 60 | high | P1-high | -12 | [#3012](https://github.com/omnigent-ai/omnigent/issues/3012) Hosts authenticated via `omnigent login` permanently 403 on first reco |
| 61 | 60 | high | P2-medium | +157 | [#2428](https://github.com/omnigent-ai/omnigent/issues/2428) sys_session_send to a completed session hangs to ReadTimeout and is si |
| 62 | 60 | high | P1-high | +29 | [#2241](https://github.com/omnigent-ai/omnigent/issues/2241) Flaky on main: test_interrupt_forwards_to_harness_before_cancelling ti |
| 63 | 60 | high | P1-high | +33 | [#2051](https://github.com/omnigent-ai/omnigent/issues/2051) [Bug] sys_session_send(session_id=…) completions never drain to sys_re |
| 64 | 59 | medium | P2-medium | +204 | [#1596](https://github.com/omnigent-ai/omnigent/issues/1596) Native-CLI harness (claude-native/codex-native) as a named agent's own |
| 65 | 59 | high | P1-high | -48 | [#3799](https://github.com/omnigent-ai/omnigent/issues/3799) Android shell cannot sign in to servers behind a front-door auth proxy |
| 66 | 59 | high | P1-high | -46 | [#3730](https://github.com/omnigent-ai/omnigent/issues/3730) [Bug] Android: renderer death terminates the app — OmnigentWebViewClie |
| 67 | 59 | high | P1-high | -45 | [#3701](https://github.com/omnigent-ai/omnigent/issues/3701) [Bug] Desktop app never completes Okta security key / biometric MFA du |
| 68 | 59 | high | P1-high | -35 | [#3299](https://github.com/omnigent-ai/omnigent/issues/3299) [Bug] Harness-credential route times out with a misleading 504 against |
| 69 | 59 | high | P2-medium | +97 | [#3284](https://github.com/omnigent-ai/omnigent/issues/3284) [Crash] DuplicateOptionError: While reading from PosixPath('/Users/*** |
| 70 | 59 | high | P2-medium | +114 | [#3070](https://github.com/omnigent-ai/omnigent/issues/3070) No progress signal on a stuck or interactive harness install |
| 71 | 59 | high | P1-high | -16 | [#2967](https://github.com/omnigent-ai/omnigent/issues/2967) [Bug] A full context window bricks a session with "Prompt is too long" |
| 72 | 59 | high | P2-medium | +144 | [#2480](https://github.com/omnigent-ai/omnigent/issues/2480) [Bug] Postgres-backed local server: bare `No module named 'psycopg'` + |
| 73 | 59 | high | P1-high | +15 | [#2270](https://github.com/omnigent-ai/omnigent/issues/2270) Windows: config list crashes — UnicodeEncodeError on cp1252 (non-UTF8) |
| 74 | 59 | high | P1-high | +15 | [#2269](https://github.com/omnigent-ai/omnigent/issues/2269) Windows: omnigent setup crashes — ModuleNotFoundError: No module named |
| 75 | 59 | high | P1-high | +24 | [#1953](https://github.com/omnigent-ai/omnigent/issues/1953) `omni host` dies permanently when the OIDC session JWT expires — no re |
| 76 | 59 | high | P1-high | +26 | [#1901](https://github.com/omnigent-ai/omnigent/issues/1901) [Bug] kimi/qwen/goose/kiro forwarders blind-retry failed conversation- |
| 77 | 59 | high | P1-high | +28 | [#1881](https://github.com/omnigent-ai/omnigent/issues/1881) [Bug] `omnigent setup` crashes with `ValueError: select() requires at  |
| 78 | 58 | high | P0-critical | -75 | [#1657](https://github.com/omnigent-ai/omnigent/issues/1657) hermes-native forwarder advances last_id per item, dropping a row's la |
| 79 | 58 | high | P1-high | +29 | [#1827](https://github.com/omnigent-ai/omnigent/issues/1827) [Bug] kimi-native: torn UTF-8 wire read crashes the forwarder; supervi |
| 80 | 58 | high | P2-medium | +187 | [#1600](https://github.com/omnigent-ai/omnigent/issues/1600) Epic: 12-feature contribution (one issue + one PR per feature) |
| 81 | 57 | high | P2-medium | +189 | [#1528](https://github.com/omnigent-ai/omnigent/issues/1528) Idle-session lifecycle UX: reap gracefully, resume seamlessly, surface |
| 82 | 57 | high | P1-high | +49 | [#108](https://github.com/omnigent-ai/omnigent/issues/108) Cannot install on Linux aarch64 — cel-expr-python has no aarch64 wheel |
| 83 | 55 | high | P2-medium | +231 | [#678](https://github.com/omnigent-ai/omnigent/issues/678) e2e: sub-agent supervisor routing / named-sub-agent auto-wake flakes ( |
| 84 | 55 | high | P2-medium | +214 | [#1022](https://github.com/omnigent-ai/omnigent/issues/1022) Behind a corporate proxy, the host daemon can't reach the model backen |
| 85 | 54 | high | P2-medium | +59 | [#3798](https://github.com/omnigent-ai/omnigent/issues/3798) Android shell shows the SPA as if signed in while native login runs in |
| 86 | 54 | high | P1-high | -57 | [#3469](https://github.com/omnigent-ai/omnigent/issues/3469) [Bug] Post-completion compaction spiral: merge-commit diff output trig |
| 87 | 54 | high | P1-high | -22 | [#2629](https://github.com/omnigent-ai/omnigent/issues/2629) web_fetch sub-agent spawn fails with unknown harness 'omnigent' — bare |
| 88 | 53 | high | P1-high | -39 | [#3011](https://github.com/omnigent-ai/omnigent/issues/3011) kiro-native harness: interactive sessions never respond with kiro-cli  |
| 89 | 53 | high | P1-high | -33 | [#2920](https://github.com/omnigent-ai/omnigent/issues/2920) Omnigent server fails to start on native Windows: os.getuid() at impor |
| 90 | 53 | high | P1-high | -33 | [#2919](https://github.com/omnigent-ai/omnigent/issues/2919) omni setup crashes on Windows: ModuleNotFoundError: No module named 't |
| 91 | 53 | high | P1-high | -12 | [#2422](https://github.com/omnigent-ai/omnigent/issues/2422) Windows: five chained defects break the documented degraded-mode subse |
| 92 | 53 | medium | P2-medium | +207 | [#1021](https://github.com/omnigent-ai/omnigent/issues/1021) [Feature] GitHub Copilot as provider |
| 93 | 53 | high | P2-medium | +162 | [#1778](https://github.com/omnigent-ai/omnigent/issues/1778) opencode-native forwarder loses session content across SSE reconnects  |
| 94 | 50 | medium | P2-medium | +110 | [#2744](https://github.com/omnigent-ai/omnigent/issues/2744) [Bug] codex-native: custom agents time out at launch — native provider |
| 95 | 49 | high | P1-high | +33 | [#523](https://github.com/omnigent-ai/omnigent/issues/523) REPL pexpect e2e tests starve on boot under full shard load (60s _wait |
| 96 | 49 | high | P2-medium | +214 | [#762](https://github.com/omnigent-ai/omnigent/issues/762) [Bug] sub agent terminal crashes when cli starts with prompt for input |
| 97 | 46 | medium | P1-high | -87 | [#3952](https://github.com/omnigent-ai/omnigent/issues/3952) A stale terminal exit removes the newer Codex resources of the same se |
| 98 | 46 | medium | P2-medium | +93 | [#2984](https://github.com/omnigent-ai/omnigent/issues/2984) [Bug] Codex incorrectly reports `needs-auth` with an authenticated cus |
| 99 | 46 | medium | P1-high | -7 | [#2184](https://github.com/omnigent-ai/omnigent/issues/2184) [Bug] Codex plugin skills are exposed with inconsistent names (`plugin |
| 100 | 46 | medium | P1-high | -7 | [#2071](https://github.com/omnigent-ai/omnigent/issues/2071) [Bug] web_search never advertised to claude-sdk sessions: unprefixed m |
| 101 | 46 | medium | P2-medium | +134 | [#2062](https://github.com/omnigent-ai/omnigent/issues/2062) [Bug] claude-native: per-session model override silently lost when wra |
| 102 | 45 | medium | P1-high | +5 | [#1831](https://github.com/omnigent-ai/omnigent/issues/1831) claude-native workers ignore executor.model pin and per-dispatch args. |
| 103 | 45 | medium | P1-high | +7 | [#1781](https://github.com/omnigent-ai/omnigent/issues/1781) codex harness: ambient DATABRICKS_BEARER/DATABRICKS_TOKEN overrides pr |
| 104 | 44 | medium | P1-high | +15 | [#1128](https://github.com/omnigent-ai/omnigent/issues/1128) [Bug] Claude SDK Appears to Use Opus Instead of Selected Model |
| 105 | 42 | medium | P1-high | -87 | [#3790](https://github.com/omnigent-ai/omnigent/issues/3790) force_sandbox policy is evaluated but structurally unreachable from cl |
| 106 | 42 | medium | P1-high | +24 | [#241](https://github.com/omnigent-ai/omnigent/issues/241) pi harness: GPT and Gemini dispatches 404 on the Databricks ucode gate |
| 107 | 42 | medium | P3-low | +240 | [#147](https://github.com/omnigent-ai/omnigent/issues/147) Tracking: gradual decomposition of monolith modules (cli.py 9.1KLOC, c |
| 108 | 42 | medium | P1-high | -50 | [#2904](https://github.com/omnigent-ai/omnigent/issues/2904) [Bug] claude-native: web-UI chat input fails with "tmux command failed |
| 109 | 42 | medium | P1-high | -28 | [#2397](https://github.com/omnigent-ai/omnigent/issues/2397) [Bug] Codex-native intelligent routing ignores live effort capabilitie |
| 110 | 42 | medium | P1-high | -23 | [#2272](https://github.com/omnigent-ai/omnigent/issues/2272) [Bug] Codex runner can't find OpenRouter secret that exists in keyring |
| 111 | 41 | medium | P2-medium | +147 | [#1724](https://github.com/omnigent-ai/omnigent/issues/1724) codex-native harness times out on WSL2 ("Codex TUI never started a thr |
| 112 | 39 | medium | P2-medium | +192 | [#890](https://github.com/omnigent-ai/omnigent/issues/890) [Bug] omnigent setup fails with npm EACCES when installing the Claude  |
| 113 | 38 | medium | P1-high | -97 | [#3852](https://github.com/omnigent-ai/omnigent/issues/3852) [Bug] Built-in write policies miss Claude Code's `MultiEdit` / `Notebo |
| 114 | 38 | medium | P2-medium | +110 | [#2369](https://github.com/omnigent-ai/omnigent/issues/2369) [Bug] pi harness only lists databricks-claude-sonnet-4-6 |
| 115 | 38 | medium | P1-high | -29 | [#2299](https://github.com/omnigent-ai/omnigent/issues/2299) [Bug] claude-native resume transcripts flatten tool_result image block |
| 116 | 38 | medium | P2-medium | +105 | [#2390](https://github.com/omnigent-ai/omnigent/issues/2390) Builtin policy for per-user sub-agent access control (subagent_access_ |
| 117 | 38 | medium | P1-high | +8 | [#668](https://github.com/omnigent-ai/omnigent/issues/668) [Bug] BUG？omni claude times out (60s) on macOS with native Claude Code |
| 118 | 37 | medium | P1-high | -9 | [#1794](https://github.com/omnigent-ai/omnigent/issues/1794) Bundled Polly: claude-sdk brain "Not logged in" + runaway spawn loop o |
| 119 | 37 | medium | P1-high | -77 | [#3101](https://github.com/omnigent-ai/omnigent/issues/3101) Docker/Kubernetes entrypoint never wires project_store — first-class P |
| 120 | 37 | medium | P1-high | -9 | [#1694](https://github.com/omnigent-ai/omnigent/issues/1694) Reliability: parallel code-fix missions fail silently (5s tmux timeout |
| 121 | 35 | medium | P2-medium | +116 | [#2055](https://github.com/omnigent-ai/omnigent/issues/2055) [Bug] codex-native harness elicitation: a resolve landing in the betwe |
| 122 | 35 | medium | P1-high | -78 | [#3076](https://github.com/omnigent-ai/omnigent/issues/3076) [Bug] claude-sdk omits ToolSearch, eagerly loading every MCP schema |
| 123 | 35 | medium | P3-low | +216 | [#2800](https://github.com/omnigent-ai/omnigent/issues/2800) [Bug] Top-level custom codex-native agents drop reasoning effort and y |
| 124 | 34 | medium | P2-medium | +159 | [#1192](https://github.com/omnigent-ai/omnigent/issues/1192) [Bug] Manual /compact errors "Compaction requires a configured LLM mod |
| 125 | 34 | medium | P1-high | -8 | [#1158](https://github.com/omnigent-ai/omnigent/issues/1158) [Bug] antigravity-native: TUI-typed turns never mirror to the web UI ( |
| 126 | 34 | medium | P2-medium | +159 | [#1157](https://github.com/omnigent-ai/omnigent/issues/1157) [Bug] antigravity-native: no Chat/Terminal toggle — terminal_antigravi |
| 127 | 34 | medium | P2-medium | +197 | [#377](https://github.com/omnigent-ai/omnigent/issues/377) gpt sub-agent fails on startup with missing databricks-sdk dependency |
| 128 | 33 | medium | P2-medium | +6 | [#4009](https://github.com/omnigent-ai/omnigent/issues/4009) [Feature] No Go client for the session API, so every Go caller hand-ro |
| 129 | 33 | medium | P1-high | -123 | [#3981](https://github.com/omnigent-ai/omnigent/issues/3981) [Bug] Desktop: Workspace rail resize is unusable on the Browser tab; a |
| 130 | 33 | medium | P1-high | -117 | [#3898](https://github.com/omnigent-ai/omnigent/issues/3898) [Bug] Pack function policies fail server-side input evaluation unless  |
| 131 | 33 | medium | P1-high | -117 | [#3870](https://github.com/omnigent-ai/omnigent/issues/3870) child-session creation returns 500 internal_error, breaking Polly/Debb |
| 132 | 33 | medium | P2-medium | +10 | [#3864](https://github.com/omnigent-ai/omnigent/issues/3864) [Bug] to_api_dict() drops ConversationItem.created_at, so flat items A |
| 133 | 33 | medium | P1-high | -118 | [#3863](https://github.com/omnigent-ai/omnigent/issues/3863) [Bug] Databricks Apps entrypoint never wires project_store — Projects  |
| 134 | 33 | medium | P2-medium | +9 | [#3861](https://github.com/omnigent-ai/omnigent/issues/3861) [Bug] omni host status renders URLs so terminals link the whole status |
| 135 | 33 | medium | P2-medium | +17 | [#3563](https://github.com/omnigent-ai/omnigent/issues/3563) [Bug] Host-bound resume into a deleted workspace: host computes the ex |
| 136 | 33 | medium | P2-medium | +17 | [#3561](https://github.com/omnigent-ai/omnigent/issues/3561) [Bug] `prompt_policy` never sends `_CLASSIFIER_SCHEMA` to the LLM — st |
| 137 | 33 | medium | P2-medium | +18 | [#3550](https://github.com/omnigent-ai/omnigent/issues/3550) [Bug] Missing signing alg's prevent using some OIDC providers |
| 138 | 33 | medium | P2-medium | +22 | [#3435](https://github.com/omnigent-ai/omnigent/issues/3435) [Feature] Admin server-wide usage report (per-user and per-model cost) |
| 139 | 33 | medium | none | +214 | [#3402](https://github.com/omnigent-ai/omnigent/issues/3402) [Bug] Label seeding and session-state writes race under concurrent upd |
| 140 | 33 | medium | P2-medium | +22 | [#3368](https://github.com/omnigent-ai/omnigent/issues/3368) Feature: first-class async write-safety (freeze → approve → apply) pri |
| 141 | 33 | medium | P2-medium | +24 | [#3352](https://github.com/omnigent-ai/omnigent/issues/3352) [Feature] OpenClaw onboarding — Option B: chat import (SQLite session  |
| 142 | 33 | medium | P2-medium | +28 | [#3247](https://github.com/omnigent-ai/omnigent/issues/3247) credential_proxy: re-resolve the source on 401 / expiry (short-lived t |
| 143 | 33 | medium | P1-high | -103 | [#3236](https://github.com/omnigent-ai/omnigent/issues/3236) web_search: bare executor.model strings are inferred as provider 'open |
| 144 | 33 | medium | P2-medium | +32 | [#3219](https://github.com/omnigent-ai/omnigent/issues/3219) [Bug] Cmd/Ctrl+Up/Down session traversal stops in an empty focused com |
| 145 | 33 | medium | P2-medium | +47 | [#2921](https://github.com/omnigent-ai/omnigent/issues/2921) Font settings: selected font (incl. Nerd Fonts) never loads — no webfo |
| 146 | 33 | medium | P1-high | -86 | [#2854](https://github.com/omnigent-ai/omnigent/issues/2854) [Bug] Cross-harness `harness_override` is ignored on the `initial_item |
| 147 | 33 | medium | P2-medium | +49 | [#2851](https://github.com/omnigent-ai/omnigent/issues/2851) Policy-supplied targets for ASK approval cards |
| 148 | 33 | medium | P2-medium | +54 | [#2756](https://github.com/omnigent-ai/omnigent/issues/2756) Expose atomic session-event admission to integrations |
| 149 | 33 | medium | P2-medium | +63 | [#2577](https://github.com/omnigent-ai/omnigent/issues/2577) [Feature] Manage OIDC/SSO admins from an id_token claim (IdP group/rol |
| 150 | 33 | medium | P2-medium | +63 | [#2558](https://github.com/omnigent-ai/omnigent/issues/2558) Distribution / Installation / Enterprise Readiness |
| 151 | 33 | medium | P1-high | -81 | [#2539](https://github.com/omnigent-ai/omnigent/issues/2539) Named sys_session_send returns 404 after first child from a bundled se |
| 152 | 33 | medium | P1-high | -81 | [#2524](https://github.com/omnigent-ai/omnigent/issues/2524) [Bug] Registering remote host fails |
| 153 | 33 | medium | P1-high | -80 | [#2444](https://github.com/omnigent-ai/omnigent/issues/2444) Accounts JWT expiry falls through to Databricks auth and breaks persis |
| 154 | 33 | medium | P2-medium | +66 | [#2404](https://github.com/omnigent-ai/omnigent/issues/2404) fix(runtime): orphan sweep can abort startup on unreadable shared-host |
| 155 | 33 | medium | P2-medium | +67 | [#2374](https://github.com/omnigent-ai/omnigent/issues/2374) Proposal: per-turn context_providers to augment system instructions at |
| 156 | 33 | medium | P1-high | -71 | [#2304](https://github.com/omnigent-ai/omnigent/issues/2304) Runner subprocess inherits host daemon cwd, causing os_env cwd resolut |
| 157 | 33 | medium | P2-medium | +77 | [#2070](https://github.com/omnigent-ai/omnigent/issues/2070) [Feature] sys_os_* file tools are hard-confined to the session workspa |
| 158 | 33 | feature | P2-medium | +155 | [#692](https://github.com/omnigent-ai/omnigent/issues/692) Polly: fan out sub-agent work across multiple concurrent claude profil |
| 159 | 32 | medium | P1-high | -59 | [#1936](https://github.com/omnigent-ai/omnigent/issues/1936) [BUG] copilot harness: 401 Bad credentials when no token is explicitly |
| 160 | 32 | medium | P1-high | -47 | [#1551](https://github.com/omnigent-ai/omnigent/issues/1551) opencode-native: blocking question tool not surfaced to web (no elicit |
| 161 | 32 | feature | P2-medium | +166 | [#197](https://github.com/omnigent-ai/omnigent/issues/197) Declarative skill sources: pull Claude Code skills + their dependency  |
| 162 | 32 | medium | P1-high | -39 | [#880](https://github.com/omnigent-ai/omnigent/issues/880) [BUG] Native harness (omnigent claude): assistant turns not streamed t |
| 163 | 32 | medium | P2-medium | +108 | [#1526](https://github.com/omnigent-ai/omnigent/issues/1526) Refactor: incrementally decompose the 4 god-files (sessions.py, runner |
| 164 | 32 | medium | P2-medium | +110 | [#1411](https://github.com/omnigent-ai/omnigent/issues/1411) Standalone reusable MCP servers: CRUD + connection verify (list tools) |
| 165 | 31 | medium | P2-medium | +125 | [#1075](https://github.com/omnigent-ai/omnigent/issues/1075) [Feature] Support AWS Lambda / Firecracker microVMs as managed sandbox |
| 166 | 31 | medium | P2-medium | +126 | [#1055](https://github.com/omnigent-ai/omnigent/issues/1055) [Test] End-to-end OTel test against a real collector to lock in the BY |
| 167 | 31 | medium | P2-medium | +126 | [#1054](https://github.com/omnigent-ai/omnigent/issues/1054) [Feature] Record gen_ai.retry events on llm_call spans |
| 168 | 31 | medium | P1-high | -90 | [#2429](https://github.com/omnigent-ai/omnigent/issues/2429) Server (python -m omnigent.cli server) CPU-spins indefinitely with no  |
| 169 | 31 | medium | P2-medium | +128 | [#1031](https://github.com/omnigent-ai/omnigent/issues/1031) [Feature] Support serving the standalone Web UI under a subpath, e.g.  |
| 170 | 31 | medium | P2-medium | +130 | [#983](https://github.com/omnigent-ai/omnigent/issues/983) Session sharing ergonomics: `sys_session_share` agent tool + `omnigent |
| 171 | 31 | feature | P2-medium | +102 | [#1454](https://github.com/omnigent-ai/omnigent/issues/1454) [Feature] Change permission mode of a running claude-native session fr |
| 172 | 31 | feature | P2-medium | +6 | [#3150](https://github.com/omnigent-ai/omnigent/issues/3150) [Feature] CLI: cross-harness fork — continue an existing session in a  |
| 173 | 30 | medium | P2-medium | +135 | [#857](https://github.com/omnigent-ai/omnigent/issues/857) [Proposal] Usage-limit detection + on-429 failover across pooled provi |
| 174 | 30 | medium | P1-high | -50 | [#765](https://github.com/omnigent-ai/omnigent/issues/765) Support interactive mid-flight policy ASK (TOOL_CALL/TOOL_RESULT/OUTPU |
| 175 | 30 | feature | P2-medium | +50 | [#2303](https://github.com/omnigent-ai/omnigent/issues/2303) [Feature] Support multi-repo workspaces (nested Git repos or multiple  |
| 176 | 30 | medium | P2-medium | +6 | [#3083](https://github.com/omnigent-ai/omnigent/issues/3083) [Bug] Cursor sessions launched from Omnigent Web is losing MCPs |
| 177 | 30 | medium | P1-high | -51 | [#547](https://github.com/omnigent-ai/omnigent/issues/547) Bug: Polly model switcher sends invalid Cursor SDK model id |
| 178 | 30 | medium | P1-high | -49 | [#522](https://github.com/omnigent-ai/omnigent/issues/522) Implement async-tool completion auto-delivery (SESSION_REARCHITECTURE  |
| 179 | 30 | feature | P2-medium | +80 | [#1703](https://github.com/omnigent-ai/omnigent/issues/1703) [Feature] Unify harness naming: bare names (claude, codex, …) are ambi |
| 180 | 30 | medium | P2-medium | +138 | [#509](https://github.com/omnigent-ai/omnigent/issues/509) [Feature] Default new-session workspace from selected agent's cwd |
| 181 | 30 | feature | P3-low | +161 | [#1678](https://github.com/omnigent-ai/omnigent/issues/1678) tech-debt(codex-native): extract a string-field helper for repeated di |
| 182 | 30 | medium | P2-medium | -13 | [#3250](https://github.com/omnigent-ai/omnigent/issues/3250) flaky e2e_ui: test_scheduled_task_create_edit_modal_and_time_picker ti |
| 183 | 30 | medium | P2-medium | +15 | [#2848](https://github.com/omnigent-ai/omnigent/issues/2848) Server logs an expected offline-runner resource 503 as ERROR + full tr |
| 184 | 30 | medium | P2-medium | +17 | [#2767](https://github.com/omnigent-ai/omnigent/issues/2767) [Bug] SQLite pool (default 5+10) not sized to the 200-thread limiter → |
| 185 | 30 | medium | P1-high | -102 | [#2357](https://github.com/omnigent-ai/omnigent/issues/2357) [Bug] admin fleet-view calls SqlAlchemyConversationStore.list_conversa |
| 186 | 30 | medium | P1-high | -91 | [#2052](https://github.com/omnigent-ai/omnigent/issues/2052) [Bug] web_fetch's __web_researcher helper sub-agent fails on 0.4.0 (si |
| 187 | 30 | medium | P2-medium | +136 | [#382](https://github.com/omnigent-ai/omnigent/issues/382) Evaluating the same agent across harnesses: no built-in way to compare |
| 188 | 30 | medium | P1-high | -87 | [#1920](https://github.com/omnigent-ai/omnigent/issues/1920) Seeder matching-hash fast path can't self-heal a lost artifact-store b |
| 189 | 30 | medium | P1-high | -184 | [#3982](https://github.com/omnigent-ai/omnigent/issues/3982) [Bug] electron-build.yml pnpm filter matches no package: desktop packa |
| 190 | 30 | medium | P3-low | +146 | [#3733](https://github.com/omnigent-ai/omnigent/issues/3733) [Bug] Android: hardcoded 25px switcher height makes the chat scroll-fa |
| 191 | 30 | medium | P2-medium | -44 | [#3732](https://github.com/omnigent-ai/omnigent/issues/3732) [Bug] Android: a Display-size change leaves the server-switcher pill's |
| 192 | 30 | medium | P2-medium | -42 | [#3592](https://github.com/omnigent-ai/omnigent/issues/3592) [Feature] Deterministic long-term memory (automatic recall/retain) — f |
| 193 | 30 | medium | P2-medium | -42 | [#3586](https://github.com/omnigent-ai/omnigent/issues/3586) [Bug] Android: native server-picker pill overlaps the sidebar header c |
| 194 | 30 | medium | P1-high | -170 | [#3578](https://github.com/omnigent-ai/omnigent/issues/3578) [Bug] MacOS Start Locally - "Error: No such command 'start'" |
| 195 | 30 | medium | P1-high | -170 | [#3536](https://github.com/omnigent-ai/omnigent/issues/3536) [Bug] A session's `reasoning_effort` never reaches in-process harnesse |
| 196 | 30 | medium | P2-medium | -39 | [#3531](https://github.com/omnigent-ai/omnigent/issues/3531) SSH_AUTH_SOCK dropped at the host→runner env boundary, breaking ssh-ag |
| 197 | 30 | medium | none | +157 | [#3392](https://github.com/omnigent-ai/omnigent/issues/3392) [Bug] Linux desktop app missing Icon |
| 198 | 30 | medium | P2-medium | -37 | [#3369](https://github.com/omnigent-ai/omnigent/issues/3369) Feature: a policy that fences a spawned type: agent worker read-only ( |
| 199 | 30 | medium | P2-medium | -31 | [#3254](https://github.com/omnigent-ai/omnigent/issues/3254) Sub-agent silently stalls after repeated context compactions during re |
| 200 | 30 | medium | P1-high | -157 | [#3095](https://github.com/omnigent-ai/omnigent/issues/3095) [Bug] Can't uninstall |
