"""neathack-agent v1: hiring-signal scout.

Usage:
    python agent.py "<market>" "<role>"            # live (Gemini + Crustdata)
    python agent.py --dry-run "<market>" "<role>"  # Gemini only, mock Crustdata data (0 credits)

Loop: plan -> tools -> state -> recover -> verify -> report.
Every LLM call (Gemini, via neatlogs.wrap) and every tool call (@neatlogs.span TOOL)
is traced in neatlogs under one WORKFLOW root.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- neatlogs must be initialised BEFORE importing the LLM library ---------
import neatlogs
from dotenv import load_dotenv

load_dotenv()
neatlogs.init(
    api_key=os.environ.get("NEATLOGS_API_KEY"),
    workflow_name="hiring-signal-scout",
    tags=["neathack-2026", "v1"],
)

import requests  # noqa: E402
from google import genai  # noqa: E402  (import after neatlogs.init)
from google.genai import types  # noqa: E402

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
CRUST_BASE = "https://api.crustdata.com"
CRUST_VERSION = "2025-11-01"
MAX_JOBS = 10      # job/search: 0.03 credits per result
MAX_PEOPLE = 5     # person/search: ~0.03-0.13 credits per result (basic fields)
MAX_PEOPLE_COMPANIES = 3
RUNS_DIR = Path(__file__).parent / "runs"

_client = None


def gemini():
    global _client
    if _client is None:
        if not os.environ.get("GEMINI_API_KEY"):
            sys.exit("GEMINI_API_KEY missing in .env")
        # Client created after neatlogs.init(); wrap() traces every call as an LLM span.
        _client = neatlogs.wrap(genai.Client(api_key=os.environ["GEMINI_API_KEY"]))
    return _client


def ask_json(prompt: str) -> dict:
    """One Gemini call that must return JSON. Retries once on bad JSON."""
    last_err = None
    for _ in range(2):
        resp = gemini().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.2
            ),
        )
        try:
            return json.loads(resp.text)
        except (json.JSONDecodeError, TypeError) as e:
            last_err = e
    raise RuntimeError(f"Gemini did not return JSON: {last_err}")


# ---------------------------------------------------------------- PLAN -----
@neatlogs.span(kind="AGENT", name="planner", role="Plans Crustdata search filters")
def plan(market: str, role: str) -> dict:
    prompt = f"""You plan searches against the Crustdata Job Search API.
Market: "{market}"
Role: "{role}"

Return JSON with exactly these keys:
- "title_keywords": list of 1-3 short job-title phrases for this role (e.g. ["backend engineer","backend developer"])
- "locations": list of 0-3 city names in the market (e.g. ["San Francisco","Palo Alto"]); [] if none given
- "country": country name or null
- "round_types": list of funding round types from: pre_seed, seed, series_a, series_b, series_c, series_d; [] if not specified
- "max_headcount": integer or null
- "decision_maker_titles": list of 2-3 titles who would own hiring for this role (e.g. ["CTO","VP Engineering"])
- "steps": short list of strings describing your plan
"""
    return ask_json(prompt)


# --------------------------------------------------------------- TOOLS -----
def _crust_post(path: str, body: dict) -> dict:
    key = os.environ.get("CRUSTDATA_API_KEY")
    if not key:
        raise RuntimeError("CRUSTDATA_API_KEY missing in .env")
    r = requests.post(
        CRUST_BASE + path,
        headers={
            "authorization": f"Bearer {key}",
            "content-type": "application/json",
            "x-api-version": CRUST_VERSION,
        },
        json=body,
        timeout=60,
    )
    if r.status_code == 429:
        time.sleep(5)
        return _crust_post(path, body)
    if r.status_code >= 400:
        raise RuntimeError(f"Crustdata {path} {r.status_code}: {r.text[:300]}")
    out = r.json()
    out["_credits_used"] = r.headers.get("X-Credits-Used")
    return out


def build_job_filters(p: dict, level: int) -> dict:
    """level 0 = strict, 1 = drop funding/headcount, 2 = drop location too."""
    since = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    titles = p.get("title_keywords") or []
    conds = [
        {"op": "or", "conditions": [
            {"field": "job_details.title", "type": "(.)", "value": t} for t in titles
        ]},
        {"field": "metadata.date_added", "type": "=>", "value": since},
    ]
    if level < 2 and p.get("locations"):
        conds.append({"op": "or", "conditions": [
            {"field": "location.city", "type": "(.)", "value": c} for c in p["locations"]
        ]})
    elif p.get("country"):
        conds.append({"field": "location.country", "type": "in",
                      "value": ["USA", "United States", "United States of America"]
                      if "united states" in p["country"].lower() or p["country"].upper() in ("US", "USA")
                      else [p["country"]]})
    if level < 1:
        if p.get("round_types"):
            conds.append({"field": "company.funding.last_round_type", "type": "in",
                          "value": p["round_types"]})
        if p.get("max_headcount"):
            conds.append({"field": "company.headcount.total", "type": "=<",
                          "value": int(p["max_headcount"])})
    return {"op": "and", "conditions": conds}


@neatlogs.span(kind="TOOL", tool_name="crustdata_job_search",
               description="POST /job/search on Crustdata (0.03 credits/result)")
def job_search(filters: dict, dry_run: bool) -> dict:
    if dry_run:
        return mock_jobs()
    return _crust_post("/job/search", {
        "filters": filters,
        "fields": [
            "crustdata_job_id", "job_details.title", "job_details.url",
            "company.basic_info.crustdata_company_id", "company.basic_info.name",
            "company.basic_info.primary_domain", "company.headcount.total",
            "company.funding.last_round_type", "location.raw", "metadata.date_added",
        ],
        "sorts": [{"field": "metadata.date_added", "order": "desc"}],
        "limit": MAX_JOBS,
    })


@neatlogs.span(kind="TOOL", tool_name="crustdata_person_search",
               description="POST /person/search on Crustdata, decision-makers at one company")
def people_search(domain: str, titles: list, dry_run: bool) -> dict:
    if dry_run:
        return mock_people(domain)
    return _crust_post("/person/search", {
        "filters": {"op": "and", "conditions": [
            {"field": "experience.employment_details.current.company_website_domain",
             "type": "=", "value": domain},
            {"op": "or", "conditions": [
                {"field": "experience.employment_details.current.title", "type": "(.)", "value": t}
                for t in titles
            ]},
        ]},
        "fields": ["crustdata_person_id", "basic_profile.name", "basic_profile.current_title",
                   "social_handles.professional_network_identifier.profile_url"],
        "limit": MAX_PEOPLE,
    })


# ------------------------------------------------------------- RECOVER -----
@neatlogs.span(kind="CHAIN", name="gather_jobs_with_recovery")
def gather_jobs(p: dict, state: dict, dry_run: bool) -> list:
    for level in range(3):
        filters = build_job_filters(p, level)
        step = {"tool": "job_search", "level": level, "filters": filters}
        try:
            res = job_search(filters, dry_run)
            jobs = res.get("job_listings", [])
            step.update(results=len(jobs), credits=res.get("_credits_used"))
            state["steps"].append(step)
            if jobs:
                return jobs
            print(f"  no jobs at strictness level {level}, broadening...")
        except Exception as e:  # noqa: BLE001
            step["error"] = str(e)
            state["steps"].append(step)
            print(f"  job search error at level {level}: {e}")
            if "401" in str(e) or "missing" in str(e):
                break
    return []


# --------------------------------------------------------------- VERIFY ----
@neatlogs.span(kind="AGENT", name="verifier", role="Drops claims without a Crustdata source")
def verify(market: str, role: str, companies: list) -> dict:
    prompt = f"""You are a strict fact checker. Market: "{market}". Role: "{role}".
