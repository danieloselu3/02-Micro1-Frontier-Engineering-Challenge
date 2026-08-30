# Reproduction guide

Written for someone starting from a clean machine with nothing installed.

**The headline result reproduces with no API key and no spend.** Every model
response from the recorded evaluation run is committed under `eval/cache/`, and
`make eval-replay` re-runs both systems over all 49 cases from those responses.
You only need credentials if you want to re-record the run yourself.

---

## 1. Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| Docker | 28.x | Provides Postgres, Redis and MinIO. Docker Desktop is fine. |
| Python | 3.12 | 3.11 will not work — the code uses 3.12 syntax. |
| `uv` | 0.5+ | Or substitute `python -m venv` and `pip install -e ".[dev]"`. |
| Disk | ~1.5 GB | Mostly the Postgres and MinIO images. |
| Network | — | Needed once to pull images and packages. Not needed to run. |

No GPU. No cloud account. No Node toolchain — the reviewer console is
server-rendered, so there is no `npm install` between a clean clone and a
working system.

---

## 2. Set up

```bash
git clone https://github.com/danieloselu3/02-Micro1-Frontier-Engineering-Challenge.git
cd 02-Micro1-Frontier-Engineering-Challenge
make install
```

`make install` creates `.venv` and installs the project. Roughly 90 seconds.

You do **not** need to create a `.env` file to reproduce the result. The
defaults in `packages/core/config.py` match the Docker services.

---

## 3. The short path

```bash
make demo
```

That is four steps in sequence — start the stack, generate the data, replay the
evaluation, and file the results for review. It takes about three minutes,
almost all of it the first Docker image pull.

Then:

```bash
make console
```

and open <http://localhost:8080>.

The rest of this document explains what each step does and what you should see.

---

## 4. Step by step

### 4.1 Start the infrastructure

```bash
make up
```

Brings up Postgres 16 with pgvector, Redis 7, and MinIO, and waits for all
three to report healthy. The database schema loads automatically on first boot.

Verify:

```bash
docker compose ps
```

All three services should read `healthy`. If Postgres does not come up, the
usual cause is port 5432 already being in use by a local Postgres install.

### 4.2 Generate the synthetic world

```bash
make seed
```

Builds everything from seed `20260830`:

```
Members                    240
Providers                  109
Accumulators               720
Policy documents           14 (68 retrievable clauses)

Cases                      49  (36 adversarial)
Verdict mix                approved 13, denied 22, no_auth_required 3,
                           partially_approved 2, pended 9
Document tiers             clean 12, fax 13, handwritten 2, photo 11, scan 11
Eligible for auto-release  8 of 49
```

Takes about 40 seconds, most of it rendering and degrading the 49 documents.

This is deterministic. The same seed produces byte-identical labels and
byte-identical document images, verified across separate processes. If your
output differs from the block above, something is wrong — say so rather than
continuing.

The rendered forms land in `data/seeds/forms/`. They are gitignored because they
rebuild from the seed; open a few to see what the system actually reads. Try
`CASE-046.png` for the handwritten member id and any `fax` case for thermal
streaking across the fields.

### 4.3 Reproduce the evaluation

```bash
make eval-replay
```

Runs both the baseline and the full pipeline over all 49 cases using the
committed responses. No API key, no network, no cost. Under a minute.

Expected output is the two summary tables and a written comparison at
`eval/reports/comparison.md`. The committed copy of that file is what the
README cites, so you can diff your run against it.

### 4.4 Fill the review queue

```bash
make process
```

Re-runs the pipeline from the same cache and files each determination through
the ledger store. This is what the console reads. Costs nothing.

You should see 49 lines, each ending `queued` or `released`, and a summary of
how many of each.

### 4.5 Open the console

```bash
make console
```

<http://localhost:8080>

The work queue lists everything awaiting a clinician, denials first. Open any
case to see the three-column review screen: the submitted document with the
extracted fields overlaid, the nine deterministic checks with the record values
each one read, the policy criteria with the narrative quoted against them, and
the recommendation with the reasons it was routed to a human.

Click any extracted field to highlight the region of the page it was read from.

Sign a determination and you will be redirected to the letter that goes back to
the provider, carrying the reviewing clinician's name and credentials.

---

## 5. Running the tests

```bash
make test
```

Expect **242 passing**. The suite covers the domain invariants, generator
determinism and world-consistency, and every one of the 49 gold cases against
the rules engine.

Tests that need Postgres skip rather than fail when it is not running, so
`make test` works in a bare checkout — but you want the database up to
exercise the full suite.

---

## 6. Re-recording the run (optional, costs money)

Only needed if you change a prompt or want to verify the cache against fresh
model output.

```bash
cp .env.example .env
# put your key in the ANTHROPIC_API_KEY line
make eval
```

**Approximate cost: $4–8** for a full baseline plus solution pass over 49
cases, at published Sonnet and Haiku pricing. **Runtime: 35–50 minutes**,
dominated by per-request latency rather than compute.

`make eval` reuses any cached response whose request is byte-identical, so
after a prompt change you only pay for the stage that actually changed.

### A caveat on determinism

The Anthropic SDK from v1.x no longer exposes sampling controls — there is no
`temperature` parameter to pin to zero. Repeated live calls are therefore not
guaranteed identical, and the reproducibility of the committed numbers rests on
the response cache rather than on the model being deterministic.

This is why the recorded responses are checked in rather than regenerated on
demand. A re-recorded run may differ slightly from the committed one. If you
re-record, `eval/reports/comparison.md` will change, and that is expected.

---

## 7. Versions this was run on

```
Python           3.12.0
anthropic        1.2.0
pydantic         2.x
FastAPI          0.115+
Postgres         16 (pgvector/pgvector:pg16)
Docker           28.x
OS               Windows 11
Models           claude-sonnet-5 (extraction, adjudication)
                 claude-haiku-4-5-20251001 (verification)
```

The pinned dependency set is in `pyproject.toml`.

---

## 8. Troubleshooting

**`Database unreachable`** — `docker compose ps` and confirm Postgres is
healthy. If port 5432 is taken, stop the conflicting service or change the port
in `docker-compose.yml` and `DATABASE_URL`.

**`No cases found. Run make seed first.`** — `make seed` has not run, or it
failed against the database.

**`No rendered document for CASE-0xx`** — the forms directory is empty. Re-run
`make seed` without `--skip-forms`.

**`Replay miss`** — a prompt has been edited since the cache was recorded, so
the request hash no longer matches. Either revert the edit or re-record with
`make eval` and an API key.

**`ANTHROPIC_API_KEY is not set`** — you are on the live path. Use
`make eval-replay` instead if you only want to reproduce the committed result.

**Console shows an empty queue** — `make process` has not run, or it hit replay
misses. Check its output.
