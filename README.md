# neathack-agent

neathack-agent is a hiring-signal scout built for neatHack 2026. Give it a market (e.g. Series A–B AI infra in the Bay Area) and a role, and it returns a ranked list of companies hiring for that role, key decision-makers, and a source for every claim. Built with Crustdata (data), neatlogs (tracing), Entire (checkpoints), and cfo.ai (unit economics).

## How it works

`plan` (Gemini turns the market + role into search filters) → `tools` (Crustdata Job Search + Person Search, capped at 10 jobs and 5 people × 3 companies) → `state` (saved to `runs/<timestamp>.json`) → `recover` (broadens filters on empty results or errors) → `verify` (Gemini plus a code check drop any claim without a Crustdata source URL) → markdown report in `runs/<timestamp>.md`. Every LLM call and tool call is traced in neatlogs.

## Run it

Put your keys in a `.env` file in the repo root (see `.env.example`): `NEATLOGS_API_KEY`, `CRUSTDATA_API_KEY`, `GEMINI_API_KEY`.

```
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && set -a && source .env && set +a && python -m neatlogs doctor --probe && python agent.py --dry-run "Series A AI infra Bay Area" "backend engineer"
```

`--dry-run` uses mock company data, so it spends no Crustdata credits (Gemini and neatlogs still run). Drop the flag for a live run (about 0.3–1 Crustdata credits). Crustdata responses are cached in `runs/crustdata_cache.json`, so repeating the same search costs 0 credits. Gemini calls retry with backoff (5s/15s/30s) on 429/5xx, then fall back to `GEMINI_FALLBACK_MODEL`; if verification still fails, the report is built from a code-only source check and marked "LLM verify unavailable".

### Deep mode and credit cap

```
python agent.py --deep "Series A AI infra Bay Area" "backend engineer"
```

`--deep` also calls Crustdata `/company/enrich` (headcount, 6-month/YoY headcount growth, total funding, last round) for the top `--deep-n` companies (default 5, about 2 credits each), shown in the report with the source. Every run prints estimated and actual Crustdata credits (actual comes from the `X-Credits-Used` header) and saves them as `credits_spent` in `runs/<timestamp>.json`. `--max-credits` (default 15) skips any paid call that would push the estimate over the cap. Decision-makers are looked up by the company's Crustdata ID first, then its website domain, then its name.

### Caching, --replan and --no-spend

- The plan Gemini makes for a market + role (ignoring case and extra spaces) is saved in `runs/plan_cache.json` and reused on reruns, together with its job-date window. That keeps the Crustdata requests identical, so they come from `runs/crustdata_cache.json`. Use `--replan` to force a new plan.
- Decision-makers and `--deep` company data are also cached per Crustdata company ID in `runs/entity_cache.json`, so a company found under a different plan is not paid for again.
- `--no-spend` uses cached data only and skips every paid Crustdata call that is not cached (0 credits).
- Each run prints cache hits, paid calls and calls skipped by `--no-spend`, and saves them as `cache_stats` in `runs/<timestamp>.json`.

## Demo web app (local)

```bash
pip install -r requirements.txt
python app.py
# then open http://localhost:8000
```

- Form: market, role, **Deep**, **No-spend** (cache only, 0 credits), **Dry run** (mock data), **Replan**,
  and **Simulate Gemini failure** (forces fake 503s on the first N Gemini calls so `[recover]` retries /
  fallback model show on camera; labeled `SIMULATED` in the timeline and as a `SIMULATED_gemini_503` span in neatlogs).
- Live timeline of the agent loop (plan → tools → state → recover → verify → report) over server-sent events.
- Report as company cards (jobs with links, decision-makers with LinkedIn links, firmographics) + dropped-claims panel.
- Cost meter: Crustdata credits spent, cache hits, est. COGS vs suggested price ($12 deep / $3 standard) and margin
  (credit $ is an assumption, see `docs/unit-economics.md`).
- **Outreach drafts**: one short first email per decision-maker, grounded only in the cited job + funding facts.
  One batched Gemini call, cached in `runs/outreach_cache.json`, template fallback if Gemini is down.
  Drafts only: nothing is ever sent. Use the Copy button.
- Trace link: “Open neatlogs traces” (top right) → app.neatlogs.com, workflow `hiring_signal_scout`.

CLI equivalent of the failure simulation: `python agent.py "<market>" "<role>" --no-spend --simulate-failures 2`.
