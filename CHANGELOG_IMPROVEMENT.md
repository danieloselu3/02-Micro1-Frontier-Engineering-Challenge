# Improvement changelog

How the system got from a single prompt to its final form, what each change was
meant to fix, and what the evidence said afterwards.

Every number here comes from `eval/reports/`, produced by `make eval-replay`
over the same 49 labelled cases. Both systems are scored identically.

---

## The headline

| Metric | Simple baseline | Agent pipeline | Change |
|---|---:|---:|---:|
| Verdict accuracy | 71.4% | **91.8%** | **+20.4 pp** |
| Reason accuracy | 69.4% | **73.5%** | +4.1 pp |
| **False denials** | 6 (12.2%) | **2 (4.1%)** | **−4** |
| **False approvals** | 5 (10.2%) | **0 (0.0%)** | **−5** |
| Field extraction | not produced | 96.6% | — |
| Settled without an adjudication call | 0 | 22 of 49 | — |
| Runtime errors | 0 | 0 | — |
| Mean cost per case | $0.0225 | $0.0598 | **+$0.037** |
| Mean latency | 7.3 s | 25.3 s | **+18 s** |

The pipeline costs **2.7× more** and takes **3.5× longer**. That is the trade,
and it is stated first rather than buried: it buys a 20-point accuracy gain and
the elimination of every false approval.

---

## Baseline

**What it is.** One model call per case. It receives the form image, every
record the pipeline's tools would fetch — member, plan, provider, procedure,
accumulators, prior authorizations — and the complete governing medical policy.
It is asked for a verdict.

It is not a straw man. It has all the information; what it lacks is
architecture. It is also handed the *correct* member and provider records,
while the pipeline must resolve them from the document it read.

**Result.** 71.4% verdict accuracy. 6 false denials, 5 false approvals.

**What it revealed.** The failures were not random. They clustered into four
patterns, and all four are structural:

| Failure | Cases | What happened |
|---|---|---|
| Narrative overrode a contractual exclusion | `excluded_cosmetic` ×2, `cosmetic_functional_exception` ×1 | A persuasive functional-necessity argument bought coverage the plan does not sell |
| Partial entitlement denied outright | `limit_partial` ×2 | The member had 60% of the cost remaining and was denied entirely |
| Coding error denied instead of returned | `code_mismatch` ×2 | A mistyped diagnosis produced an adverse determination rather than a correction request |
| Silent documentation treated as failed | `necessity_no_evidence` ×2 | The record did not mention conservative therapy, so it was denied — a paperwork denial |

Three of those four are false *denials*. That set the agenda for everything
that followed.

---

## Iteration 1 — move the facts out of the model

**Tried.** Nine deterministic rules over the payer records: eligibility,
waiting period, benefit exclusion, service area, provider standing, benefit
balance, duplicate authorization, code coherence, and whether authorization is
required at all. Pure functions, no model. Verdict assembly under a written
precedence order.

**Why.** A model asked whether a policy was active on a date, or how much of a
limit remains, does date arithmetic and subtraction in prose — fluently, and
wrong some fraction of the time. Two of the baseline's four failure patterns
(partial entitlement, contractual exclusion) are arithmetic and precedence
problems that have exactly one correct answer derivable from a record.

Two orderings carry most of the safety argument:

- **A contractual exclusion outranks medical necessity**, so a persuasive
  narrative cannot buy uncovered coverage.
- **A coding error outranks a denial**, so a mistyped diagnosis pends.

**Evidence.** All 49 gold cases run against the rules alone: every rule-decided
case produces the gold verdict citing the gold rule. 242 unit tests.

**Kept.** This is the load-bearing change. It eliminates three of the four
baseline failure patterns by construction rather than by persuasion.

---

## Iteration 2 — separate `unmet` from `no_evidence`

**Tried.** The necessity judgment returns one of three statuses per criterion,
not two: `met`, `unmet` (the record contradicts it), `no_evidence` (the record
is silent). Only `unmet` supports a denial; `no_evidence` produces a pend that
names the missing document.

**Why.** The baseline's `necessity_no_evidence` failures were denials issued
because a narrative did not mention conservative therapy. Nothing contradicted
the criterion. The provider had simply not attached the notes.

**Evidence.** `necessity_no_evidence` went from 0% (baseline denied both) to
67% correct.

**Kept.** This is the distinction the whole system is organised around, and
the one most likely to matter to a real member.

---

## Iteration 3 — requirements and exceptions are different things

**Tried.** Every policy clause carries a role: `criterion`, `exception`,
`scope`, or `note`. Only criteria are things the documentation must establish.
An `exception` — a red-flag clause — *waives* the criteria when it applies.
Scope and notes are not assessed at all.

**Why this was needed.** The first full run scored **67.3%, below the
baseline**. Diagnosis: 11 of 14 misses were the same failure, and it was mine,
not the model's. I was passing the entire policy document as if every clause
were a required criterion — including the scope preamble, the closing note, and
the red-flag exception. The adjudicator correctly reported "no red flags
documented" as `no_evidence`, and my assembler then pended the case.

Absence of a red flag is the ordinary condition of nearly every request. I had
built a system that pended every clean approval for failing to document an
emergency it did not have.

**Evidence.** Verdict accuracy on the first 30 cases went from 67.3% to
**100%**, and to 91.8% across all 49.

**Kept.** The single largest measured improvement in the project.

