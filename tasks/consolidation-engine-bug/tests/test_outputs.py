"""Behavioral verifier for the consolidation-engine-bug task.

The agent must fix the defect in the engine under /app. This verifier re-runs
the agent's `python3 /app/consolidate.py` on hidden, regenerated datasets and
compares the result field-by-field to an INDEPENDENT reference implementation of
the engine's intended ("house rule") behavior:

  * monetary legs at closing, result legs at average, round half-up;
  * eliminated = min of the two legs, or the whole leg for a one-sided document;
  * imbalance reported as usd_b - usd_a;
  * ic_imbalance_usd = sum of |imbalance| across documents;
  * PIP at the average rate, NCI = profit * (1 - effective interest), where the
    effective interest is the ownership product up the WHOLE parent chain.

The unfixed engine computes effective interest for the wrong set of entities, so
lower-tier subsidiaries fall back to their direct rate and their NCI is wrong;
the generated datasets contain such sellers, so the buggy engine fails here.
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
    assert proc.returncode == 0, "Engine exited non-zero."
    assert os.path.exists(OUTPUT_FILE), "Engine did not write /app/output.json."
    with open(OUTPUT_FILE) as f:
        return json.load(f)


def assert_matches(result, expected):
    assert set(result.keys()) == {"documents", "totals"}, f"top-level keys: {sorted(result)}"
    rd, ed = result["documents"], expected["documents"]
    assert set(rd.keys()) == set(ed.keys()), (
        f"document id set mismatch: missing {sorted(set(ed) - set(rd))[:5]}, "
        f"extra {sorted(set(rd) - set(ed))[:5]}")
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
# independent reference implementation of the engine's intended behavior
# --------------------------------------------------------------------------- #
def _q2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reference(entities, fx, txns, pip):
    ent = {r[0]: r for r in entities}
    rates = {r[0]: (Decimal(r[1]), Decimal(r[2])) for r in fx}

    def to_usd(amount, ccy, leg_type):
        closing, average = rates[ccy]
        r = closing if leg_type in CLOSING_TYPES else average
        return _q2(Decimal(str(amount)) * r)

    def effective(eid):
        pct = Decimal("1")
        cur = eid
        while ent[cur][2].strip():
            pct *= Decimal(ent[cur][3])
            cur = ent[cur][2].strip()
        return pct

    by_doc = {}
    for doc_id, entity_id, leg_type, amount, ccy in txns:
        d = by_doc.setdefault(doc_id, {"a": None, "b": None, "cat": CATEGORY[leg_type]})
        d["a" if leg_type in A_SIDE else "b"] = to_usd(amount, ccy, leg_type)

    documents = {}
    cat = {"ar_ap": Decimal("0.00"), "rev_exp": Decimal("0.00"), "div": Decimal("0.00")}
    imb_total = Decimal("0.00")
    for doc_id, d in by_doc.items():
        two = d["a"] is not None and d["b"] is not None
        ua = d["a"] if d["a"] is not None else Decimal("0.00")
        ub = d["b"] if d["b"] is not None else Decimal("0.00")
        if two:
            eliminated = ua if ua < ub else ub
            diff = abs(ua - ub)
            tol = Decimal("0.005") * (ua if ua > ub else ub)
            if tol < Decimal("1.00"):
                tol = Decimal("1.00")
            cls = "matched" if diff == 0 else ("within_tolerance" if diff <= tol else "out_of_tolerance")
        else:
            eliminated = ua if d["a"] is not None else ub
            cls = "one_sided"
        documents[doc_id] = {"eliminated_usd": float(eliminated),
                             "imbalance_usd": float(ub - ua), "classification": cls}
        cat[d["cat"]] += eliminated
        imb_total += abs(ub - ua)

    pip_total = Decimal("0.00")
    nci_total = Decimal("0.00")
    for seller_id, buyer_id, profit, ccy in pip:
        usd = to_usd(profit, ccy, "REVENUE")
        pip_total += usd
        if ent[seller_id][2].strip() == "":
            continue
        nci_total += _q2(usd * (Decimal("1") - effective(seller_id)))

    return {
        "documents": documents,
        "totals": {
            "eliminated_ar_ap_usd": float(cat["ar_ap"]),
            "eliminated_rev_exp_usd": float(cat["rev_exp"]),
            "eliminated_dividends_usd": float(cat["div"]),
            "ic_imbalance_usd": float(imb_total),
            "pip_eliminated_usd": float(pip_total),
            "pip_nci_usd": float(nci_total),
        },
    }


# --------------------------------------------------------------------------- #
# generated datasets
# --------------------------------------------------------------------------- #
def build_generated():
    """Deterministic dataset covering every category x classification, one-sided
    documents, and PIP from direct, lower-tier (leaf), and downstream sellers."""
    # ownership chains, including multi-tier leaves that are never a parent
    entities = [
        ["US", "USD", "", ""],
        ["FR", "EUR", "US", "0.80"], ["DE", "EUR", "US", "0.60"],
        ["GB", "GBP", "US", "0.90"], ["JP", "JPY", "US", "0.75"],
        ["FRH", "EUR", "FR", "0.70"],     # mid-tier holdco under FR
        ["FR2", "EUR", "FRH", "0.50"],    # leaf, 3 tiers: 0.80*0.70*0.50 = 0.28
        ["DE2", "EUR", "DE", "0.40"],     # leaf, 2 tiers: 0.60*0.40 = 0.24
        ["GB2", "GBP", "GB", "0.80"],     # leaf, 2 tiers: 0.90*0.80 = 0.72
    ]
    fx = [["USD", "1.0", "1.0"], ["EUR", "1.10", "1.08"], ["GBP", "1.27", "1.25"],
          ["JPY", "0.0068", "0.0067"]]
    rates = {r[0]: (Decimal(r[1]), Decimal(r[2])) for r in fx}

    cats = [("AR", "AP"), ("REVENUE", "EXPENSE"), ("DIV_INCOME", "DIV_PAID")]
    modes = ["matched", "within", "out", "one_a", "one_b"]
    subs = ["FR", "DE", "GB", "JP"]
    sub_ccy = {"FR": "EUR", "DE": "EUR", "GB": "GBP", "JP": "JPY"}
    txns = []
    for i in range(200):
        a_type, b_type = cats[i % 3]
        mode = modes[i % 5]
        sub = subs[i % len(subs)]
        ccy = sub_ccy[sub]
        rate = rates[ccy][0] if a_type in CLOSING_TYPES else rates[ccy][1]
        amount_f = Decimal(1000 + (i * 17) % 8000)
        usd_f = (amount_f * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        doc = f"G{i:04d}"
        foreign_is_a = (i % 2 == 0)
        f_leg = [doc, sub, (a_type if foreign_is_a else b_type), str(amount_f), ccy]
        if mode == "matched":
            u_amt = usd_f
        elif mode == "within":
            u_amt = usd_f + Decimal("0.50")
        else:
            u_amt = usd_f + (usd_f * Decimal("0.03")).quantize(Decimal("0.01")) + Decimal("4.00")
        u_leg = [doc, "US", (b_type if foreign_is_a else a_type), str(u_amt), "USD"]
        if mode == "one_a":
            txns.append(f_leg if foreign_is_a else u_leg)
        elif mode == "one_b":
            txns.append(u_leg if foreign_is_a else f_leg)
        else:
            txns.append(f_leg)
            txns.append(u_leg)

    pip = [
        ["FR", "US", "1200.00", "EUR"],     # direct sub
        ["DE", "US", "900.00", "EUR"],      # direct sub
        ["FR2", "US", "1500.00", "EUR"],    # leaf, 3-tier (effective 0.28)
        ["DE2", "US", "1700.00", "EUR"],    # leaf, 2-tier (effective 0.24)
        ["GB2", "US", "1300.00", "GBP"],    # leaf, 2-tier (effective 0.72)
        ["FRH", "US", "800.00", "EUR"],     # mid-tier holdco (effective 0.56)
        ["US", "FR", "1000.00", "USD"],     # downstream (nci 0)
        ["US", "DE", "650.50", "USD"],      # downstream (nci 0)
    ]
    return entities, fx, txns, pip


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_generated_coverage():
    entities, fx, txns, pip = build_generated()
    _reset(entities, fx, txns, pip)
    expected = reference(entities, fx, txns, pip)

    classes = {d["classification"] for d in expected["documents"].values()}
    assert {"matched", "within_tolerance", "out_of_tolerance", "one_sided"} <= classes
    for k in ("eliminated_ar_ap_usd", "eliminated_rev_exp_usd", "eliminated_dividends_usd",
              "ic_imbalance_usd", "pip_eliminated_usd", "pip_nci_usd"):
        assert expected["totals"][k] > 0

    # the bug is load-bearing: a lower-tier leaf seller (parent is itself a
    # subsidiary) must be present so effective interest != direct interest.
    ent_by_id = {r[0]: r for r in entities}

    def depth(eid):
        d, cur = 0, eid
        while ent_by_id[cur][2].strip():
            d += 1
            cur = ent_by_id[cur][2].strip()
        return d

    assert any(depth(row[0]) >= 2 for row in pip), "need a lower-tier PIP seller"
    assert any(depth(row[0]) >= 3 for row in pip), "need a 3-tier PIP seller"

    result = run_agent()
    assert_matches(result, expected)


def test_second_dataset():
    """A different shape (no rev_exp, deeper PIP mix) so a fix must generalize."""
    entities = [
        ["P", "USD", "", ""],
        ["A", "EUR", "P", "0.90"], ["B", "GBP", "P", "0.55"],
        ["A1", "EUR", "A", "0.60"],            # 2-tier leaf: 0.54
        ["A11", "EUR", "A1", "0.80"],          # 3-tier leaf: 0.432
    ]
    fx = [["USD", "1.0", "1.0"], ["EUR", "1.07", "1.05"], ["GBP", "1.30", "1.28"]]
    txns = [
        ["X1", "A", "AR", "2000.00", "EUR"], ["X1", "P", "AP", "2140.00", "USD"],
        ["X2", "B", "DIV_PAID", "300.00", "GBP"], ["X2", "P", "DIV_INCOME", "385.00", "USD"],
        ["X3", "A", "AR", "750.00", "EUR"],   # one-sided
    ]
    pip = [
        ["A11", "P", "1234.00", "EUR"],   # 3-tier leaf
        ["A1", "P", "980.00", "EUR"],     # 2-tier leaf
        ["B", "P", "640.00", "GBP"],      # direct
        ["P", "A", "500.00", "USD"],      # downstream
    ]
    _reset(entities, fx, txns, pip)
    expected = reference(entities, fx, txns, pip)
    result = run_agent()
    assert_matches(result, expected)


def test_empty_inputs():
    _reset([["US", "USD", "", ""]], [["USD", "1.0", "1.0"]], [], [])
    result = run_agent()
    assert result["documents"] == {}
    for v in result["totals"].values():
        assert abs(float(v)) < 0.005
