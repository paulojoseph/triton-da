#!/usr/bin/env python3
"""Streaming, memory-bounded event-time telemetry aggregator (reference).

Single pass over the arrival-ordered log. Tracks a watermark (running max of
event time over valid records), drops events more than 30s behind it, assigns
the rest to 60s tumbling windows, and finalizes a window once the watermark has
advanced past window_end + lateness (so no further accepted event can land in
it). Only a handful of open-window histograms are ever resident, so peak RSS
stays far below 64MB regardless of stream length.
"""
import json
import os
from decimal import Decimal, ROUND_HALF_UP

INPUT_PATH = "/app/data/events.log"
OUTPUT_PATH = "/app/output.json"

SERVICES = ("auth", "gateway", "payment")
WINDOW = 60
LATENESS = 30
MAX_LATENCY = 1000


def _valid(line):
    """Return (ts, svc, status, latency_ms) for a valid line, else None."""
    try:
        d = json.loads(line)
    except Exception:
        return None
    if type(d) is not dict or set(d.keys()) != {"ts", "svc", "status", "latency_ms"}:
        return None
    ts, svc, status, latency = d["ts"], d["svc"], d["status"], d["latency_ms"]
    if svc not in SERVICES:
        return None
    if type(ts) is not int or isinstance(ts, bool) or ts < 0:
        return None
    if type(status) is not int or isinstance(status, bool) or not (100 <= status <= 599):
        return None
    if type(latency) is not int or isinstance(latency, bool) or not (0 <= latency <= 1000):
        return None
    return (ts, svc, status, latency)


def _finalize(window):
    n = window["count"]
    errs = window["errs"]
    error_rate = float((Decimal(errs) / Decimal(n)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    rank = -(-95 * n // 100)  # ceil(0.95 * n), 1-based
    hist = window["hist"]
    cumulative = 0
    p = 0
    for ms in range(MAX_LATENCY + 1):
        cumulative += hist[ms]
        if cumulative >= rank:
            p = ms
            break
    p95 = float(Decimal(p).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {"count": n, "error_rate": error_rate, "p95_latency_ms": p95}


def main():
    processed = 0
    malformed = 0
    late = 0
    watermark = None
    open_windows = {}   # window_start -> {count, errs, hist}
    results = {}        # window_start(str) -> finalized metrics

    if os.path.exists(INPUT_PATH):
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                ev = _valid(line)
                if ev is None:
                    malformed += 1
                    continue
                ts, svc, status, latency = ev

                is_late = watermark is not None and watermark - ts > LATENESS
                watermark = ts if watermark is None else (ts if ts > watermark else watermark)
                if is_late:
                    late += 1
                    continue

                processed += 1
                wstart = ts - (ts % WINDOW)
                w = open_windows.get(wstart)
                if w is None:
                    w = {"count": 0, "errs": 0, "hist": [0] * (MAX_LATENCY + 1)}
                    open_windows[wstart] = w
                w["count"] += 1
                if status >= 400:
                    w["errs"] += 1
                w["hist"][latency] += 1

                # Finalize windows the watermark has moved safely past.
                if open_windows:
                    closed = [s for s in open_windows if s + WINDOW + LATENESS <= watermark]
                    for s in closed:
                        results[str(s)] = _finalize(open_windows.pop(s))

    for s in list(open_windows):
        results[str(s)] = _finalize(open_windows.pop(s))

    out = {
        "processed_count": processed,
        "malformed_count": malformed,
        "late_count": late,
        "windows": results,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
