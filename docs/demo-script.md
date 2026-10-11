# Demo video script (≤ 3:00)

Goal: show the agent finishing a real task and **explicitly** show neatlogs, Entire and cfo.ai, each with proof.

## Prep (before recording)
```
cd ~/neathack-agent && git pull && source .venv/bin/activate
# rehearsal: cache only, 0 credits
python agent.py --deep --no-spend "Series A AI infra Bay Area" "backend engineer"
```
- Do a rehearsal run with the exact market + role from your last paid `--deep` run, so the `--no-spend` take is fully cached. The terminal should show `Cache: … 0 paid call(s)`.
- Open browser tabs: (1) app.neatlogs.com → the trace of this run, (2) Entire checkpoint https://entire.io/gh/moscraciunxxx/neathack-agent/commit/4436e7ae5f9edbe346f405d3aabbf0ea2efdb8ea, (3) the later Entire checkpoints for commits b389c83 ("First live run working", checkpoint 01M4MD82D6XQE6MYERPKEHA15R) and 2c51a5f (checkpoint 01M4MDNDYSKQ5VPBN6H5GRDZF1), (4) the cfo.ai plan, (5) the generated `runs/<timestamp>.md`.
- Terminal font size 18+, hide `.env`. Never show API keys.

## Shots

| Time | Shot | Say (voice-over) |
|---|---|---|
| 0:00–0:15 | Title card / README | "Hiring-signal scout: give it a market and a role, get the companies actually hiring for it, the decision-makers, and a source for every claim." |
| 0:15–0:55 | Terminal: run `python agent.py --deep --no-spend "Series A AI infra Bay Area" "backend engineer"` | Point at each stage as it prints: **1/5 plan** (Gemini turns the market into filters), **2/5 tools** (Crustdata job search), **3/5** people + deep enrich (tools), **state** (`runs/*.json`), **4/5 verify**, **5/5 report**. "Cached, so this take costs 0 credits; a fresh deep run costs about 12 Crustdata credits." |
| 0:55–1:10 | Show a `[recover]` line (from a previous run log or a live 503 take) | "**Recover**: Gemini returns 503 under load, so the agent backs off 5/15/30s, falls back to Flash-Lite, and if verify still fails it falls back to a code-only source check instead of crashing. Empty searches broaden automatically." |
| 1:10–1:35 | Open `runs/<ts>.md` | Ranked companies with job links, decision-makers, firmographics. Scroll to **Dropped claims**: "**Verify** drops anything without a Crustdata source, with the reason." |
| 1:35–2:05 | **neatlogs** trace view | "Every step is traced in **neatlogs**: the WORKFLOW root, the planner and verifier agents, each Gemini LLM span with tokens, the Crustdata TOOL spans, and the recover events." Click one TOOL span, then one LLM span. |
| 2:05–2:30 | **Entire** checkpoint pages | "Every AI-written commit is checkpointed with **Entire**: here's the first one, checkpoint 01M4JGPF…, and the later live-run commits, so judges can see the session behind each change." |
| 2:30–2:55 | **cfo.ai** plan | "Unit economics with **cfo.ai**'s Ari: deep report COGS is about $1.31 (12.12 credits plus LLM). Priced at $12 per report or $149/$499 per month, that's ~80% gross margin and cash-positive from month 3. Here's the downside scenario." |
| 2:55–3:00 | End card | Repo link + #neatHack |

## Exact commands shown on screen
```
python agent.py --deep --no-spend "Series A AI infra Bay Area" "backend engineer"
ls runs/
open runs/<timestamp>.md
```
Optional live (spends ~0.3–0.75 credits): `python agent.py "Seed devtools New York" "founding engineer"`.

## Recording tips
- QuickTime → New Screen Recording, or Cmd+Shift+5. Record in 2–3 takes and trim. Keep it **under 3:00**.
- Say the three sponsor names out loud when each is on screen.
