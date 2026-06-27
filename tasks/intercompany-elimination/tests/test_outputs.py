"""Behavioral verifier for the intercompany-elimination task.

Two layers of ground truth:
  * test_worked_examples uses a fixed dataset whose expected output is hardcoded
    from hand calculation (independent of any reference code), pinning every rule.
  * test_generated_coverage builds a larger deterministic dataset covering every
    classification/category/FX-direction and compares the agent's program output
    to an independent reference implementation.
The agent's /app/consolidate.py is re-run on hidden, regenerated data each time,
so a hardcoded output cannot pass.
"""
import os
import csv
import json
import subprocess
from decimal import Decimal, ROUND_HALF_UP

DATA_DIR = "/app/data"
OUTPUT_FILE = "/app/output.json"
ENTRY = "python3 /app/consolidate.py"

CLOSING_TYPES = {"AR", "AP", "DIV_INCOME", "DIV_PAID"}
A_SIDE = {"AR", "REVENUE", "DIV_INCOME"}
CATEGORY = {"AR": "ar_ap", "AP": "ar_ap", "REVENUE": "rev_exp",
            "EXPENSE": "rev_exp", "DIV_INCOME": "div", "DIV_PAID": "div"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _reset(entities, fx, txns, pip):
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    _write_csv(os.path.join(DATA_DIR, "entities.csv"),
               ["entity_id", "functional_ccy", "parent_id", "ownership_pct"], entities)
    _write_csv(os.path.join(DATA_DIR, "fx_rates.csv"),
               ["ccy", "closing_rate", "average_rate"], fx)
    _write_csv(os.path.join(DATA_DIR, "ic_transactions.csv"),
               ["doc_id", "entity_id", "leg_type", "amount", "currency"], txns)
    _write_csv(os.path.join(DATA_DIR, "profit_in_inventory.csv"),
               ["seller_id", "buyer_id", "unrealized_profit", "currency"], pip)


def run_agent(timeout=120):
    proc = subprocess.run(ENTRY, shell=True, timeout=timeout)
    assert proc.returncode == 0, "Agent program exited non-zero."
    assert os.path.exists(OUTPUT_FILE), "Agent did not write /app/output.json."
    with open(OUTPUT_FILE) as f:
        return json.load(f)


def assert_matches(result, expected):
    assert set(result.keys()) == {"documents", "totals"}, f"top-level keys: {sorted(result)}"
    rd, ed = result["documents"], expected["documents"]
    assert set(rd.keys()) == set(ed.keys()), (
        f"document id set mismatch: missing {sorted(set(ed) - set(rd))[:5]}, extra {sorted(set(rd) - set(ed))[:5]}"
    )
    for doc, ev in ed.items():
        rv = rd[doc]
        assert set(rv.keys()) == {"eliminated_usd", "imbalance_usd", "classification"}, f"doc {doc} keys"
        assert rv["classification"] == ev["classification"], (
            f"doc {doc} classification: {rv['classification']} != {ev['classification']}")
        assert abs(float(rv["eliminated_usd"]) - ev["eliminated_usd"]) < 0.005, (
            f"doc {doc} eliminated_usd: {rv['eliminated_usd']} != {ev['eliminated_usd']}")
        assert abs(float(rv["imbalance_usd"]) - ev["imbalance_usd"]) < 0.005, (
            f"doc {doc} imbalance_usd: {rv['imbalance_usd']} != {ev['imbalance_usd']}")
    rt, et = result["totals"], expected["totals"]
    assert set(rt.keys()) == set(et.keys()), f"totals keys: {sorted(rt)} vs {sorted(et)}"
    for k, ev in et.items():
        assert abs(float(rt[k]) - ev) < 0.005, f"total {k}: {rt[k]} != {ev}"


# --------------------------------------------------------------------------- #
# independent reference (used only for the generated dataset)
# --------------------------------------------------------------------------- #
def _q2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reference(entities, fx, txns, pip):
    ent = {r[0]: r for r in entities}
    rates = {r[0]: (Decimal(r[1]), Decimal(r[2])) for r in fx}  # ccy -> (closing, average)

    def eff_own(eid):
        pct = Decimal("1")
        cur = eid
        while ent[cur][2].strip() != "":
            pct *= Decimal(ent[cur][3])
            cur = ent[cur][2].strip()
        return pct

    def to_usd(amount, ccy, leg_type):
        closing, average = rates[ccy]
        r = closing if leg_type in CLOSING_TYPES else average
        return _q2(Decimal(str(amount)) * r)

    by_doc = {}
    for doc_id, entity_id, leg_type, amount, ccy in txns:
        d = by_doc.setdefault(doc_id, {"a": None, "b": None, "cat": CATEGORY[leg_type]})
        side = "a" if leg_type in A_SIDE else "b"
        d[side] = to_usd(amount, ccy, leg_type)

    documents = {}
    tot = {k: Decimal("0.00") for k in (
        "eliminated_ar_ap_usd", "eliminated_rev_exp_usd", "eliminated_dividends_usd",
        "ic_imbalance_usd", "pip_eliminated_usd", "pip_nci_usd")}
    for doc_id, d in by_doc.items():
        ua = d["a"] if d["a"] is not None else Decimal("0.00")
        ub = d["b"] if d["b"] is not None else Decimal("0.00")
        eliminated = ua if ua < ub else ub
        imbalance = ua - ub
        if d["a"] is None or d["b"] is None:
            cls = "one_sided"
        else:
            diff = abs(ua - ub)
            tol = Decimal("0.005") * (ua if ua > ub else ub)
            if tol < Decimal("1.00"):
                tol = Decimal("1.00")
            cls = "matched" if diff == 0 else ("within_tolerance" if diff <= tol else "out_of_tolerance")
        documents[doc_id] = {"eliminated_usd": float(eliminated),
                             "imbalance_usd": float(imbalance), "classification": cls}
        tot["ic_imbalance_usd"] += imbalance
        tot["eliminated_" + {"ar_ap": "ar_ap", "rev_exp": "rev_exp", "div": "dividends"}[d["cat"]] + "_usd"] += eliminated

    for seller_id, buyer_id, profit, ccy in pip:
        usd = to_usd(profit, ccy, "REVENUE")
        tot["pip_eliminated_usd"] += usd
        seller = ent[seller_id]
        if seller[2].strip() == "":
            nci = Decimal("0.00")
        else:
            nci = _q2(usd * (Decimal("1") - eff_own(seller_id)))
        tot["pip_nci_usd"] += nci

    return {"documents": documents, "totals": {k: float(v) for k, v in tot.items()}}


# --------------------------------------------------------------------------- #
# datasets
# --------------------------------------------------------------------------- #
WORKED_ENTITIES = [
    ["US", "USD", "", ""],
    ["FR", "EUR", "US", "0.80"],
    ["DE", "EUR", "US", "0.75"],
    ["JP", "JPY", "US", "0.90"],
    ["FR2", "EUR", "FR", "0.50"],   # held through FR: effective ownership 0.80 x 0.50 = 0.40
]
WORKED_FX = [["USD", "1.0", "1.0"], ["EUR", "1.10", "1.08"], ["JPY", "0.0068", "0.0068"]]
WORKED_TXNS = [
    ["D1", "FR", "AR", "1000.00", "EUR"], ["D1", "US", "AP", "1095.00", "USD"],
    ["D2", "FR", "AR", "1000.00", "EUR"], ["D2", "US", "AP", "1080.00", "USD"],
    ["D3", "DE", "REVENUE", "2000.00", "EUR"], ["D3", "US", "EXPENSE", "2200.00", "USD"],
    ["D4", "JP", "AR", "150000", "JPY"],
    ["D5", "US", "DIV_INCOME", "500.00", "USD"], ["D5", "FR", "DIV_PAID", "460.00", "EUR"],
    ["D6", "FR", "AR", "1000.00", "EUR"], ["D6", "US", "AP", "1100.00", "USD"],  # matched
]
WORKED_PIP = [
    ["FR", "US", "1000.00", "EUR"],   # upstream, direct sub (g = 0.80)
    ["US", "FR", "500.00", "USD"],    # downstream (nci 0)
    ["FR2", "US", "1000.00", "EUR"],  # upstream, lower-tier sub (g = 0.40)
]
# Hand-verified expected output (independent of any reference code).
WORKED_EXPECTED = {
    "documents": {
        "D1": {"eliminated_usd": 1095.00, "imbalance_usd": 5.00, "classification": "within_tolerance"},
        "D2": {"eliminated_usd": 1080.00, "imbalance_usd": 20.00, "classification": "out_of_tolerance"},
        "D3": {"eliminated_usd": 2160.00, "imbalance_usd": -40.00, "classification": "out_of_tolerance"},
        "D4": {"eliminated_usd": 0.00, "imbalance_usd": 1020.00, "classification": "one_sided"},
        "D5": {"eliminated_usd": 500.00, "imbalance_usd": -6.00, "classification": "out_of_tolerance"},
        "D6": {"eliminated_usd": 1100.00, "imbalance_usd": 0.00, "classification": "matched"},
    },
    "totals": {
        "eliminated_ar_ap_usd": 3275.00,       # 1095 + 1080 + 1100
        "eliminated_rev_exp_usd": 2160.00,
        "eliminated_dividends_usd": 500.00,
        "ic_imbalance_usd": 999.00,            # 5 + 20 - 40 + 1020 - 6 + 0
        "pip_eliminated_usd": 2660.00,         # 1080 + 500 + 1080
        "pip_nci_usd": 864.00,                 # 1080*0.20 + 0 + 1080*0.60
    },
}


def build_generated():
    """Deterministic mid-size dataset covering every category x classification x
    FX direction, plus upstream/downstream/full-ownership PIP."""
    subs = [("FR", "EUR", "0.80"), ("DE", "EUR", "0.60"), ("GB", "GBP", "0.90"),
            ("JP", "JPY", "0.75"), ("CH", "CHF", "1.00")]
    entities = [["US", "USD", "", ""]] + [[s[0], s[1], "US", s[2]] for s in subs]
    # lower-tier subsidiaries held through another subsidiary (effective != direct)
    entities += [["FR2", "EUR", "FR", "0.50"],   # effective 0.80 x 0.50 = 0.40
                 ["DE2", "EUR", "DE", "0.70"]]   # effective 0.60 x 0.70 = 0.42
    fx = [["USD", "1.0", "1.0"], ["EUR", "1.10", "1.08"], ["GBP", "1.27", "1.25"],
          ["JPY", "0.0068", "0.0067"], ["CHF", "1.12", "1.11"]]
    rates = {r[0]: (Decimal(r[1]), Decimal(r[2])) for r in fx}

    cats = [("ar_ap", "AR", "AP"), ("rev_exp", "REVENUE", "EXPENSE"), ("div", "DIV_INCOME", "DIV_PAID")]
    modes = ["matched", "within", "out", "one_a", "one_b"]
    txns = []
    n = 0
    for i in range(300):
        cat, a_type, b_type = cats[i % 3]
        mode = modes[i % 5]
        sub = subs[i % len(subs)]
        foreign_is_a = (i % 2 == 0)
        rate = rates[sub[1]][0] if a_type in CLOSING_TYPES else rates[sub[1]][1]
        amount_f = Decimal(1000 + (i * 13) % 9000)
        usd_f = (amount_f * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        doc = f"G{i:04d}"
        # foreign leg
        f_entity, f_ccy, f_amt = sub[0], sub[1], amount_f
        # usd-controlled leg
        if mode == "matched":
            u_amt = usd_f
        elif mode == "within":
            u_amt = usd_f + Decimal("0.50")
        else:  # out / one_*
            u_amt = usd_f + (usd_f * Decimal("0.02")).quantize(Decimal("0.01")) + Decimal("5.00")
        f_leg = [doc, f_entity, (a_type if foreign_is_a else b_type), str(f_amt), f_ccy]
        u_leg = [doc, "US", (b_type if foreign_is_a else a_type), str(u_amt), "USD"]
        if mode == "one_a":
            txns.append(f_leg if foreign_is_a else u_leg)  # keep only the A-side leg
            # determine which physical leg is A-side
            txns[-1] = f_leg if foreign_is_a else u_leg
        elif mode == "one_b":
            txns.append(u_leg if foreign_is_a else f_leg)  # keep only the B-side leg
        else:
            txns.append(f_leg)
            txns.append(u_leg)
        n += 1

    pip = []
    for j, sub in enumerate(subs):
        pip.append([sub[0], "US", str(500 + j * 137), sub[1]])   # upstream from each direct sub
    pip.append(["FR2", "US", "1500.00", "EUR"])                  # upstream, 2-tier (effective 0.40)
    pip.append(["DE2", "US", "1700.00", "EUR"])                  # upstream, 2-tier (effective 0.42)
    pip.append(["US", "FR", "900.00", "USD"])                    # downstream
    pip.append(["US", "DE", "1234.50", "USD"])                   # downstream
    return entities, fx, txns, pip


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_worked_examples():
    """Fixed dataset with hand-verified expected output pinning every rule."""
    _reset(WORKED_ENTITIES, WORKED_FX, WORKED_TXNS, WORKED_PIP)
    result = run_agent()
    assert_matches(result, WORKED_EXPECTED)


def test_generated_coverage():
    """Mid-size deterministic dataset vs an independent reference; asserts that
    every classification, every category, and both PIP directions are exercised."""
    entities, fx, txns, pip = build_generated()
    _reset(entities, fx, txns, pip)
    expected = reference(entities, fx, txns, pip)

    classes = {d["classification"] for d in expected["documents"].values()}
    assert {"matched", "within_tolerance", "out_of_tolerance", "one_sided"} <= classes
    assert expected["totals"]["eliminated_ar_ap_usd"] > 0
    assert expected["totals"]["eliminated_rev_exp_usd"] > 0
    assert expected["totals"]["eliminated_dividends_usd"] > 0
    assert expected["totals"]["pip_nci_usd"] > 0

    # A lower-tier seller (parent is itself a subsidiary) must be present, so the
    # ownership chain is load-bearing — effective ownership differs from direct.
    ent_by_id = {r[0]: r for r in entities}
    two_tier = [row[0] for row in pip
                if ent_by_id[row[0]][2].strip()
                and ent_by_id[ent_by_id[row[0]][2].strip()][2].strip()]
    assert two_tier, "expected at least one lower-tier PIP seller"

    result = run_agent()
    assert_matches(result, expected)


def test_empty_inputs():
    """No transactions and no profit-in-inventory yields zeroed totals."""
    _reset([["US", "USD", "", ""]], [["USD", "1.0", "1.0"]], [], [])
    result = run_agent()
    assert result["documents"] == {}
    for v in result["totals"].values():
        assert abs(float(v)) < 0.005
