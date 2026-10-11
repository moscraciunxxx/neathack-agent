# Evidence: what the agent did, what failed, how it recovered

All numbers come from real runs on the user's Mac (files in `runs/`, not committed). Fill the `<paste …>` placeholders before submitting.

## Before vs after

| | **BEFORE** (a782dad era) | **AFTER** (a1e25ee) |
|---|---|---|
| Run | `20261010-213936`, deep + replan. An earlier run kept Canopy Connect and signed its emails "Alex". | `20261010-215413`, deep |
| Companies kept | **1** | **4**: Eventual, Cartesia, Tessera Labs, Cambio (*fit unconfirmed*) |
| Dropped | 5, **including Cambio** for "insufficient evidence … from domain and title alone" | **8, all off-market with reasons**: Jack & Jill, Ketch, Ellipsis Health, Venmo, Flexion, Zed, Epsilon Health, Aegis AI Security |
| Off-market leak | Canopy Connect (insurance carrier integrations) kept in an earlier run | Market-fit judgment at temperature 0, verdicts cached per market + company |
| Outreach | Signed "Best, Alex" (invented sender), duplicates, people not on the cards | Exactly the people on the cards, deduped, always "Best, <your name>", each with a distinct cited hook |
| Recover | n/a | `broaden_market` fired (kept < 3). Gemini **429 → fallback `gemini-3.5-flash-lite`** |
| Crustdata credits | 8.25 | 12.77 (14 cache hits / 6 paid calls) |
| COGS / margin (deep, $12) | n/a | **$1.38 COGS, 88.5% gross margin** |
| neatlogs trace | `<paste neatlogs trace link>` | `<paste neatlogs trace link>` |

## Failed actions and what the agent did

| Failure (real) | What the agent did | Where to see it |
|---|---|---|
| Gemini `503 UNAVAILABLE` / `429 RESOURCE_EXHAUSTED` | Backed off 5/15/30 s, then switched to `gemini-3.5-flash-lite` (`[recover] gemini_retry`, `fallback_model`). If both fail: LiteLLM proxy (`provider_switch`), then a code-only verify ("LLM verify unavailable"). It never crashes. | timeline + `recover:*` spans `<paste neatlogs trace link>` |
| Verify kept only 1 company | `[recover] broaden_market`: one broader plan (AI/ML infra, ML platform, MLOps, data infra, devtools). New companies only, inside `--max-credits`, cache first. Then verify again. | run `20261010-215413` |
| Over-strict fit ("insufficient evidence") | Now kept with a **fit unconfirmed** badge. Old unsure verdicts are removed from the cache (`[recover] fit_cache_invalidated`). | card badge |
| People search returned 0 (v1) | Lookup by company_id, then domain, then name (`people_search_broaden`). "None found" is cached, and the card says "not looked up (budget)" when that's the reason. | company cards |
| Empty job search | Filters broadened over 3 strictness levels. | `no jobs at strictness level …` |
| Re-runs spent credits again | Plan, request and per-company caches, plus `--no-spend`. A cached rerun costs 0 credits. | cost meter "cache hits" |

## Entire (checkpoints + Graph)

| Commit | What | Entire |
|---|---|---|
| `4436e7ae5f9edbe346f405d3aabbf0ea2efdb8ea` | First feature with Entire, checkpoint **01M4JGPF985VEY8QKQQVS73S5V** | https://entire.io/gh/moscraciunxxx/neathack-agent/commit/4436e7ae5f9edbe346f405d3aabbf0ea2efdb8ea |
| `b389c8331610849b07c36c79d0a8328bf91d9afd` | First live run working, checkpoint 01M4MD82D6XQE6MYERPKEHA15R | https://entire.io/gh/moscraciunxxx/neathack-agent/commit/b389c8331610849b07c36c79d0a8328bf91d9afd |
| `2c51a5ffc2bcfd85246ab3b2715f75bd98ef4f3b` | Rounded growth %, softer verify, sample report, checkpoint 01M4MDNDYSKQ5VPBN6H5GRDZF1 | https://entire.io/gh/moscraciunxxx/neathack-agent/commit/2c51a5ffc2bcfd85246ab3b2715f75bd98ef4f3b |
| `a8d6c0886ddf58e0f3d8957b625004dea826f6ec` | Demo instructions, checkpoint 01M4MH6A6KDH3D7ZZHYAQZCNWH | https://entire.io/gh/moscraciunxxx/neathack-agent/commit/a8d6c0886ddf58e0f3d8957b625004dea826f6ec |
| `af6fe58cae87867a7d7c2dc0e24f6142e941ad5b` | CHANGELOG, checkpoint 01M4MQAQV310M0GYQRZG3E7V2W | https://entire.io/gh/moscraciunxxx/neathack-agent/commit/af6fe58cae87867a7d7c2dc0e24f6142e941ad5b |
| `b460063c8afdc989d60e4256e1e390989e710659` | Enable Entire Graph, checkpoint 01M4MQM8EEPPTST33HMDNKMJP1 | https://entire.io/gh/moscraciunxxx/neathack-agent/commit/b460063c8afdc989d60e4256e1e390989e710659 |

**Graph:** Cursor used `entire graph` search to find `broaden_market`, `run` and `recover_event` in `agent.py` before editing (see `.entire/graph-agent.md`). Screenshot: `docs/img/entire-graph.png` `<add screenshot>`.

## cfo.ai (Ari) results

| Scenario | Ending cash (12 mo) | 12-mo gross margin |
|---|---|---|
| Base | **$28,382.74** | **90.32%** |
| Downside ($0.20/credit) | **$13,899.06** | **76.30%** |
| Upside | **$33,761.05** | **90.24%** |

- Ari's downside showed margin pressure from deep reports, so plan allowances were cut: **Starter 30 → 7 deep, Team 120 → 18 deep**. That keeps downside margin ≥ 75%.
- **Deep price floor: $12.62** in the downside from Jan 2027 (Gemini paid prices double). PAYG deep stays at $12 for now. See `docs/unit-economics.md`.
- Screenshots: `docs/img/cfo-plan.png`, `docs/img/cfo-scenarios.png` `<add screenshots>`.

## Build in public (X)
- Sat night progress: `<paste X post link>`
- Sun mid-build: `<paste X post link>`
- Sun evening: `<paste X post link>`
- Mon pre-submission: `<paste X post link>`
- Submission quote-tweet: `<paste X post link>`
