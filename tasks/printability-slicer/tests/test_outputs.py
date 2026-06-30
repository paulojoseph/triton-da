"""Behavioral verifier for printability-slicer.

For each hidden part (a sheared polycube built from scratch here, never shown to
the agent), write its mesh and slice heights to /app/data, run the agent's
/app/slice.py, and compare the produced /app/result.json against an independent
exact-arithmetic reference:

  * regions, holes  -- exact integer match (topology; no tolerance)
  * area, perimeter, centroid, overhang_area, layer_volume -- rel/abs tolerance

The hidden parts differ from the one shipped in /app/data, so a solution that
hard-codes the development answers fails.  Many slice planes pass exactly through
mesh vertices and edges, so a solution that classifies them with floating point
(or nudges the plane off the degeneracies) merges or drops loops and pieces and
fails the exact region/hole checks.
"""
import os
import sys
import json
import math
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import slicer_oracle as R

DATA_DIR = "/app/data"
MESH = os.path.join(DATA_DIR, "mesh.obj")
HEIGHTS = os.path.join(DATA_DIR, "heights.json")
RESULT = "/app/result.json"
ENTRY = "python3 /app/slice.py"
INT_KEYS = ("regions", "holes")
NUM_KEYS = ("area", "perimeter", "overhang_area", "layer_volume")
REL_TOL = 1e-4
ABS_TOL = 1e-4
RUN_TIMEOUT = 300


def _close(got, exp):
    return math.isclose(got, exp, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def _run_instance(name, V, Faces, heights):
    os.makedirs(DATA_DIR, exist_ok=True)
    R.write_obj(MESH, V, Faces)
    with open(HEIGHTS, "w") as f:
        json.dump(heights, f)
    if os.path.exists(RESULT):
        os.remove(RESULT)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(ENTRY, shell=True, timeout=RUN_TIMEOUT,
                          capture_output=True, text=True, cwd="/app", env=env)
    assert proc.returncode == 0, (
        f"[{name}] /app/slice.py exited {proc.returncode}; "
        f"stderr:\n{proc.stderr[-2000:]}")
    assert os.path.exists(RESULT), f"[{name}] /app/slice.py wrote no /app/result.json"
    with open(RESULT) as f:
        got = json.load(f)
    return got


def _check(name, got, heights, expected):
    assert isinstance(got, list), f"[{name}] result must be a JSON array"
    assert len(got) == len(expected), (
        f"[{name}] expected {len(expected)} layers, got {len(got)}")
    for i, (g, e) in enumerate(zip(got, expected)):
        h = heights[i]
        assert isinstance(g, dict), f"[{name}] layer {i} (z={h}) not an object"
        for k in INT_KEYS:
            assert k in g, f"[{name}] layer z={h} missing '{k}'"
            assert g[k] == e[k], (
                f"[{name}] layer z={h}: {k}={g[k]} expected {e[k]}")
        for k in NUM_KEYS:
            assert k in g, f"[{name}] layer z={h} missing '{k}'"
            assert _close(float(g[k]), e[k]), (
                f"[{name}] layer z={h}: {k}={g[k]} expected {e[k]:.6f}")
        assert "centroid" in g, f"[{name}] layer z={h} missing 'centroid'"
        c = g["centroid"]
        assert isinstance(c, (list, tuple)) and len(c) == 2, (
            f"[{name}] layer z={h}: centroid must be a 2-element list")
        assert _close(float(c[0]), e["centroid"][0]) and \
            _close(float(c[1]), e["centroid"][1]), (
            f"[{name}] layer z={h}: centroid={c} expected {e['centroid']}")


def test_hidden_parts():
    instances = R.make_instances()
    assert instances, "no grading instances built"
    for (name, V, Faces, heights, expected) in instances:
        got = _run_instance(name, V, Faces, heights)
        _check(name, got, heights, expected)
