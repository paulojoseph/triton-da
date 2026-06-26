"""Behavioral verifier for the event-time watermark aggregator task.

Each test regenerates a hidden event log, runs the agent's aggregator at
/app/aggregator.py under an RSS sampler, and compares /app/output.json against
an independent brute-force reference computed here (which buffers everything and
sorts -- sharing no implementation with a correct streaming solution).
"""
import os
import json
import time
import subprocess

import psutil
import pytest
from decimal import Decimal, ROUND_HALF_UP

SERVICES = ("auth", "gateway", "payment")
DATA_DIR = "/app/data"
LOG_PATH = "/app/data/events.log"
OUTPUT_FILE = "/app/output.json"
ENTRY = "python3 /app/aggregator.py"

WINDOW = 60
LATENESS = 30
MEM_BOUND_MB = 64.0


# --------------------------------------------------------------------------- #
# Deterministic event-log construction
# --------------------------------------------------------------------------- #
class Gen:
    """Builds an arrival-ordered list of log lines while tracking the watermark,
    so late and exactly-on-the-boundary events can be placed precisely."""

    def __init__(self):
        self.lines = []
        self.wm = None

    def _valid(self, ts, svc, status, latency):
        self.lines.append(json.dumps({"ts": ts, "svc": svc, "status": status, "latency_ms": latency}))
        self.wm = ts if self.wm is None else max(self.wm, ts)

    def blank(self):
        self.lines.append("   ")

    def malformed(self, kind):
        k = kind % 9
        if k == 0:
            self.lines.append("definitely not json {{")
        elif k == 1:  # missing key
            self.lines.append(json.dumps({"ts": 100000, "svc": "auth", "status": 200}))
        elif k == 2:  # extra key
            self.lines.append(json.dumps({"ts": 100000, "svc": "auth", "status": 200, "latency_ms": 100, "x": 1}))
        elif k == 3:  # status float
            self.lines.append(json.dumps({"ts": 100000, "svc": "gateway", "status": 200.0, "latency_ms": 100}))
        elif k == 4:  # ts bool
            self.lines.append(json.dumps({"ts": True, "svc": "payment", "status": 200, "latency_ms": 100}))
        elif k == 5:  # status out of range
            self.lines.append(json.dumps({"ts": 100000, "svc": "auth", "status": 99, "latency_ms": 100}))
        elif k == 6:  # svc invalid
            self.lines.append(json.dumps({"ts": 100000, "svc": "billing", "status": 200, "latency_ms": 100}))
        elif k == 7:  # latency out of range
            self.lines.append(json.dumps({"ts": 100000, "svc": "gateway", "status": 200, "latency_ms": 1001}))
        elif k == 8:  # latency bool
            self.lines.append(json.dumps({"ts": 100000, "svc": "payment", "status": 200, "latency_ms": False}))

    def late_event(self, svc):
        """An event 40s behind the watermark -> dropped as late."""
        self._valid(self.wm - 40, svc, 500, 100)

    def boundary_event(self, svc):
        """An event exactly 30s behind the watermark -> NOT late (kept)."""
        self._valid(self.wm - 30, svc, 200, 100)

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(self.lines) + "\n")


def build_log(path, n_windows, plain_count, base_ts=100020):  # base_ts must be a multiple of WINDOW
    """Emit n_windows 60s windows of accepted events in ascending event time,
    plus late, boundary, malformed and blank traps. Windows 5 and 7 are
    engineered: window 5 has a p95 step, window 7 has a 1/32 error rate."""
    g = Gen()
    for wi in range(n_windows):
        wstart = base_ts + wi * WINDOW
        if wi == 5:
            count, special = 100, "pstep"
        elif wi == 7:
            count, special = 32, "round"
        else:
            count, special = plain_count, "plain"

        for k in range(count):
            ts = wstart + 5 + (k * 50) // count  # ascending within [wstart+5, wstart+54]
            svc = SERVICES[(wi + k) % 3]
            if special == "round":
                status = 500 if k == 0 else 200
                latency = 100 + (k % 40)
            elif special == "pstep":
                status = 500 if k < 10 else 200
                latency = 900 if k >= 95 else 100
            else:
                status = 500 if k % 8 == 0 else 200
                latency = 100 + (k % 50)
            g._valid(ts, svc, status, latency)
            if k % 50 == 0:
                g.blank()
            if k % 37 == 0:
                g.malformed(wi + k)

        g.late_event(SERVICES[wi % 3])
        if special == "plain":
            g.boundary_event(SERVICES[wi % 3])

    g.write(path)


def build_small(path, base_ts=500040):  # base_ts must be a multiple of WINDOW
    """Small log: partial windows, the 1/32 rounding window, a p95-step window,
    late + boundary events, and the empty/edge traps."""
    build_log(path, n_windows=10, plain_count=40, base_ts=base_ts)


# --------------------------------------------------------------------------- #
# Independent brute-force reference (the "truth")
# --------------------------------------------------------------------------- #
def _ref_valid(line):
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


