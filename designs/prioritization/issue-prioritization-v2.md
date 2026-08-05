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

**Three layers, one flow (resolving the priority-vs-score discussion).** These
are distinct and it's worth being precise:

1. **Severity** — a graded property of the issue, a function of the axes below
   (type, blast radius, harness tier, …). Scored `low / medium / high /
   critical = 10 / 30 / 60 / 100`.
2. **Score** — severity combined with the mechanical multipliers (reach, tier,
   readiness, dup, demand). This is the **continuous ordering** — it sorts
   issues *within and across* priority labels, so two issues that share a label
   aren't stuck equal.
3. **Priority label (the outcome)** — the human-facing bucket the score lands
   in, **by fixed score thresholds** (below). This is what maintainers **sort,
   filter, and action on**; the score is the *reference for why* an issue got
   that label. The label is derived from the score, not hand-assigned by type.

**Score → priority label.** One derivation, no parallel rubric: the label is
just which band the final score falls in. The cut-points sit at the severity
band values, so a *multiplier* (tier / reach / dup / readiness / demand) is what
lets an issue cross **up** a band:

| Score | Priority | Reading |
|---|---|---|
| **≥ 100** | **P0-critical** | a critical-severity issue, or one pushed there by reach/tier |
| **≥ 60** | **P1-high** | high severity, or a medium boosted by a tier-1 harness / broad reach |
| **≥ 25** | **P2-medium** | ordinary graded work |
| **< 25** | **P3-low** | minor / narrow |

Example: a "high" bug (severity 60) in a tier-1 harness scores 60 × 1.4 = 84 →
clears **P1**; the same bug on a niche harness scores 60 × 0.9 = 54 → stays
**P2**. The multiplier moved the label. (Thresholds are tunable constants —
`P0_MIN`/`P1_MIN`/`P2_MIN` in `score_prototype.py`; the current values give P0 9
/ P1 58 / P2 206 / P3 87 on the snapshot, a 22% P1-bug share.)

*One consequence worth naming:* because the label comes from the full score,
non-severity signals **can** tip it — a heavily-reacted FR or a much-duplicated
bug can cross into P1. That's intended (demand/blast-radius are legitimate
priority inputs), but it's bounded: demand is capped (Community demand) and a
single FR can't reach P0 on reactions alone.

So: axes → severity → score → priority label. The score exists precisely because
a label alone can't order issues that share it (Serena/Pat: "two issues of the
same label are not equally important"); the label exists because people action
on buckets, not on a float.

Priority stays a 4-bucket label but gets a **rubric that forces separation**,
enforced in the classifier prompt (`.github/triage/config.yaml`) and by a
one-time backfill.

| Priority | Definition (severity × reach — applies to bugs AND FRs) |
|---|---|
| **P0-critical** | A concrete, named critical failure (list below), not a vague "bad." |
| **P1-high** | High severity (bug: crash / hang / permanent breakage, no workaround. FR: a capability whose *absence* blocks a common workflow) **AND** broad reach (default config, all/most users, or a tier-1 harness). Not "a thing I care about." |
| **P2-medium** | Real bug with a workaround, OR a substantive capability/feature with a moderate reach. |
| **P3-low** | Genuinely minor: cosmetic, polish, trivial convenience, narrow nice-to-have — bug or FR. |

**P0 is an explicit list, not a judgment call** (per review — even security
issues have a severity range, so we enumerate rather than blanket-P0 anything
"security"). An issue is P0 if it is any of:

- **Cannot start / use the product** — server, host, web UI, app, or sessions
  fail to start or are unusable for a common configuration.
- **A critical API is broken** — an endpoint the web UI/app depends on (usefully
  cross-checked against the harness/API benchmark) returns errors or wrong data.
- **DB migration failure or data loss** — persistence corruption, a migration
  that bricks existing data.
- **Security escape** — a sandbox/policy *bypass* or credential-crossing that
  lets an agent exceed its granted permissions (this is the one severity that
  ignores reach — a one-user escape is still P0).

Grow the list as real P0s surface. Note we **don't run a hosted service**, so
"all users down" is nearly hypothetical (only something like telemetry crashing
on every client) — dropped from the definition in favor of the concrete cases
above.

**Tier-1 grading heuristic** (per review). Rather than a hard label floor that
would override the score, this is guidance to the *grader*: a valid,
reproducible bug in a **tier-1** harness should rarely be graded below `high`
severity — a flagship harness failing is, by definition, a serious problem. That
severity (60) × the tier-1 multiplier (1.4) = 84, which clears P1 through the
normal score→label path. So the heuristic keeps flagship bugs out of P2 *without*
a second rule: it just tells the grader not to under-call their severity. Tier
2/3 bugs land P2/P3 unless severity/reach earn more.

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

Regrading assigns an issue's priority *label* by computing its score and
applying the thresholds above — the same derivation used everywhere, so there's
no second rubric to keep in sync. It runs in two situations:

1. **One-time backfill.** Re-run the classifier over the existing open issues
   once, so the backlog reflects the new rubric on day one. This is a labels-only
   pass — same tool-less classifier, same trusted label-application steps as
   [Stage 2 triage](../issue-triage-proposal.md); nothing new to build.
2. **Ongoing, on demand.** A maintainer who disagrees just changes the label
   (P2 → P1, or the reverse). That *is* the bump mechanism — no separate pin
   lever (see "Ongoing adjustment"). The scheduled re-score reads the updated
   label the next time it runs.

The mapping is exactly the score → priority table above (`score ≥ 100 → P0`,
`≥ 60 → P1`, `≥ 25 → P2`, else `P3`); nothing separate to define.

**Backfill preview** (`score_prototype.py --regrade`, regex grader over the 360
open issues — the production backfill uses the LLM grader):

| Priority | Now | Regraded |
|---|---|---|
| P0-critical | 3 | 9 |
| **P1-high** | **128** | **58** |
| P2-medium | 203 | 206 |
| P3-low | 15 | 87 |
| (no priority) | 11 | 0 |

**P1 share of open bugs: 60% → 22%** — the inflation drained, and P3 fills out
(score-thresholding sends genuinely-minor items to P3, where the old label
distribution left it vestigial). What moves, and why:

| Change | Count | Example |
|---|---|---|
| P1 → P2 | 85 | #3981 desktop rail resize — medium severity, single-platform (score 33) |
| P2 → P3 | 68 | #4027 "delete button on web UI" — narrow FR (score 22, below the P2 cut) |
| P2 → P1 | 23 | #3976 headless OAuth2 grant — high-severity FR, broad reach (score 99) |
| P1 → P3 | 9 | #3980 desktop dialog paint-over — minor, single-platform (score 25) |
| P2 → P0 | 4 | #2125 multi-host git creds — credential-crossing (score 104) |

