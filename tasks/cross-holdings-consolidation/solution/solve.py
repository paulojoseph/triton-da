#!/usr/bin/env python3
"""Reference: group effective interest under reciprocal (cross) holdings.

Effective interest g_e of the top parent P in entity e is the unique solution of
  g_P = 1
  g_e = sum over owners o of e of  fraction(o owns e) * g_o     (for e != P)
which, when the ownership graph has cycles, is a linear system (NOT a tree walk).
Solved exactly here with Fraction + Gaussian elimination, then rounded.
"""
import csv
import json
import os
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP

DATA_DIR = "/app/data"
OUTPUT_PATH = "/app/output.json"


def _load(name):
    with open(os.path.join(DATA_DIR, name), newline="") as f:
        return list(csv.DictReader(f))


def _solve(M, b):
    """Solve M x = b over the rationals (Gaussian elimination, partial pivot)."""
    n = len(b)
    A = [row[:] + [b[i]] for i, row in enumerate(M)]
    for col in range(n):
        piv = next((r for r in range(col, n) if A[r][col] != 0), None)
        if piv is None:
            continue
        A[col], A[piv] = A[piv], A[col]
        pivot = A[col][col]
        A[col] = [v / pivot for v in A[col]]
        for r in range(n):
            if r != col and A[r][col] != 0:
                f = A[r][col]
                A[r] = [a - f * b_ for a, b_ in zip(A[r], A[col])]
    return [A[i][n] for i in range(n)]


def _round_cents(frac):
    return Decimal(frac.numerator) / Decimal(frac.denominator)


def main():
    entities = _load("entities.csv")
    ownership = _load("ownership.csv")

    ids = [r["entity_id"] for r in entities]
    equity = {r["entity_id"]: Fraction(r["equity"]) for r in entities}
    parent = next(r["entity_id"] for r in entities if r.get("is_parent", "").strip() == "1")

    owners = {e: [] for e in ids}
    for r in ownership:
        owners[r["owned_id"]].append((r["owner_id"], Fraction(r["fraction"])))

    unknown = [e for e in ids if e != parent]
    idx = {e: i for i, e in enumerate(unknown)}
    n = len(unknown)

    M = [[Fraction(0)] * n for _ in range(n)]
    b = [Fraction(0)] * n
    for e in unknown:
        i = idx[e]
        M[i][i] += 1
        for owner, frac in owners[e]:
            if owner == parent:
                b[i] += frac
            elif owner in idx:
                M[i][idx[owner]] -= frac
            # owners outside the group contribute nothing

    sol = _solve(M, b) if n else []
    g = {parent: Fraction(1)}
    for e in unknown:
        g[e] = sol[idx[e]]

    q = Decimal("0.01")
    nci = {}
    nci_total = Decimal("0.00")
    for e in ids:
        amount = (Fraction(1) - g[e]) * equity[e]
        cents = _round_cents(amount).quantize(q, rounding=ROUND_HALF_UP)
        nci[e] = float(cents)
        nci_total += cents

    out = {
        "effective_interest": {e: float(g[e]) for e in ids},
        "nci": nci,
        "nci_total": float(nci_total),
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
