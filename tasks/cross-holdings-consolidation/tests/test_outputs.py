"""Behavioral verifier for the cross-holdings-consolidation task.

The agent's /app/consolidate.py is re-run on hidden, regenerated ownership
graphs (with reciprocal/cyclic holdings) and compared to an INDEPENDENT
reference that solves the effective-interest linear system exactly with
Fraction arithmetic. A one-pass "walk the ownership tree" implementation gives
the wrong effective interest whenever a cycle feeds back into an attributable
entity, so it fails the generated datasets.
"""
import os
import csv
import json
import subprocess
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP

DATA_DIR = "/app/data"
OUTPUT_FILE = "/app/output.json"
ENTRY = "python3 /app/consolidate.py"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _reset(entities, ownership):
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    _write_csv(os.path.join(DATA_DIR, "entities.csv"),
               ["entity_id", "equity", "is_parent"], entities)
    _write_csv(os.path.join(DATA_DIR, "ownership.csv"),
               ["owner_id", "owned_id", "fraction"], ownership)


def run_agent(timeout=120):
    proc = subprocess.run(ENTRY, shell=True, timeout=timeout)
    assert proc.returncode == 0, "Agent program exited non-zero."
    assert os.path.exists(OUTPUT_FILE), "Agent did not write /app/output.json."
    with open(OUTPUT_FILE) as f:
        return json.load(f)


def assert_matches(result, expected):
    assert set(result.keys()) == set(expected.keys()), f"top-level keys: {sorted(result)}"
    re_, ee_ = result["effective_interest"], expected["effective_interest"]
    assert set(re_.keys()) == set(ee_.keys()), "effective_interest entity set mismatch"
    for e, ev in ee_.items():
        assert abs(float(re_[e]) - ev) < 1e-6, f"effective_interest[{e}]: {re_[e]} != {ev}"
    rn, en = result["nci"], expected["nci"]
    assert set(rn.keys()) == set(en.keys()), "nci entity set mismatch"
    for e, ev in en.items():
        assert abs(float(rn[e]) - ev) < 0.005, f"nci[{e}]: {rn[e]} != {ev}"
    assert abs(float(result["nci_total"]) - expected["nci_total"]) < 0.01, (
        f"nci_total: {result['nci_total']} != {expected['nci_total']}")


# --------------------------------------------------------------------------- #
# independent reference (exact linear solve over the rationals)
# --------------------------------------------------------------------------- #
def _solve(M, b):
    n = len(b)
    A = [row[:] + [b[i]] for i, row in enumerate(M)]
    for col in range(n):
        piv = next((r for r in range(col, n) if A[r][col] != 0), None)
        assert piv is not None, "singular system"
        A[col], A[piv] = A[piv], A[col]
        p = A[col][col]
        A[col] = [v / p for v in A[col]]
        for r in range(n):
            if r != col and A[r][col] != 0:
                f = A[r][col]
                A[r] = [a - f * c for a, c in zip(A[r], A[col])]
    return [A[i][n] for i in range(n)]


def reference(entities, ownership):
    ids = [r[0] for r in entities]
    equity = {r[0]: Fraction(r[1]) for r in entities}
    parent = next(r[0] for r in entities if r[2].strip() == "1")
    owners = {e: [] for e in ids}
    for owner, owned, fr in ownership:
        owners[owned].append((owner, Fraction(fr)))

    unknown = [e for e in ids if e != parent]
    idx = {e: i for i, e in enumerate(unknown)}
    n = len(unknown)
    M = [[Fraction(0)] * n for _ in range(n)]
    b = [Fraction(0)] * n
    for e in unknown:
        i = idx[e]
        M[i][i] += 1
        for owner, fr in owners[e]:
            if owner == parent:
                b[i] += fr
            elif owner in idx:
                M[i][idx[owner]] -= fr
    sol = _solve(M, b) if n else []
    g = {parent: Fraction(1)}
    for e in unknown:
        g[e] = sol[idx[e]]

    q = Decimal("0.01")
    nci, total = {}, Decimal("0.00")
    for e in ids:
        amt = (Fraction(1) - g[e]) * equity[e]
        cents = (Decimal(amt.numerator) / Decimal(amt.denominator)).quantize(q, rounding=ROUND_HALF_UP)
        nci[e] = float(cents)
        total += cents
    return {"effective_interest": {e: float(g[e]) for e in ids},
            "nci": nci, "nci_total": float(total)}


