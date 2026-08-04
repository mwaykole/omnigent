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

1. **Periodic re-score.** A scheduled job (weekly) recomputes the score for all
   open issues and posts/updates a single **ranked view** (a pinned issue or a
   generated `PRIORITY-QUEUE.md`), so demand/age/dup changes are reflected
   without re-triaging. Cheap: no LLM call needed for re-score if severity is
   cached as a field at triage time.
2. **Re-grade severity to bump.** To push an issue up or down, a maintainer
   changes its priority/severity label (P2 → P1) — exactly what you asked: "I
   can bump P2 → P1 or vice versa." No separate `pin:high` / `pin:low` lever.
   A dedicated pin was in the previous draft; it's dropped as over-engineering
   — a second override that means the same thing as changing severity, but out
   of band from it. One knob, and it's the one maintainers already use.

The earlier draft leaned on `pin` to rescue "high-severity P2s" like #2125. The
better fix is upstream: grade severity honestly in the first place (Axis 2) so
#2125 lands where it belongs, and re-grade if it's wrong. The score reads
severity; fixing severity fixes the score.

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
