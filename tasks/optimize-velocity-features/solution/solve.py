#!/usr/bin/env python3
"""Fast reference implementation of the velocity-feature job.

Per account, transactions are processed in timestamp order with a two-pointer
trailing window. `count`/`sum_amount` are running aggregates (self excluded by
subtraction). `max_repeat` -- the size of the largest equal-`amount` group in
the window -- is the maximum frequency over a sliding window with deletions:
incrementing the running max is trivial, but a deletion can lower it, so we keep
a "frequency of frequencies" table (`cnt_at[f]` = how many distinct amounts
currently occur exactly `f` times) and drop `max_freq` only when its bucket
empties. Same-`ts` transactions are admitted as a group before any is answered.
Overall O(N).
"""
import json
from collections import defaultdict

WINDOW = 3600
INPUT_PATH = "/app/data/transactions.jsonl"
OUTPUT_PATH = "/app/output.json"


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

    by_acc = defaultdict(list)
    for idx, (acc, ts, amt) in enumerate(txns):
        by_acc[acc].append(idx)

    for acc, idxs in by_acc.items():
        idxs.sort(key=lambda i: txns[i][1])
        freq = {}            # amount -> occurrences in the window
        cnt_at = {}          # frequency f -> number of distinct amounts seen exactly f times
        max_freq = 0
        wsum = 0
        size = 0
        rem = 0
        L = len(idxs)
        i = 0
        while i < L:
            cur_ts = txns[idxs[i]][1]
            j = i
            while j < L and txns[idxs[j]][1] == cur_ts:
                j += 1
            limit = cur_ts - WINDOW
            # Evict transactions older than the trailing window.
            while rem < i and txns[idxs[rem]][1] < limit:
                a = txns[idxs[rem]][2]
                f = freq[a]
                cnt_at[f] -= 1
                if f == max_freq and cnt_at[f] == 0:
                    max_freq -= 1
                if f == 1:
                    del freq[a]
                else:
                    freq[a] = f - 1
                    cnt_at[f - 1] = cnt_at.get(f - 1, 0) + 1
                wsum -= a
                size -= 1
                rem += 1
            # Admit the whole same-timestamp group.
            for t in range(i, j):
                a = txns[idxs[t]][2]
                f = freq.get(a, 0)
                if f:
                    cnt_at[f] -= 1
                freq[a] = f + 1
                cnt_at[f + 1] = cnt_at.get(f + 1, 0) + 1
                if f + 1 > max_freq:
                    max_freq = f + 1
                wsum += a
                size += 1
            # Answer the group (window now includes every member).
            for t in range(i, j):
                gi = idxs[t]
                out[gi] = {
                    "count": size - 1,
                    "sum_amount": wsum - txns[gi][2],
                    "max_repeat": max_freq,
                }
            i = j

    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    run()
