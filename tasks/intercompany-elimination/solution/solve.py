#!/usr/bin/env python3
"""Reference intercompany elimination engine."""
import csv
import json
import os
from decimal import Decimal, ROUND_HALF_UP

DATA_DIR = "/app/data"
OUTPUT_PATH = "/app/output.json"

CLOSING_TYPES = {"AR", "AP", "DIV_INCOME", "DIV_PAID"}
A_SIDE = {"AR", "REVENUE", "DIV_INCOME"}
CATEGORY = {
    "AR": "ar_ap", "AP": "ar_ap",
    "REVENUE": "rev_exp", "EXPENSE": "rev_exp",
    "DIV_INCOME": "div", "DIV_PAID": "div",
}


def q2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _load(name):
    with open(os.path.join(DATA_DIR, name), newline="") as f:
        return list(csv.DictReader(f))


def main():
    entities = {r["entity_id"]: r for r in _load("entities.csv")}
    fx = {r["ccy"]: r for r in _load("fx_rates.csv")}

    def rate(ccy, leg_type):
        r = fx[ccy]
        return Decimal(r["closing_rate"]) if leg_type in CLOSING_TYPES else Decimal(r["average_rate"])

    def effective_ownership(entity_id):
        pct = Decimal("1")
        cur = entity_id
        while entities[cur]["parent_id"].strip() != "":
            pct *= Decimal(entities[cur]["ownership_pct"])
            cur = entities[cur]["parent_id"].strip()
        return pct

    docs = {}  # doc_id -> {a, b, cat}
    for row in _load("ic_transactions.csv"):
        doc = row["doc_id"]
        lt = row["leg_type"]
        usd = q2(Decimal(row["amount"]) * rate(row["currency"], lt))
        d = docs.setdefault(doc, {"a": None, "b": None, "cat": CATEGORY[lt]})
        if lt in A_SIDE:
            d["a"] = usd
        else:
            d["b"] = usd

    documents = {}
    totals = {k: Decimal("0.00") for k in (
        "eliminated_ar_ap_usd", "eliminated_rev_exp_usd", "eliminated_dividends_usd",
        "ic_imbalance_usd", "pip_eliminated_usd", "pip_nci_usd")}

    for doc, d in docs.items():
        a, b = d["a"], d["b"]
        ua = a if a is not None else Decimal("0.00")
        ub = b if b is not None else Decimal("0.00")
        eliminated = min(ua, ub)
        imbalance = ua - ub
        if a is None or b is None:
            classification = "one_sided"
        else:
            diff = abs(ua - ub)
            tol = max(Decimal("1.00"), Decimal("0.005") * max(ua, ub))
            classification = "matched" if diff == 0 else ("within_tolerance" if diff <= tol else "out_of_tolerance")
        documents[doc] = {
            "eliminated_usd": float(eliminated),
            "imbalance_usd": float(imbalance),
            "classification": classification,
        }
        totals["ic_imbalance_usd"] += imbalance
        cat = d["cat"]
        if cat == "ar_ap":
            totals["eliminated_ar_ap_usd"] += eliminated
        elif cat == "rev_exp":
            totals["eliminated_rev_exp_usd"] += eliminated
        else:
            totals["eliminated_dividends_usd"] += eliminated

    for row in _load("profit_in_inventory.csv"):
        usd = q2(Decimal(row["unrealized_profit"]) * rate(row["currency"], "REVENUE"))
        totals["pip_eliminated_usd"] += usd
        seller = entities[row["seller_id"]]
        if seller["parent_id"].strip() == "":
            nci = Decimal("0.00")
        else:
            nci = q2(usd * (Decimal("1") - effective_ownership(row["seller_id"])))
        totals["pip_nci_usd"] += nci

    out = {"documents": documents, "totals": {k: float(v) for k, v in totals.items()}}
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
