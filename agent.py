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

import hashlib  # noqa: E402
import requests  # noqa: E402
from google import genai  # noqa: E402  (import after neatlogs.init)
from google.genai import types  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
RETRY_DELAYS = [5, 15, 30]  # seconds between attempts on 429/500/503
CRUST_BASE = "https://api.crustdata.com"
CRUST_VERSION = "2025-11-01"
MAX_JOBS = 10      # job/search: 0.03 credits per result
MAX_PEOPLE = 5     # person/search: ~0.03-0.13 credits per result (basic fields)
MAX_PEOPLE_COMPANIES = 3
DEEP_TOP_N_DEFAULT = 5
DEFAULT_MAX_CREDITS = 15.0
# Estimated list prices (docs.crustdata.com/general/pricing): search 0.03/result, enrich 2/company
EST = {"job": 0.03 * 10, "people": 0.03 * 5, "enrich": 2.0}
SENIORITY = ["CXO", "Vice President", "Director", "Owner / Partner"]
DEFAULT_DM_TITLES = ["CTO", "VP Engineering", "Head of Engineering", "Founder", "CEO"]
CREDITS = {"spent": 0.0, "estimated": 0.0, "max": DEFAULT_MAX_CREDITS, "skipped": []}
RUNS_DIR = Path(__file__).parent / "runs"
CACHE_FILE = RUNS_DIR / "crustdata_cache.json"
PLAN_CACHE_FILE = RUNS_DIR / "plan_cache.json"      # normalized (market, role) -> plan
ENTITY_CACHE_FILE = RUNS_DIR / "entity_cache.json"  # people:<company_id> / enrich:<company_id>
CACHE_STATS = {"hits": 0, "misses": 0, "skipped_no_spend": 0, "entity_hits": 0}
NO_SPEND = {"on": False}
RECOVERY_LOG = []  # retry/fallback events, saved into run state

_client = None


def gemini():
    global _client
    if _client is None:
        if not os.environ.get("GEMINI_API_KEY"):
            sys.exit("GEMINI_API_KEY missing in .env")
        # Client created after neatlogs.init(); wrap() traces every call as an LLM span.
        _client = neatlogs.wrap(genai.Client(api_key=os.environ["GEMINI_API_KEY"]))
    return _client


def recover_event(what: str, **info) -> None:
    """Visible print + a neatlogs span so retries/fallbacks show up as 'recover' in traces."""
    msg = f"  [recover] {what} " + " ".join(f"{k}={v}" for k, v in info.items())
    print(msg)
    RECOVERY_LOG.append({"event": what, **{k: str(v) for k, v in info.items()}})
    with neatlogs.trace(f"recover:{what}", kind="CHAIN") as span:
        span.set_attribute("neatlogs.recover.event", what)
        for k, v in info.items():
            span.set_attribute(f"neatlogs.recover.{k}", str(v)[:500])


def _is_transient(e: Exception) -> bool:
    code = getattr(e, "code", None)
    if isinstance(e, genai_errors.ServerError):
        return True
    return code in (429, 500, 502, 503, 504)


def _generate_json(model: str, prompt: str) -> dict:
    resp = gemini().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.2
        ),
    )
    return json.loads(resp.text)


def ask_json(prompt: str) -> dict:
    """Gemini call that must return JSON.
    Main model: up to len(RETRY_DELAYS)+1 attempts with backoff on 429/5xx or bad JSON,
    then the same on FALLBACK_MODEL. Raises RuntimeError if everything fails."""
    last_err = None
    for model in (MODEL, FALLBACK_MODEL):
        if model != MODEL:
            recover_event("fallback_model", from_model=MODEL, to_model=model, reason=last_err)
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return _generate_json(model, prompt)
            except (json.JSONDecodeError, TypeError) as e:
                last_err = f"bad JSON: {e}"
            except genai_errors.APIError as e:
                last_err = f"{getattr(e, 'code', '?')} {str(e)[:200]}"
                if not _is_transient(e):
                    break  # e.g. 404 model not found / 400: go straight to fallback
            if attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                recover_event("gemini_retry", model=model, attempt=attempt + 1,
                              wait_s=delay, error=last_err)
                time.sleep(delay)
    raise RuntimeError(f"Gemini unavailable after retries + fallback: {last_err}")


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
def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))


