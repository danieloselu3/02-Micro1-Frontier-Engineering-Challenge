# Micro1 Frontier Engineering Challenge 2026

- Platform: [hackerearth.com](https://www.hackerearth.com/challenges/hackathon/micro1-frontier-engineering-challenge-2026/)
- Org: micro1 x HackerEarth
- Format: Online, solo, daily 6–9 PM Africa/Nairobi (3–6 PM UTC) window
- Window: Aug 28 – Aug 31, 2026
  - Aug 28, 15:00 UTC: Kickoff — full problem PDF released
  - Aug 31, 18:00 UTC: Submissions close
- Team size: 1 (individual only, no teams)
- Contact: Yeison Cruz, yeison@micro1.ai

## Theme
Build at the frontier of agentic AI — use coding agents to tackle a real-world
engineering problem where correctness, reproducibility, and human judgment matter.
Any industry/domain is fair game.

Every valid entry needs **both**:
- a baseline solution
- an advanced solution showing meaningful improvement (capability, reliability,
  efficiency, coverage, or engineering quality — not cosmetic)

## Tech policy
- Recommended: Python, TypeScript, Java, C++, Go, Rust (others allowed if reproducible)
- Coding-agent use is REQUIRED — must disclose tools used + submit agent trajectories
- No API keys/credits provided — bring your own agent setup
- Problem PDF may prescribe a starter repo, runtime, dependency limits, or test env

## Prizes
$10,000 cash (three selective awards) + up to 50 paid opportunities with micro1
(subject to technical verification). Optional separate trace-acquisition program
($2–$15/trace, capped $100–$200/participant) — not part of prize pool, not guaranteed.

## Eligibility
- 18+ at registration
- Global, except where prohibited by law/sanctions/export controls
- Individual only — one registration, one final submission (revisions allowed until deadline)
- ~6 months practical software-building experience (employment not required)
- Must be able to receive payout via approved rail in your country for cash prizes

## Evaluation (scored /100)
Qualification gate first (eligibility, completeness, integrity, trace, reproducibility —
fail this and you're disqualified before scoring). Then scored + tie-broken in this order:
1. Agent Solution & Engineering
2. Reproducibility
3. Measured Improvement
4. End-to-End Quality
Final panel review of documented evidence is binding.

## Submission package (5 parts)
1. **Code + Improvement Changelog** — full project incl. agent instructions. README
   introduces the intended user, their bottleneck, why it matters. Changelog has one
   entry per meaningful iteration tied to evidence, ends with main failure mode + hot take.
2. **Reproduction guide** — clean-environment setup, exact commands for baseline/
   solution/eval, required data, expected output, versions, runtime/cost.
3. **Solution video (≤5 min)** — problem → baseline → one real end-to-end run →
   comparison → changelog highlights (what helped most, what you cut).
4. **Agent trajectories** — representative traces per agent used: tool calls, tool
   responses, feedback that shaped next steps, retries/human checkpoints.
5. Rule Book compliance (sandbox consequential actions + human approval, legal/ethical
   use case, no credentials in submission, every claim backed by evidence).

Note: submissions are governed by the Hackathon Participation Agreement — micro1 owns
submissions and may use them for AI model training/evaluation.

## Deliverables checklist
- [ ] Register on HackerEarth (must be done by the user — account creation)
- [ ] Read the full problem PDF released at kickoff
- [ ] Pick language/stack + coding agent(s) to use
- [ ] Build baseline solution
- [ ] Build advanced solution with measurable improvement
- [ ] Write README (user/bottleneck/value) + Improvement Changelog
- [ ] Write reproduction guide (clean-env setup, commands, expected output)
- [ ] Record ≤5 min solution video
- [ ] Collect/export agent trajectories for every agent used
- [ ] Final review against Rule Book (no secrets, licensed tools, sandboxed actions)
- [ ] Submit before Aug 31, 18:00 UTC

## Getting started

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash; use .venv\Scripts\activate on cmd/PowerShell
pip install -r requirements.txt
python src/main.py
```

## Notes
Live now — problem PDF not yet reviewed by user. Update this file once the actual
problem statement is available.