*Caveat:* these per-issue moves use the regex grader, so they inherit its known
false positives (e.g. #2057/#2054 "sandbox bypass" FRs wrongly reach P0). Read
the **aggregate shape** (60% → 22%) as the reliable signal and individual rows
as illustrative; the LLM backfill corrects the outliers.

### Axis 3 — Harness tier (new, derived)

Harnesses are not equal in strategic weight. Tier is **derived from the
existing `areas.json` harness areas** (no new hand-labeling). The assignment is
informed by activity (open issues · reactions), not a guess:

- **Tier 1** — `claude` (128 open / 26 👍), `codex` (95 / 16). Flagship.
- **Tier 2** — `pi` (41 / 15), `cursor` (37 / 15), `antigravity` (24 / 13),
  `copilot` (15 / 13), `openai`/`gemini`. **Pi moved up to T2 on the data**
  (per review: it's the 3rd-most-active harness, above cursor — a T3 default
  under-weighted it). `opencode` (19 / 3) is the marginal T2/T3 call.
- **Tier 3** — the low-activity, near-zero-reaction rest: `goose`, `hermes`,
  `kimi`, `kiro`, `qwen` (each ~10–16 open, 0 👍).

Tier is a maintainer call, not a formula — the counts inform it, and the
mapping lives in `areas.json` so re-tiering (e.g. finalizing opencode) is a
one-line edit. Open follow-up flagged in review: confirm the T2 cut in the team
channel.

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

There are 8 `comp:` labels today, and several are mega-buckets that merge many
`areas.json` areas. Review consensus (Serena/Pat) is to go **more granular** —
fine-grained routing helps both prioritization and reviewer assignment. Two ways
to add granularity, and we use both deliberately:

- **New top-level `comp:` label** when a slice is a distinct discipline you'd
  *filter and prioritize on* (e.g. `comp:sandbox` is security-grade).
- **A `sub_area` tag** for finer structure. `areas.json` *already* models these
  sub-areas (runner vs sandbox, chat vs composer, …); the classifier can emit
  the matched sub-area as a second-level tag without minting a GH label per
  slice. This gives Serena's granularity (chat page / composer / settings /
  file viewer, runner-start / shutdown / server-comms) for routing and metrics
  **without dozens of flat labels to sync** — the repo has no label-sync, so
  keeping the label set small matters.

**Top-level labels — recommended set:**

