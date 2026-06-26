import json

WINDOW = 3600  # trailing window, in seconds
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
    out = []
    for i in range(n):
        account, ts, amount = txns[i]
        count = 0
        sum_amount = 0
        count_ge = 0
        for j in range(n):
            if j == i:
                continue
            acc_j, ts_j, amt_j = txns[j]
            if acc_j != account:
                continue
            if ts - WINDOW <= ts_j <= ts:
                count += 1
                sum_amount += amt_j
                if amt_j >= amount:
                    count_ge += 1
        out.append({"count": count, "sum_amount": sum_amount, "count_ge": count_ge})

    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    run()
