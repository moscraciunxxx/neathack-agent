# Changelog

## 2026-10-10 — neatHack demo day

### Web app
- Local demo UI (`python app.py` → http://localhost:8000) with live SSE timeline of the agent loop (plan → tools → state → recover → verify → report).
- Company cards (jobs, decision-makers, firmographics), dropped-claims panel, cost meter, and neatlogs trace link.
- Rehearsal toggles: **No-spend** (cache-only, 0 Crustdata credits), **Dry run**, **Deep**, **Replan**, and **Simulate Gemini failure** (fake 503s so recover/fallback show on camera).

### Recover / broaden
- Visible `[recover]` events for Gemini retries, fallback model, people-search fallbacks, credit-cap / no-spend skips, and empty result handling.
- When fewer than 3 companies survive verify, automatically broaden the market (AI/ML infra, MLOps, data infra, developer tools), re-collect, and re-verify.

### Market-fit verify
- Temperature-0 market-fit pass tags each company `fit` / `off_market` / `unconfirmed`.
- Keep fit and fit-unconfirmed companies; drop only clear off-market with a stated reason.
- Soft source check: keep claims grounded by source URL or `company_id`; list every hard drop under **Dropped claims**.

### Outreach drafts
- One short first-email draft per decision-maker on the card (deduped by profile), each with a distinct cited hook from the job/funding facts.
- Batched Gemini call, cached in `runs/outreach_cache.json`, template fallback if Gemini is down; copy-only — nothing is sent.

### cfo.ai pricing
- Unit economics in `docs/unit-economics.md` updated from the cfo.ai/Ari session: standard **$3**, deep **$12** PAYG; Starter **$149**/mo (150 standard + 7 deep); Team **$499**/mo (600 + 18 deep).
- Cost meter uses cfo.ai base ($0.10/credit) and downside ($0.20/credit) assumptions; deep 80% GM floor noted at **$12.62** from Jan 2027.
