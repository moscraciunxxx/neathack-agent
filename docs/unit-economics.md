# Unit economics: hiring-signal scout

Prepared for neatHack 2026 (cfo.ai track). **A** = assumption, **M** = measured on our own runs, **S** = published source.

## 1. Measured cost drivers (M)

| Run type | What it does | Crustdata credits |
|---|---|---|
| Standard | plan → job search (≤10) → decision-makers (≤3 companies × 5) → verify | 0.3–0.75 |
| Deep (`--deep`) | standard + company enrich for 5 companies (headcount, growth, funding) | **12.12** (measured live run) |
| Cached rerun | same market + role (plan, job, people, enrich caches) | **0** |

LLM: 2 Gemini calls per run (plan + verify), currently on the **free tier** (`gemini-3.8-flash`, fallback `gemini-3.5-flash-lite`).

## 2. Unit prices

| Input | Value | Source |
|---|---|---|
| Crustdata search | 0.03 credits/result | S: docs.crustdata.com/general/pricing |
| Crustdata company enrich | 2 credits/company (4 with technographics) | S: same |
| Crustdata **$ per credit** | **$0.10** (sensitivity: $0.05 / $0.20) | **A**. Crustdata does not publish a $/credit rate: its blog says "Dollar value per credit is set by plan" and the "lowest tier starts at $95/mo" (S: crustdata.com/blog/data-enrichment-cost). Replace with the rate on your Crustdata Credits page. |
| Gemini 3.8 Flash, paid tier | $0.75 in / $3.75 out per 1M tokens to Dec 31 2026; **$1.50 / $7.50 from Jan 1 2027** | S: ai.google.dev/gemini-api/docs/pricing |
| Tokens per run | ~12k input, ~4k output incl. thinking, plus retries | A (from prompt sizes; check usage in the neatlogs trace) |

LLM $/run at 2027 rates: 12k × $1.50/1M + 4k × $7.50/1M ≈ $0.05. We budget **$0.10** to cover 503/429 retries and the fallback model.

## 3. COGS per report (A: $0.10/credit)

| Report | Crustdata $ | LLM $ | **COGS** | at $0.05/cr | at $0.20/cr |
|---|---|---|---|---|---|
| Standard (0.3–0.75 cr, use 0.75) | $0.075 | $0.05 | **~$0.13** | $0.09 | $0.20 |
| Deep (12.12 cr) | $1.21 | $0.10 | **~$1.31** | $0.71 | $2.52 |
| Cached rerun | $0 | $0.05–0.10 | **~$0.10** | — | — |

Biggest lever: company enrich (10 of the 12.12 credits). The per-company cache means repeat markets cost close to nothing.

## 4. Proposed pricing (A)

| Plan | Price | Includes | COGS at 100% use | GM at 100% use | GM at 50% use (A) |
|---|---|---|---|---|---|
| Pay-per-report: standard | $3 | 1 report | $0.13 | 96% | — |
| Pay-per-report: deep | $12 | 1 deep report | $1.31 | 89% | — |
| Starter | $149/mo | 30 deep + 150 standard | $58.80 | 61% | ~80% |
| Team | $499/mo | 120 deep + 600 standard | $235.20 | 53% | ~76% |

Positioning: one deep report replaces about an hour of a recruiter's or SDR's manual research (worth $40–80 at $40–80/h, A). That makes $12 an easy buy and leaves room for future price increases.

## 5. 12-month scenario (base case, all A)

Assumptions: founder-only (no salary), $5,000 starting cash, fixed opex $250/mo (Crustdata minimum plan around $95, hosting, domains, tools). PAYG from month 2: 10 deep + 20 standard per month. Starter: +3 new per month from month 3, 5% monthly churn. Team: +1 every 3 months from month 6. Usage at 50% of plan allowance.

|Month|Starter|Team|PAYG rev|MRR|Revenue|COGS|Opex|Net|Cash|
|---|---|---|---|---|---|---|---|---|---|
|1|0|0|$0|$0|$0|$0|$250|-$250|$4,750|
|2|0|0|$180|$0|$180|$16|$250|-$86|$4,664|
|3|3|0|$180|$447|$627|$104|$250|$273|$4,937|
|4|6|0|$180|$894|$1,074|$192|$250|$632|$5,569|
|5|9|0|$180|$1,341|$1,521|$280|$250|$991|$6,560|
|6|11|1|$180|$2,138|$2,318|$457|$250|$1,611|$8,171|
|7|14|1|$180|$2,585|$2,765|$545|$250|$1,970|$10,141|
|8|16|1|$180|$2,883|$3,063|$604|$250|$2,209|$12,351|
|9|18|2|$180|$3,680|$3,860|$780|$250|$2,830|$15,181|
|10|20|2|$180|$3,978|$4,158|$839|$250|$3,069|$18,250|
|11|22|2|$180|$4,276|$4,456|$898|$250|$3,308|$21,558|
|12|24|3|$180|$5,073|$5,253|$1,074|$250|$3,929|$25,487|

Month-12 MRR is about $5.1k (~$61k ARR run-rate) at ~80% gross margin. Cash-flow positive from month 3, so runway is not a constraint. Downside to model in cfo.ai: $0.20/credit, 100% utilisation, half the new customers. Upside: Team plan adoption doubles.

## 6. Exact steps in cfo.ai (Ari)

cfo.ai's product is **Ari**, a personal-CFO agent: "Ask a question. Ari builds the model from your actuals and shows you what changes". It runs scenarios (base/upside/downside) and is also reachable from your terminal over MCP (source: cfo.ai and cfo.ai/neathacks, which show the same product page; there are no separate public docs). There is no billing history yet, so we give Ari the assumptions directly.

1. Go to **https://cfo.ai/neathacks**, sign in or claim the hackathon access, and open the app (app.cfo.ai). Create a company/workspace named **"neathack-agent (hiring-signal scout)"**.
2. Skip connecting Stripe, Salesforce or Rippling (no actuals yet). Tell Ari: *"No actuals yet; build a plan from assumptions."*
3. Paste this prompt into Ari:

> Build a 12-month operating plan starting Nov 2026 for an AI agent SaaS that sells hiring-signal reports.
> **Pricing:** pay-per-report standard $3, deep $12; Starter $149/mo (30 deep + 150 standard reports); Team $499/mo (120 deep + 600 standard).
> **COGS per report:** standard $0.13, deep $1.31 (Crustdata 12.12 credits × $0.10 + LLM $0.10). Usage = 50% of plan allowance.
> **Customers:** PAYG from month 2 = 10 deep + 20 standard/month; Starter +3 new/month from month 3 with 5% monthly churn; Team +1 every 3 months from month 6.
> **Opex:** $250/month fixed, no salaries. **Starting cash:** $5,000.
> Show monthly revenue, MRR, COGS, gross margin, net income, ending cash and runway.

4. Then ask for scenarios: *"Add downside (Crustdata $0.20/credit, 100% utilisation, half the new customers) and upside (2× Team adoption). Compare ending cash and gross margin."*
5. Ask: *"Gemini prices double on Jan 1 2027. Raise LLM cost per report from $0.05 to $0.10 from Jan 2027 and show the margin impact."*
6. Ask: *"What price for the deep report keeps gross margin ≥ 80% in the downside case?"* (Expected answer: around $12.60 or more, since $2.52 COGS / 0.2 = $12.60.)
7. **Proof for judges:** screenshot or record the plan table, the scenario chart and the margin answer. Save the workspace share link if Ari offers one. Add the link and screenshots to the README and the submission post.

Note: the cfo.ai UI wording above is from its public page. If menus differ, the prompts in steps 3–6 are what matter.
