# Meridian — prior authorization with a clinician in the loop

An agentic system that clears a utilization-review nurse's prior-authorization
queue: it reads the submitted form, checks the member's coverage against the
payer's records, judges the clinical documentation against the governing
medical policy, and arrives at the nurse's desk with the evidence packet
already assembled — every fact traced to the record it came from.

It does not decide anything on its own that matters. **No denial is ever issued
without a clinician's name on it.**

```bash
make demo      # stack, data, evaluation, review queue — about three minutes
make console   # http://localhost:8080
```

No API key required. No cloud account. No GPU. See [REPRODUCTION.md](REPRODUCTION.md).

---

## Who has this problem

A **utilization-review nurse at a mid-size US health plan**. They open a queue
each morning holding forty to sixty prior-authorization requests, most arriving
as faxes and scans.

For each one they open the document, transcribe the member and provider
identifiers into the claims system, and then look up — one screen at a time —
whether the policy was active on the date of service, whether the waiting
period had elapsed, whether the plan covers the benefit category, whether the
provider is in network and in the service area, whether the annual limit still
has room, whether an identical authorization already exists, and whether the
diagnosis even supports the procedure code.

Only then do they read the clinical narrative and decide whether it meets the
policy criteria.

**The bottleneck is not the clinical judgment.** It is the twenty minutes of
clerical assembly that precedes ninety seconds of expertise. A licensed
clinician spends most of the day as a data-entry operator, and meanwhile the
request sits in a queue — a patient waiting on an MRI is waiting on paperwork,
not on medicine.

Two consequences make this worth solving rather than merely annoying. Reviewers
under queue pressure deny for administrative reasons: the note did not mention
conservative therapy, so it comes back denied rather than returned for the
note. And because the assembly is manual, two nurses working the same case can
reach different answers.

**What this system changes:** the agent does not decide. It assembles. The
nurse's time moves from gathering evidence to judging it.

---

## Results

Over 49 labelled cases, against a single-prompt baseline given the same
documents, the same records, and the same policy text.

| Metric | Simple baseline | Agent pipeline | Change |
|---|---:|---:|---:|
| Verdict accuracy | 71.4% | **91.8%** | **+20.4 pp** |
| Reason accuracy | 69.4% | 73.5% | +4.1 pp |
| **False denials** | 6 (12.2%) | **2 (4.1%)** | **−4** |
| **False approvals** | 5 (10.2%) | **0 (0.0%)** | **−5** |
| Field extraction accuracy | not produced | 96.6% | — |
| Settled without an adjudication call | 0 | 22 of 49 | — |
| Mean cost per case | $0.0225 | $0.0598 | +$0.037 |
| Mean latency | 7.3 s | 25.3 s | +18 s |

It costs **2.7× more** and takes **3.5× longer**. Stated first, because that is
the trade: it buys twenty points of accuracy and removes every false approval.

Full breakdown in [`eval/reports/comparison.md`](eval/reports/comparison.md).
The story of how it got there — including the iteration that scored *below*
baseline — is in [CHANGELOG_IMPROVEMENT.md](CHANGELOG_IMPROVEMENT.md).

**Two caveats, up front.** The case mix is a stress set built for failure-mode
coverage: 22 of 49 are denials where real prior auth approves roughly 85%.
Accuracy here measures robustness, not production performance. And the baseline
is handed the correct member and provider records while the pipeline must
resolve them from the document — the comparison is conservative.

---

## How it works

Twelve stages. **The model touches three of them.**

```
  intake ─► EXTRACT ─► resolve ─► gather facts ─► 9 rules ──┬─► no auth needed ──────────► issue
                                                            ├─► hard stop ─► deny ─► nurse
                                                            └─► retrieve criteria
                                                                      │
                                                                      ▼
                                                              JUDGE NECESSITY
                                                                      │
                                                                assemble verdict
                                                                      │
                                                                    VERIFY
                                                                      │
                                                                release gate ─► nurse ─► issue
```

Capitalised stages are the model. Everything else is code.

### The bet: the model never decides eligibility

Ask a language model whether a policy was active on a date, or how much of a
benefit limit remains, and it will do date arithmetic and subtraction in
natural language — fluently, with an explanation attached, and wrong some
fraction of the time. In prior authorization that is not a rounding error. It
is a member denied an MRI because a model subtracted 4,200 from 15,000 and got
9,800.

So the split is by **the nature of the question, not its difficulty**. Lookups,
comparisons, date intervals and sums are code. Only reading prose and forming a
judgment goes to a model.

Nine deterministic rules cover eligibility, waiting period, benefit exclusion,
service area, provider standing, benefit balance, duplicate authorization, code
coherence, and whether authorization is required at all. Each returns
pass / fail / unknown **plus the record identifiers it consulted**, so the
console can show `policy PLN-HMO-CORE, termination 07/31/2026` rather than an
assertion the nurse has to trust. A rule that cannot find its record returns
`unknown`, never `pass` — absence of evidence is not evidence of eligibility.

### Precedence is written down, not inferred

Two orderings carry most of the safety argument:

- **A contractual exclusion outranks medical necessity.** A persuasive
  narrative cannot buy coverage the plan does not sell. The baseline failed
  exactly here, three times.
- **A coding error outranks a denial.** A mistyped diagnosis produces a
  correction request, not an adverse determination the member must appeal.

### `unmet` is not `no_evidence`

The distinction the system is built around. **Unmet** means the record
contradicts the criterion — that supports a denial. **No evidence** means the
documentation is silent — that supports a request for the missing document.