def _has_cycle(entities, ownership):
    ids = {r[0] for r in entities}
    edges = {}
    for owner, owned, _ in ownership:
        if owner in ids and owned in ids:
            edges.setdefault(owner, []).append(owned)
    color = {}

    def dfs(u):
        color[u] = 1
        for v in edges.get(u, []):
            if color.get(v, 0) == 1:
                return True
            if color.get(v, 0) == 0 and dfs(v):
                return True
        color[u] = 2
        return False

    return any(color.get(u, 0) == 0 and dfs(u) for u in ids)


# --------------------------------------------------------------------------- #
# generated cyclic graphs
# --------------------------------------------------------------------------- #
def build_graph(variant):
    """Deterministic group with several reciprocal rings, cross-ring links and
    some owners outside the group. Each entity's incoming ownership stays below
    1 (slack held outside the group), so the system is non-singular."""
    R = 3 + variant          # number of rings
    k = 3 + (variant % 2)    # ring size
    entities = [["P", "100000", "1"]]
    ownership = []
    for r in range(R):
        for j in range(k):
            eq = 10000 + (r * 37 + j * 101) % 60000
            entities.append([f"E{r}_{j}", str(eq), ""])
    # parent owns the head of each ring
    for r in range(R):
        ownership.append(["P", f"E{r}_0", str(Fraction(30 + (r * 7) % 16, 100))])  # 0.30-0.45
    # each ring is a directed cycle E_r0 -> E_r1 -> ... -> E_r0
    for r in range(R):
        for j in range(k):
            fr = Fraction(15 + (j * 4) % 14, 100)  # 0.15-0.28
            ownership.append([f"E{r}_{j}", f"E{r}_{(j + 1) % k}", str(fr)])
    # cross-ring links create larger interlocking cycles
    for r in range(R):
        ownership.append([f"E{r}_1", f"E{(r + 1) % R}_2", "0.12"])
    # owners outside the group (must be ignored, not treated as parent)
    for r in range(R):
        ownership.append(["OUTSIDE", f"E{r}_2", "0.10"])
    return entities, ownership


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_sample_worked():
    """The reciprocal sample from the instruction, with hand-verified values."""
    entities = [["P", "100000", "1"], ["A", "50000", ""], ["B", "30000", ""], ["C", "20000", ""]]
    ownership = [["P", "A", "0.80"], ["P", "B", "0.60"], ["A", "C", "0.50"],
                 ["C", "A", "0.20"], ["B", "C", "0.30"]]
    _reset(entities, ownership)
    result = run_agent()
    expected = {
        "effective_interest": {"P": 1.0, "A": 209 / 225, "B": 0.6, "C": 29 / 45},
        "nci": {"P": 0.0, "A": 3555.56, "B": 12000.0, "C": 7111.11},
        "nci_total": 22666.67,
    }
    assert_matches(result, expected)


def test_generated_cyclic():
    for variant in (0, 1, 2):
        entities, ownership = build_graph(variant)
        assert _has_cycle(entities, ownership), "generated graph must contain a cycle"
        _reset(entities, ownership)
        expected = reference(entities, ownership)
        # the cross-holdings must actually bite: at least one interior entity is
        # attributed strictly more than a single parent->entity path would give.
        assert any(0 < v < 1 for v in expected["effective_interest"].values())
        result = run_agent()
        assert_matches(result, expected)


def test_acyclic_and_external():
    """A tree plus an out-of-group owner: effective interest is the path product."""
    entities = [["P", "80000", "1"], ["A", "40000", ""], ["B", "25000", ""], ["D", "15000", ""]]
    ownership = [["P", "A", "0.90"], ["A", "B", "0.50"], ["P", "D", "0.70"],
                 ["OUTSIDE", "B", "0.20"]]
    _reset(entities, ownership)
    expected = reference(entities, ownership)
    result = run_agent()
    assert_matches(result, expected)
