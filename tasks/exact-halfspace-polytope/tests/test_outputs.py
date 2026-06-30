"""Behavioral verifier for exact-halfspace-polytope.

For each hidden half-space set (generated here, never shown to the agent), write
it to /app/data, run the agent's /app/polytope.py, and check /app/result.json
against an independent exact reference: the polytope's vertex/edge/face counts
and face-size list exactly, its volume within tolerance, and every probe-point
classification exactly. Then re-run with the half-spaces shuffled and require
identical output, since the answer must not depend on input ordering.

The half-spaces include tilted cuts (rational vertices that float libraries place
imprecisely) and redundant planes (tight nowhere, so they are not faces). A
solution that uses scipy.spatial.HalfspaceIntersection tends to error out or
mis-handle the degenerate vertices, and one that counts a face per half-space
over-counts the redundant ones.
"""
import os
import sys
import json
import math
import random
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import halfspace_oracle as R

DATA_DIR = "/app/data"
RESULT = "/app/result.json"
ENTRY = "python3 /app/polytope.py"
EXACT_KEYS = ("num_vertices", "num_edges", "num_faces", "face_sizes", "classification")
KEYS = {"num_vertices", "num_edges", "num_faces", "face_sizes", "volume", "classification"}
RUN_TIMEOUT = 150


def _run_agent(name):
    if os.path.exists(RESULT):
        os.remove(RESULT)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(ENTRY, shell=True, timeout=RUN_TIMEOUT,
                          capture_output=True, text=True, cwd="/app", env=env)
    assert proc.returncode == 0, (
        f"[{name}] /app/polytope.py exited {proc.returncode}; "
        f"stderr:\n{proc.stderr[-2000:]}")
    assert os.path.exists(RESULT), f"[{name}] /app/polytope.py wrote no /app/result.json"
    with open(RESULT) as f:
        got = json.load(f)
    assert isinstance(got, dict) and set(got.keys()) == KEYS, (
        f"[{name}] result keys: {sorted(got) if isinstance(got, dict) else got}")
    return got


def _compare(name, got, expected):
    for k in EXACT_KEYS:
        assert got[k] == expected[k], (
            f"[{name}] {k}: {got[k]} != {expected[k]}")
    assert math.isclose(float(got["volume"]), expected["volume"],
                        rel_tol=1e-6, abs_tol=1e-6), (
        f"[{name}] volume {got['volume']} != {expected['volume']}")


def _check(name, seed):
    H, queries, expected = R.make_instance(seed)
    R.write_data(DATA_DIR, H, queries)
    got = _run_agent(name)
    _compare(name, got, expected)
    # order-invariance: shuffling the half-spaces must not change the answer
    rng = random.Random(seed * 31 + 5)
    for r in range(2):
        H2 = list(H)
        rng.shuffle(H2)
        R.write_data(DATA_DIR, H2, queries)
        g2 = _run_agent(name)
        _compare(f"{name}-shuffled{r}", g2, expected)


def test_polytopes_small():
    """Boxes clipped by a few tilted cuts: rational vertices, redundant planes,
    and probe classification across inside/outside/vertex/edge/face."""
    for seed in (70001, 70002, 70003):
        _check(f"small-{seed}", seed)


def test_polytopes_dense():
    """More cuts, so more rational vertices and larger face counts."""
    for seed in (80001, 80002):
        _check(f"dense-{seed}", seed)


def test_redundant_and_classification():
    """A single instance focused on redundant-plane exclusion and exact probe
    classification (the face count must ignore tight-nowhere half-spaces)."""
    H, queries, expected = R.make_instance(90001)
    R.write_data(DATA_DIR, H, queries)
    got = _run_agent("redundant")
    _compare("redundant", got, expected)
    assert "outside" in expected["classification"]
    assert any(c in ("vertex", "edge", "face") for c in expected["classification"])
