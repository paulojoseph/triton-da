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

PERF_BUDGET_SEC = 60.0


# --------------------------------------------------------------------------- #
# Deterministic dataset construction
# --------------------------------------------------------------------------- #
def _write(path, txns):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for acc, ts, amt in txns:
            f.write(json.dumps({"account": acc, "ts": ts, "amount": amt}) + "\n")


def build_large(path, n=300000, n_accounts=10, span=7200):
    """Round-robin interleaved accounts; each account's transactions are dense
    inside ~2h so the trailing 1h window holds ~15k of them. A per-account window
    *scan* for count_ge is ~N*avg_window ≈ 4.5e9 ops and blows the budget; only a
    log-time structure (Fenwick/BIT) survives."""
    per = n // n_accounts
    txns = []
    for k in range(per):
        for a in range(n_accounts):
            ts = a * 10_000_000 + (k * span) // per
            amount = (k * 37 + a * 5) % 600 + 1
            txns.append((f"acct-{a:03d}", ts, amount))
    _write(path, txns)


def build_small(path):
    """Small, edge-case-rich input: self-exclusion, same-ts ties, the inclusive
    window boundary at ts-3600, amount ties for the >= comparison, a lone
    transaction, and a same-account pair outside each other's window."""
    txns = [
        # acct-A: a burst with ties and a boundary case.
        ("acct-A", 10000, 100),
        ("acct-A", 10000, 100),   # same ts and amount as previous -> they count each other
        ("acct-A", 10000, 50),    # same ts, smaller amount
        ("acct-A", 13600, 80),    # exactly 3600 after ts=10000 -> those are in-window (boundary inclusive)
        ("acct-A", 13601, 200),   # 3601 after 10000 -> the ts=10000 ones are out of window for this one
        # acct-B: interleaved with A in the file, independent window.
        ("acct-B", 50000, 10),
        ("acct-B", 51000, 10),    # same amount -> count_ge includes the equal one
        ("acct-B", 99000, 999),   # far away -> sees none of the earlier acct-B txns
        # acct-C: a single transaction -> all features zero.
        ("acct-C", 7, 7),
    ]
    _write(path, txns)


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #
def brute_truth(path):
    """Obviously-correct O(N^2) reference."""
    txns = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            txns.append((d["account"], d["ts"], d["amount"]))
    n = len(txns)
    out = []
    for i in range(n):
        acc, ts, amt = txns[i]
        c = s = cge = 0
        for j in range(n):
            if j == i:
                continue
            aj, tj, amj = txns[j]
            if aj != acc:
                continue
            if ts - WINDOW <= tj <= ts:
                c += 1
                s += amj
                if amj >= amt:
                    cge += 1
        out.append({"count": c, "sum_amount": s, "count_ge": cge})
    return out


class _Fen:
    def __init__(self, n):
        self.n = n
        self.t = [0] * (n + 1)

    def add(self, i, v):
        while i <= self.n:
            self.t[i] += v
            i += i & -i

    def pref(self, i):
        s = 0
        while i > 0:
            s += self.t[i]
            i -= i & -i
        return s


def fast_truth(path):
    """Independent O(N log N) reference used to score the large input."""
    txns = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            txns.append((d["account"], d["ts"], d["amount"]))
    n = len(txns)
    out = [None] * n
    uniq = sorted({t[2] for t in txns})
    rk = {a: i + 1 for i, a in enumerate(uniq)}
    groups = defaultdict(list)
    for idx, (acc, ts, amt) in enumerate(txns):
        groups[acc].append(idx)
    for acc, idxs in groups.items():
        idxs.sort(key=lambda i: txns[i][1])
        fen = _Fen(len(uniq))
        total = wsum = 0
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
                fen.add(rk[a], -1)
                wsum -= a
                total -= 1
                rem += 1
            for r in range(p, q):
                a = txns[idxs[r]][2]
                fen.add(rk[a], 1)
                wsum += a
                total += 1
            for r in range(p, q):
                gi = idxs[r]
                a = txns[gi][2]
                less = fen.pref(rk[a] - 1)
                out[gi] = {"count": total - 1, "sum_amount": wsum - a, "count_ge": total - less - 1}
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
    """Exact output on a tiny input that exercises self-exclusion, same-ts ties,
    the inclusive trailing-window boundary, amount ties, and isolated rows."""
    _reset()
    build_small(INPUT_PATH)
    truth = brute_truth(INPUT_PATH)
    # Guards: the dataset really does exercise the subtle cases.
    assert any(r["count_ge"] != r["count"] for r in truth), "amount >= comparison not exercised"
    assert any(r["count"] == 0 for r in truth), "isolated-row case not exercised"
    assert any(r["count"] >= 2 for r in truth), "tie/window grouping not exercised"

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