def compute_truth(path):
    processed = malformed = late = 0
    watermark = None
    windows = {}  # window_start -> list of (is_err, latency)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ev = _ref_valid(line)
            if ev is None:
                malformed += 1
                continue
            ts, svc, status, latency = ev
            is_late = watermark is not None and watermark - ts > LATENESS
            watermark = ts if watermark is None else max(watermark, ts)
            if is_late:
                late += 1
                continue
            processed += 1
            wstart = ts - (ts % WINDOW)
            windows.setdefault(wstart, []).append((1 if status >= 400 else 0, latency))

    wout = {}
    for wstart, items in windows.items():
        n = len(items)
        errs = sum(e for e, _ in items)
        error_rate = float((Decimal(errs) / Decimal(n)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        lats = sorted(l for _, l in items)
        rank = -(-95 * n // 100)
        p95 = float(Decimal(lats[rank - 1]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        wout[str(wstart)] = {"count": n, "error_rate": error_rate, "p95_latency_ms": p95}
    return {"processed_count": processed, "malformed_count": malformed, "late_count": late, "windows": wout}


# --------------------------------------------------------------------------- #
# Execution + memory sampling
# --------------------------------------------------------------------------- #
def run_with_peak_rss(cmd, timeout=300):
    proc = subprocess.Popen(cmd, shell=True)
    p = psutil.Process(proc.pid)
    peak = 0
    start = time.time()
    while proc.poll() is None:
        try:
            mem = p.memory_info().rss
            for child in p.children(recursive=True):
                mem += child.memory_info().rss
            peak = max(peak, mem)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        if time.time() - start > timeout:
            proc.kill()
            raise AssertionError("Aggregator exceeded execution timeout.")
        time.sleep(0.02)
    return proc.returncode, peak / (1024 * 1024)


def assert_matches(result, truth):
    assert isinstance(result, dict), "Output is not a JSON object."
    assert set(result.keys()) == {"processed_count", "malformed_count", "late_count", "windows"}, (
        f"Top-level keys must be exactly the four specified; got {sorted(result.keys())}"
    )
    for key in ("processed_count", "malformed_count", "late_count"):
        assert result[key] == truth[key], f"{key}: got {result[key]}, want {truth[key]}"

    rw, tw = result["windows"], truth["windows"]
    assert isinstance(rw, dict), "'windows' must be an object."
    assert set(rw.keys()) == set(tw.keys()), (
        f"window keys mismatch: missing {sorted(set(tw)-set(rw))[:5]}, extra {sorted(set(rw)-set(tw))[:5]}"
    )
    for wstart, twin in tw.items():
        rwin = rw[wstart]
        assert set(rwin.keys()) == {"count", "error_rate", "p95_latency_ms"}, (
            f"window {wstart} keys must be exactly count/error_rate/p95_latency_ms; got {sorted(rwin.keys())}"
        )
        assert rwin["count"] == twin["count"], f"window {wstart} count: {rwin['count']} != {twin['count']}"
        assert abs(float(rwin["error_rate"]) - twin["error_rate"]) < 1e-9, (
            f"window {wstart} error_rate: {rwin['error_rate']} != {twin['error_rate']}"
        )
        assert abs(float(rwin["p95_latency_ms"]) - twin["p95_latency_ms"]) < 1e-9, (
            f"window {wstart} p95: {rwin['p95_latency_ms']} != {twin['p95_latency_ms']}"
        )


def _reset():
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    os.makedirs(DATA_DIR, exist_ok=True)


def _enforce_stdlib_only():
    with open("/app/aggregator.py", "r", encoding="utf-8") as f:
        src = f.read()
    for mod in ("numpy", "pandas", "scipy", "polars", "pyarrow", "sklearn"):
        assert mod not in src, f"Forbidden third-party module '{mod}' found in /app/aggregator.py."


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_large_stream_memory_and_correctness():
    """Production-scale out-of-order stream: enforces the <64MB RSS bound (any
    aggregator that buffers the whole file or all events blows it) plus exact
    watermark late-drop, event-time windowing, percentile and rounding."""
    _reset()
    build_log(LOG_PATH, n_windows=300, plain_count=2000)
    truth = compute_truth(LOG_PATH)

    rc, peak_mb = run_with_peak_rss(ENTRY)
    assert rc == 0, "Aggregator crashed on the large stream."
    assert os.path.exists(OUTPUT_FILE), "Aggregator did not write /app/output.json."
    _enforce_stdlib_only()

    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert_matches(result, truth)

    print(f"Peak RSS: {peak_mb:.2f} MB; windows: {len(truth['windows'])}; late: {truth['late_count']}")
    assert peak_mb < MEM_BOUND_MB, f"Memory budget exceeded: {peak_mb:.2f} MB."


def test_partial_windows_late_and_rounding():
    """Small out-of-order stream: partial windows, exactly-30s-behind kept vs
    40s-behind dropped, a 1/32 round-half-up boundary, and a p95 step."""
    _reset()
    build_small(LOG_PATH)
    truth = compute_truth(LOG_PATH)
    # Guards: the dataset really exercises these edges.
    assert truth["late_count"] > 0
    assert any(w["count"] == 32 and w["error_rate"] == 0.0313 for w in truth["windows"].values())

    rc, _ = run_with_peak_rss(ENTRY)
    assert rc == 0, "Aggregator crashed on the small stream."
    _enforce_stdlib_only()
    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert_matches(result, truth)


def test_empty_stream():
    """Whitespace-only input yields zeroed counts and no windows."""
    _reset()
    with open(LOG_PATH, "w") as f:
        f.write("\n\n   \n\n")

    rc, _ = run_with_peak_rss(ENTRY)
    assert rc == 0, "Aggregator crashed on the empty stream."
    _enforce_stdlib_only()
    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert result == {"processed_count": 0, "malformed_count": 0, "late_count": 0, "windows": {}}