**What it taught.** The bug was invisible in the unit tests, which fed
synthetic judgments, and invisible in the code, which read correctly. It was
only visible in the *scenario breakdown* of a failing run — eleven cases
failing identically on the same clause id. Aggregate accuracy said "the model
is bad at approvals". The per-scenario table said "you are asking it the wrong
question."

---

## Iteration 4 — calibrate identity resolution

**Tried.** A unique match on surname *and* exact date of birth scores 0.97,
rising from 0.90. Both names matching scores higher than surname alone.

**Why.** `illegible_member_id` cases were pending. The extractor did the right
thing — it reported the smudged digit as `?` rather than guessing — and the
name-plus-date-of-birth fallback resolved the member correctly. Then my
`ENTITY_MATCH_FLOOR` of 0.92 threw the match away.

The threshold was miscalibrated. Two independent identifiers agreeing uniquely
is stronger evidence than a member id read in isolation, because a transposed
digit lands silently on a real and entirely different person, whereas an exact
surname-plus-date-of-birth collision does not.

**Evidence.** Both `illegible_member_id` cases now resolve and approve
correctly, with the extractor still refusing to guess the digit.

**Kept.**

---

## Iteration 5 — repair the benchmark, twice

Two changes that made the comparison *less* flattering to this project. Both
were necessary.

**5a. The baseline was being scored on formatting.** It initially returned 0%
reason accuracy. Inspection showed it was substantively right — "coverage
terminated", "PLN-HMO-CORE waiting_period_days" — but answering in prose while
the grader compared against rule identifiers. That measured formatting
compliance, not reasoning. Giving the baseline the same rule catalogue the
pipeline is held to moved it from 0% to **69.4%**, cutting the reason-accuracy
gap from 47 points to 4.

**5b. The harness was truncating the baseline.** Three of 49 baseline
responses hit `max_tokens` mid-JSON and were scored as failures. Those were the
harness's fault. Raising the ceiling removed them.

**Net effect on the story.** The baseline's *verdict* accuracy moved 77.6% →
71.4% once it was required to name a governing rule, and its reason accuracy
went 0% → 69.4%. The measured improvement shrank substantially. That is the
correct number.

**Kept.** A benchmark that flatters the thing being benchmarked is not
evidence.

---

## Removed: nothing, but one thing was never built

**Vector search over the policy corpus.** The conventional move, and it was
rejected on inspection rather than after measurement — an experiment I chose
not to run and should say so plainly.

Medical policies are written to look alike. Every one contains a
near-identically phrased "failure of conservative management" clause. Embedding
search across the corpus retrieves the *knee* policy's criterion when
adjudicating a *spine* request: the clinical language is similar, the
thresholds are not. And the payer already knows which policy governs CPT 72148,
because that mapping is a maintained business record.

So the procedure code selects the document deterministically and BM25 ranks
clauses within it. Retrieval never varies between runs, which means a change in
results is always attributable to something we actually changed.

The honest caveat: **this was reasoned, not measured.** A fair test would run
both retrieval strategies over the same cases. I did not have the time.

---

## Where it still fails

Four of 49 cases, and they are worth naming individually.

| Case | Scenario | Expected | Produced | What went wrong |
|---|---|---|---|---|
| CASE-034 | `necessity_no_evidence` | pended | denied | The model marked a criterion `unmet` where the record was merely silent — the exact confusion iteration 2 targets, still occurring about a third of the time |
| CASE-038 | `necessity_borderline` | pended | denied | Genuinely ambiguous case; the model resolved it rather than escalating |
| CASE-042 | `always_review_specialty_drug` | approved | pended | Over-cautious on an oncology agent |
| CASE-043 | `always_review_specialty_drug` | approved | pended | Member resolution failed (R2) |

**The main failure mode: `unmet` and `no_evidence` still blur under pressure.**
Two of the four remaining misses are that distinction breaking down, and both
produce a denial where a pend was correct. It is the same failure the baseline
made — reduced from 6 occurrences to 2, but not eliminated by a prompt
instruction alone.

The fix is probably structural rather than another instruction: require a
verbatim quote before permitting `unmet`, the way `met` already requires one.
If the model cannot quote the sentence that contradicts the criterion, it
should not be able to claim contradiction. Untested — the deadline arrived
first.

---

## Hot take

**Aggregate accuracy is where agent bugs go to hide, and it will happily hide
yours from you.**

The most expensive mistake in this project scored as a broad, unremarkable
capability gap. 67.3% verdict accuracy, below baseline, spread across the
approval-shaped cases. Every instinct that number produces is wrong: tune the
prompt, try a stronger model, add examples. I would have spent the remaining
time doing exactly that.

The per-scenario table said something completely different. Eleven cases
failing *identically*, all citing `MP-IMG-001#5`. Not a capability gap — a
question I should never have asked. I was requiring the model to prove the
absence of a medical emergency before it could approve a routine MRI.

The lesson generalises past this project: **an agent's failures should be
grouped by what you asked it, not counted by whether it was right.** A single
accuracy number is an average over questions of different kinds, and averaging
destroys exactly the signal that tells you which kind is broken. Build the
per-category breakdown before you build the agent, because the first time your
system underperforms you will otherwise reach for the model when the bug is in
your prompt assembly.

The corollary, and the reason both error types are reported separately
throughout: this system's job is not to be right. It is to be *wrong in the
recoverable direction*. It ends with zero false approvals and two false
denials, and if I had another day I would spend all of it on those two — not
on the accuracy figure.
