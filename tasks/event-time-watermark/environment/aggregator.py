import json
import os

INPUT_PATH = "/app/data/events.log"
OUTPUT_PATH = "/app/output.json"
VALID_SERVICES = {"auth", "gateway", "payment"}
REQUIRED = {"ts", "svc", "status", "latency_ms"}


def run():
    if not os.path.exists(INPUT_PATH):
        with open(OUTPUT_PATH, "w") as f:
            json.dump({"processed_count": 0, "malformed_count": 0, "late_count": 0, "windows": {}}, f, indent=2)
        return

    # Batch load: read the whole file up front, then group by window.
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    windows = {}
    processed = 0
    malformed = 0

    for line in lines:
        s = line.strip()
        if not s:
            continue
        try:
            d = json.loads(s)
        except Exception:
            malformed += 1
            continue
        if not isinstance(d, dict) or not REQUIRED.issubset(d.keys()):
            malformed += 1
            continue
        if d["svc"] not in VALID_SERVICES:
            malformed += 1
            continue
        if not isinstance(d["ts"], int) or d["ts"] < 0:
            malformed += 1
            continue
        if not isinstance(d["status"], int) or not (100 <= d["status"] <= 599):
            malformed += 1
            continue
        if not isinstance(d["latency_ms"], int) or not (0 <= d["latency_ms"] <= 1000):
            malformed += 1
            continue

        processed += 1
        wid = d["ts"] // 60
        windows.setdefault(wid, []).append((d["status"], d["latency_ms"]))

    result = {"processed_count": processed, "malformed_count": malformed, "late_count": 0, "windows": {}}
    for wid, items in windows.items():
        n = len(items)
        errs = sum(1 for st, _ in items if st >= 400)
        rate = round(errs / n, 4)
        lats = sorted(lat for _, lat in items)
        p = lats[int(0.95 * n)]
        result["windows"][str(wid)] = {
            "count": n,
            "error_rate": rate,
            "p95_latency_ms": round(float(p), 2),
        }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    run()
