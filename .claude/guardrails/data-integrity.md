# Data integrity guardrail

Rules for `data/inventory.xlsx`, the system's only database. All three subagents that touch it must follow these.

## Sales sheet

- **Append-only.** Never edit or delete a historical `Sales` row. If a past day's figure was wrong, append a correction note rather than rewriting history — the rolling avg_demand/sigma calculation depends on every row being what was actually recorded that day.
- `avg_demand` and `sigma` are recomputed from the **full** history every run, not a fixed trailing window, and not carried over from the previous row unless recalculated fresh.

## Stock floor & lost sales

- **On-hand stock must never go negative.** If a day's `units_sold` for a SKU exceeds that SKU's on-hand stock before the sale, the SKU has stocked out partway through the day: clamp `on_hand_after` at **0**, and record the unmet demand as `lost_sales = units_sold - on_hand_before` (never negative itself).
- `units_sold` still records the **full requested demand** as given, including the lost-sales portion — don't reduce it to what was actually fulfillable. Demand planning (avg_demand, sigma, and therefore Safety Stock and ROP) must reflect true customer demand, not demand artificially capped by that day's stock level; understating it here would make future stockouts more likely, not less.
- This applies at write time, in data-agent, not as a later correction — a day's `on_hand_after` should never be written negative in the first place.

## OnOrder sheet

- Each row may be marked `received = TRUE` **exactly once**. Before adding a new on-order row, and before flipping a row to received, re-read the sheet's current state — don't rely on a stale in-memory copy from earlier in the run.
- Never delete an `OnOrder` row, including after it's received — it's part of the audit trail.

## Formula correctness

- `data/inventory.xlsx`'s `Sales` and `OnOrder` sheets hold **plain computed values, not live Excel formulas.** Every cell (`on_hand_after`, `avg_demand`, `sigma`, `arrival_date`, etc.) is a number data-agent/planning-agent already computed in Python before writing — it's a historical snapshot for that day/order, not a value that should auto-recompute if a past row is ever corrected. Do not write these as `=...` formulas.
- This is also a practical constraint, not just a style choice: this project's environment has no LibreOffice/`soffice` installed, so the xlsx skill's `recalc.py` (which the skill normally requires after any write that includes a formula) cannot run here. Writing formulas that can never be recalculated would leave the workbook silently un-verified.
- **Verify every write by re-reading the affected cells directly with openpyxl** (not `recalc.py`) immediately after writing, and confirm they hold the value you intended before finishing. Treat a mismatch the same as a formula error: fix it and re-verify.
- If a future change genuinely needs a live formula (e.g. a summary sheet a human will open and expect to recalculate on edit), that's a deliberate exception — flag it back to the user rather than adding it silently, since it reintroduces the recalc dependency this environment can't satisfy.
