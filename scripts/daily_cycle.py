"""
Deterministic implementation of data-agent + planning-agent (see .claude/subagents/).

This used to be delegated to an LLM subagent every day. That cost 20-40k+ tokens
per run for pure arithmetic and xlsx I/O, and a cheap model once silently used the
wrong EOQ formula (dropped the material-cost term) because it "remembered" the
textbook version instead of following this spec's derivation exactly. Fixed
formulas in code can't drift like that and cost near-zero tokens to run, so the
number-crunching lives here now. supervisor/the top-level session call this
script and only use an LLM for what actually needs judgement: collecting input,
drafting the email, getting send approval.

Usage:
    python scripts/daily_cycle.py <date YYYY-MM-DD> <units_sold_json>
    e.g. python scripts/daily_cycle.py 2026-10-01 '{"A":30,"B":45,...}'

Prints one compact JSON object with the full 10-SKU result to stdout.
"""
import sys
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

import os

REPO_ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH = Path(os.environ.get("DAILY_CYCLE_XLSX_PATH", REPO_ROOT / "data" / "inventory.xlsx"))

SKUS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
LEAD_TIME_DAYS = {"A": 2, "B": 3, "C": 4, "D": 7, "E": 4, "F": 6, "G": 4, "H": 7, "I": 5, "J": 9}
PRICE = {"A": 23, "B": 54, "C": 76, "D": 35, "E": 66, "F": 76, "G": 78, "H": 897, "I": 54, "J": 77}

Z = 1.65  # 95% service level, fixed per spec
ORDERING_COST = 250
ANNUAL_DEMAND_DEFAULT = 10000
DEFAULT_AVG_DEMAND = 10
DEFAULT_SIGMA = 10
ORDER_QTY_SANITY_MULTIPLE = 5  # flag rather than record if order_qty > 5x ROP


def eoq(price):
    return math.sqrt(ORDERING_COST * ANNUAL_DEMAND_DEFAULT / (1.05 * price))


def load_or_create_workbook():
    if XLSX_PATH.exists():
        return openpyxl.load_workbook(XLSX_PATH)
    XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    sales = wb.active
    sales.title = "Sales"
    sales.append(["date", "sku", "units_sold", "on_hand_after", "lost_sales", "avg_demand", "sigma"])
    onorder = wb.create_sheet("OnOrder")
    onorder.append(["order_date", "sku", "qty", "lead_time_days", "arrival_date", "received"])
    return wb


