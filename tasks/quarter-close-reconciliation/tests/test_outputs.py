"""Behavioral verifier for quarter-close-reconciliation.

Each test regenerates a fresh entity's books (hidden seeds, the same source
formats as the sample), runs the agent's /app/reconcile.py on them, and compares
the result to the golden reconciliation computed by recon_gen. Because the data
is regenerated and the program is re-run, a hardcoded reconciliation.json cannot
pass — the agent must actually parse and reconcile.
"""
import os
import sys
import json
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import recon_gen as g

ROOT = "/app"
SOURCES = os.path.join(ROOT, "sources")
OUTPUT = os.path.join(ROOT, "reconciliation.json")
ENTRY = "python3 /app/reconcile.py"
KEYS = {"matched", "unmatched_bank", "unmatched_ledger",
        "bank_close_usd", "ledger_close_usd", "residual_usd"}


def _setup(seed):
    if os.path.isdir(SOURCES):
        shutil.rmtree(SOURCES)
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)
    if os.path.exists(os.path.join(ROOT, "fx_rates.csv")):
        os.remove(os.path.join(ROOT, "fx_rates.csv"))
    entity = g.generate(seed)
    g.write_sources(entity, ROOT)
    return g.golden(entity)


def run_agent(timeout=300):
    proc = subprocess.run(ENTRY, shell=True, timeout=timeout)
    assert proc.returncode == 0, "reconcile.py exited non-zero."
    assert os.path.exists(OUTPUT), "reconcile.py did not write /app/reconciliation.json."
    with open(OUTPUT) as f:
        return json.load(f)


def assert_matches(result, gold):
    assert set(result.keys()) == set(gold.keys()), (
        f"account set mismatch: {sorted(set(gold) ^ set(result))}")
    for acc, gv in gold.items():
        rv = result[acc]
        assert set(rv.keys()) == KEYS, f"{acc} keys: {sorted(rv)}"
        rm = [list(p) for p in rv["matched"]]
        assert rm == gv["matched"], f"{acc} matched differs"
        assert list(rv["unmatched_bank"]) == gv["unmatched_bank"], f"{acc} unmatched_bank differs"
        assert list(rv["unmatched_ledger"]) == gv["unmatched_ledger"], f"{acc} unmatched_ledger differs"
        for k in ("bank_close_usd", "ledger_close_usd", "residual_usd"):
            assert abs(float(rv[k]) - gv[k]) < 0.005, f"{acc} {k}: {rv[k]} != {gv[k]}"


def _assert_nontrivial(gold):
    assert sum(len(v["matched"]) for v in gold.values()) >= 10
    assert sum(len(v["unmatched_bank"]) for v in gold.values()) >= 3
    assert sum(len(v["unmatched_ledger"]) for v in gold.values()) >= 3


def test_reconcile_entity_a():
    """A regenerated entity with all three bank formats and the ERP ledger."""
    gold = _setup(8101)
    _assert_nontrivial(gold)
    assert_matches(run_agent(), gold)


def test_reconcile_entity_b():
    """A different entity; a correct reconciler must generalise across seeds."""
    gold = _setup(8202)
    _assert_nontrivial(gold)
    assert_matches(run_agent(), gold)


def test_reconcile_entity_c():
    """A third entity, exercising different dates, duplicates and FX fallbacks."""
    gold = _setup(8303)
    _assert_nontrivial(gold)
    assert_matches(run_agent(), gold)
