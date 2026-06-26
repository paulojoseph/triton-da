"""Behavioral verifier for the trace-latency pipeline repair task.

Each test regenerates a hidden dataset in code, runs the agent's pipeline at
/app/tracer/main.py under an RSS sampler, and compares its /app/output.json
against an *independent* brute-force reference computed in this file. The
reference deliberately uses the simplest possible (buffer-everything) method,
so it shares no implementation with a correct streaming solution.
"""
import os
import json
import glob
import time
import subprocess

import psutil
import pytest
from decimal import Decimal, ROUND_HALF_UP

SERVICES = ("auth", "gateway", "payment")
DATA_DIR = "/app/data"
OUTPUT_FILE = "/app/output.json"
ENTRY = "python3 /app/tracer/main.py"

GLOBAL_CAP = 5000
SERVICE_CAP = 2000
MEM_BOUND_MB = 64.0


# --------------------------------------------------------------------------- #
# Deterministic dataset construction
# --------------------------------------------------------------------------- #
class StreamBuilder:
    """Builds an ordered list of raw log lines, then splits it into shards.

    Shards are named shard-000.log, shard-001.log, ... so that concatenating
    them in ascending filename order reproduces the build order exactly.
    """

    MALFORMED_KINDS = 9

    def __init__(self):
        self.lines = []
        self.ts = 1_000_000

    def _emit(self, obj):
        self.lines.append(json.dumps(obj))

    def request(self, rid, svc, latency, status, end_svc=None):
        """One well-formed request: a start then an end (adjacent)."""
        self._emit({"id": rid, "svc": svc, "phase": "start", "ts": self.ts, "status": 200})
        self._emit({"id": rid, "svc": end_svc or svc, "phase": "end",
                    "ts": self.ts + latency, "status": status})
        self.ts += 1000

    def dup_start(self, rid, svc, latency, status):
        """A duplicate start (second start while open) followed by an end.
        The duplicate start is malformed; the request still completes."""
        self._emit({"id": rid, "svc": svc, "phase": "start", "ts": self.ts, "status": 200})
        self._emit({"id": rid, "svc": svc, "phase": "start", "ts": self.ts + 1, "status": 200})
        self._emit({"id": rid, "svc": svc, "phase": "end",
                    "ts": self.ts + latency, "status": status})
        self.ts += 1000

    def orphan_start(self, rid, svc):
        self._emit({"id": rid, "svc": svc, "phase": "start", "ts": self.ts, "status": 200})
        self.ts += 1000

    def orphan_end(self, rid, svc, status=200):
        self._emit({"id": rid, "svc": svc, "phase": "end", "ts": self.ts, "status": status})
        self.ts += 1000

    def blank(self):
        self.lines.append("   ")

    def malformed(self, kind):
        """Emit one malformed line. `kind` in [0, MALFORMED_KINDS)."""
        k = kind % self.MALFORMED_KINDS
        t = self.ts
        self.ts += 1000
        if k == 0:
            self.lines.append("this is not json at all }{")
        elif k == 1:  # missing key (no status)
            self._emit({"id": "m", "svc": "auth", "phase": "start", "ts": t})
        elif k == 2:  # extra key
            self._emit({"id": "m", "svc": "auth", "phase": "start", "ts": t,
                        "status": 200, "trace": "x"})
        elif k == 3:  # status as float
            self._emit({"id": "m", "svc": "gateway", "phase": "end", "ts": t, "status": 200.0})
        elif k == 4:  # ts as bool
            self._emit({"id": "m", "svc": "payment", "phase": "start", "ts": True, "status": 200})
        elif k == 5:  # status out of range
            self._emit({"id": "m", "svc": "auth", "phase": "end", "ts": t, "status": 99})
        elif k == 6:  # service not in enum
            self._emit({"id": "m", "svc": "billing", "phase": "start", "ts": t, "status": 200})
        elif k == 7:  # phase invalid
            self._emit({"id": "m", "svc": "gateway", "phase": "tick", "ts": t, "status": 200})
        elif k == 8:  # status as bool
            self._emit({"id": "m", "svc": "payment", "phase": "end", "ts": t, "status": True})

    def write_shards(self, out_dir, n_shards):
        os.makedirs(out_dir, exist_ok=True)
        for old in glob.glob(os.path.join(out_dir, "shard-*.log")):
            os.remove(old)
        total = len(self.lines)
        chunk = (total + n_shards - 1) // n_shards
        for s in range(n_shards):
            part = self.lines[s * chunk:(s + 1) * chunk]
            with open(os.path.join(out_dir, f"shard-{s:03d}.log"), "w") as f:
                if part:
                    f.write("\n".join(part) + "\n")