| Label | Open | Action |
|---|---|---|
| `comp:harnesses` | 148 | Split by **tier** `-t1/-t2/-t3` (Axis 3); add a `sub_area` for **SDK vs native** and the specific harness (per review — SDK and native are different failure domains). |
| `comp:runner` | 109 | **Carve out `comp:sandbox`** (~29: bwrap/seatbelt/egress — security-grade, home of P0 #3557). Keep runner sub-areas (start / shutdown / server+terminal comms) as `sub_area`, not labels. |
| `comp:web-ui` | 99 | **Add `comp:mobile`** with device sub-tags **desktop / mobile-iOS / mobile-Android** (~23 mobile, ~11 desktop). Keep UI surfaces (chat / composer / session-nav / settings / file-viewer / comment-panel) as `sub_area`. |
| `comp:server` | 135 | Keep the label, **but add `comp:auth`** as its own label (per review — auth is a distinct surface with types: local / multi-user / OIDC / OAuth / Databricks) and mark **web-UI-critical APIs** so a break there grades P0 (Axis 2). Other server sub-areas (host / db) stay `sub_area`. |
| `comp:tui` · `comp:infra` · `comp:repr` · `comp:policies` | 40 / 34 / 13 / 21 | Keep as-is; use `sub_area` if a slice ever needs filtering. |

**Net new top-level labels:** `comp:sandbox`, `comp:mobile`, `comp:auth`, plus
the three `comp:harness-t*` tiers. Everything finer rides on `sub_area`.

Naming note: `comp:sandbox` (narrow) over a broad `comp:security` umbrella —
"security" would swallow the 120 credential/auth issues (now mostly `comp:auth`
/ server), re-creating a mega-bucket. Sandbox/policy *bypass* severity is handled
by the P0 rubric (Axis 2), not by an umbrella label.

**Trade-off, stated honestly:** this is more labels than my first draft argued
for. The review's call is that granularity earns its keep here — it drives
reviewer routing too, not just the score. The `sub_area` tag is the pressure
valve that lets us be granular without unbounded label growth.

### Axis 4 — The composite score (the ordering primitive)

```
base  = severity_weight              # LLM-graded from content (P0/P1/P2/P3-ish, 0–100)
      × reach_multiplier             # all-users/default 1.5 · normal 1.0 · single-platform 0.9
      × harness_tier_multiplier      # T1 1.4 · T2 1.1 · T3 0.9 · non-harness 1.0
      × dup_reach                    # +15% per confirmed duplicate, capped +50% (Axis 5)
      × readiness                    # ready-to-work 1.1 · normal 1.0 · needs-info 0.85 (Axis 6)

score = apply_demand(base, type)     # type-dependent — see "Community demand" below
      × age_factor                   # DEFAULT 1.0 (neutral) — see note below
```

Every weight is a named constant in one place. The score is the **continuous
ordering**; the priority label (Axis 2) is the bucket it lands in. Labels stay
authoritative for filtering, the score decides *what to look at first* within
and across them.

**On age (open review point).** An earlier draft *decayed* old issues. Review
pushed back: a real bug we haven't fixed in 30 days isn't *less* important — if
anything it's a sign we should **escalate**, not bury it. So the default is
**neutral (age_factor = 1.0)**; age does not lower the score. We surface aging
instead through the metrics ("priority age separation") and can add an *upward*
staleness escalation later if we want, rather than a downward decay. (The dry-run
defaults to neutral age; the old decaying variant is behind a `DECAY_OLD` flag
in `score_prototype.py` for comparison only.)

**Worked example — one issue, data points → score.** Take
[#3265](https://github.com/omnigent-ai/omnigent/issues/3265) ("claude-sdk agent
with linux_bwrap dies at spawn"):

| Factor | Value | Why |
|---|---|---|
| severity | 60 (high) | spawn death — a hard failure, no workaround |
| × reach | × 1.5 | body says it hits every session on the config → broad |
| × harness_tier | × 1.4 | title says `claude-sdk` → tier-1 |
| × dup_reach | × 1.0 | no confirmed duplicates (yet) |
| × readiness | × 1.0 | no explicit repro section matched → no bump |
| = base | **126** | 60 × 1.5 × 1.4 |
| × demand (bug) | + 0 | 0 reactions; bugs get only the additive tiebreak |
| × age | × 1.0 | neutral by default — age never lowers the score |
| **= score** | **126** | **≥ 100 → P0-critical**; ranks **#3** of 360 (was P1, rank #37) |

Contrast a vague, low-tier ticket: severity 30 (medium) × reach 0.9
(single-platform) × tier 0.9 (tier-3 harness) × readiness 1.0 ≈ **24** → **P3**
(below the 25 cut) — an order of magnitude lower, so it sits deep in the queue.
Same five data points, opposite ends of the queue *and* opposite priority
labels: that's the score→label derivation doing the work.

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
for a bug with a repro section and a ≥400-char body (or any substantive FR), 1.0
otherwise. It's deliberately gentle — it breaks near-ties, it never overrides
severity.

**`needs-info` vs partial info (review clarification).** These are two different
states and the design treats them differently:

- **`needs-info` = genuinely incomprehensible** — we can't tell what's going on
  from the description at all. These get **no priority** (Serena's point: don't
  prioritize or assign a reviewer to something we can't understand); the pending
  backfill leaves priority unset until the reporter responds. In the score they
  sit at `readiness = 0.85`, but the more important effect is having no priority
  label to sort by.
- **Partial info** — comprehensible, but missing a repro or a demo. These are
  **not** `needs-info`; we still grade and prioritize them, because a serious bug
  is worth looking at even without a clean repro (Pat's point). They just don't
  get the +1.1 readiness bump.

Today `needs-info` is on **0** open bugs, so the backfill also gives the
classifier an explicit reason to apply it — only to the incomprehensible ones.

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
| Truly incomprehensible | Add `needs-info` and leave priority unset (don't prioritize what we can't understand). Partial-but-serious info: keep prioritizing, skip the label. |
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

- **Harness** (dropdown: claude / codex / cursor / … / n/a) **+ mode (SDK /
  native)** — the #1 component, currently buried in prose. Feeds tier directly;
  the SDK-vs-native split feeds `sub_area` (per review).
- **Platform / device** (dropdown: macOS / Linux / Windows / **desktop /
  mobile-iOS / mobile-Android** / Docker) — a whole class of bugs is
  platform-specific (Windows setup crashes, iOS/Android OIDC, Linux aarch64).
  Feeds reach and the `comp:mobile` device sub-tag.
- **Impact / reach** (dropdown: all users / most / some / edge) — the reach axis
  the reporter can often answer better than the grader.
- **Auth type** (dropdown: local / multi-user / OIDC / OAuth / Databricks /
  n-a) — shown for auth issues; feeds `comp:auth` (per review).

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
   rubric (grade FRs across buckets; explicit P0 list; tier-1 floor) + the "P1
   scarcity" guardrail + emit `severity`, `readiness`, and `sub_area` fields.
   Low risk, affects new issues immediately.
2. **Component labels** — add `comp:harness-t1/-t2/-t3` (map each harness area in
   `areas.json` to a tier; confirm the T2 cut incl. Pi/opencode in the team
   channel), plus `comp:sandbox`, `comp:mobile`, `comp:auth`; add the `sub_area`
   taxonomy for finer routing (SDK/native, UI surface, runner phase, device).
   Update the classifier allowlist and backfill. See "Component taxonomy."
3. **Template fields** — add Harness (+SDK/native) / Platform-device / Impact /
   Auth-type dropdowns.
4. **Scoring job** — productionize `score_prototype.py` into a scheduled action
   that reads LLM-graded severity + readiness + dup count and publishes the
   ranked view.
5. **One-time backfill (regrade)** — re-run the classifier over open issues to
   relabel under the new rubric (see "How regrading works"); preview with
   `score_prototype.py --regrade`. Target: P1 back under ~20% of open bugs
   (regex preview lands it at 22%; the LLM pass should do better).
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
backwards**; #61 (rank 9) is a *bot* audit issue riding a "security" keyword.
That's the doc's thesis made concrete: regex can't grade severity. The scaffold
is sound — strip those artifacts and the genuine tier-1 bugs (#3265, #3557,
#3270, #3180, #2373) cluster correctly in the top 16. Scores also *tie* in coarse
bands (many issues share 92/84/…), so within-band order is arbitrary — read this
as a handful of tiers, not 200 true ranks. Age is now neutral (review point), so
older issues no longer decay. With the LLM grader plus ≤10% hand-correction (see
the maintainer guide), this is the shape the production ranking takes.

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
| 9 | 100 | critical | P3-low | +340 | [#61](https://github.com/omnigent-ai/omnigent/issues/61) 🤖 Code Audit: 21 potential issue(s) found |
| 10 | 99 | high | P2-medium | +126 | [#3976](https://github.com/omnigent-ai/omnigent/issues/3976) [Feature] OAuth2 client-credentials grant so a headless process can au |
| 11 | 99 | high | P2-medium | +153 | [#3363](https://github.com/omnigent-ai/omnigent/issues/3363) [Feature] Per-project custom instructions (project-scoped context) |
| 12 | 99 | high | P2-medium | +165 | [#3164](https://github.com/omnigent-ai/omnigent/issues/3164) [Feature] Optional runtimeClassName on the kubernetes sandbox provider |
| 13 | 99 | high | P2-medium | +263 | [#1388](https://github.com/omnigent-ai/omnigent/issues/1388) Make agents a first-class CRUD entity with a dedicated sidebar UI (dec |
| 14 | 99 | critical | P2-medium | +301 | [#659](https://github.com/omnigent-ai/omnigent/issues/659) [Feature] add a microvm backend for sandbox |
| 15 | 92 | high | P1-high | +26 | [#3180](https://github.com/omnigent-ai/omnigent/issues/3180) codex-native: runner never exits on idle timeout — cancelled delta-coa |
| 16 | 92 | high | P1-high | +66 | [#2373](https://github.com/omnigent-ai/omnigent/issues/2373) [Bug] claude-native: pasted web-UI message loses its Enter, stuck draf |
| 17 | 92 | high | P1-high | +77 | [#2060](https://github.com/omnigent-ai/omnigent/issues/2060) [Bug] claude-native: first web-UI message silently dropped when Claude |
| 18 | 92 | high | P1-high | +85 | [#1898](https://github.com/omnigent-ai/omnigent/issues/1898) [Bug] codex-native: cancelling a task awaiting flush() poisons the del |
| 19 | 92 | high | P2-medium | +297 | [#654](https://github.com/omnigent-ai/omnigent/issues/654) [Bug] Streaming with codex is hanging and paragraphs are not split. |
| 20 | 92 | high | P1-high | +107 | [#542](https://github.com/omnigent-ai/omnigent/issues/542) [Bug] AttributeError: 'SubprocessCLITransport' object has no attribute |
| 21 | 90 | high | P1-high | +31 | [#3001](https://github.com/omnigent-ai/omnigent/issues/3001) [Performance] GET /v1/sessions pre-fetches every accessible conversati |
| 22 | 89 | high | P2-medium | +273 | [#1051](https://github.com/omnigent-ai/omnigent/issues/1051) [Feature] Forward OTel exporter knobs to executor subprocess env |
| 23 | 84 | high | P2-medium | +131 | [#3558](https://github.com/omnigent-ai/omnigent/issues/3558) claude-sdk: cached client does not rebuild on framework-instruction ch |
| 24 | 84 | high | P1-high | +29 | [#3000](https://github.com/omnigent-ai/omnigent/issues/3000) claude-native transcript forwarder polls at 4 Hz per session with no i |
| 25 | 84 | high | P1-high | +37 | [#2748](https://github.com/omnigent-ai/omnigent/issues/2748) Runner idle-shutdown deadlocks forever: codex-forwarder close()/flush( |
| 26 | 84 | high | P1-high | +41 | [#2575](https://github.com/omnigent-ai/omnigent/issues/2575) pi-native: non-Claude Databricks models (GLM, Gemini, …) hang — provid |
| 27 | 84 | high | P1-high | +45 | [#2454](https://github.com/omnigent-ai/omnigent/issues/2454) [Bug] Unbounded ~/.omnigent growth: per-session native-harness dirs ar |
| 28 | 84 | high | P1-high | +52 | [#2421](https://github.com/omnigent-ai/omnigent/issues/2421) [Bug] codex app-server + MCP bridge children leak on ANY unclean runne |
| 29 | 83 | high | P2-medium | +276 | [#888](https://github.com/omnigent-ai/omnigent/issues/888) [Feature] Side-by-side multi-session view |
| 30 | 81 | high | P2-medium | +107 | [#3970](https://github.com/omnigent-ai/omnigent/issues/3970) pi-native: every turn fails with "Pi model error: 401 Invalid Token" w |
| 31 | 78 | high | P2-medium | +303 | [#16](https://github.com/omnigent-ai/omnigent/issues/16) Is native Windows support in scope, or should docs recommend WSL2? |
| 32 | 76 | high | P2-medium | +297 | [#151](https://github.com/omnigent-ai/omnigent/issues/151) Native claude_code worker hangs on the one-time Bypass Permissions acc |
| 33 | 70 | high | P1-high | +5 | [#3261](https://github.com/omnigent-ai/omnigent/issues/3261) [Crash] AttributeError: module 'os' has no attribute 'WNOHANG' |
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
| 49 | 66 | high | P2-medium | +195 | [#1907](https://github.com/omnigent-ai/omnigent/issues/1907) Sub-agent model_override triggers an unnecessary first-turn harness re |
| 50 | 66 | high | P1-high | +54 | [#1888](https://github.com/omnigent-ai/omnigent/issues/1888) ansi-to-react default import resolves to the CJS exports object under  |
| 51 | 66 | high | P2-medium | +202 | [#1804](https://github.com/omnigent-ai/omnigent/issues/1804) spec parser crashes with TypeError on a null tools.builtins key (and s |
| 52 | 66 | high | P2-medium | +237 | [#1076](https://github.com/omnigent-ai/omnigent/issues/1076) Runner-layer Tier-2 escalation: release an unresponsive per-conversati |
| 53 | 66 | high | P1-high | +68 | [#1026](https://github.com/omnigent-ai/omnigent/issues/1026) Runner orphans tool callbacks with "no active turn context" after mid- |
| 54 | 65 | high | P2-medium | +154 | [#2714](https://github.com/omnigent-ai/omnigent/issues/2714) Upgrade openai-agents and remove the temporary openai<2.45 cap |
| 55 | 65 | high | P1-high | +35 | [#2245](https://github.com/omnigent-ai/omnigent/issues/2245) [Bug] openai-agents harness turn wedges permanently after policy-verdi |
| 56 | 63 | high | P1-high | +75 | [#108](https://github.com/omnigent-ai/omnigent/issues/108) Cannot install on Linux aarch64 — cel-expr-python has no aarch64 wheel |
| 57 | 61 | medium | P2-medium | +211 | [#1596](https://github.com/omnigent-ai/omnigent/issues/1596) Native-CLI harness (claude-native/codex-native) as a named agent's own |
| 58 | 60 | high | P1-high | -50 | [#3971](https://github.com/omnigent-ai/omnigent/issues/3971) Host runners inherit the daemon's cwd; a deleted launch dir breaks eve |
| 59 | 60 | high | P1-high | -25 | [#3274](https://github.com/omnigent-ai/omnigent/issues/3274) Sub-agent terminal status rejected with missing_parent_inbox and retri |
| 60 | 60 | high | P2-medium | +112 | [#3235](https://github.com/omnigent-ai/omnigent/issues/3235) Flaky E2E UI: test_scheduled_task_create_edit_modal_and_time_picker[ch |
| 61 | 60 | high | P1-high | -14 | [#3016](https://github.com/omnigent-ai/omnigent/issues/3016) [Bug] A transient session-snapshot failure permanently pins a session  |
| 62 | 60 | high | P1-high | -14 | [#3012](https://github.com/omnigent-ai/omnigent/issues/3012) Hosts authenticated via `omnigent login` permanently 403 on first reco |
| 63 | 60 | high | P2-medium | +155 | [#2428](https://github.com/omnigent-ai/omnigent/issues/2428) sys_session_send to a completed session hangs to ReadTimeout and is si |
| 64 | 60 | high | P1-high | +27 | [#2241](https://github.com/omnigent-ai/omnigent/issues/2241) Flaky on main: test_interrupt_forwards_to_harness_before_cancelling ti |
| 65 | 60 | high | P1-high | +31 | [#2051](https://github.com/omnigent-ai/omnigent/issues/2051) [Bug] sys_session_send(session_id=…) completions never drain to sys_re |
| 66 | 60 | high | P0-critical | -63 | [#1657](https://github.com/omnigent-ai/omnigent/issues/1657) hermes-native forwarder advances last_id per item, dropping a row's la |
| 67 | 60 | high | P2-medium | +247 | [#678](https://github.com/omnigent-ai/omnigent/issues/678) e2e: sub-agent supervisor routing / named-sub-agent auto-wake flakes ( |
| 68 | 59 | high | P1-high | -51 | [#3799](https://github.com/omnigent-ai/omnigent/issues/3799) Android shell cannot sign in to servers behind a front-door auth proxy |
| 69 | 59 | high | P1-high | -49 | [#3730](https://github.com/omnigent-ai/omnigent/issues/3730) [Bug] Android: renderer death terminates the app — OmnigentWebViewClie |
| 70 | 59 | high | P1-high | -48 | [#3701](https://github.com/omnigent-ai/omnigent/issues/3701) [Bug] Desktop app never completes Okta security key / biometric MFA du |
| 71 | 59 | high | P1-high | -38 | [#3299](https://github.com/omnigent-ai/omnigent/issues/3299) [Bug] Harness-credential route times out with a misleading 504 against |
| 72 | 59 | high | P2-medium | +94 | [#3284](https://github.com/omnigent-ai/omnigent/issues/3284) [Crash] DuplicateOptionError: While reading from PosixPath('/Users/*** |
| 73 | 59 | high | P2-medium | +111 | [#3070](https://github.com/omnigent-ai/omnigent/issues/3070) No progress signal on a stuck or interactive harness install |
| 74 | 59 | high | P1-high | -19 | [#2967](https://github.com/omnigent-ai/omnigent/issues/2967) [Bug] A full context window bricks a session with "Prompt is too long" |
| 75 | 59 | high | P2-medium | +141 | [#2480](https://github.com/omnigent-ai/omnigent/issues/2480) [Bug] Postgres-backed local server: bare `No module named 'psycopg'` + |
| 76 | 59 | high | P1-high | +12 | [#2270](https://github.com/omnigent-ai/omnigent/issues/2270) Windows: config list crashes — UnicodeEncodeError on cp1252 (non-UTF8) |
| 77 | 59 | high | P1-high | +12 | [#2269](https://github.com/omnigent-ai/omnigent/issues/2269) Windows: omnigent setup crashes — ModuleNotFoundError: No module named |
| 78 | 59 | high | P1-high | +21 | [#1953](https://github.com/omnigent-ai/omnigent/issues/1953) `omni host` dies permanently when the OIDC session JWT expires — no re |
| 79 | 59 | high | P1-high | +23 | [#1901](https://github.com/omnigent-ai/omnigent/issues/1901) [Bug] kimi/qwen/goose/kiro forwarders blind-retry failed conversation- |
| 80 | 59 | high | P1-high | +25 | [#1881](https://github.com/omnigent-ai/omnigent/issues/1881) [Bug] `omnigent setup` crashes with `ValueError: select() requires at  |
| 81 | 59 | high | P1-high | +27 | [#1827](https://github.com/omnigent-ai/omnigent/issues/1827) [Bug] kimi-native: torn UTF-8 wire read crashes the forwarder; supervi |
| 82 | 59 | high | P2-medium | +185 | [#1600](https://github.com/omnigent-ai/omnigent/issues/1600) Epic: 12-feature contribution (one issue + one PR per feature) |
| 83 | 59 | high | P2-medium | +187 | [#1528](https://github.com/omnigent-ai/omnigent/issues/1528) Idle-session lifecycle UX: reap gracefully, resume seamlessly, surface |
| 84 | 58 | high | P2-medium | +214 | [#1022](https://github.com/omnigent-ai/omnigent/issues/1022) Behind a corporate proxy, the host daemon can't reach the model backen |
| 85 | 57 | medium | P2-medium | +214 | [#1021](https://github.com/omnigent-ai/omnigent/issues/1021) [Feature] GitHub Copilot as provider |
| 86 | 54 | high | P2-medium | +58 | [#3798](https://github.com/omnigent-ai/omnigent/issues/3798) Android shell shows the SPA as if signed in while native login runs in |
| 87 | 54 | high | P1-high | -58 | [#3469](https://github.com/omnigent-ai/omnigent/issues/3469) [Bug] Post-completion compaction spiral: merge-commit diff output trig |
| 88 | 54 | high | P1-high | -23 | [#2629](https://github.com/omnigent-ai/omnigent/issues/2629) web_fetch sub-agent spawn fails with unknown harness 'omnigent' — bare |
| 89 | 54 | high | P2-medium | +166 | [#1778](https://github.com/omnigent-ai/omnigent/issues/1778) opencode-native forwarder loses session content across SSE reconnects  |
| 90 | 54 | high | P1-high | +38 | [#523](https://github.com/omnigent-ai/omnigent/issues/523) REPL pexpect e2e tests starve on boot under full shard load (60s _wait |
| 91 | 53 | high | P1-high | -42 | [#3011](https://github.com/omnigent-ai/omnigent/issues/3011) kiro-native harness: interactive sessions never respond with kiro-cli  |
| 92 | 53 | high | P1-high | -36 | [#2920](https://github.com/omnigent-ai/omnigent/issues/2920) Omnigent server fails to start on native Windows: os.getuid() at impor |
| 93 | 53 | high | P1-high | -36 | [#2919](https://github.com/omnigent-ai/omnigent/issues/2919) omni setup crashes on Windows: ModuleNotFoundError: No module named 't |
| 94 | 53 | high | P1-high | -15 | [#2422](https://github.com/omnigent-ai/omnigent/issues/2422) Windows: five chained defects break the documented degraded-mode subse |
| 95 | 53 | high | P2-medium | +215 | [#762](https://github.com/omnigent-ai/omnigent/issues/762) [Bug] sub agent terminal crashes when cli starts with prompt for input |
| 96 | 50 | medium | P2-medium | +108 | [#2744](https://github.com/omnigent-ai/omnigent/issues/2744) [Bug] codex-native: custom agents time out at launch — native provider |
| 97 | 46 | medium | P1-high | -87 | [#3952](https://github.com/omnigent-ai/omnigent/issues/3952) A stale terminal exit removes the newer Codex resources of the same se |
| 98 | 46 | medium | P2-medium | +93 | [#2984](https://github.com/omnigent-ai/omnigent/issues/2984) [Bug] Codex incorrectly reports `needs-auth` with an authenticated cus |
| 99 | 46 | medium | P1-high | -7 | [#2184](https://github.com/omnigent-ai/omnigent/issues/2184) [Bug] Codex plugin skills are exposed with inconsistent names (`plugin |
| 100 | 46 | medium | P1-high | -7 | [#2071](https://github.com/omnigent-ai/omnigent/issues/2071) [Bug] web_search never advertised to claude-sdk sessions: unprefixed m |
| 101 | 46 | medium | P2-medium | +134 | [#2062](https://github.com/omnigent-ai/omnigent/issues/2062) [Bug] claude-native: per-session model override silently lost when wra |
| 102 | 46 | medium | P1-high | +5 | [#1831](https://github.com/omnigent-ai/omnigent/issues/1831) claude-native workers ignore executor.model pin and per-dispatch args. |
| 103 | 46 | medium | P1-high | +7 | [#1781](https://github.com/omnigent-ai/omnigent/issues/1781) codex harness: ambient DATABRICKS_BEARER/DATABRICKS_TOKEN overrides pr |
| 104 | 46 | medium | P1-high | +15 | [#1128](https://github.com/omnigent-ai/omnigent/issues/1128) [Bug] Claude SDK Appears to Use Opus Instead of Selected Model |
| 105 | 46 | medium | P1-high | +25 | [#241](https://github.com/omnigent-ai/omnigent/issues/241) pi harness: GPT and Gemini dispatches 404 on the Databricks ucode gate |
| 106 | 46 | medium | P3-low | +241 | [#147](https://github.com/omnigent-ai/omnigent/issues/147) Tracking: gradual decomposition of monolith modules (cli.py 9.1KLOC, c |
| 107 | 42 | medium | P1-high | -89 | [#3790](https://github.com/omnigent-ai/omnigent/issues/3790) force_sandbox policy is evaluated but structurally unreachable from cl |
| 108 | 42 | medium | P2-medium | +150 | [#1724](https://github.com/omnigent-ai/omnigent/issues/1724) codex-native harness times out on WSL2 ("Codex TUI never started a thr |
| 109 | 42 | medium | P1-high | -51 | [#2904](https://github.com/omnigent-ai/omnigent/issues/2904) [Bug] claude-native: web-UI chat input fails with "tmux command failed |
| 110 | 42 | medium | P1-high | -29 | [#2397](https://github.com/omnigent-ai/omnigent/issues/2397) [Bug] Codex-native intelligent routing ignores live effort capabilitie |
| 111 | 42 | medium | P1-high | -24 | [#2272](https://github.com/omnigent-ai/omnigent/issues/2272) [Bug] Codex runner can't find OpenRouter secret that exists in keyring |
| 112 | 42 | medium | P2-medium | +192 | [#890](https://github.com/omnigent-ai/omnigent/issues/890) [Bug] omnigent setup fails with npm EACCES when installing the Claude  |
| 113 | 42 | medium | P1-high | +12 | [#668](https://github.com/omnigent-ai/omnigent/issues/668) [Bug] BUG？omni claude times out (60s) on macOS with native Claude Code |
| 114 | 38 | medium | P1-high | -98 | [#3852](https://github.com/omnigent-ai/omnigent/issues/3852) [Bug] Built-in write policies miss Claude Code's `MultiEdit` / `Notebo |
| 115 | 38 | medium | P2-medium | +109 | [#2369](https://github.com/omnigent-ai/omnigent/issues/2369) [Bug] pi harness only lists databricks-claude-sonnet-4-6 |
| 116 | 38 | medium | P1-high | -30 | [#2299](https://github.com/omnigent-ai/omnigent/issues/2299) [Bug] claude-native resume transcripts flatten tool_result image block |
| 117 | 38 | medium | P2-medium | +104 | [#2390](https://github.com/omnigent-ai/omnigent/issues/2390) Builtin policy for per-user sub-agent access control (subagent_access_ |
| 118 | 38 | medium | P2-medium | +206 | [#377](https://github.com/omnigent-ai/omnigent/issues/377) gpt sub-agent fails on startup with missing databricks-sdk dependency |
| 119 | 38 | medium | P1-high | -10 | [#1794](https://github.com/omnigent-ai/omnigent/issues/1794) Bundled Polly: claude-sdk brain "Not logged in" + runaway spawn loop o |
| 120 | 38 | medium | P1-high | -9 | [#1694](https://github.com/omnigent-ai/omnigent/issues/1694) Reliability: parallel code-fix missions fail silently (5s tmux timeout |
| 121 | 37 | medium | P1-high | -79 | [#3101](https://github.com/omnigent-ai/omnigent/issues/3101) Docker/Kubernetes entrypoint never wires project_store — first-class P |
| 122 | 36 | medium | P2-medium | +161 | [#1192](https://github.com/omnigent-ai/omnigent/issues/1192) [Bug] Manual /compact errors "Compaction requires a configured LLM mod |
| 123 | 36 | medium | P1-high | -6 | [#1158](https://github.com/omnigent-ai/omnigent/issues/1158) [Bug] antigravity-native: TUI-typed turns never mirror to the web UI ( |
| 124 | 36 | medium | P2-medium | +161 | [#1157](https://github.com/omnigent-ai/omnigent/issues/1157) [Bug] antigravity-native: no Chat/Terminal toggle — terminal_antigravi |
| 125 | 36 | feature | P2-medium | +188 | [#692](https://github.com/omnigent-ai/omnigent/issues/692) Polly: fan out sub-agent work across multiple concurrent claude profil |
| 126 | 36 | feature | P2-medium | +201 | [#197](https://github.com/omnigent-ai/omnigent/issues/197) Declarative skill sources: pull Claude Code skills + their dependency  |
| 127 | 35 | medium | P2-medium | +110 | [#2055](https://github.com/omnigent-ai/omnigent/issues/2055) [Bug] codex-native harness elicitation: a resolve landing in the betwe |
| 128 | 35 | medium | P1-high | -84 | [#3076](https://github.com/omnigent-ai/omnigent/issues/3076) [Bug] claude-sdk omits ToolSearch, eagerly loading every MCP schema |
| 129 | 35 | medium | P3-low | +210 | [#2800](https://github.com/omnigent-ai/omnigent/issues/2800) [Bug] Top-level custom codex-native agents drop reasoning effort and y |
| 130 | 35 | medium | P1-high | -7 | [#880](https://github.com/omnigent-ai/omnigent/issues/880) [BUG] Native harness (omnigent claude): assistant turns not streamed t |
| 131 | 33 | medium | P1-high | -18 | [#1551](https://github.com/omnigent-ai/omnigent/issues/1551) opencode-native: blocking question tool not surfaced to web (no elicit |
| 132 | 33 | medium | P2-medium | +2 | [#4009](https://github.com/omnigent-ai/omnigent/issues/4009) [Feature] No Go client for the session API, so every Go caller hand-ro |
| 133 | 33 | medium | P1-high | -127 | [#3981](https://github.com/omnigent-ai/omnigent/issues/3981) [Bug] Desktop: Workspace rail resize is unusable on the Browser tab; a |
| 134 | 33 | medium | P1-high | -121 | [#3898](https://github.com/omnigent-ai/omnigent/issues/3898) [Bug] Pack function policies fail server-side input evaluation unless  |
| 135 | 33 | medium | P1-high | -121 | [#3870](https://github.com/omnigent-ai/omnigent/issues/3870) child-session creation returns 500 internal_error, breaking Polly/Debb |
| 136 | 33 | medium | P2-medium | +6 | [#3864](https://github.com/omnigent-ai/omnigent/issues/3864) [Bug] to_api_dict() drops ConversationItem.created_at, so flat items A |
| 137 | 33 | medium | P1-high | -122 | [#3863](https://github.com/omnigent-ai/omnigent/issues/3863) [Bug] Databricks Apps entrypoint never wires project_store — Projects  |
| 138 | 33 | medium | P2-medium | +5 | [#3861](https://github.com/omnigent-ai/omnigent/issues/3861) [Bug] omni host status renders URLs so terminals link the whole status |
| 139 | 33 | medium | P2-medium | +13 | [#3563](https://github.com/omnigent-ai/omnigent/issues/3563) [Bug] Host-bound resume into a deleted workspace: host computes the ex |
| 140 | 33 | medium | P2-medium | +13 | [#3561](https://github.com/omnigent-ai/omnigent/issues/3561) [Bug] `prompt_policy` never sends `_CLASSIFIER_SCHEMA` to the LLM — st |
| 141 | 33 | medium | P2-medium | +14 | [#3550](https://github.com/omnigent-ai/omnigent/issues/3550) [Bug] Missing signing alg's prevent using some OIDC providers |
| 142 | 33 | medium | P2-medium | +18 | [#3435](https://github.com/omnigent-ai/omnigent/issues/3435) [Feature] Admin server-wide usage report (per-user and per-model cost) |
| 143 | 33 | medium | none | +210 | [#3402](https://github.com/omnigent-ai/omnigent/issues/3402) [Bug] Label seeding and session-state writes race under concurrent upd |
| 144 | 33 | medium | P2-medium | +18 | [#3368](https://github.com/omnigent-ai/omnigent/issues/3368) Feature: first-class async write-safety (freeze → approve → apply) pri |
| 145 | 33 | medium | P2-medium | +20 | [#3352](https://github.com/omnigent-ai/omnigent/issues/3352) [Feature] OpenClaw onboarding — Option B: chat import (SQLite session  |
| 146 | 33 | medium | P2-medium | +24 | [#3247](https://github.com/omnigent-ai/omnigent/issues/3247) credential_proxy: re-resolve the source on 401 / expiry (short-lived t |
| 147 | 33 | medium | P1-high | -107 | [#3236](https://github.com/omnigent-ai/omnigent/issues/3236) web_search: bare executor.model strings are inferred as provider 'open |
| 148 | 33 | medium | P2-medium | +28 | [#3219](https://github.com/omnigent-ai/omnigent/issues/3219) [Bug] Cmd/Ctrl+Up/Down session traversal stops in an empty focused com |
| 149 | 33 | medium | P2-medium | +43 | [#2921](https://github.com/omnigent-ai/omnigent/issues/2921) Font settings: selected font (incl. Nerd Fonts) never loads — no webfo |
| 150 | 33 | medium | P1-high | -90 | [#2854](https://github.com/omnigent-ai/omnigent/issues/2854) [Bug] Cross-harness `harness_override` is ignored on the `initial_item |
| 151 | 33 | medium | P2-medium | +45 | [#2851](https://github.com/omnigent-ai/omnigent/issues/2851) Policy-supplied targets for ASK approval cards |
| 152 | 33 | medium | P2-medium | +50 | [#2756](https://github.com/omnigent-ai/omnigent/issues/2756) Expose atomic session-event admission to integrations |
| 153 | 33 | medium | P2-medium | +59 | [#2577](https://github.com/omnigent-ai/omnigent/issues/2577) [Feature] Manage OIDC/SSO admins from an id_token claim (IdP group/rol |
| 154 | 33 | medium | P2-medium | +59 | [#2558](https://github.com/omnigent-ai/omnigent/issues/2558) Distribution / Installation / Enterprise Readiness |
| 155 | 33 | medium | P1-high | -85 | [#2539](https://github.com/omnigent-ai/omnigent/issues/2539) Named sys_session_send returns 404 after first child from a bundled se |
| 156 | 33 | medium | P1-high | -85 | [#2524](https://github.com/omnigent-ai/omnigent/issues/2524) [Bug] Registering remote host fails |
| 157 | 33 | medium | P1-high | -84 | [#2444](https://github.com/omnigent-ai/omnigent/issues/2444) Accounts JWT expiry falls through to Databricks auth and breaks persis |
| 158 | 33 | medium | P2-medium | +62 | [#2404](https://github.com/omnigent-ai/omnigent/issues/2404) fix(runtime): orphan sweep can abort startup on unreadable shared-host |
| 159 | 33 | medium | P2-medium | +63 | [#2374](https://github.com/omnigent-ai/omnigent/issues/2374) Proposal: per-turn context_providers to augment system instructions at |
| 160 | 33 | medium | P1-high | -75 | [#2304](https://github.com/omnigent-ai/omnigent/issues/2304) Runner subprocess inherits host daemon cwd, causing os_env cwd resolut |
| 161 | 33 | medium | P2-medium | +73 | [#2070](https://github.com/omnigent-ai/omnigent/issues/2070) [Feature] sys_os_* file tools are hard-confined to the session workspa |
| 162 | 33 | medium | P2-medium | +109 | [#1526](https://github.com/omnigent-ai/omnigent/issues/1526) Refactor: incrementally decompose the 4 god-files (sessions.py, runner |
| 163 | 33 | medium | P2-medium | +111 | [#1411](https://github.com/omnigent-ai/omnigent/issues/1411) Standalone reusable MCP servers: CRUD + connection verify (list tools) |
| 164 | 33 | medium | P2-medium | +126 | [#1075](https://github.com/omnigent-ai/omnigent/issues/1075) [Feature] Support AWS Lambda / Firecracker microVMs as managed sandbox |
| 165 | 33 | medium | P2-medium | +127 | [#1055](https://github.com/omnigent-ai/omnigent/issues/1055) [Test] End-to-end OTel test against a real collector to lock in the BY |
| 166 | 33 | medium | P2-medium | +127 | [#1054](https://github.com/omnigent-ai/omnigent/issues/1054) [Feature] Record gen_ai.retry events on llm_call spans |
| 167 | 33 | medium | P2-medium | +130 | [#1031](https://github.com/omnigent-ai/omnigent/issues/1031) [Feature] Support serving the standalone Web UI under a subpath, e.g.  |
| 168 | 33 | medium | P2-medium | +132 | [#983](https://github.com/omnigent-ai/omnigent/issues/983) Session sharing ergonomics: `sys_session_share` agent tool + `omnigent |
| 169 | 33 | medium | P2-medium | +139 | [#857](https://github.com/omnigent-ai/omnigent/issues/857) [Proposal] Usage-limit detection + on-429 failover across pooled provi |
| 170 | 33 | medium | P1-high | -46 | [#765](https://github.com/omnigent-ai/omnigent/issues/765) Support interactive mid-flight policy ASK (TOOL_CALL/TOOL_RESULT/OUTPU |
| 171 | 33 | medium | P1-high | -45 | [#547](https://github.com/omnigent-ai/omnigent/issues/547) Bug: Polly model switcher sends invalid Cursor SDK model id |
| 172 | 33 | medium | P1-high | -43 | [#522](https://github.com/omnigent-ai/omnigent/issues/522) Implement async-tool completion auto-delivery (SESSION_REARCHITECTURE  |
| 173 | 33 | medium | P2-medium | +145 | [#509](https://github.com/omnigent-ai/omnigent/issues/509) [Feature] Default new-session workspace from selected agent's cwd |
| 174 | 33 | medium | P2-medium | +149 | [#382](https://github.com/omnigent-ai/omnigent/issues/382) Evaluating the same agent across harnesses: no built-in way to compare |
| 175 | 33 | medium | P1-high | -75 | [#1936](https://github.com/omnigent-ai/omnigent/issues/1936) [BUG] copilot harness: 401 Bad credentials when no token is explicitly |
| 176 | 32 | feature | P2-medium | +97 | [#1454](https://github.com/omnigent-ai/omnigent/issues/1454) [Feature] Change permission mode of a running claude-native session fr |
| 177 | 31 | medium | P1-high | -99 | [#2429](https://github.com/omnigent-ai/omnigent/issues/2429) Server (python -m omnigent.cli server) CPU-spins indefinitely with no  |
| 178 | 31 | medium | P1-high | -58 | [#1113](https://github.com/omnigent-ai/omnigent/issues/1113) Native sub-agent/runner failures surface as bare "failed" with no reas |
| 179 | 31 | feature | P2-medium | -1 | [#3150](https://github.com/omnigent-ai/omnigent/issues/3150) [Feature] CLI: cross-harness fork — continue an existing session in a  |
| 180 | 31 | feature | P2-medium | +79 | [#1703](https://github.com/omnigent-ai/omnigent/issues/1703) [Feature] Unify harness naming: bare names (claude, codex, …) are ambi |
| 181 | 31 | feature | P3-low | +161 | [#1678](https://github.com/omnigent-ai/omnigent/issues/1678) tech-debt(codex-native): extract a string-field helper for repeated di |
| 182 | 31 | feature | P2-medium | +137 | [#503](https://github.com/omnigent-ai/omnigent/issues/503) [Feature] Switch Claude Code account per session via isolated profiles |
| 183 | 30 | feature | P2-medium | +42 | [#2303](https://github.com/omnigent-ai/omnigent/issues/2303) [Feature] Support multi-repo workspaces (nested Git repos or multiple  |
| 184 | 30 | medium | P2-medium | -2 | [#3083](https://github.com/omnigent-ai/omnigent/issues/3083) [Bug] Cursor sessions launched from Omnigent Web is losing MCPs |
| 185 | 30 | medium | P1-high | -67 | [#1156](https://github.com/omnigent-ai/omnigent/issues/1156) [Bug] antigravity-native: web/mobile turns never appear in the native  |
| 186 | 30 | medium | P2-medium | -17 | [#3250](https://github.com/omnigent-ai/omnigent/issues/3250) flaky e2e_ui: test_scheduled_task_create_edit_modal_and_time_picker ti |
| 187 | 30 | medium | P2-medium | +11 | [#2848](https://github.com/omnigent-ai/omnigent/issues/2848) Server logs an expected offline-runner resource 503 as ERROR + full tr |
| 188 | 30 | medium | P2-medium | +13 | [#2767](https://github.com/omnigent-ai/omnigent/issues/2767) [Bug] SQLite pool (default 5+10) not sized to the 200-thread limiter → |
| 189 | 30 | medium | P1-high | -106 | [#2357](https://github.com/omnigent-ai/omnigent/issues/2357) [Bug] admin fleet-view calls SqlAlchemyConversationStore.list_conversa |
| 190 | 30 | medium | P1-high | -95 | [#2052](https://github.com/omnigent-ai/omnigent/issues/2052) [Bug] web_fetch's __web_researcher helper sub-agent fails on 0.4.0 (si |
| 191 | 30 | medium | P1-high | -90 | [#1920](https://github.com/omnigent-ai/omnigent/issues/1920) Seeder matching-hash fast path can't self-heal a lost artifact-store b |
| 192 | 30 | medium | P1-high | -86 | [#1857](https://github.com/omnigent-ai/omnigent/issues/1857) Host daemon stays alive but shows offline — server-dropped host tunnel |
| 193 | 30 | medium | P1-high | -81 | [#1686](https://github.com/omnigent-ai/omnigent/issues/1686) xai: reasoning_effort sent to all Grok models returns HTTP 400 on unsu |
| 194 | 30 | medium | P2-medium | +94 | [#1117](https://github.com/omnigent-ai/omnigent/issues/1117) async generator ignored GeneratorExit — orphaned SSE relay task, excep |
| 195 | 30 | medium | P2-medium | +117 | [#725](https://github.com/omnigent-ai/omnigent/issues/725) Changes panel is empty for native-harness and external edits in non-gi |
| 196 | 30 | medium | P2-medium | +134 | [#146](https://github.com/omnigent-ai/omnigent/issues/146) StreamHooks.on_sub_agent_spawned / on_sub_agent_completed are declared |
| 197 | 30 | medium | P1-high | -192 | [#3982](https://github.com/omnigent-ai/omnigent/issues/3982) [Bug] electron-build.yml pnpm filter matches no package: desktop packa |
| 198 | 30 | medium | P3-low | +138 | [#3733](https://github.com/omnigent-ai/omnigent/issues/3733) [Bug] Android: hardcoded 25px switcher height makes the chat scroll-fa |
| 199 | 30 | medium | P2-medium | -52 | [#3732](https://github.com/omnigent-ai/omnigent/issues/3732) [Bug] Android: a Display-size change leaves the server-switcher pill's |
| 200 | 30 | medium | P2-medium | -50 | [#3592](https://github.com/omnigent-ai/omnigent/issues/3592) [Feature] Deterministic long-term memory (automatic recall/retain) — f |