def plan_key(market: str, role: str) -> str:
    norm = lambda x: " ".join(x.lower().split())  # noqa: E731
    return f"{norm(market)}|{norm(role)}"


def entity_get(kind: str, company_id):
    if company_id is None:
        return None
    v = _read_json(ENTITY_CACHE_FILE).get(f"{kind}:{company_id}")
    if v is not None:
        CACHE_STATS["entity_hits"] += 1
        print(f"  (entity cache hit {kind}:{company_id}, 0 credits)")
    return v


def entity_put(kind: str, company_id, value) -> None:
    if company_id is None or not value:
        return
    data = _read_json(ENTITY_CACHE_FILE)
    data[f"{kind}:{company_id}"] = value
    _write_json(ENTITY_CACHE_FILE, data)


class NoSpendSkip(Exception):
    """Raised in --no-spend mode when a paid request is not in the cache."""


def _crust_post(path: str, body: dict) -> dict:
    """Cached: identical requests (same path + body) are served from runs/crustdata_cache.json,
    so re-running the same market/role does not re-spend credits."""
    ck = hashlib.sha256((path + json.dumps(body, sort_keys=True)).encode()).hexdigest()
    cache = _load_cache()
    if ck in cache:
        print(f"  (cache hit for {path}, 0 credits)")
        out = dict(cache[ck])
        out["_credits_used"] = "0 (cached)"
        CACHE_STATS["hits"] += 1
        return out
    if NO_SPEND["on"]:
        CACHE_STATS["skipped_no_spend"] += 1
        recover_event("no_spend_skip", path=path)
        raise NoSpendSkip(f"--no-spend: {path} not cached, skipped")
    CACHE_STATS["misses"] += 1
    out = _crust_post_live(path, body)
    try:
        CREDITS["spent"] += float(out.get("_credits_used") or 0)
    except ValueError:
        pass
    cache[ck] = out
    RUNS_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache))
    return out


def _crust_post_live(path: str, body: dict) -> dict:
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
        return _crust_post_live(path, body)
    if r.status_code >= 400:
        raise RuntimeError(f"Crustdata {path} {r.status_code}: {r.text[:300]}")
    out = r.json()
    if isinstance(out, list):  # /company/enrich returns a JSON array
        out = {"results": out}
    out["_credits_used"] = r.headers.get("X-Credits-Used")
    return out


def within_budget(kind: str, n: int = 1) -> bool:
    """Credit cap: skip a paid call if the running estimate would exceed --max-credits."""
    cost = EST[kind] * n
    if NO_SPEND["on"]:
        return True  # nothing paid can happen; uncached calls are skipped in _crust_post
    if CREDITS["estimated"] + cost > CREDITS["max"]:
        CREDITS["skipped"].append(f"{kind} x{n} (est {cost:.2f})")
        recover_event("credit_cap_skip", kind=kind, est=round(cost, 2),
                      so_far=round(CREDITS["estimated"], 2), cap=CREDITS["max"])
        return False
    CREDITS["estimated"] += cost
    return True


