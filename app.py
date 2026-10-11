"""Local demo web app for the hiring-signal scout.

    python app.py      # then open http://localhost:8000

Streams the agent loop (plan -> tools -> state -> recover -> verify) live over
server-sent events, renders the report as cards, shows a cost meter, and drafts
outreach emails (drafts only, nothing is ever sent).
"""
import json
import queue
import threading
import time
from pathlib import Path

import agent  # initialises neatlogs before any LLM import
import neatlogs
import outreach
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

ROOT = Path(__file__).parent
CREDIT_USD = 0.10          # cfo.ai base case ($/Crustdata credit, assumption)
CREDIT_USD_DOWNSIDE = 0.20 # cfo.ai downside case
LLM_USD = {"deep": 0.10, "standard": 0.05}
PRICE_USD = {"deep": 12.0, "standard": 3.0}   # pay-as-you-go per report
DEEP_FLOOR_80PCT = 12.62   # cfo.ai downside: min deep price for 80% GM from Jan 2027
PLANS = "Starter $149/mo (150 standard + 7 deep) · Team $499/mo (600 standard + 18 deep)"
NEATLOGS_URL = "https://app.neatlogs.com"

app = FastAPI(title="Hiring-signal scout")
RUN_LOCK = threading.Lock()
RESULTS: dict = {}


def economics(state: dict) -> dict:
    kind = "deep" if state.get("deep") else "standard"
    credits = float(state.get("credits_spent") or 0)
    crust = credits * CREDIT_USD
    llm = LLM_USD[kind]
    cogs = crust + llm
    cogs_down = credits * CREDIT_USD_DOWNSIDE + llm
    price = PRICE_USD[kind]
    return {"kind": kind, "credits_spent": round(credits, 3),
            "credits_estimated": state.get("credits_estimated"),
            "cache": state.get("cache_stats") or {}, "credit_usd_assumption": CREDIT_USD,
            "credit_usd_downside": CREDIT_USD_DOWNSIDE,
            "crustdata_usd": round(crust, 3), "llm_usd": llm, "cogs_usd": round(cogs, 3),
            "cogs_downside_usd": round(cogs_down, 3),
            "price_usd": price, "margin_pct": round(100 * (price - cogs) / price, 1),
            "margin_downside_pct": round(100 * (price - cogs_down) / price, 1),
            "plans": PLANS, "deep_floor_80pct": DEEP_FLOOR_80PCT,
            "full_cost_note": ("Fresh deep run measured 12.12 credits: ~$1.31 COGS at $0.10/credit, ~$2.52 at $0.20. "
                               "Cached reruns cost $0 in Crustdata.")}


def summarize(state: dict) -> dict:
    res = state.get("result") or {}
    ev = state.get("evidence") or []
    firmo = res.get("_firmo") or {}

    def find(c):
        for e in ev:
            if (c.get("domain") and c.get("domain") == e.get("domain")) or c.get("name") == e.get("name"):
                return e
        return {}
    cards = []
    for c in sorted(res.get("companies", []), key=lambda x: x.get("rank", 99)):
        e = find(c)
        cards.append({"rank": c.get("rank"), "name": c.get("name"), "domain": c.get("domain") or e.get("domain"),
                      "why": c.get("why"), "claims": c.get("claims", []),
                      "jobs": e.get("jobs", []),
                      "people": c.get("decision_makers") or [
                          {"name": p.get("name"), "title": p.get("title"), "source": p.get("url")} for p in e.get("people", [])],
                      "firmographics": firmo.get(c.get("name")) or e.get("firmographics"),
                      "headcount": e.get("headcount"), "last_round": e.get("last_round"),
                      "people_status": e.get("people_status"),
                      "people_label": agent.PEOPLE_STATUS_LABEL.get(e.get("people_status") or "none_found"),
                      "market_fit": next((f["reason"] for f in res.get("market_fit") or []
                                          if f.get("name") == c.get("name")), None),
                      "grounding": c.get("grounding"),
                      "fit_status": next((f.get("status") for f in res.get("market_fit") or []
                                          if f.get("name") == c.get("name")), None)})
    return {"run_id": state.get("run_id"), "market": state.get("market"), "role": state.get("role"),
            "dry_run": state.get("dry_run"), "llm_verify": res.get("llm_verify", True),
            "plan": state.get("plan"), "plan_source": state.get("plan_source"),
            "cards": cards, "dropped": res.get("dropped", []),
            "recovery_events": state.get("recovery_events", []),
            "economics": economics(state), "grounding": res.get("grounding"), "neatlogs_url": NEATLOGS_URL,
            "report_md": agent.LAST_RUN.get("report")}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/run")
def run_stream(market: str, role: str, deep: bool = False, no_spend: bool = False,
               simulate: int = 0, dry_run: bool = False, replan: bool = False):
    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A run is already in progress")
    q: queue.Queue = queue.Queue()

    def worker():
        try:
            agent.EVENT_HOOK["fn"] = q.put
            agent.NO_SPEND["on"] = no_spend
            agent.SIMULATE["remaining"] = max(0, min(simulate, 10))
            if simulate:
                q.put({"stage": "info", "msg": f"SIMULATION ON: next {simulate} Gemini call(s) will fail with a fake 503 "
                                               "(labeled SIMULATED in neatlogs)"})
            agent.run(market, role, dry_run, deep, agent.DEEP_TOP_N_DEFAULT, replan)
            st = agent.LAST_RUN["state"]
            summary = summarize(st)
            RESULTS[st["run_id"]] = st
            q.put({"stage": "done", "msg": "done", "result": summary})
        except Exception as e:  # noqa: BLE001
            q.put({"stage": "error", "msg": f"Run failed: {e}"})
        finally:
            agent.EVENT_HOOK["fn"] = None
            agent.SIMULATE["remaining"] = 0
            agent.NO_SPEND["on"] = False
            try:
                neatlogs.flush()
            except Exception:  # noqa: BLE001
                pass
            q.put(None)
            RUN_LOCK.release()

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        t0 = time.time()
        while True:
            try:
                ev = q.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if ev is None:
                break
            ev.setdefault("t", round(time.time() - t0, 1))
            yield f"data: {json.dumps(ev, default=str)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/outreach/{run_id}")
def outreach_drafts(run_id: str):
    st = RESULTS.get(run_id)
    if not st:
        raise HTTPException(404, "Unknown run (restart the run first)")
    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A run is in progress")
    try:
        # exactly the decision-makers rendered on the cards
        return outreach.draft(summarize(st)["cards"], st.get("role", ""))
    finally:
        try:
            neatlogs.flush()
        except Exception:  # noqa: BLE001
            pass
        RUN_LOCK.release()


if __name__ == "__main__":
    print("Hiring-signal scout demo: open http://localhost:8000")
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
