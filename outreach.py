"""Outreach drafts: one short, personalized first email per decision-maker.

Uses exactly the decision-makers rendered on the report cards (deduped by profile URL),
grounded only in cited Crustdata facts (open role, headcount / growth, funding round + date).
One batched Gemini call per run, cached in runs/outreach_cache.json. Deterministic template
fallback if Gemini is unavailable. Nothing is ever sent: drafts are for copy/paste only.
"""
import hashlib
import json
from datetime import date, datetime

import neatlogs

import agent

OUTREACH_CACHE = agent.RUNS_DIR / "outreach_cache.json"
MAX_PEOPLE = 15
MAX_WORDS = 90
OPENERS = ["Saw that", "Noticed", "Quick note:", "Congrats:", "Came across the fact that"]


def _money(v):
    return f"${v / 1e6:.0f}M" if isinstance(v, (int, float)) and v else None


def _months_ago(d):
    try:
        dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    m = (date.today().year - dt.year) * 12 + date.today().month - dt.month
    return "this month" if m <= 0 else f"{m} month{'s' if m != 1 else ''} ago"


def _person_key(p: dict, company: str) -> str:
    return (p.get("source") or "").strip().rstrip("/").lower() or f"{company}|{p.get('name', '')}".lower()


def company_facts(card: dict) -> list:
    """Every fact carries its source; ordered most-specific first."""
    facts = []
    jobs = [j for j in card.get("jobs") or [] if j.get("url")]
    if jobs:
        j = jobs[0]
        loc = f" ({j['location']})" if j.get("location") else ""
        facts.append({"kind": "role", "fact": f"{card['name']} has an open {j['title']} role{loc}", "source": j["url"]})
        if len(jobs) > 1:
            facts.append({"kind": "roles_count", "fact": f"{card['name']} has {len(jobs)} matching open roles",
                          "source": jobs[1]["url"]})
    f = card.get("firmographics") or {}
    fsrc = f.get("source") or f"Crustdata /company/enrich ({card['name']})"
    g6, gy = f.get("headcount_growth_6m_pct"), f.get("headcount_growth_yoy_pct")
    if isinstance(gy, (int, float)) and gy:
        facts.append({"kind": "growth", "fact": f"headcount grew {gy:.0f}% year over year", "source": fsrc})
    elif isinstance(g6, (int, float)) and g6:
        facts.append({"kind": "growth", "fact": f"headcount grew {g6:.0f}% in the last 6 months", "source": fsrc})
    hc = f.get("headcount") or card.get("headcount")
    if hc:
        facts.append({"kind": "headcount", "fact": f"{card['name']} is a team of about {hc} people",
                      "source": fsrc if f.get("headcount") else (jobs[0]["url"] if jobs else fsrc)})
    rnd = f.get("last_round_type") or card.get("last_round")
    if rnd:
        amt, when = _money(f.get("last_round_amount_usd")), f.get("last_fundraise_date")
        ago = _months_ago(when) if when else None
        txt = f"raised a {rnd.replace('_', ' ').title()}" + (f" of {amt}" if amt else "") + (f" {ago}" if ago else "")
        facts.append({"kind": "round", "fact": txt, "source": fsrc if f else (jobs[0]["url"] if jobs else fsrc)})
    return facts


def build_inputs(cards: list) -> list:
    """Exactly the decision-makers shown on the cards, deduped, each with a distinct 'hook' fact."""
    out, seen = [], set()
    for card in cards:
        facts = company_facts(card)
        if not facts:
            continue
        prio = {"growth": 0, "role": 1, "headcount": 2, "roles_count": 3}
        hooks = sorted([f for f in facts if f["kind"] in prio], key=lambda f: prio[f["kind"]]) or facts
        for i, p in enumerate(card.get("people") or []):
            k = _person_key(p, card["name"])
            if not p.get("name") or k in seen:
                continue
            seen.add(k)
            hook = hooks[i % len(hooks)]
            out.append({"id": k, "person": p["name"], "title": p.get("title") or "", "profile": p.get("source"),
                        "company": card["name"], "hook": hook, "facts": facts,
                        "opener": OPENERS[len(out) % len(OPENERS)]})
    return out[:MAX_PEOPLE]


def _trim(body: str) -> str:
    words = body.split(" ")
    return body if len(words) <= MAX_WORDS else " ".join(words[:MAX_WORDS]).rstrip(",.;") + "…"


