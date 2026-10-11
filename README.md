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
