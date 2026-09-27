# email-agent

**Not an Agent-tool call — never spawn this.** Drafting is formatting `scripts/daily_cycle.py`'s output — `supervisor`/top-level does it inline. Sending is one permission-gated tool call, done only by the top-level session after the user's explicit approval, never through Agent.

---

Input: `daily_cycle.py`'s JSON — `{"skus": {...}, "ordering_and_material_cost_to_date": N, "holding_cost_to_date": N, "grand_total_cost_to_date": N}`. Each SKU has `on_hand, pending_before, rop, flagged, eoq, order_qty, price, avg_demand, sigma, lost_sales, anomaly, pending_orders`.

**Two-line cost summary at the very top, before either table** (two numbers, not one — they answer different questions, see `../CLAUDE.md`'s cost-accounting note if unsure why):
- `Ordering + material cost to date: $<ordering_and_material_cost_to_date>` (one-time cost of every order ever placed, as of when it was placed)
- `Holding cost to date: $<holding_cost_to_date>` (real, day-by-day accrual — grows every day inventory sits, even with no new orders)
- `Grand total: $<grand_total_cost_to_date>`

`pending_orders` is a list of **every order still outstanding** for that SKU — not just today's, all of them: `[{qty, order_date, arrival_date}, ...]`, oldest first. This exists so a SKU that was ordered days ago and still hasn't arrived keeps showing up, even on a day nothing new is ordered for it.

**Send as HTML** (`htmlBody`, not plain `body` — a wall of comma-separated text per SKU is exactly what's hard to scan; use `body` only as a plain-text fallback of the same content). **Two separate HTML `<table>`s**, one column per field, so on-hand/ROP/etc. line up down the page instead of running together in a sentence:

- Subject: `DC Inventory — N flagged, M OK — <date>` (N = flagged count, M = 10-N).
- **Table 1, heading "Reorder needed"** (flagged SKUs only; omit the table entirely if N=0, with a one-line "no SKU needs reordering today" instead). Columns: SKU | On-hand | ROP | EOQ/batch | Ordering today | Price | Avg demand | Sigma | Lost sales | In transit.
- **Table 2, heading "No action needed"** (every non-flagged SKU). Columns: SKU | On-hand | ROP | EOQ/batch | Price | Avg demand | Sigma | Lost sales | In transit.
- **In transit column**: for each entry in that SKU's `pending_orders`, one line (`<br>` between them): `X units → arriving <arrival_date>` (order_date optional, arrival date is what matters). Empty/`—` if `pending_orders` is empty. This is what makes an order placed days ago still visible today even if nothing new happened for that SKU.
- Give the "Reorder needed" table a light highlight (e.g. a colored heading or a border) so it visually stands out from "No action needed" at a glance — the whole point is the user shouldn't have to read every row to know what needs attention.
- Lost sales column: the number, or `—` if 0.
- If any SKU has a non-null `anomaly` (planning logic refused to place an order — order size vs. ROP looked like a data error), add a third section, "Needs review", naming the SKU and the anomaly text verbatim.
- Plain and scannable, no filler.

**Recipient:** naivedyajain1602@gmail.com only, always.
