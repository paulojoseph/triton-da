#!/usr/bin/env python3
"""Fast reference implementation of the velocity-feature job.

Per account, transactions are processed in timestamp order with a two-pointer
trailing window for `count`/`sum_amount`, and a Fenwick tree over compressed
amounts for `count_ge` (count of in-window amounts >= the current amount).
Same-timestamp transactions are admitted as a group before any of them is
answered, so they see one another. Overall O(N log N).
"""
import json
from collections import defaultdict

WINDOW = 3600
INPUT_PATH = "/app/data/transactions.jsonl"
OUTPUT_PATH = "/app/output.json"


class Fenwick:
    __slots__ = ("n", "t")

    def __init__(self, n):
        self.n = n
        self.t = [0] * (n + 1)

    def add(self, i, v):
        n, t = self.n, self.t
        while i <= n:
            t[i] += v
            i += i & -i

    def prefix(self, i):
        t = self.t
        s = 0
        while i > 0:
            s += t[i]
            i -= i & -i
        return s


def run():
    txns = []
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            txns.append((d["account"], d["ts"], d["amount"]))

    n = len(txns)
    out = [None] * n

    # Compress amounts to dense ranks (1-based) for the Fenwick tree.
    amounts_sorted = sorted({t[2] for t in txns})
    rank = {a: i + 1 for i, a in enumerate(amounts_sorted)}
    m = len(amounts_sorted)

    by_acc = defaultdict(list)
    for idx, (acc, ts, amt) in enumerate(txns):
        by_acc[acc].append(idx)

    for acc, idxs in by_acc.items():
        idxs.sort(key=lambda i: txns[i][1])
        fw = Fenwick(m)
        wsum = 0
        wcount = 0
        rem = 0
        L = len(idxs)
        i = 0
        while i < L:
            cur_ts = txns[idxs[i]][1]
            j = i
            while j < L and txns[idxs[j]][1] == cur_ts:
                j += 1
            # Evict transactions older than the trailing window.
            limit = cur_ts - WINDOW
            while rem < i and txns[idxs[rem]][1] < limit:
                amt_r = txns[idxs[rem]][2]
                fw.add(rank[amt_r], -1)
                wsum -= amt_r
                wcount -= 1
                rem += 1
            # Admit the whole same-timestamp group, then answer it.
            for t in range(i, j):
                amt_a = txns[idxs[t]][2]
                fw.add(rank[amt_a], 1)
                wsum += amt_a
                wcount += 1
            for t in range(i, j):
                gi = idxs[t]
                amt_i = txns[gi][2]
                less = fw.prefix(rank[amt_i] - 1)
                out[gi] = {
                    "count": wcount - 1,
                    "sum_amount": wsum - amt_i,
                    "count_ge": wcount - less - 1,
                }
            i = j

    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    run()
