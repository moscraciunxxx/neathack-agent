# neatHack submission checklist

Deadline: **Mon Oct 12, ~6:30–11:25 AM PDT**, submitted by quote-tweeting the official post on X.

## Agent finishes a real task (30%)
- [ ] Fresh live run with `--deep` on the demo market + role; `runs/<ts>.md` has companies, decision-makers and firmographics with sources
- [ ] `--no-spend` rerun works (0 paid calls) for recording
- [ ] Copy the best report into `examples/` (already has `deep-run-sample.md`; update if needed)

## Sponsor tools with proof (25%)
- [ ] **neatlogs**: trace of the demo run open; screenshot of the WORKFLOW → AGENT/LLM/TOOL spans plus a recover span
- [ ] **Entire**: checkpoint links (first: commit 4436e7a / 01M4JGPF985VEY8QKQQVS73S5V; later: b389c83 / 01M4MD82D6XQE6MYERPKEHA15R, 2c51a5f / 01M4MDNDYSKQ5VPBN6H5GRDZF1); make at least one more Cursor/Entire commit if you change code
- [ ] **cfo.ai**: plan built with the prompts in `docs/unit-economics.md`; screenshot the table, scenarios and margin answer
- [ ] Add the links/screenshots to README ("Proof" section)

## Demo video ≤ 3 min (20%)
- [x] Follow `docs/demo-script.md`; shows plan → tools → state → recover → verify
- [x] Says and shows **neatlogs, Entire and cfo.ai** explicitly
- [x] Length ≤ 3:00, no API keys visible, uploaded (X video or YouTube unlisted): https://youtu.be/pwV75xrBH1w

## Build in public (15%)
- [ ] Posts 1–4 from `docs/build-in-public.md` published Sat/Sun/Mon with #neatHack (manually, by you)
  - [x] Day 1 post
  - [x] Day 2 post
  - [ ] Mon pre-submission post

## Useful + original (10%)
- [ ] README states the problem, who it's for (recruiters, SDRs, founders hiring), and the cost per report

## Final
- [ ] Repo **public**, or judges given access
- [ ] `.env` not committed (`git status` clean; `.gitignore` has `.env`)
- [ ] README "Run it" works from a fresh clone (`--dry-run`)
- [ ] Quote-tweet the official neatHack post with the template in `docs/build-in-public.md` inside the window
- [ ] Double-check every link in the post opens in a logged-out browser