def template_email(x: dict, role: str) -> dict:
    first = (x["person"] or "there").split()[0]
    role_f = next((f for f in x["facts"] if f["kind"] == "role"), None)
    used = [x["hook"]] + ([role_f] if role_f and role_f is not x["hook"] else [])
    hook = x["hook"]["fact"]
    hook = hook if hook.startswith(x["company"]) else f"{x['company']}'s {hook}" if hook.startswith("headcount") else f"{x['company']}: {hook}"
    body = f"Hi {first},\n\n{x['opener']} {hook}."
    if role_f and role_f is not x["hook"]:
        body += f" I also see {role_f['fact'].split(' has ', 1)[-1]}."
    rnd = next((f for f in x["facts"] if f["kind"] == "round"), None)
    if rnd and rnd is not x["hook"]:
        body += f" And congrats, you {rnd['fact']}."
        used.append(rnd)
    body += (f"\n\nAs {x['title'] or 'a leader there'}, you are likely feeling the hiring load. We help teams "
             f"find strong {role} candidates fast. Open to a 15-minute call next week?\n\nBest,\n<your name>")
    subj = f"{x['company']} + {role} hiring" if x["hook"]["kind"] != "role" else f"Your {role_f['fact'].split('open ', 1)[-1].split(' role')[0]} search"
    return {"id": x["id"], "person": x["person"], "company": x["company"], "subject": subj,
            "body": _trim(body), "sources": list(dict.fromkeys(f["source"] for f in used)), "generated_by": "template"}


@neatlogs.span(kind="AGENT", name="outreach_writer", role="Drafts grounded first emails (never sends)")
def draft(cards: list, role: str) -> dict:
    inputs = build_inputs(cards)
    if not inputs:
        return {"emails": [], "mode": "none", "note": "No decision-makers with cited facts on the cards."}
    key = hashlib.sha256(json.dumps(["v2", role, inputs], sort_keys=True).encode()).hexdigest()
    cache = agent._read_json(OUTREACH_CACHE)
    if key in cache:
        agent.emit("tools", "  (outreach cache hit, 0 LLM calls)")
        return {**cache[key], "cached": True}
    slim = [{k: x[k] for k in ("id", "person", "title", "company", "hook", "facts", "opener")} for x in inputs]
    prompt = f"""Write one short, personalized cold first email for EACH person below (exactly one per id).
Sender helps companies hire for the role "{role}".
Rules:
- Use ONLY that person's facts. Never invent numbers, news, names, products or customers.
- Lead with that person's "hook" fact (it differs per person) and start with their suggested "opener"
  phrase or a close variant; no two emails may share the same first sentence.
- Mention one other fact at most (e.g. the specific open role title). Reference their title naturally.
- Max {MAX_WORDS} words in the body, one clear ask, sign off exactly "Best,\\n<your name>".
- "sources": copy verbatim the source of every fact you used.
Return JSON: {{"emails": [{{"id": str, "subject": str, "body": str, "sources": [str]}}]}}

PEOPLE:
{json.dumps(slim, indent=1)}
"""
    by_id = {x["id"]: x for x in inputs}
    try:
        out = agent.ask_json(prompt)
        emails, done = [], set()
        for e in out.get("emails") or []:
            x = by_id.get(e.get("id"))
            if not x or x["id"] in done:  # unknown person or duplicate: drop
                continue
            done.add(x["id"])
            allowed = {f["source"] for f in x["facts"]}
            srcs = [s for s in e.get("sources") or [] if s in allowed] or [x["hook"]["source"]]
            emails.append({"id": x["id"], "person": x["person"], "company": x["company"],
                           "subject": e.get("subject") or "", "body": _trim(e.get("body") or ""),
                           "sources": srcs, "generated_by": "gemini"})
        for x in inputs:  # anyone the LLM skipped gets a template draft
            if x["id"] not in done:
                emails.append(template_email(x, role))
        result = {"emails": emails, "mode": "gemini"}
    except RuntimeError as e:
        agent.recover_event("outreach_template_fallback", reason=str(e)[:200])
        result = {"emails": [template_email(x, role) for x in inputs], "mode": "template"}
    for e in result["emails"]:
        e["profile"] = by_id[e["id"]]["profile"]
        e["title"] = by_id[e["id"]]["title"]
    cache[key] = result
    agent._write_json(OUTREACH_CACHE, cache)
    return result
