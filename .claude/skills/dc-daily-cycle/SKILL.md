---
name: dc-daily-cycle
description: Run one day of the DC Inventory Manager cycle — collects today's units sold per SKU, runs the deterministic ROP/EOQ script, drafts the two-section reorder email, and handles getting the user's approval before anything is actually sent.
---

# DC Daily Cycle

No agent spawning anywhere in this flow — data-agent/planning-agent's logic is deterministic code (`scripts/daily_cycle.py`), and email-agent is just formatting + one tool call. Do all of this yourself, directly, right here:

1. If the day's units sold per SKU (A–J) weren't already given, ask for all 10 in one message. Never assume a missing figure is zero — ask instead (`.claude/guardrails/permissions.md`).
2. Write the day's units-sold dict to a scratch JSON file, then run `python scripts/daily_cycle.py <today YYYY-MM-DD> <that file's path>`. Parse its one-line JSON result (all 10 SKUs).
3. Draft the two-section email per `.claude/subagents/email-agent.md` (Reorder needed / No action needed / Needs review if any anomaly).
4. Append one line to `.claude/logs/runs/<today>.md`.
5. Show the user: per-SKU status (both sections), what was ordered + arrival dates, any anomaly, and the draft.
6. Ask directly whether to send the draft now. Only on a clear "yes," call the Gmail send tool yourself (`ToolSearch` for `mcp__33e014ff-eaf1-4894-b71a-0aee7e720f37__send_message` if not loaded), to naivedyajain1602@gmail.com only, with the exact approved subject/body. Never spawn an agent for this — it's permission-gated and gets auto-denied from inside a spawned agent regardless of prior approval, and it's one deterministic call that needs no separate reasoning anyway.
