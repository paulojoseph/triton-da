#!/usr/bin/env python3
"""Group consolidation entry point.

Reads the CSV files under /app/data and writes the consolidated result to
/app/output.json. The per-module docstrings document the intended consolidation
rules; this script wires the pieces together:

  1. translate every transaction leg to USD,
  2. pair the legs of each document and eliminate them,
  3. roll the eliminations up into per-category totals and the imbalance total,
  4. eliminate unrealised profit in inventory and split off NCI.

Output JSON shape:
  {"documents": {doc_id: {eliminated_usd, imbalance_usd, classification}},
   "totals": {eliminated_ar_ap_usd, eliminated_rev_exp_usd,
              eliminated_dividends_usd, ic_imbalance_usd,
              pip_eliminated_usd, pip_nci_usd}}

House rule (intentional): ``ic_imbalance_usd`` is the total ABSOLUTE mismatch
across documents -- the sum of |imbalance_usd| -- a measure of how much
intercompany detail fails to tie out, regardless of direction.
"""
import csv
import json
import os
from decimal import Decimal

from congraph import OwnershipGraph
from fxtrans import Translator
from icelim import eliminate_document, CATEGORY, A_SIDE
from invprofit import eliminate_pip

DATA_DIR = "/app/data"
OUTPUT_PATH = "/app/output.json"


def _load(name):
    with open(os.path.join(DATA_DIR, name), newline="") as f:
        return list(csv.DictReader(f))


def main():
    entities = {r["entity_id"]: r for r in _load("entities.csv")}
    graph = OwnershipGraph(entities)
    translator = Translator(_load("fx_rates.csv"))

    # effective interest for every consolidated subsidiary
    effective = {eid: graph.effective_interest(eid)
                 for eid in graph.consolidated_entities()}

    # collect the two legs of each document
    legs = {}
    for row in _load("ic_transactions.csv"):
        leg_type = row["leg_type"]
        usd = translator.to_usd(row["amount"], row["currency"], leg_type)
        slot = legs.setdefault(row["doc_id"], {"a": None, "b": None, "cat": CATEGORY[leg_type]})
        slot["a" if leg_type in A_SIDE else "b"] = usd

    documents = {}
    cat_totals = {"ar_ap": Decimal("0.00"), "rev_exp": Decimal("0.00"), "div": Decimal("0.00")}
    imbalance_total = Decimal("0.00")
    for doc_id, slot in legs.items():
        result = eliminate_document(slot["a"], slot["b"])
        documents[doc_id] = result
        cat_totals[slot["cat"]] += result["eliminated_usd"]
        imbalance_total += abs(result["imbalance_usd"])

    pip_total, nci_total = eliminate_pip(
        _load("profit_in_inventory.csv"), translator, graph, effective)

    out = {
        "documents": {
            doc_id: {
                "eliminated_usd": float(r["eliminated_usd"]),
                "imbalance_usd": float(r["imbalance_usd"]),
                "classification": r["classification"],
            } for doc_id, r in documents.items()
        },
        "totals": {
            "eliminated_ar_ap_usd": float(cat_totals["ar_ap"]),
            "eliminated_rev_exp_usd": float(cat_totals["rev_exp"]),
            "eliminated_dividends_usd": float(cat_totals["div"]),
            "ic_imbalance_usd": float(imbalance_total),
            "pip_eliminated_usd": float(pip_total),
            "pip_nci_usd": float(nci_total),
        },
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