def stdev_sample(values):
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def run(today_str, units_sold):
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    wb = load_or_create_workbook()
    sales_ws = wb["Sales"]
    onorder_ws = wb["OnOrder"]

    # last on_hand_after per SKU (seed 1000 if no history yet)
    last_on_hand = {sku: 1000 for sku in SKUS}
    history_units_sold = {sku: [] for sku in SKUS}
    for row in sales_ws.iter_rows(min_row=2, values_only=True):
        date_v, sku_v, units_v, on_hand_v = row[0], row[1], row[2], row[3]
        if sku_v in history_units_sold:
            history_units_sold[sku_v].append(units_v)
            last_on_hand[sku_v] = on_hand_v

    # receive any on-order rows whose lead time has elapsed, not yet received
    pending_before = {sku: 0 for sku in SKUS}
    onorder_rows = list(onorder_ws.iter_rows(min_row=2))
    received_indices = []
    for idx, row in enumerate(onorder_rows):
        order_date, sku_v, qty_v, lead_v, arrival_v, received_v = [c.value for c in row]
        if received_v:
            continue
        if sku_v in pending_before:
            pending_before[sku_v] += qty_v
        if as_date(arrival_v) <= today:
            last_on_hand[sku_v] = last_on_hand.get(sku_v, 0) + qty_v
            pending_before[sku_v] -= qty_v
            received_indices.append(idx)

    result = {}
    for sku in SKUS:
        on_hand_before = last_on_hand[sku]
        sold = units_sold[sku]
        on_hand_after = max(0, on_hand_before - sold)
        lost_sales = max(0, sold - on_hand_before)

        history = history_units_sold[sku] + [sold]
        avg_demand = sum(history) / len(history) if len(history) >= 2 else DEFAULT_AVG_DEMAND
        sigma = stdev_sample(history) if len(history) >= 2 else DEFAULT_SIGMA

        sales_ws.append([today_str, sku, sold, on_hand_after, lost_sales, round(avg_demand, 4), round(sigma, 4)])

        lead = LEAD_TIME_DAYS[sku]
        safety_stock = Z * sigma * math.sqrt(lead)
        pipeline_stock = avg_demand * lead
        rop = safety_stock + pipeline_stock

        pending = pending_before[sku]
        inventory_position = on_hand_after + pending
        flagged = inventory_position < rop

        order_qty = 0
        eoq_val = eoq(PRICE[sku])
        anomaly = None
        if flagged:
            shortfall = rop - inventory_position
            batches = max(1, math.ceil(shortfall / eoq_val))
            order_qty = round(batches * eoq_val)
            if order_qty > ORDER_QTY_SANITY_MULTIPLE * rop or order_qty <= 0:
                anomaly = f"order_qty {order_qty} exceeds {ORDER_QTY_SANITY_MULTIPLE}x ROP ({rop:.1f}) - not recorded, needs review"
                order_qty = 0
            else:
                arrival = today + timedelta(days=lead)
                onorder_ws.append([today_str, sku, order_qty, lead, arrival.isoformat(), False])

        result[sku] = {
            "on_hand": on_hand_after,
            "pending_before": pending,
            "rop": round(rop, 2),
            "flagged": flagged and order_qty > 0,
            "eoq": round(eoq_val, 2),
            "order_qty": order_qty,
            "price": PRICE[sku],
            "avg_demand": round(avg_demand, 2),
            "sigma": round(sigma, 2),
            "lost_sales": lost_sales,
            "anomaly": anomaly,
        }

    for idx in received_indices:
        onorder_rows[idx][5].value = True

    # detail list of everything still outstanding per SKU (prior days' orders and
    # anything just placed above), for the email — not just the aggregate sum
    pending_orders = {sku: [] for sku in SKUS}
    for row in onorder_ws.iter_rows(min_row=2, values_only=True):
        order_date_v, sku_v, qty_v, lead_v, arrival_v, received_v = row
        if received_v or sku_v not in pending_orders:
            continue
        pending_orders[sku_v].append({
            "qty": qty_v,
            "order_date": str(order_date_v)[:10],
            "arrival_date": str(arrival_v)[:10],
        })
    for sku in SKUS:
        pending_orders[sku].sort(key=lambda o: o["order_date"])
        result[sku]["pending_orders"] = pending_orders[sku]

    # one-time cost of every order ever placed (regardless of received status —
    # incurred at order time): ordering + material cost for that order's qty.
    # The EOQ derivation's "holding" term (0.10*price*Q/2) is a batch-sizing proxy,
    # not a real cost — it's deliberately excluded here so it isn't double-counted
    # against the real, day-by-day holding_cost_to_date below.
    ordering_and_material_cost_to_date = 0.0
    for row in onorder_ws.iter_rows(min_row=2, values_only=True):
        _, sku_v, qty_v, _, _, _ = row
        if sku_v not in PRICE or not qty_v:
            continue
        price = PRICE[sku_v]
        ordering = (ANNUAL_DEMAND_DEFAULT / qty_v) * ORDERING_COST
        material = price * qty_v
        ordering_and_material_cost_to_date += ordering + material

    # real, continuously-accruing holding cost: on_hand * price * daily rate,
    # summed over every day-per-SKU row ever recorded. Holding rate (10% of
    # price) is treated as an ANNUAL rate per the spec, so daily rate = 0.10/365.
    DAILY_HOLDING_RATE = 0.10 / 365
    holding_cost_to_date = 0.0
    for row in sales_ws.iter_rows(min_row=2, values_only=True):
        _, sku_v, _, on_hand_after_v, *_ = row
        if sku_v not in PRICE:
            continue
        holding_cost_to_date += on_hand_after_v * PRICE[sku_v] * DAILY_HOLDING_RATE

    grand_total_cost_to_date = ordering_and_material_cost_to_date + holding_cost_to_date

    wb.save(XLSX_PATH)
    return {
        "skus": result,
        "ordering_and_material_cost_to_date": round(ordering_and_material_cost_to_date, 2),
        "holding_cost_to_date": round(holding_cost_to_date, 2),
        "grand_total_cost_to_date": round(grand_total_cost_to_date, 2),
    }


if __name__ == "__main__":
    date_arg = sys.argv[1]
    arg2 = sys.argv[2]
    # arg2 is either inline JSON or a path to a JSON file (avoids shell quoting issues)
    if arg2.strip().startswith("{"):
        units_sold_arg = json.loads(arg2)
    else:
        units_sold_arg = json.loads(Path(arg2).read_text())
    output = run(date_arg, units_sold_arg)
    print(json.dumps(output))
