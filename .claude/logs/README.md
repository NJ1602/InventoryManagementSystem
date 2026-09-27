# Run logs

One markdown file per day's run, at `logs/runs/<date>.md` (e.g. `logs/runs/2026-09-27.md`), written by `supervisor` as the last step of each daily cycle. This is a human-readable audit trail of what the agents *decided* — distinct from `data/inventory.xlsx`, which holds the raw sales/order data itself.

## Format

Each run log should record:

- The date and the units-sold figures the run was given for each SKU.
- Each SKU's on-hand stock, ROP, and whether it was flagged.
- For each flagged SKU: the EOQ quantity recorded and its expected arrival date.
- Whether an email draft was produced, and — filled in later, once known — whether the user approved it and it was sent.
- Anything a guardrail stopped or flagged (e.g. a suspicious EOQ, a missing SKU figure).

Keep it short and scannable — this is a log, not a report. `logs/runs/` is created on the first real run; it doesn't need to exist ahead of time.
