"""Outreach drafts: one short, personalized first email per decision-maker.

Grounded only in cited Crustdata data (the open job + funding facts). One batched Gemini
call per run, cached in runs/outreach_cache.json. Falls back to a deterministic template
if Gemini is unavailable. Nothing is ever sent: drafts are for copy/paste only.
"""
import hashlib
import json

import neatlogs

import agent

OUTREACH_CACHE = agent.RUNS_DIR / "outreach_cache.json"
MAX_PEOPLE = 12


def _money(v):
    return f"${v / 1e6:.0f}M" if isinstance(v, (int, float)) and v else None


def build_inputs(state: dict) -> list:
    """One entry per decision-maker, with only the facts we can cite."""
    out = []
    for c in state.get("evidence") or []:
        job = next((j for j in c.get("jobs", []) if j.get("url")), None)
        if not job:
            continue
        f = c.get("firmographics") or {}
        facts = [{"fact": f"{c['name']} is hiring: {job['title']}", "source": job["url"]}]
        rnd = f.get("last_round_type") or c.get("last_round")
        if rnd:
            amt = _money(f.get("last_round_amount_usd"))
            when = f.get("last_fundraise_date")
            txt = f"Last round: {rnd.replace('_', ' ').title()}" + (f" ({amt})" if amt else "") + (f", {when}" if when else "")
            facts.append({"fact": txt, "source": f.get("source") or f"Crustdata job record ({c['name']})"})
        for p in c.get("people", []):
            if p.get("name"):
                out.append({"person": p["name"], "title": p.get("title") or "", "profile": p.get("url"),
                            "company": c["name"], "facts": facts})
    return out[:MAX_PEOPLE]


def template_email(x: dict, role: str) -> dict:
    first = (x["person"] or "there").split()[0]
    job = x["facts"][0]["fact"].split("hiring: ", 1)[-1]
    fund = next((f["fact"] for f in x["facts"][1:]), None)
    body = (f"Hi {first},\n\nI saw {x['company']} is hiring a {job}"
            + (f" (and congrats on the {fund.split(': ', 1)[-1]} raise)" if fund else "") + ". "
            f"We help teams like yours find and reach strong {role} candidates faster.\n\n"
            "Would a short call next week be useful?\n\nBest,\n<your name>")
    return {"person": x["person"], "company": x["company"], "subject": f"Your {job} search at {x['company']}",
            "body": body, "sources": [f["source"] for f in x["facts"]], "generated_by": "template"}


@neatlogs.span(kind="AGENT", name="outreach_writer", role="Drafts grounded first emails (never sends)")
def draft(state: dict) -> dict:
    inputs = build_inputs(state)
    if not inputs:
        return {"emails": [], "mode": "none", "note": "No decision-makers with cited facts."}
    role = state.get("role", "")
    key = hashlib.sha256(json.dumps([role, inputs], sort_keys=True).encode()).hexdigest()
    cache = agent._read_json(OUTREACH_CACHE)
    if key in cache:
        agent.emit("tools", "  (outreach cache hit, 0 LLM calls)")
        return {**cache[key], "cached": True}
    prompt = f"""Write one short, personalized first email (max 90 words) for each person below.
Context: the sender helps companies hire for the role "{role}".
Use ONLY the facts provided for that person; do not invent anything (no metrics, names or news
that are not in the facts). Mention the open job; mention funding only if a funding fact is given.
Friendly, specific, one clear ask. Sign off with "<your name>".
Return JSON: {{"emails": [{{"person": str, "company": str, "subject": str, "body": str,
"sources": [str]}}]}} where sources are copied verbatim from the facts you used.

PEOPLE:
{json.dumps(inputs, indent=1)}
"""
    try:
        out = agent.ask_json(prompt)
        emails = out.get("emails") or []
        allowed = {f["source"] for x in inputs for f in x["facts"]}
        for e in emails:
            e["sources"] = [s for s in e.get("sources") or [] if s in allowed]
            e["generated_by"] = "gemini"
        result = {"emails": emails, "mode": "gemini"}
    except RuntimeError as e:
        agent.recover_event("outreach_template_fallback", reason=str(e)[:200])
        result = {"emails": [template_email(x, role) for x in inputs], "mode": "template"}
    cache[key] = result
    agent._write_json(OUTREACH_CACHE, cache)
    return result
