"""Behavioral verifier for crdt-causal-merge.

For each hidden edit history (generated here, never shown to the agent), write
the per-replica logs to /app/data/replicas, run the agent's /app/merge.py, and
check /app/result.json against an independent causal-merge reference. Then, the
decisive anti-cheat check: re-deliver the SAME edit multiset under several
different file partitions and orderings and require the agent's program to
produce byte-identical output every time. A solution that applies edits in
file/arrival order (the common shortcut) drifts across deliveries and fails even
when one ordering happens to match the reference.
"""
import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import crdt_oracle as R

DATA_DIR = "/app/data/replicas"
RESULT = "/app/result.json"
ENTRY = "python3 /app/merge.py"
KEYS = {"set", "register", "sequence", "applied"}
RUN_TIMEOUT = 120


def _run_agent(name):
    if os.path.exists(RESULT):
        os.remove(RESULT)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(ENTRY, shell=True, timeout=RUN_TIMEOUT,
                          capture_output=True, text=True, cwd="/app", env=env)
    assert proc.returncode == 0, (
        f"[{name}] /app/merge.py exited {proc.returncode}; "
        f"stderr:\n{proc.stderr[-2000:]}")
    assert os.path.exists(RESULT), f"[{name}] /app/merge.py wrote no /app/result.json"
    with open(RESULT) as f:
        got = json.load(f)
    assert isinstance(got, dict) and set(got.keys()) == KEYS, (
        f"[{name}] result keys: {sorted(got) if isinstance(got, dict) else got}")
    return got


def _check(name, seed):
    logs, expected = R.make_instance(name, seed)
    R.write_logs(DATA_DIR, logs)
    got = _run_agent(name)
    assert got == expected, (
        f"[{name}] merged document mismatch.\n  expected={json.dumps(expected, sort_keys=True)}"
        f"\n  got     ={json.dumps(got, sort_keys=True)}")
    # convergence: identical bytes across re-deliveries of the same edit multiset
    canonical = json.dumps(expected, sort_keys=True)
    for vi, variant in enumerate(R.shuffle_deliveries(logs, 5, seed * 911 + 13)):
        R.write_logs(DATA_DIR, variant)
        g = _run_agent(name)
        assert json.dumps(g, sort_keys=True) == canonical, (
            f"[{name}] non-convergent: delivery #{vi} gave a different result.\n"
            f"  expected={canonical}\n  got     ={json.dumps(g, sort_keys=True)}")


def test_convergence_small():
    """Several concurrent histories: every part (add-wins set, LWW register, RGA
    list) must match the reference and stay byte-identical across re-deliveries."""
    for seed in (40001, 40002, 40003):
        _check(f"small-{seed}", seed)


def test_convergence_dense():
    """Denser histories with more replicas and steps, so concurrency saturates
    (concurrent add/remove of one tag, shared insert anchors, ts ties)."""
    for seed in (50001, 50002):
        logs, expected = R.make_instance(f"dense-{seed}", seed, replicas=5, steps=120)
        R.write_logs(DATA_DIR, logs)
        got = _run_agent(f"dense-{seed}")
        assert got == expected, (
            f"[dense-{seed}] mismatch.\n  expected={json.dumps(expected, sort_keys=True)}"
            f"\n  got     ={json.dumps(got, sort_keys=True)}")
        canonical = json.dumps(expected, sort_keys=True)
        for vi, variant in enumerate(R.shuffle_deliveries(logs, 5, seed * 7 + 1)):
            R.write_logs(DATA_DIR, variant)
            g = _run_agent(f"dense-{seed}")
            assert json.dumps(g, sort_keys=True) == canonical, (
                f"[dense-{seed}] non-convergent on delivery #{vi}")


def test_orphan_excluded():
    """An edit whose causal dependencies never arrive must be dropped, excluded
    from `applied`, and must not win the register."""
    logs, expected = R.make_instance("orphan", 60001)
    assert expected["register"]["value"] != "ORPHAN_MUST_NOT_WIN"
    R.write_logs(DATA_DIR, logs)
    got = _run_agent("orphan")
    assert got == expected, (
        f"[orphan] mismatch.\n  expected={json.dumps(expected, sort_keys=True)}"
        f"\n  got     ={json.dumps(got, sort_keys=True)}")
