# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This repository holds an **AI-driven Distribution Centre (DC) inventory manager**. Its job is to run once a day, ask the user for that day's units sold per SKU, update a running sales history, recompute each SKU's Reorder Point (ROP) and Economic Order Quantity (EOQ), and email the user a purchase recommendation for every SKU that has fallen below its ROP.

The project is *documented* as a supervisor/3-subagent agentic architecture, but execution has been "compiled down" over several rounds of token optimization: **no agent is actually spawned anywhere in the daily cycle anymore.** `agents/supervisor.md` and `subagents/*.md` remain as the human-readable spec for what each role does and why — read them to understand the logic — but the top-level session (via `skills/dc-daily-cycle/SKILL.md`) now does everything directly: run a deterministic script, template an email, log, get approval, send. This wasn't the original design; it's what token-efficiency pressure converged on, one role at a time (see each file's own note on why).

## Folder map (`.claude/`)

- `CLAUDE.md` — this file, the single source of truth for the spec. The root-level `CLAUDE.md` is only a pointer to here (that's the file Claude Code actually auto-loads; keep it in sync if this file's location ever changes).
- `agents/supervisor.md` — spec only, not spawned. Documents the end-to-end flow; `skills/dc-daily-cycle/SKILL.md` actually runs it, inline, at the top level.
- `subagents/{data-agent,planning-agent,email-agent}.md` — spec only, none spawned.
  - **data-agent + planning-agent**'s logic is now `scripts/daily_cycle.py` — deterministic Python, not an LLM call. It used to be one combined `Agent` call; that was tried on `model: "haiku"` first, which silently used the textbook EOQ formula instead of this spec's material-cost-inclusive one, over-ordering every flagged SKU by ~3.24x until caught and hand-corrected. Moving the formulas into code fixes the failure mode (a script can't misremember a formula) and removes the LLM cost for pure arithmetic/file I/O entirely, rather than just picking a bigger model.
  - **email-agent**: drafting is formatting the script's JSON output; sending is one permission-gated tool call. Both done inline by the top-level session, never spawned — sending in particular gets auto-denied when attempted from inside a spawned agent regardless of prior approval, so there was never a version of this that worked as a subagent anyway.
- `guardrails/{permissions,data-integrity}.md` — hard rules that apply regardless of how the logic executes (script or LLM).
- `logs/` — one markdown file per day's run (`logs/runs/<date>.md`), a human-readable audit trail distinct from the raw data in `data/inventory.xlsx`.
- `skills/dc-daily-cycle/SKILL.md` — the user-facing entry point, `/dc-daily-cycle`, and the actual orchestrator now.

## `scripts/daily_cycle.py`

The deterministic implementation of data-agent + planning-agent. Takes today's date and a units-sold-per-SKU JSON (inline or as a file path — inline hits shell-quoting issues, prefer a scratch file), reads/writes `data/inventory.xlsx` directly, and prints `{"skus": {...}, "total_cost_to_date": N}`. Each of the 10 SKUs has `on_hand, pending_before, rop, flagged, eoq, order_qty, price, avg_demand, sigma, lost_sales, anomaly, pending_orders`. `anomaly` is non-null when the order-size sanity guardrail refused to record an order (see `subagents/planning-agent.md`). `pending_orders` is every order still outstanding for that SKU (not just today's) — `[{qty, order_date, arrival_date}, ...]` — so the email can show an order placed days ago that still hasn't arrived, even on a day nothing new happens for that SKU. Cost accounting note: the EOQ derivation's `0.10*price*Q/2` term is a **batch-sizing proxy**, not a real incurred cost — it exists only to pick a good order size, evaluated once at order time. It does not represent "how much it costs to hold this batch," so it's excluded from the running cost totals to avoid double-counting against real holding cost. The script tracks three numbers instead: `ordering_and_material_cost_to_date` (ordering + material cost of every order ever placed, one-time, at order time), `holding_cost_to_date` (real: `on_hand * price * (0.10/365)` summed over every day-per-SKU row ever recorded — this one genuinely grows day by day even with no new orders, which is what a user should expect from "holding cost"), and `grand_total_cost_to_date` (their sum). The 10%-of-price holding rate is treated as **annual** (no period was specified originally, and annual is the standard convention for a holding-cost rate), hence `/365` for the daily accrual.

## Daily workflow

1. On day 1, initialize on-hand stock to **1000 units for each of the 10 SKUs** (A–J).
2. Each day, data-agent prompts the user in chat (or reads the "Daily SKU Consumption" input page's submission) for units sold for each SKU that day.
3. Subtract that day's sales from each SKU's on-hand stock.
4. Append the day's sales figures to the Excel database, then recompute rolling average demand and σ per SKU from all data recorded since day 1.
5. planning-agent computes ROP for every SKU and flags any SKU whose **inventory position** — on-hand stock **plus** whatever is already on order but not yet received — is below ROP. (Checking on-hand alone would double-order a SKU that already has enough in transit.)
6. For each flagged SKU, planning-agent computes the per-batch EOQ, then orders as many EOQ batches as needed to bring inventory position up to ROP (`ceil(shortfall / EOQ)` batches, minimum 1) — not always exactly one batch. A single EOQ order that still leaves the SKU short of ROP once it arrives gets topped up immediately, in the same cycle, rather than waiting to react next time.
7. The top-level session drafts the report (inline, no agent — see Folder map), covering **all 10 SKUs in two sections**: flagged SKUs get full detail (on-hand, ROP, EOQ per batch, total quantity ordered, price, average daily demand), non-flagged SKUs get a brief on-hand/ROP line each. A third section lists any SKU the order-size guardrail flagged as a probable data error instead of ordering. It is never sent without the user's explicit approval in chat — see `guardrails/permissions.md`.
8. Ordered quantity is tracked separately as "on order" and only moves into on-hand stock once that SKU's lead time has elapsed since the order date.
9. A run-log entry summarizing the day is written to `logs/`.

## Business logic / formulas

- **Reorder Point (ROP)** = Safety Stock + Pipeline Stock
- **Safety Stock** = `Z * σ * sqrt(n)`
  - `Z` = **1.65**, corresponding to a 95% service level (fixed; never recompute).
  - `σ` = standard deviation of daily demand for that SKU. Recomputed **every day** from the full historical daily-sales record in the Excel database (a rolling statistic over all data since day 1; the "10" default only applies before real sales data exists).
  - `n` = lead time **in days** for that SKU.
- **Pipeline Stock** = `average daily demand * lead time` for that SKU. Average daily demand is the same rolling, continuously-recomputed statistic used for σ.
- **EOQ (per batch)** minimizes total cost, where:
  - **Holding cost** = `0.10 * price * Q / 2`
  - **Ordering cost** = `(Annual Demand / Q) * 250`
  - **Material cost** = `price * Q`
  - **Total cost** = Holding cost + Ordering cost + Material cost
  - Material cost is intentionally included: ordering 20 units must cost less in total than ordering 1000, so `Q` cannot be chosen ignoring the `price * Q` term. Minimizing gives the closed form: `Q* = sqrt( (250 * Annual Demand) / (1.05 * price) )`.
  - **Order quantity** (what actually gets recorded in OnOrder) is `ceil(shortfall / Q*) * Q*`, where `shortfall = ROP - inventory_position` — as many EOQ batches as it takes to clear the gap, not always exactly one.

## Defaults / constants

| SKU | Lead time (days) | Price |
|-----|-------------------|-------|
| A   | 2                 | 23    |
| B   | 3                 | 54    |
| C   | 4                 | 76    |
| D   | 7                 | 35    |
| E   | 4                 | 66    |
| F   | 6                 | 76    |
| G   | 4                 | 78    |
| H   | 7                 | 897   |
| I   | 5                 | 54    |
| J   | 9                 | 77    |

- Initial on-hand stock: **1000 units per SKU** on day 1.
- Default average daily demand (until computed from real data): **10**.
- Default demand variability / σ (until computed from real data): **10**.
- Default Annual Demand (used in the ordering-cost term): **10000**.
- Ordering cost per order: **250** (same for all SKUs).
- Holding cost rate: **10% of price** per unit.

Note: the default average daily demand (10) and default Annual Demand (10000) are independent inputs and are **not** self-consistent (10 * 365 ≠ 10000). Keep them as two separate, independently-configurable defaults.

## Data store

A single Excel file, `data/inventory.xlsx`, acts as the system's database:

- Sheet `Sales`: one row per day per SKU — date, units sold (full demand, even if unmet), on-hand stock after sale (never negative — see `guardrails/data-integrity.md`'s stock floor), lost sales (demand that exceeded on-hand that day), rolling average daily demand, rolling σ (both recomputed daily from all history to date).
- Sheet `OnOrder`: one row per order placed — order date, quantity ordered (EOQ), expected arrival date (order date + lead time), and a received flag. A background step each day checks for any on-order rows whose lead time has elapsed and moves that quantity into on-hand stock.

## Tech stack

Python, with the built-in xlsx skill (openpyxl/pandas) for the Excel database and the connected Gmail tool for the Email Agent.
