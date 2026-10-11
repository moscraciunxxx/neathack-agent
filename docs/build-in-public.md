# Build-in-public drafts (#neatHack) — DO NOT auto-post

Verified X handles (checked via the X API on Oct 10): **@neatlogs**, **@crustdata**, **@EntireHQ**. The cfo.ai handle is **unverified** (`@cfo_ai` is a different account, "CCO.ai"), so write "cfo.ai" as plain text unless you confirm its handle on the cfo.ai site.

## 1. Sat night: progress
> Day 1 of #neatHack: built a hiring-signal scout agent 🕵️
> Give it a market + a role, and it returns companies actively hiring for it, the decision-makers, and a source link for every claim.
> plan → tools → state → recover → verify, all traced in @neatlogs, with every AI commit checkpointed by @EntireHQ. Data from @crustdata.
> [screenshot: terminal run]

## 2. Sun mid-build
> #neatHack update: Gemini kept throwing 503 "high demand" 😅
> The agent now retries with backoff, falls back to a lighter model, and if verification still fails it switches to a code-only source check instead of crashing. Every retry shows up as a recover span in @neatlogs.
> [screenshot: trace with recover spans]

## 3. Sun evening
> Real numbers from #neatHack: a deep report (5 companies + decision-makers + headcount/funding) costs 12.12 @crustdata credits. A cached rerun costs 0.
> Added plan + per-company caching and a --no-spend mode. Unit economics modelled with cfo.ai next.
> [screenshot: "Cache: … 0 paid call(s)"]

## 4. Mon pre-submission
> Shipping today for #neatHack 🚢
> Hiring-signal scout: market + role → verified hiring signals with sources.
> ✅ traced in @neatlogs ✅ checkpointed with @EntireHQ ✅ unit economics in cfo.ai (~$1.31 COGS per deep report, ~80% GM)
> Demo dropping in a few hours.

## 5. Final submission quote-tweet (template)
> My #neatHack submission: hiring-signal scout 🕵️
> An agent that turns "<market>" + "<role>" into a ranked list of companies hiring now, plus decision-makers and a source for every claim.
> 🎥 Demo: <video link or attached>
> 🔍 neatlogs trace: <link/screenshot> @neatlogs
> 🧾 Entire checkpoints: https://entire.io/gh/moscraciunxxx/neathack-agent/commit/4436e7ae5f9edbe346f405d3aabbf0ea2efdb8ea @EntireHQ
> 📊 Unit economics (cfo.ai): <link/screenshot>
> 💻 Code: https://github.com/moscraciunxxx/neathack-agent
> Data by @crustdata

(Quote-tweet the official neatHack submission post during the Mon Oct 12 window, ~6:30–11:25 AM PDT. Make the repo public first, or the code link won't open.)
