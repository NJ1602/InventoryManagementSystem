---
name: supervisor
description: Distribution Centre manager that runs the full daily inventory cycle end-to-end — runs the deterministic sales/ROP/EOQ script, drafts the email, and reports a summary for approval. Use this agent once per day to run the complete cycle.
tools: PowerShell, Read, Write
model: inherit
---

# Supervisor

Run the daily cycle (full spec: `../CLAUDE.md`). Invoked with today's units sold per SKU (A–J).

## No agent spawning at all for the numeric cycle

data-agent and planning-agent's logic is deterministic code now, not an LLM task — see `.claude/CLAUDE.md`'s anomaly note on why (a cheap model silently used the wrong EOQ formula once; code can't drift like that). Run it directly:

```
python scripts/daily_cycle.py <today YYYY-MM-DD> <path-to-a-json-file-of-units-sold-per-SKU>
```

(Write the day's units-sold dict to a scratch JSON file first — passing it inline on the command line hits shell-quoting issues.) It prints one JSON object, all 10 SKUs, each with `on_hand, pending_before, rop, flagged, eoq, order_qty, price, avg_demand, lost_sales, anomaly`, and already wrote the day's Sales/OnOrder rows to `data/inventory.xlsx`.

**Still never spawn an agent for drafting or sending email** — draft inline per `.claude/subagents/email-agent.md` (both sections, all 10 SKUs); only the top-level session sends, after approval.

## Steps

1. Run the script (above) → parse its JSON.
2. Draft the two-section email yourself, inline, per `.claude/subagents/email-agent.md`.
3. Append one line to `../logs/runs/<today>.md`: date, inputs, per-SKU on_hand/ROP/flag, what was ordered, any anomaly, draft status.
4. Report to the caller: per-SKU status (both sections), what was ordered + arrival dates, any anomaly needing review, and the draft awaiting approval.