Below is raw Crustdata evidence per company (job postings with URLs, people with profile URLs).
Write a ranked list of companies most relevant to the market and role.
Rules: every claim must cite a source URL taken verbatim from the evidence; if a claim has no
source in the evidence, drop it. Do not invent companies, people, or URLs.

Return JSON: {{"companies": [{{"name": str, "domain": str, "rank": int, "why": str,
"claims": [{{"text": str, "source": str}}],
"decision_makers": [{{"name": str, "title": str, "source": str}}]}}],
"dropped": [str]}}

EVIDENCE:
{json.dumps(companies, indent=1)[:30000]}
"""
    out = ask_json(prompt)
    # Deterministic second pass: keep only sources that really appear in the evidence.
    evidence = json.dumps(companies)
    dropped = out.get("dropped", [])
    for c in out.get("companies", []):
        keep = []
        for cl in c.get("claims", []):
            if cl.get("source") and cl["source"] in evidence:
                keep.append(cl)
            else:
                dropped.append(f"claim: {cl.get('text')}")
        c["claims"] = keep
        dms = []
        for d in c.get("decision_makers", []):
            if d.get("source") and d["source"] in evidence:
                dms.append(d)
            else:
                dropped.append(f"person: {d.get('name')}")
        c["decision_makers"] = dms
    out["companies"] = [c for c in out.get("companies", []) if c["claims"]]
    out["dropped"] = dropped
    return out


# --------------------------------------------------------------- REPORT ----
def render(market: str, role: str, result: dict, dry_run: bool) -> str:
    lines = [f"# Hiring-signal scout: {role} in {market}",
             f"_Generated {datetime.now():%Y-%m-%d %H:%M}{' (DRY RUN, mock data)' if dry_run else ''}_", ""]
    if not result.get("companies"):
        lines.append("No verified companies found.")
    for c in sorted(result.get("companies", []), key=lambda x: x.get("rank", 99)):
        lines.append(f"## {c.get('rank')}. {c.get('name')} ({c.get('domain', '')})")
        lines.append(c.get("why", ""))
        for cl in c["claims"]:
            lines.append(f"- {cl['text']} [source]({cl['source']})")
        if c["decision_makers"]:
            lines.append("**Decision-makers:**")
            for d in c["decision_makers"]:
                lines.append(f"- {d['name']}, {d['title']} [profile]({d['source']})")
        lines.append("")
    if result.get("dropped"):
        lines.append(f"_Dropped {len(result['dropped'])} unsupported claim(s) during verification._")
    return "\n".join(lines)


# ------------------------------------------------------------- WORKFLOW ----
@neatlogs.span(kind="WORKFLOW", name="hiring_signal_scout")
def run(market: str, role: str, dry_run: bool) -> str:
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    state = {"market": market, "role": role, "dry_run": dry_run, "model": MODEL, "steps": []}

    print("1/5 planning with Gemini...")
    p = plan(market, role)
    state["plan"] = p

    print("2/5 searching Crustdata jobs...")
    jobs = gather_jobs(p, state, dry_run)

    companies = {}
    for j in jobs:
        co = j.get("company", {}).get("basic_info", {})
        key = co.get("primary_domain") or co.get("name")
        if not key:
            continue
        c = companies.setdefault(key, {"name": co.get("name"), "domain": co.get("primary_domain"),
                                       "headcount": j.get("company", {}).get("headcount", {}).get("total"),
                                       "last_round": j.get("company", {}).get("funding", {}).get("last_round_type"),
                                       "jobs": [], "people": []})
        c["jobs"].append({"title": j.get("job_details", {}).get("title"),
                          "url": j.get("job_details", {}).get("url"),
                          "location": j.get("location", {}).get("raw"),
                          "posted": j.get("metadata", {}).get("date_added")})

    print(f"3/5 finding decision-makers at top {MAX_PEOPLE_COMPANIES} companies...")
    titles = p.get("decision_maker_titles") or ["CTO", "VP Engineering"]
    ranked = sorted(companies.values(), key=lambda c: -len(c["jobs"]))
    for c in ranked[:MAX_PEOPLE_COMPANIES]:
        if not c["domain"]:
            continue
        try:
            res = people_search(c["domain"], titles, dry_run)
            for pr in res.get("profiles", []):
                c["people"].append({
                    "name": pr.get("basic_profile", {}).get("name"),
                    "title": pr.get("basic_profile", {}).get("current_title"),
                    "url": (pr.get("social_handles", {}).get("professional_network_identifier") or {}).get("profile_url"),
                })
            state["steps"].append({"tool": "people_search", "domain": c["domain"],
                                   "results": len(res.get("profiles", [])),
                                   "credits": res.get("_credits_used")})
        except Exception as e:  # noqa: BLE001 - recover: skip this company, keep going
            state["steps"].append({"tool": "people_search", "domain": c["domain"], "error": str(e)})
            print(f"  people search failed for {c['domain']}: {e}")
    state["evidence"] = ranked

    print("4/5 verifying claims with Gemini...")
    result = verify(market, role, ranked) if ranked else {"companies": [], "dropped": []}
    state["result"] = result

    print("5/5 writing report...")
    report = render(market, role, result, dry_run)
    (RUNS_DIR / f"{stamp}.json").write_text(json.dumps(state, indent=2, default=str))
    (RUNS_DIR / f"{stamp}.md").write_text(report)
    print(f"\nSaved runs/{stamp}.json and runs/{stamp}.md\n")
    return report


# --------------------------------------------------------------- MOCKS -----
def mock_jobs() -> dict:
    rows = [
        ("Acme Inference", "acmeinference.example", "Senior Backend Engineer", "San Francisco, CA", 85, "series_a"),
        ("Acme Inference", "acmeinference.example", "Backend Engineer, Platform", "San Francisco, CA", 85, "series_a"),
        ("VectorForge", "vectorforge.example", "Backend Engineer", "Palo Alto, CA", 140, "series_b"),
        ("GPUlane", "gpulane.example", "Backend Software Engineer", "Mountain View, CA", 60, "series_a"),
    ]
    return {"_credits_used": "0 (mock)", "job_listings": [{
        "crustdata_job_id": i,
        "job_details": {"title": t, "url": f"https://jobs.example.com/{d}/{i}"},
        "company": {"basic_info": {"name": n, "primary_domain": d},
                    "headcount": {"total": h}, "funding": {"last_round_type": r}},
        "location": {"raw": loc}, "metadata": {"date_added": "2026-09-30T12:00:00"},
    } for i, (n, d, t, loc, h, r) in enumerate(rows)]}


def mock_people(domain: str) -> dict:
    slug = domain.split(".")[0]
    return {"_credits_used": "0 (mock)", "profiles": [
        {"basic_profile": {"name": f"Jordan {slug.title()}", "current_title": "CTO"},
         "social_handles": {"professional_network_identifier":
                            {"profile_url": f"https://profiles.example.com/{slug}-cto"}}},
    ]}


def main():
    ap = argparse.ArgumentParser(description="Hiring-signal scout (neatHack 2026)")
    ap.add_argument("market", help='e.g. "Series A AI infra Bay Area"')
    ap.add_argument("role", help='e.g. "backend engineer"')
    ap.add_argument("--dry-run", action="store_true",
                    help="skip Crustdata and use mock data (Gemini + neatlogs still run)")
    args = ap.parse_args()
    if not os.environ.get("NEATLOGS_API_KEY"):
        print("warning: NEATLOGS_API_KEY not set; traces will NOT be exported")
    try:
        print(run(args.market, args.role, args.dry_run))
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
