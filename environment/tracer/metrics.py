"""Computes error-rate and latency percentile metrics."""


def _p95(latencies):
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    idx = int(0.95 * len(ordered))
    return round(float(ordered[idx]), 2)


def _block(items):
    n = len(items)
    if n == 0:
        return 0.0, 0.0
    errs = sum(is_err for _, is_err, _ in items)
    rate = round(errs / n, 4)
    p95 = _p95([latency for _, _, latency in items])
    return rate, p95


def compute(completed, services, global_window, service_window):
    out = {}
    g_rate, g_p95 = _block(completed)
    out["global_error_rate"] = g_rate
    out["global_p95_latency_ms"] = g_p95
    for svc in services:
        items = [c for c in completed if c[0] == svc]
        rate, p95 = _block(items)
        out[f"{svc}_error_rate"] = rate
        out[f"{svc}_p95_latency_ms"] = p95
    return out