def build_large(out_dir, n_requests=300000, n_shards=6):
    """Large dataset: forces unbounded memory in the naive pipeline and exercises
    rolling-window eviction, per-start service attribution, and shard ordering."""
    b = StreamBuilder()
    tail = 9000
    volume = n_requests - tail

    # Volume phase: completed fast requests plus interleaved traps. These all
    # fall out of every rolling window, but a non-evicting correlator keeps them.
    for i in range(volume):
        rid = f"v{i:09d}"
        svc = SERVICES[i % 3]
        b.request(rid, svc, 100, 200)
        if i % 12 == 0:
            b.blank()
        if i % 20 == 0:
            b.malformed(i)
        if i % 500 == 0:
            b.orphan_start(f"os{i:09d}", SERVICES[(i // 500) % 3])
        if i % 700 == 0:
            b.orphan_end(f"oe{i:09d}", SERVICES[(i // 700) % 3], status=503)
        if i % 9000 == 0:
            b.dup_start(f"d{i:09d}", svc, 100, 200)

    # Clean tail: determines the final windows. Last 250 globally are slow (900),
    # placing the nearest-rank boundary exactly at the global p95 rank.
    for j in range(tail):
        rid = f"t{j:09d}"
        svc = SERVICES[j % 3]
        latency = 900 if j >= tail - 250 else 100
        status = 500 if j % 8 == 0 else 200
        # A band of requests whose END carries a different service tag than the
        # START, to exercise start-based service attribution.
        end_svc = SERVICES[(j + 1) % 3] if 5000 <= j < 5300 else svc
        b.request(rid, svc, latency, status, end_svc=end_svc)

    b.write_shards(out_dir, n_shards)


def build_partial(out_dir, n_shards=3):
    """Small dataset: every window is partial. Includes a service window whose
    error rate is a true round-half-up boundary (1/32 = 0.03125)."""
    b = StreamBuilder()

    # auth: 100 completed; nearest-rank p95 boundary at rank 95 (95 fast, 5 slow).
    for i in range(100):
        status = 500 if i < 10 else 200
        latency = 900 if i >= 95 else 100
        b.request(f"a{i:05d}", "auth", latency, status)
        if i % 7 == 0:
            b.blank()
        if i % 11 == 0:
            b.malformed(i)

    # gateway: 60 completed, 9 errored.
    for i in range(60):
        status = 500 if i < 9 else 200
        b.request(f"g{i:05d}", "gateway", 100 + (i % 50), status)

    # payment: exactly 32 completed, exactly 1 errored -> 1/32 = 0.03125.
    for i in range(32):
        status = 500 if i == 0 else 200
        b.request(f"p{i:05d}", "payment", 100 + (i % 40), status)

    # Orphans and a duplicate start.
    b.orphan_start("orph-a", "auth")
    b.orphan_end("orph-b", "gateway", status=500)
    b.orphan_end("orph-c", "payment", status=200)
    b.dup_start("dup-1", "gateway", 120, 200)

    b.write_shards(out_dir, n_shards)


# --------------------------------------------------------------------------- #
# Independent brute-force reference (the "truth")
# --------------------------------------------------------------------------- #
def _ref_valid(line):
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if type(obj) is not dict or set(obj.keys()) != {"id", "svc", "phase", "ts", "status"}:
        return None
    rid, svc, phase, ts, status = (obj["id"], obj["svc"], obj["phase"], obj["ts"], obj["status"])
    if type(rid) is not str or rid == "":
        return None
    if svc not in SERVICES or phase not in ("start", "end"):
        return None
    if type(ts) is not int or isinstance(ts, bool) or ts < 0:
        return None
    if type(status) is not int or isinstance(status, bool) or not (100 <= status <= 599):
        return None
    return (rid, svc, phase, ts, status)


def _ref_metrics(items):
    """items: list of (is_err, latency). Returns (error_rate_4dp, p95_2dp)."""
    n = len(items)
    if n == 0:
        return 0.0, 0.0
    errs = sum(e for e, _ in items)
    rate = float((Decimal(errs) / Decimal(n)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    lats = sorted(l for _, l in items)
    rank = -(-95 * n // 100)  # ceil(0.95 * n), 1-based
    p95 = float(Decimal(lats[rank - 1]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return rate, p95


def compute_truth(out_dir):
    processed = malformed = unmatched = 0
    open_reqs = {}
    completed = []  # (svc, is_err, latency) in completion order
    for path in sorted(glob.glob(os.path.join(out_dir, "shard-*.log"))):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                ev = _ref_valid(line)
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
                    if rid not in open_reqs:
                        unmatched += 1
                        continue
                    ts0, svc0 = open_reqs.pop(rid)
                    completed.append((svc0, 1 if status >= 400 else 0, ts - ts0))
                    processed += 1
    unmatched += len(open_reqs)

    out = {"processed_count": processed, "malformed_count": malformed, "unmatched_count": unmatched}
    g_items = [(e, l) for _, e, l in completed[-GLOBAL_CAP:]]
    out["global_error_rate"], out["global_p95_latency_ms"] = _ref_metrics(g_items)
    for s in SERVICES:
        s_items = [(e, l) for sv, e, l in completed if sv == s][-SERVICE_CAP:]
        out[f"{s}_error_rate"], out[f"{s}_p95_latency_ms"] = _ref_metrics(s_items)
    return out


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
            raise AssertionError("Pipeline exceeded execution timeout.")
        time.sleep(0.02)
    return proc.returncode, peak / (1024 * 1024)


def assert_matches(result, truth):
    assert isinstance(result, dict), "Output is not a JSON object."
    assert set(result.keys()) == set(truth.keys()), (
        f"Output keys mismatch.\n got: {sorted(result.keys())}\n want: {sorted(truth.keys())}"
    )
    for key, want in truth.items():
        got = result[key]
        if key.endswith("_count"):
            assert got == want, f"{key}: got {got}, want {want}"
        else:
            assert isinstance(got, (int, float)) and abs(float(got) - float(want)) < 1e-9, (
                f"{key}: got {got}, want {want}"
            )


def _reset_output():
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)


def _enforce_stdlib_only():
    """Supplemental guard for the stated standard-library-only constraint."""
    forbidden = ("numpy", "pandas", "scipy", "polars", "pyarrow", "sklearn")
    for path in glob.glob("/app/tracer/*.py"):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        for mod in forbidden:
            assert mod not in src, f"Forbidden third-party module '{mod}' found in {path}."


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_large_stream_memory_and_correctness():
    """Production-scale stream: enforces the <64MB RSS bound (defeats any
    correlator that retains all open or completed requests) and exact rolling
    metrics, per-start service attribution, and deterministic shard ordering."""
    _reset_output()
    build_large(DATA_DIR)
    truth = compute_truth(DATA_DIR)

    rc, peak_mb = run_with_peak_rss(ENTRY)
    assert rc == 0, "Pipeline crashed on the large stream."
    assert os.path.exists(OUTPUT_FILE), "Pipeline did not write /app/output.json."
    _enforce_stdlib_only()

    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert len(result) == 11, "Output must contain exactly 11 keys."
    assert_matches(result, truth)

    print(f"Peak RSS: {peak_mb:.2f} MB")
    assert peak_mb < MEM_BOUND_MB, f"Memory budget exceeded: {peak_mb:.2f} MB."


def test_partial_windows_and_rounding():
    """Partially-full windows computed over available items, including a service
    error rate at an exact round-half-up boundary (1/32 = 0.03125)."""
    _reset_output()
    build_partial(DATA_DIR)
    truth = compute_truth(DATA_DIR)

    rc, _ = run_with_peak_rss(ENTRY)
    assert rc == 0, "Pipeline crashed on the partial-window stream."
    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert len(result) == 11, "Output must contain exactly 11 keys."
    # Guard: this dataset really does exercise the half-up boundary.
    assert truth["payment_error_rate"] == 0.0313
    assert_matches(result, truth)


def test_empty_stream():
    """Whitespace-only input yields a fully zeroed report."""
    _reset_output()
    os.makedirs(DATA_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(DATA_DIR, "shard-*.log")):
        os.remove(old)
    with open(os.path.join(DATA_DIR, "shard-000.log"), "w") as f:
        f.write("\n\n   \n\n")

    rc, _ = run_with_peak_rss(ENTRY)
    assert rc == 0, "Pipeline crashed on the empty stream."
    with open(OUTPUT_FILE) as f:
        result = json.load(f)
    assert len(result) == 11
    assert result["processed_count"] == 0
    assert result["malformed_count"] == 0
    assert result["unmatched_count"] == 0
    for key, val in result.items():
        if key.endswith("_count"):
            continue
        assert float(val) == 0.0, f"{key} should be 0 on empty input, got {val}"
