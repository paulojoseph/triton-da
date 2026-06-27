"""Behavioral verifier for limit-order-book-engine.

Regenerates hidden event streams, runs the agent's /app/engine.py on them, and
checks the produced /app/result.json exactly against an independent reference
engine. The large stream additionally enforces a wall-clock budget: a per-event
scan of the book is O(n^2) and cannot finish, so the engine must use the right
data structures while remaining exactly correct.
"""
import os
import sys
import json
import time
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import lob_ref as R

EVENTS = "/app/events.csv"
RESULT = "/app/result.json"
ENTRY = "python3 /app/engine.py"
KEYS = {"trades", "volume", "notional", "resting_orders", "resting_volume",
        "resting_id_sum", "resting_notional", "best_bid", "best_ask"}
SPEED_BUDGET = 30.0


def _setup(seed, n):
    for p in (RESULT, EVENTS):
        if os.path.exists(p):
            os.remove(p)
    events = R.generate(seed, n)
    R.write_events(events, EVENTS)
    return R.run(events)


def run_agent(timeout):
    if os.path.exists(RESULT):
        os.remove(RESULT)
    t0 = time.time()
    proc = subprocess.run(ENTRY, shell=True, timeout=timeout)
    elapsed = time.time() - t0
    assert proc.returncode == 0, "engine exited non-zero."
    assert os.path.exists(RESULT), "engine did not write /app/result.json."
    with open(RESULT) as f:
        return json.load(f), elapsed


def check(expected, timeout, budget=None):
    got, elapsed = run_agent(timeout)
    assert set(got.keys()) == KEYS, f"result keys: {sorted(got)}"
    for k in KEYS:
        assert got[k] == expected[k], f"{k}: {got[k]} != {expected[k]}"
    if budget is not None:
        assert elapsed < budget, f"too slow: {elapsed:.1f}s >= {budget}s budget"


def test_correctness_small():
    """Several adversarial streams (cancels, market sweeps, recycled price
    levels, partial fills); every aggregate must match exactly."""
    for seed in (40001, 40002, 40003, 40004):
        expected = _setup(seed, 60000)
        check(expected, timeout=40)


def test_correctness_medium():
    """A larger stream; a quadratic engine cannot finish in time."""
    expected = _setup(50007, 300000)
    check(expected, timeout=60)


def test_speed_and_correctness():
    """A large stream: exact result AND within the wall-clock budget."""
    expected = _setup(60011, 1500000)
    check(expected, timeout=90, budget=SPEED_BUDGET)
