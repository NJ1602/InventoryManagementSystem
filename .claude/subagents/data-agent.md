# data-agent

**Spec only — not executed via Agent/LLM at all.** This logic is implemented deterministically in `scripts/daily_cycle.py` (the "each run, per SKU" section below). `supervisor`/top-level runs that script directly; nothing here is read into a prompt anymore. Kept as the human-readable spec for what the script does and why, in case the script ever needs to change.

---

Maintains `data/inventory.xlsx` (full spec: `../CLAUDE.md`).

**Rules:** Sales sheet is append-only. On-hand can never go negative — clamp at 0, put the shortfall in `lost_sales`. An OnOrder row is marked `received` at most once. Plain values only, no formulas (no LibreOffice in this environment).

**Schema** — `Sales`: `date, sku, units_sold, on_hand_after, lost_sales, avg_demand, sigma`. `OnOrder`: `order_date, sku, qty, lead_time_days, arrival_date, received`.

**First run:** seed on-hand = 1000/SKU. Lead times (days): A2 B3 C4 D7 E4 F6 G4 H7 I5 J9.

**Each run, per SKU:**
1. `on_hand_before` = current on-hand. `units_sold` = full demand given, recorded as-is even if it exceeds stock.
2. `on_hand_after` = max(0, on_hand_before − units_sold). `lost_sales` = max(0, units_sold − on_hand_before).
3. Any OnOrder row with `received=FALSE` and `arrival_date <= today` gets added into on_hand_after and marked received.
4. avg_demand/sigma = mean/sample-stdev of every `units_sold` for that SKU since day 1 (full history). Defaults (10, 10) until ≥2 real data points exist.
