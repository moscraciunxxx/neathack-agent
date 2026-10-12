# Demo video narration

Voice-over for the neatHack demo video (≤3 min). Narrated in Vitalie's own voice from his private local voice bank (the voice bank itself is not in this repo).

1. **[Title card]** Hi, I'm Vitalie. This is hiring-signal scout, built for neatHack.

2. **[Problem slide]** Sales and recruiting reps waste hours finding which companies are actually hiring, and who owns the hire.

3. **[Agent loop slide]** Give the agent a market and a role. It plans with Gemini, searches Crustdata for jobs, finds the decision-makers, verifies every claim, and writes a report.

4. **[Recovery log (runs/20261011-153241)]** In this run, Gemini failed eight times in a row. The agent retried, fell back to Flash-Lite, then switched providers to Claude Haiku through LiteLLM.

5. **[broaden_market log]** Only two companies fit the market, so the agent broadened it and verified again.

6. **[Report: 4 companies, 100% grounded, 0 credits]** The result is four companies: Cartesia, Eventual, Tessera Labs and Cambio. Eight off-market companies were dropped, each with a reason. One hundred percent of claims are grounded, and it spent zero Crustdata credits.

7. **[neatlogs trace: recovery spans (docs/img/Recovery_1/2.png)]** neatlogs traces every step. Here are the retries, the fallback and the provider switch, all inside one trace.

8. **[neatlogs 'Recover event fired' detection, 113 spans]** I built a neatlogs detection called Recover event fired. It flagged one hundred thirteen recovery spans across my runs.

9. **[Entire checkpoints / Entire Graph]** Entire checkpointed every AI-written commit with the session behind it, and Entire Graph found the right functions before each edit.

10. **[cfo.ai tier table + plan assumptions]** Then, cfo.ai turned my measured run costs into unit economics. A fresh deep report costs about a dollar thirty-five to make and sells for twelve dollars.

11. **[cfo.ai cash chart + scenario comparison]** Its downside case showed margins breaking, so I cut the deep report allowances. Margin now stays above seventy-five percent, in every case.

12. **[End card: repo URL]** The code and evidence are at github.com/moscraciunxxx/neathack-agent. Thanks for watching.
