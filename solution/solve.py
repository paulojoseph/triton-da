#!/usr/bin/env python3
"""Reference repair of the trace-latency pipeline.

Single-pass, bounded-memory streaming implementation. Correlates start/end
events into completed requests, evicting open requests as soon as they close,
and keeps only fixed-capacity rolling windows of completed requests. Peak RSS
stays far below the 64MB budget regardless of input size.
"""
import json
import os
import glob
import array
from decimal import Decimal, ROUND_HALF_UP

SERVICES = ("auth", "gateway", "payment")
DATA_DIR = "/app/data"
OUT_PATH = "/app/output.json"

# Rolling window capacities (completed requests).
GLOBAL_CAP = 5000
SERVICE_CAP = 2000

# latency_ms is an integer in [0, 1000] by construction.
MAX_LATENCY = 1000


def _rate(errs, size):
    if size == 0:
        return 0.0
    return float((Decimal(errs) / Decimal(size)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _round2(value):
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class RollingWindow:
    """Fixed-capacity FIFO of completed requests with O(1) error count and an
    O(MAX_LATENCY) nearest-rank p95 via an eviction-aware latency histogram."""
    __slots__ = ("cap", "is_err", "lat", "hist", "head", "size", "errs")

    def __init__(self, cap):
        self.cap = cap
        self.is_err = array.array("B", bytes(cap))         # 1 byte / slot
        self.lat = array.array("H", bytes(2 * cap))        # 2 bytes / slot
        self.hist = [0] * (MAX_LATENCY + 1)
        self.head = 0
        self.size = 0
        self.errs = 0

    def push(self, is_err, latency):
        if self.size == self.cap:
            h = self.head
            self.errs -= self.is_err[h]
            self.hist[self.lat[h]] -= 1
            self.is_err[h] = is_err
            self.lat[h] = latency
            self.head = (h + 1) % self.cap
        else:
            idx = (self.head + self.size) % self.cap
            self.is_err[idx] = is_err
            self.lat[idx] = latency
            self.size += 1
        self.errs += is_err
        self.hist[latency] += 1

    def error_rate(self):
        return _rate(self.errs, self.size)

    def p95(self):
        if self.size == 0:
            return 0.0
        # nearest-rank: 1-based index ceil(0.95 * size)
        target = -(-95 * self.size // 100)
        cumulative = 0
        for ms in range(MAX_LATENCY + 1):
            cumulative += self.hist[ms]
            if cumulative >= target:
                return _round2(ms)
        return 0.0


def _valid_event(line):
    """Returns the parsed (id, svc, phase, ts, status) tuple or None if malformed."""
    try:
        data = json.loads(line)
    except Exception:
        return None
    if type(data) is not dict or set(data.keys()) != {"id", "svc", "phase", "ts", "status"}:
        return None
    rid = data["id"]
    svc = data["svc"]
    phase = data["phase"]
    ts = data["ts"]
    status = data["status"]
    if type(rid) is not str or rid == "":
        return None
    if svc not in SERVICES or phase not in ("start", "end"):
        return None
    if type(ts) is not int or isinstance(ts, bool) or ts < 0:
        return None
    if type(status) is not int or isinstance(status, bool) or not (100 <= status <= 599):
        return None
    return (rid, svc, phase, ts, status)


def main():
    shards = sorted(glob.glob(os.path.join(DATA_DIR, "shard-*.log")))

    processed = 0
    malformed = 0
    unmatched = 0
    open_reqs = {}  # id -> (ts_start, svc)

    gwin = RollingWindow(GLOBAL_CAP)
    swins = {s: RollingWindow(SERVICE_CAP) for s in SERVICES}

    for path in shards:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                ev = _valid_event(line)
                if ev is None:
                    malformed += 1
                    continue
                rid, svc, phase, ts, status = ev
                if phase == "start":
                    if rid in open_reqs:
                        malformed += 1
                        continue
                    open_reqs[rid] = (ts, svc)
                else:
                    start = open_reqs.pop(rid, None)
                    if start is None:
                        unmatched += 1
                        continue
                    ts0, svc0 = start
                    latency = ts - ts0
                    is_err = 1 if status >= 400 else 0
                    processed += 1
                    gwin.push(is_err, latency)
                    swins[svc0].push(is_err, latency)

    unmatched += len(open_reqs)

    out = {
        "processed_count": processed,
        "malformed_count": malformed,
        "unmatched_count": unmatched,
        "global_error_rate": gwin.error_rate(),
        "global_p95_latency_ms": gwin.p95(),
    }
    for s in SERVICES:
        out[f"{s}_error_rate"] = swins[s].error_rate()
        out[f"{s}_p95_latency_ms"] = swins[s].p95()

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