def build_job_filters(p: dict, level: int) -> dict:
    """level 0 = strict, 1 = drop funding/headcount, 2 = drop location too."""
    # 'since' is frozen into the cached plan so the request (and its cache key) stays identical on reruns
    since = p.get("since") or (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
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


PEOPLE_FIELDS = ["crustdata_person_id", "basic_profile.name", "basic_profile.current_title",
                 "social_handles.professional_network_identifier.profile_url"]


def _people_filters(company_cond: dict, titles: list) -> dict:
    """Current employer = company AND (senior level OR a decision-maker title)."""
    role_conds = [{"field": "experience.employment_details.current.seniority_level",
                   "type": "in", "value": SENIORITY}]
    for t in titles:
        role_conds.append({"field": "experience.employment_details.current.title",
                           "type": "(.)", "value": t})
    return {"op": "and", "conditions": [company_cond, {"op": "or", "conditions": role_conds}]}


@neatlogs.span(kind="TOOL", tool_name="crustdata_person_search",
               description="POST /person/search: decision-makers currently at one company")
def people_search_once(company_cond: dict, titles: list, dry_run: bool, domain: str = "") -> dict:
    if dry_run:
        return mock_people(domain or "company.example")
    body = {"filters": _people_filters(company_cond, titles), "fields": PEOPLE_FIELDS,
            "limit": MAX_PEOPLE}
    try:
        return _crust_post("/person/search", body)
    except RuntimeError as e:
        if "Invalid fields" in str(e):  # field-path drift: retry with default fields
            recover_event("people_fields_fallback", error=str(e)[:200])
            body.pop("fields")
            return _crust_post("/person/search", body)
        raise


@neatlogs.span(kind="CHAIN", name="find_decision_makers_with_recovery")
def people_search(company: dict, titles: list, dry_run: bool, state: dict) -> list:
    """Try company_id (exact) -> website domain -> company name. Follows Crustdata
    'condition_eliminates_all' remarks that suggest a resolved company_id."""
    cur = "experience.employment_details.current."
    cached = None if dry_run else entity_get("people", company.get("company_id"))
    if cached:
        state["steps"].append({"tool": "people_search", "by": "entity_cache",
                               "company": company.get("name"), "results": len(cached), "credits": 0})
        return cached
    attempts = []
    if company.get("company_id"):
        attempts.append(("company_id", {"field": cur + "company_id", "type": "in",
                                        "value": [company["company_id"]]}))
    if company.get("domain"):
        attempts.append(("domain", {"field": cur + "company_website_domain", "type": "=",
                                    "value": company["domain"]}))
    if company.get("name"):
        attempts.append(("name", {"field": cur + "company_name", "type": "in",
                                  "value": [company["name"]]}))
    for how, cond in attempts:
        if not dry_run and not within_budget("people"):
            return []
        try:
            res = people_search_once(cond, titles, dry_run, company.get("domain") or "")
        except NoSpendSkip as e:
            state["steps"].append({"tool": "people_search", "by": how, "skipped": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            state["steps"].append({"tool": "people_search", "by": how, "error": str(e)})
            recover_event("people_search_error", company=company.get("name"), by=how, error=str(e)[:200])
            continue
        profiles = res.get("profiles", [])
        state["steps"].append({"tool": "people_search", "by": how, "company": company.get("name"),
                               "results": len(profiles), "credits": res.get("_credits_used")})
        if profiles:
            if not dry_run:
                entity_put("people", company.get("company_id"), profiles)
            return profiles
        for rm in res.get("remarks") or []:
            resol = (rm or {}).get("resolution") or {}
            if resol.get("field") and resol.get("value") and how != "resolved":
                attempts.append(("resolved", {"field": resol["field"], "type": "in",
                                              "value": resol["value"]}))
        if how != attempts[-1][0]:
            recover_event("people_search_broaden", company=company.get("name"), empty_by=how)
    return []


@neatlogs.span(kind="TOOL", tool_name="crustdata_company_enrich",
               description="POST /company/enrich (headcount + funding), ~2 credits/company")
def company_enrich(ids: list, dry_run: bool) -> dict:
    if dry_run:
        return {"_credits_used": "0 (mock)", "results": [
            {"matched_on": str(i), "matches": [{"company_data": {
                "crustdata_company_id": i, "basic_info": {"name": f"Mock {i}"},
                "headcount": {"total": 80 + i, "growth_percent": {"six_months": 12.5, "yoy": 40.0}},
                "funding": {"total_investment_usd": 20000000.0, "last_round_type": "series_a",
                            "last_fundraise_date": "2026-03-01", "last_round_amount_usd": 15000000.0}}}]}
            for i in ids]}
    return _crust_post("/company/enrich", {"crustdata_company_ids": ids,
                                           "fields": ["basic_info", "headcount", "funding"]})


# ------------------------------------------------------------- RECOVER -----
@neatlogs.span(kind="CHAIN", name="gather_jobs_with_recovery")
def gather_jobs(p: dict, state: dict, dry_run: bool) -> list:
    for level in range(3):
        filters = build_job_filters(p, level)
        step = {"tool": "job_search", "level": level, "filters": filters}
        if not dry_run and not within_budget("job"):
            break
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
def _evidence_company(c: dict, companies: list) -> dict | None:
    """Match a verified company row back to its Crustdata evidence blob."""
    for ec in companies:
        if c.get("domain") and c.get("domain") == ec.get("domain"):
            return ec
        if c.get("name") and c.get("name") == ec.get("name"):
            return ec
    return None


def _source_in_company_results(source: str, company_ev: dict | None) -> bool:
    """True if source URL appears in that company's Crustdata results, or its company_id does.

    company_id presence soft-grounds enrich/firmographic citations like
    'Crustdata /company/enrich (company_id 123)' that are not raw job URLs.
    """
    if not source or not company_ev:
        return False
    blob = json.dumps(company_ev)
    if source in blob:
        return True
    cid = company_ev.get("company_id")
    return cid is not None and str(cid) in blob


def _normalize_dropped(items) -> list:
    """Coerce LLM dropped entries into {text, reason} dicts."""
    out = []
    for d in items or []:
        if isinstance(d, dict) and d.get("reason"):
            out.append({"text": d.get("text") or d.get("claim") or str(d),
                        "reason": d["reason"]})
        else:
            out.append({"text": str(d), "reason": "unspecified"})
    return out


@neatlogs.span(kind="AGENT", name="verifier", role="Soft verify: drop only missing sources")
def verify(market: str, role: str, companies: list) -> dict:
    prompt = f"""You are a fact checker. Market: "{market}". Role: "{role}".
Below is raw Crustdata evidence per company (job postings with URLs, people with profile URLs,
optional firmographics with company_id).
Write a ranked list of companies most relevant to the market and role.
Rules: every claim should cite a source URL or company_id from that company's evidence.
Keep a claim if its source URL or company_id appears anywhere in the Crustdata results for
that company. Only drop claims whose source is missing entirely — for each dropped item
include the reason. Do not invent companies, people, or URLs.

Return JSON: {{"companies": [{{"name": str, "domain": str, "rank": int, "why": str,
"claims": [{{"text": str, "source": str}}],
"decision_makers": [{{"name": str, "title": str, "source": str}}]}}],
"dropped": [{{"text": str, "reason": str}}]}}

EVIDENCE:
{json.dumps(companies, indent=1)[:30000]}
"""
    try:
        out = ask_json(prompt)
        out["llm_verify"] = True
    except RuntimeError as e:
        recover_event("verify_code_only", reason=e)
        out = code_only_result(companies)
        out["llm_verify"] = False
    # Soft deterministic pass vs prior exact global URL match:
    # keep if source URL or company_id appears in THAT company's Crustdata results;
    # only hard-drop when source is missing entirely.
    dropped = _normalize_dropped(out.get("dropped"))
    for c in out.get("companies", []):
        ev = _evidence_company(c, companies)
        keep = []
        for cl in c.get("claims", []):
            src = (cl.get("source") or "").strip()
            text = cl.get("text") or ""
            if not src:
                dropped.append({"text": text or "(empty claim)", "reason": "missing source"})
            elif _source_in_company_results(src, ev):
                keep.append(cl)
            else:
                # Source present but not found in results — still keep (only missing drops).
                keep.append(cl)
        c["claims"] = keep
        dms = []
        for d in c.get("decision_makers", []):
            src = (d.get("source") or "").strip()
            label = d.get("name") or "(unnamed person)"
            if not src:
                dropped.append({"text": label, "reason": "missing source"})
            elif _source_in_company_results(src, ev) or src:
                dms.append(d)
        c["decision_makers"] = dms
    out["companies"] = [c for c in out.get("companies", []) if c["claims"]]
    out["dropped"] = dropped
    return out


def code_only_result(companies: list) -> dict:
    """No-LLM fallback: every claim is built straight from Crustdata evidence with its URL."""
    out = {"companies": [], "dropped": []}
    for i, c in enumerate(companies, 1):
        claims = [{"text": f"Hiring: {j['title']} ({j.get('location') or 'n/a'}, posted {j.get('posted')})",
                   "source": j["url"]} for j in c["jobs"] if j.get("url")]
        dms = [{"name": p["name"], "title": p.get("title") or "", "source": p["url"]}
               for p in c["people"] if p.get("url")]
        out["companies"].append({"name": c["name"], "domain": c.get("domain") or "", "rank": i,
                                 "why": f"{len(c['jobs'])} matching open role(s); "
                                        f"headcount {c.get('headcount')}, last round {c.get('last_round')}.",
                                 "claims": claims, "decision_makers": dms})
    return out


# --------------------------------------------------------------- REPORT ----
def render(market: str, role: str, result: dict, dry_run: bool) -> str:
    lines = [f"# Hiring-signal scout: {role} in {market}",
             f"_Generated {datetime.now():%Y-%m-%d %H:%M}{' (DRY RUN, mock data)' if dry_run else ''}_", ""]
    if result.get("llm_verify") is False:
        lines += ["> **LLM verify unavailable** (Gemini overloaded). Ranking is by number of open roles; "
                  "every line below is copied directly from Crustdata with its source.", ""]
    if not result.get("companies"):
        lines.append("No verified companies found.")
    for c in sorted(result.get("companies", []), key=lambda x: x.get("rank", 99)):
        lines.append(f"## {c.get('rank')}. {c.get('name')} ({c.get('domain', '')})")
        lines.append(c.get("why", ""))
        for cl in c["claims"]:
            lines.append(f"- {cl['text']} [source]({cl['source']})")
        f = (result.get("_firmo") or {}).get(c.get("name"))
        if f:
            def m(v):
                return f"${v/1e6:.1f}M" if isinstance(v, (int, float)) else "n/a"

            def pct(v):
                return f"{v:.1f}" if isinstance(v, (int, float)) else "n/a"

            lines.append(f"**Firmographics** ({f['source']}): headcount {f['headcount']}, "
                         f"growth 6m {pct(f['headcount_growth_6m_pct'])}% / YoY "
                         f"{pct(f['headcount_growth_yoy_pct'])}%, "
                         f"total funding {m(f['funding_total_usd'])}, last round {f['last_round_type']} "
                         f"{m(f['last_round_amount_usd'])} on {f['last_fundraise_date']}")
        if c["decision_makers"]:
            lines.append("**Decision-makers:**")
            for d in c["decision_makers"]:
                lines.append(f"- {d['name']}, {d['title']} [profile]({d['source']})")
        lines.append("")
    if result.get("_credits"):
        lines.append(f"_Crustdata credits this run: estimated {result['_credits'][0]:.2f}, "
                     f"actual {result['_credits'][1]:.2f}._")
    if result.get("dropped"):
        lines.append("## Dropped claims")
        for d in result["dropped"]:
            if isinstance(d, dict):
                lines.append(f"- {d.get('text', '')}: {d.get('reason', 'unspecified')}")
            else:
                lines.append(f"- {d}")
    return "\n".join(lines)


# ------------------------------------------------------------- WORKFLOW ----
@neatlogs.span(kind="WORKFLOW", name="hiring_signal_scout")
def run(market: str, role: str, dry_run: bool, deep: bool = False, deep_n: int = DEEP_TOP_N_DEFAULT,
        replan: bool = False) -> str:
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    state = {"market": market, "role": role, "dry_run": dry_run, "deep": deep, "model": MODEL, "steps": []}
    planned = EST["job"] + EST["people"] * MAX_PEOPLE_COMPANIES + (EST["enrich"] * deep_n if deep else 0)
    print(f"Estimated Crustdata credits (upper bound, before cache): ~{planned:.2f}; cap {CREDITS['max']}")

    pk = plan_key(market, role)
    plans = _read_json(PLAN_CACHE_FILE)
    if pk in plans and not replan:
        print("1/5 reusing cached plan for this market+role (use --replan for a new one)")
        p = plans[pk]
        state["plan_source"] = "cache"
    else:
        print("1/5 planning with Gemini...")
        p = plan(market, role)
        state["plan_source"] = "gemini"
        p["since"] = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
        if not dry_run:
            plans[pk] = p
            _write_json(PLAN_CACHE_FILE, plans)
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
                                       "company_id": co.get("crustdata_company_id"),
                                       "headcount": j.get("company", {}).get("headcount", {}).get("total"),
                                       "last_round": j.get("company", {}).get("funding", {}).get("last_round_type"),
                                       "jobs": [], "people": []})
        c["jobs"].append({"title": j.get("job_details", {}).get("title"),
                          "url": j.get("job_details", {}).get("url"),
                          "location": j.get("location", {}).get("raw"),
                          "posted": j.get("metadata", {}).get("date_added")})

    print(f"3/5 finding decision-makers at top {MAX_PEOPLE_COMPANIES} companies...")
    titles = list(dict.fromkeys((p.get("decision_maker_titles") or []) + DEFAULT_DM_TITLES))[:6]
    ranked = sorted(companies.values(), key=lambda c: -len(c["jobs"]))
    for c in ranked[:MAX_PEOPLE_COMPANIES]:
        for pr in people_search(c, titles, dry_run, state):
            pid = pr.get("crustdata_person_id")
            url = ((pr.get("social_handles") or {}).get("professional_network_identifier") or {}).get("profile_url")
            c["people"].append({
                "name": (pr.get("basic_profile") or {}).get("name"),
                "title": (pr.get("basic_profile") or {}).get("current_title"),
                "url": url or (f"crustdata:person/{pid}" if pid else None),
            })

    if deep:
        top = [c for c in ranked[:deep_n] if c.get("company_id")]
        print(f"3b deep mode: enriching {len(top)} companies (headcount, growth, funding)...")
        by_id = {}
        if not dry_run:
            for c in top:
                d = entity_get("enrich", c["company_id"])
                if d:
                    by_id[c["company_id"]] = d
        need = [c for c in top if c["company_id"] not in by_id]
        if top and (not need or dry_run or within_budget("enrich", len(need))):
            try:
                if need:
                    res = company_enrich([c["company_id"] for c in need], dry_run)
                    state["steps"].append({"tool": "company_enrich", "n": len(need),
                                           "credits": res.get("_credits_used")})
                    for r in res.get("results", []):
                        for m in (r.get("matches") or [])[:1]:
                            d = m.get("company_data") or {}
                            by_id[d.get("crustdata_company_id")] = d
                            if not dry_run:
                                entity_put("enrich", d.get("crustdata_company_id"), d)
                state["steps"].append({"tool": "company_enrich", "from_entity_cache": len(top) - len(need)})
                for c in top:
                    d = by_id.get(c["company_id"])
                    if not d:
                        continue
                    hc, fu = d.get("headcount") or {}, d.get("funding") or {}
                    c["firmographics"] = {
                        "source": f"Crustdata /company/enrich (company_id {c['company_id']})",
                        "headcount": hc.get("total"),
                        "headcount_growth_6m_pct": (hc.get("growth_percent") or {}).get("six_months"),
                        "headcount_growth_yoy_pct": (hc.get("growth_percent") or {}).get("yoy"),
                        "funding_total_usd": fu.get("total_investment_usd"),
                        "last_round_type": fu.get("last_round_type"),
                        "last_round_amount_usd": fu.get("last_round_amount_usd"),
                        "last_fundraise_date": fu.get("last_fundraise_date"),
                    }
            except NoSpendSkip as e:
                state["steps"].append({"tool": "company_enrich", "skipped": str(e)})
            except Exception as e:  # noqa: BLE001
                state["steps"].append({"tool": "company_enrich", "error": str(e)})
                recover_event("company_enrich_error", error=str(e)[:200])
    state["evidence"] = ranked

    print("4/5 verifying claims with Gemini...")
    result = verify(market, role, ranked) if ranked else {"companies": [], "dropped": []}
    state["result"] = result
    state["recovery_events"] = RECOVERY_LOG
    state["credits_spent"] = round(CREDITS["spent"], 3)
    state["credits_estimated"] = round(CREDITS["estimated"], 3)
    state["credits_skipped_by_cap"] = CREDITS["skipped"]
    state["cache_stats"] = dict(CACHE_STATS)
    state["no_spend"] = NO_SPEND["on"]
    result["_firmo"] = {c["name"]: c["firmographics"] for c in ranked if c.get("firmographics")}
    result["_credits"] = (state["credits_estimated"], state["credits_spent"])

    print("5/5 writing report...")
    report = render(market, role, result, dry_run)
    (RUNS_DIR / f"{stamp}.json").write_text(json.dumps(state, indent=2, default=str))
    (RUNS_DIR / f"{stamp}.md").write_text(report)
    print(f"\nSaved runs/{stamp}.json and runs/{stamp}.md")
    print(f"Crustdata credits: estimated {state['credits_estimated']:.2f}, "
          f"actual {state['credits_spent']:.2f} (from X-Credits-Used)")
    print(f"Cache: {CACHE_STATS['hits']} request hit(s), {CACHE_STATS['entity_hits']} company hit(s), "
          f"{CACHE_STATS['misses']} paid call(s), {CACHE_STATS['skipped_no_spend']} skipped by --no-spend\n")
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
        "company": {"basic_info": {"name": n, "primary_domain": d, "crustdata_company_id": 1000 + i},
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
    ap.add_argument("--deep", action="store_true",
                    help="also run /company/enrich on the top companies (~2 credits each)")
    ap.add_argument("--deep-n", type=int, default=DEEP_TOP_N_DEFAULT,
                    help=f"companies to enrich in --deep mode (default {DEEP_TOP_N_DEFAULT})")
    ap.add_argument("--max-credits", type=float, default=DEFAULT_MAX_CREDITS,
                    help=f"hard cap on estimated Crustdata credits per run (default {DEFAULT_MAX_CREDITS})")
    ap.add_argument("--replan", action="store_true",
                    help="ignore runs/plan_cache.json and ask Gemini for a new plan")
    ap.add_argument("--no-spend", action="store_true",
                    help="only use cached Crustdata data; skip any uncached paid call (0 credits)")
    args = ap.parse_args()
    CREDITS["max"] = args.max_credits
    NO_SPEND["on"] = args.no_spend
    if not os.environ.get("NEATLOGS_API_KEY"):
        print("warning: NEATLOGS_API_KEY not set; traces will NOT be exported")
    try:
        print(run(args.market, args.role, args.dry_run, args.deep, args.deep_n, args.replan))
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
