# Demo video script (≤ 3:00)

Goal: show the agent finishing a real task, then give **neatlogs, Entire and cfo.ai one ~25 s segment each**. Each segment covers the same five beats: **architecture → implementation → runtime → reasoning → result**.

## Prep (before recording)
```
cd ~/neathack-agent && git pull && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # open http://localhost:8000
```
- Use the market + role from your last paid deep run (e.g. `Series A AI infra Bay Area` / `backend engineer`), so a **No-spend** run is fully cached (cost meter shows 0 paid calls).
- Tabs, in order: (1) the app, (2) app.neatlogs.com with the trace of the run you will show, (3) Entire: https://entire.io/gh/moscraciunxxx/neathack-agent/commit/4436e7ae5f9edbe346f405d3aabbf0ea2efdb8ea plus the later checkpoints in `docs/EVIDENCE.md`, (4) the cfo.ai (Ari) plan with the scenario table, (5) `docs/EVIDENCE.md` on GitHub.
- Terminal/browser zoom 125%+. Never show `.env` or API keys.

## Shots (total 3:00)

| Time | Shot | Say (voice-over) |
|---|---|---|
| 0:00–0:20 | **Problem / value**: README "For judges" | "Sales and recruiting reps waste hours finding who is *actually* hiring and who owns the hire. Hiring-signal scout takes a market and a role and returns companies hiring now, their decision-makers, a grounded first email, and a source for every claim. A fresh deep report costs about $1.31–$1.38 to make and sells for $12 (a cached rerun is ~$0.10)." |
| 0:20–1:30 | **The agent doing the task**: app, Deep + No-spend + *Simulate Gemini failure = 2*, Run | Follow the timeline chips. **plan**: Gemini turns the market into Crustdata filters (cached per market). **tools**: job search, then decision-makers and company enrich, with cache hits shown. **recover**: the orange `SIMULATED` 503s, then retry and backoff. In the real run Gemini returned 429 and we switched to Flash-Lite. With fewer than 3 companies it ran `broaden_market`. **state**: everything saved to `runs/*.json`. **verify**: market-fit judgment at temperature 0. Off-market companies are dropped with a reason (Venmo, Zed…), and Cambio is kept as *fit unconfirmed*. Show the cards, the **grounded-claims score**, the dropped panel and the cost meter. Click **Draft first emails** and show one draft with its sources. |
| 1:30–1:55 | **neatlogs**: trace view | *Architecture*: "One WORKFLOW root per run, with AGENT spans for planner, verifier and outreach writer, TOOL spans for each Crustdata call, and LLM spans for Gemini." *Implementation*: "`neatlogs.init` before the clients, `neatlogs.wrap` on the Gemini client, decorators on our functions." *Runtime*: click a TOOL span, which shows credits, then an LLM span with tokens. *Reasoning*: click a `recover:*` span: "here is the 429 and the fallback decision." *Result*: "every decision in the report is auditable." |
| 1:55–2:20 | **Entire**: checkpoint pages | *Architecture*: "Entire checkpoints every AI-written commit with the session behind it." *Implementation*: "Cursor commits carry an `Entire-Checkpoint` trailer. Here's the first one, 01M4JGPF…" *Runtime*: open the checkpoint for 2c51a5f or a8d6c08 and show the prompt and transcript. *Reasoning*: "With Entire Graph, Cursor searched the code graph to find `broaden_market`, `run` and `recover_event` before editing." *Result*: "the full build history is reviewable, not just the diff." |
| 2:20–2:45 | **cfo.ai**: Ari plan | *Architecture*: "Our measured run costs feed cfo.ai's Ari." *Implementation*: "inputs: 12.12 credits per deep run, $0.10 per credit (downside $0.20), LLM cost, plans." *Runtime*: show the base, downside and upside table. *Reasoning*: "Ari showed the downside margin breaking, so we cut deep allowances from 30 to 7 and 120 to 18. The deep price floor is $12.62 from January." *Result*: "ending cash $28.4k base, $13.9k downside, with 90% and 76% gross margin." |
| 2:45–3:00 | **Result / close**: EVIDENCE.md before/after table | "Before: 1 company kept and an invented sender. After: 4 companies kept, 8 off-market dropped with reasons, 88.5% margin on that run. Repo and evidence linked. #neatHack." |

## Exact commands shown on screen
```
python app.py
# CLI alternative (same loop, cache only, forced 503s):
python agent.py --deep --no-spend --simulate-failures 2 "Series A AI infra Bay Area" "backend engineer"
```

## Recording tips
- Record each segment as its own take and trim (QuickTime or Cmd+Shift+5). Hard cap 3:00.
- Say "neatlogs", "Entire" and "cfo.ai" out loud while each is on screen.
- The simulated 503 retries wait 5 s + 15 s. Cut that pause in editing, or start the run before the voice-over.
