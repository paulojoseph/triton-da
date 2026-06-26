"""Behavioral verifier for the velocity-feature optimization task.

Correctness is checked against a brute-force reference on small, edge-case-rich
inputs (the brute force is obviously correct). Scale is checked on a large,
adversarial input under a hard wall-clock budget that the quadratic baseline
cannot meet, with the output compared to a fast independent reference.
"""
import os
import json
import time
import subprocess
from collections import defaultdict

WINDOW = 3600
DATA_DIR = "/app/data"
INPUT_PATH = "/app/data/transactions.jsonl"
OUTPUT_FILE = "/app/output.json"
ENTRY = "python3 /app/engine.py"

PERF_BUDGET_SEC = 20.0


# --------------------------------------------------------------------------- #
# Deterministic dataset construction
# --------------------------------------------------------------------------- #
def _write(path, txns):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for acc, ts, amt in txns:
            f.write(json.dumps({"account": acc, "ts": ts, "amount": amt}) + "\n")


def build_large(path, hot=720000, cold_accounts=8, cold_each=10000):
    """One hot account whose ~50-minute burst (720k transactions inside a span
    shorter than the 1h window) makes the trailing window hold ~360k rows, plus
    several normal low-volume accounts. With the window that dense, computing
    max_repeat by rebuilding a Counter per window (~N*avg_window) or by keeping an
    incremental Counter but scanning all distinct amounts for the max each step
    (~N*distinct) runs for tens of seconds to minutes and blows the budget; only
    O(1)-per-step maintenance of the sliding max-frequency stays under it."""
    txns = []
    base = 1_000_000
    for k in range(hot):
        # Mostly-unique amounts (a large distinct-value range) with a periodically
        # repeated "card-testing" amount. The large range makes scanning the
        # in-window frequencies for a max prohibitively slow.
        amount = 1 if k % 8 == 0 else 1000 + k
        txns.append(("hot", base + (k * 3000) // hot, amount))
    for a in range(cold_accounts):
        cbase = 5_000_000 + a * 1_000_000
        for k in range(cold_each):
            txns.append((f"cold-{a}", cbase + (k * 86400) // cold_each, 1 if k % 5 == 0 else 100000 + k))
    _write(path, txns)


def build_small(path):
    """Small, edge-case-rich input: max_repeat counts the row itself, same-ts
    ties, the inclusive window boundary at ts-3600, a peak frequency that must
    DROP once the window evicts its peak group, and isolated rows."""
    txns = [
        # acct-A: three equal amounts at one ts (peak max_repeat 3), then the
        # window slides past them so the peak frequency has to fall to 2.
        ("acct-A", 10000, 100),
        ("acct-A", 10000, 100),
        ("acct-A", 10000, 100),   # 3x amount 100 at ts=10000
        ("acct-A", 10000, 50),    # one 50 at the same ts
        ("acct-A", 13600, 200),   # ts-3600 == 10000 -> the ts=10000 rows are still in-window (boundary inclusive)
        ("acct-A", 13601, 200),   # 3601 later -> the ts=10000 rows drop out; peak must fall from 3 to 2
        ("acct-A", 13601, 100),   # same ts as the previous 200
        # acct-B: a same-amount pair within one hour -> max_repeat 2.
        ("acct-B", 50000, 10),
        ("acct-B", 51000, 10),
        ("acct-B", 99000, 999),   # far away -> sees none of the earlier acct-B rows
        # acct-C: a single transaction -> count 0 but max_repeat 1 (counts itself).
        ("acct-C", 7, 7),
    ]
    _write(path, txns)


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #
def _load(path):
    txns = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            txns.append((d["account"], d["ts"], d["amount"]))
    return txns


def brute_truth(path):
    """Obviously-correct O(N^2) reference (Counter per window for max_repeat)."""
    txns = _load(path)
    n = len(txns)
    out = []
    for i in range(n):
        acc, ts, amt = txns[i]
        count = 0
        s = 0
        freq = {}
        for j in range(n):
            aj, tj, amj = txns[j]
            if aj != acc:
                continue
            if ts - WINDOW <= tj <= ts:
                freq[amj] = freq.get(amj, 0) + 1     # includes self (j == i)
                if j != i:
                    count += 1
                    s += amj
        out.append({"count": count, "sum_amount": s, "max_repeat": max(freq.values())})
    return out


def fast_truth(path):
    """Independent near-linear reference used to score the large input. Maintains
    the sliding max-frequency via a frequency-of-frequencies table."""
    txns = _load(path)
    n = len(txns)
    out = [None] * n
    groups = defaultdict(list)
    for idx, (acc, ts, amt) in enumerate(txns):
        groups[acc].append(idx)
    for acc, idxs in groups.items():
        idxs.sort(key=lambda i: txns[i][1])
        freq = {}
        cnt_at = {}
        mx = 0
        wsum = 0
        size = 0
        rem = 0
        L = len(idxs)
        p = 0
        while p < L:
            cur = txns[idxs[p]][1]
            q = p
            while q < L and txns[idxs[q]][1] == cur:
                q += 1
            lo = cur - WINDOW
            while rem < p and txns[idxs[rem]][1] < lo:
                a = txns[idxs[rem]][2]
                f = freq[a]
                cnt_at[f] -= 1
                if f == mx and cnt_at[f] == 0:
                    mx -= 1
                if f == 1:
                    del freq[a]
                else:
                    freq[a] = f - 1
                    cnt_at[f - 1] = cnt_at.get(f - 1, 0) + 1
                wsum -= a
                size -= 1
                rem += 1
            for r in range(p, q):
                a = txns[idxs[r]][2]
                f = freq.get(a, 0)
                if f:
                    cnt_at[f] -= 1
                freq[a] = f + 1
                cnt_at[f + 1] = cnt_at.get(f + 1, 0) + 1
                if f + 1 > mx:
                    mx = f + 1
                wsum += a
                size += 1
            for r in range(p, q):
                gi = idxs[r]
                out[gi] = {"count": size - 1, "sum_amount": wsum - txns[gi][2], "max_repeat": mx}
            p = q
    return out


# --------------------------------------------------------------------------- #
# Execution helpers
# --------------------------------------------------------------------------- #
def run_timed(cmd, timeout):
    """Return elapsed seconds, or None if it exceeded `timeout`."""
    start = time.time()
    try:
        proc = subprocess.run(cmd, shell=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    assert proc.returncode == 0, "Engine exited non-zero."
    return time.time() - start


def enforce_stdlib_only():
    with open("/app/engine.py", "r", encoding="utf-8") as f:
        src = f.read()
    for mod in ("numpy", "pandas", "scipy", "polars", "pyarrow", "cython"):
        assert mod not in src, f"Forbidden third-party module '{mod}' found in /app/engine.py."


def _reset():
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    os.makedirs(DATA_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_small_correctness_edge_cases():
    """Exact output on a tiny input that exercises max_repeat's self-inclusion,
    same-ts ties, the inclusive trailing-window boundary, and a peak frequency
    that must drop as the window evicts its peak group, plus isolated rows."""
    _reset()
    build_small(INPUT_PATH)
    truth = brute_truth(INPUT_PATH)
    # Guards: the dataset really does exercise the subtle cases.
    assert any(r["max_repeat"] >= 3 for r in truth), "peak repeat group not exercised"
    assert any(r["count"] == 0 and r["max_repeat"] == 1 for r in truth), "self-inclusion/isolated row not exercised"
    assert any(r["max_repeat"] == 2 for r in truth), "intermediate repeat not exercised"

    elapsed = run_timed(ENTRY, PERF_BUDGET_SEC)
    assert elapsed is not None, "Engine did not finish on the tiny input."
    enforce_stdlib_only()
    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert result == truth, "Output does not match the reference on the edge-case input."


def test_large_performance_and_correctness():
    """Full-day-scale adversarial input: the engine must finish within the budget
    (the quadratic baseline cannot) and produce exactly the right features."""
    _reset()
    build_large(INPUT_PATH)
    truth = fast_truth(INPUT_PATH)

    elapsed = run_timed(ENTRY, PERF_BUDGET_SEC)
    assert elapsed is not None, (
        f"Engine exceeded the {PERF_BUDGET_SEC:.0f}s budget on full-day data — still too slow."
    )
    enforce_stdlib_only()
    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert len(result) == len(truth), "Wrong number of output rows."
    assert result == truth, "Output is incorrect on the large input."
    print(f"Engine finished in {elapsed:.2f}s (budget {PERF_BUDGET_SEC:.0f}s).")