A member whose provider forgot to attach the physical-therapy notes has not
failed the criterion. Denying them is denying care for a paperwork reason, and
it is the single most common way an automated utilization system harms someone.

### `no_auth_required` is not `approved`

A procedure that never needed authorization has not been adjudicated for
medical necessity. Recording it as an approval creates a phantom authorization
that can be cited later in a claims dispute as though the payer reviewed and
blessed the service. It is a distinct verdict with its own letter, and it exits
in one model call.

### The release gate

Policy, not judgment. An approval auto-releases only when every rule passed,
every field cleared the confidence floor, the verification pass found no
uncited claim, the amount is under the ceiling, and the procedure is not on the
always-review list.

**Denials never auto-release.** That is a module constant, not a setting.

---

## Agents

Three, and an orchestrator that is deliberately not one.

| Agent | Sees | Deliberately does not see |
|---|---|---|
| `intake_extractor` | The page image | Anything about the member or the policy |
| `adjudicator` | Policy criteria + the clinical narrative | Eligibility, balances, network, dates |
| `reviewer_critic` | The claims and the evidence supplied | Why the adjudicator believed anything |

The adjudicator is not shown the member record or benefit balances. Feeding
them in would invite it to re-litigate arithmetic that is already correct, and
let a lapsed policy colour a clinical judgment that should be independent of
it. The critic runs in a fresh context because an auditor who watched the
reasoning happen inherits its assumptions.

**The orchestrator is a state machine.** Twelve stages, fixed order, explicit
branches. An LLM router here would be slower, costlier, non-deterministic and
unreproducible, in exchange for nothing — there is no ambiguity about what
follows "gather facts".

Agent instructions are version-controlled markdown at
[`agents/*/prompt.md`](agents/), so prompt iterations are diffable.

### Where the cost goes

**22 of 49 cases reach a determination without ever paying for an
adjudication** — 3 because the procedure never required authorization, 19
because a contractual or eligibility rule stopped them, where medical necessity
is irrelevant and assessing it anyway would be waste with a clinical risk
attached.

---

## Retrieval

The procedure code selects the governing policy document from a maintained
business record; retrieval only ranks clauses *within* it.

Vector search across the corpus would be the conventional move and it is wrong
here. Medical policies are written to look alike — every one carries a
near-identically phrased "failure of conservative management" clause — so
nearest-neighbour search retrieves the *knee* policy's criterion when
adjudicating a *spine* request. The clinical language is similar; the
thresholds are not.

The necessity judgment receives the **complete** criteria list, never the top-k
most similar to the narrative. The criterion a narrative fails to mention is
precisely the one least similar to it, so a similarity cut-off would drop the
criterion most likely to matter and turn a pend into an approval.

---

## The reviewer console

`make console` → <http://localhost:8080>

Built on one principle: **a reviewer cannot verify a verdict, only evidence.**
So the recommendation is never the first thing on the page.

- **Left** — the submitted document, with every extracted field overlaid on the
  page region it was read from. Click a value to locate it.
- **Centre** — the nine checks, each expanding to the exact records and values
  consulted; then the policy criteria with the narrative quoted verbatim
  against each one.
- **Right** — the recommendation, what the agent was *uncertain* about, why the
  case was routed to a human, and the sign-off. An override requires a reason.

Time on case is measured in the browser, so "human minutes per determination"
is a measured figure rather than an estimate. Signing produces the
determination letter with the clinician's name, credentials, the governing
clause, and appeal rights.

---

## Data

Everything is synthetic and generated from one seed. No real patient data.

`make seed` produces 240 members, 109 providers, a 68-clause policy corpus, and
49 labelled cases across five document conditions — clean PDF, flatbed scan,
low-resolution fax with thermal streaking, phone photograph, and a form with
the member id filled in by hand.

Labels are derived from the record state the generator just created, so they
are correct by construction rather than by annotation, and are computed
*without* consulting the policy prose the retriever later sees. Codes are real
CPT/HCPCS and ICD-10-CM values with their actual descriptions — the public code
vocabulary a payer operates on.

The same seed reproduces byte-identical labels and documents, verified across
separate processes.

---

## Reproducing

Every model response is committed under `eval/cache/`, so the headline result
reproduces with no API key and no spend:

```bash
make demo
```

`make test` runs 242 tests. Full guide in [REPRODUCTION.md](REPRODUCTION.md).

---

## What it does not do

- **Not clinically validated.** Graded against synthetic ground truth, not
  against decisions made by practising utilization-review nurses.
- **One form layout.** Five document conditions, but a single template.
- **Sixteen procedures, three plans.** Enough to exercise every rule; not a
  benefit catalogue.
- **No appeals or resubmission cycle.** Pends name what is missing, but nothing
  re-adjudicates on receipt.
- **`infra/` is unapplied.** Terraform and Kubernetes manifests are a
  demonstration of the deployment path, not the reproduction path, and were
  never run against a cloud account.

The main failure mode, and the hot take about how it hid, are at the end of
[CHANGELOG_IMPROVEMENT.md](CHANGELOG_IMPROVEMENT.md).

---

## Layout

```
packages/core/        domain contracts, records, repository, retrieval
packages/rules/       the nine rules and verdict assembly — no model
packages/orchestrator/ the twelve-stage state machine
agents/               three agents, prompts in version control
eval/                 gold cases, baseline, harness, committed reports
data/generator/       the seeded synthetic world
apps/reviewer_console/ the review screen and determination letter
services/worker/      queue processing
infra/                optional AWS deployment path — not applied
```
