# planning-agent

**Spec only — not executed via Agent/LLM at all.** This logic is implemented deterministically in `scripts/daily_cycle.py` (the ROP/EOQ/ordering section below). Kept as the human-readable spec for what the script does and why. It was previously delegated to a cheap LLM subagent, which silently used the textbook EOQ formula instead of this one — see `../CLAUDE.md`'s anomaly note. That's exactly the failure mode fixed by moving this into code: a formula in a script can't drift between runs.

---

Full spec: `../CLAUDE.md`.

**Formulas:** Safety Stock = `1.65 * sigma * sqrt(lead_time_days)` (Z fixed). Pipeline Stock = `avg_demand * lead_time_days`. ROP = Safety + Pipeline. EOQ (per batch) = `sqrt(250 * AnnualDemand / (1.05 * price))`, AnnualDemand defaults 10000 — material cost is deliberately included.

**Defaults:** lead times (days) A2 B3 C4 D7 E4 F6 G4 H7 I5 J9. Prices A23 B54 C76 D35 E66 F76 G78 H897 I54 J77.

**Inventory position, not just on-hand:** `pending` = sum of OnOrder `qty` for that SKU where `received=FALSE`. `inventory_position = on_hand + pending`. Flag if `inventory_position < ROP`.

**Order sizing:** if flagged, `shortfall = ROP - inventory_position`; `batches = ceil(shortfall / EOQ)`, minimum 1; `order_qty = batches * EOQ`, rounded.

**Sanity guardrail:** don't record (flag as an anomaly instead) an `order_qty` that's more than 5x the SKU's ROP, or ≤0 — a huge multiple of ROP suggests a data error rather than a real order. (Earlier version compared against on-hand instead of ROP; that broke for any stocked-out SKU, since dividing by an on-hand of 0 always looks infinite. ROP is a meaningful, always-positive baseline instead.)
