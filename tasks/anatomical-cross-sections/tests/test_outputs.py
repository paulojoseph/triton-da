"""Behavioral verifier for anatomical-cross-sections.

For each hidden organ mesh (built from scratch here, never shown to the agent),
write it to /app/data, run the agent's /app/slice.py, and compare the produced
/app/result.json against an independent exact-arithmetic reference:

  * loops          -- exact integer match (topology; no tolerance)
  * area           -- relative/absolute tolerance
  * perimeter      -- relative/absolute tolerance
  * volume_*       -- relative/absolute tolerance

The meshes differ from the one shipped in /app/data, so a solution that hard-codes
answers for the development mesh fails. The planes pass exactly through many
mesh vertices and edges, so a solution that classifies vertices with floating
point (or nudges the plane off the degeneracies) misplaces or merges contour
loops and fails the exact `loops` check.
"""
import os
import sys
import json
import math
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import cross_section_oracle as R

DATA_DIR = "/app/data"
MESH = os.path.join(DATA_DIR, "mesh.obj")
PLANES = os.path.join(DATA_DIR, "planes.json")
RESULT = "/app/result.json"
ENTRY = "python3 /app/slice.py"
KEYS = {"loops", "area", "perimeter", "volume_positive", "volume_negative"}
REL_TOL = 1e-4
ABS_TOL = 1e-4
RUN_TIMEOUT = 200


def _close(got, exp):
    return math.isclose(got, exp, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def _run_instance(name, V, Faces, planes):
    os.makedirs(DATA_DIR, exist_ok=True)
    R.write_obj(MESH, V, Faces)
    with open(PLANES, "w") as f:
        json.dump(planes, f)
    if os.path.exists(RESULT):
        os.remove(RESULT)
    # Run the agent's program from /app with a clean import path (the reference
    # lives under /tests and must not be importable by the solution under test).
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
    assert isinstance(got, list), f"[{name}] result.json must be a JSON array"
    assert len(got) == len(planes), (
        f"[{name}] result has {len(got)} entries, expected {len(planes)}")
    return got


def _check_instance(name):
    _, V, Faces, planes, expected = R.make_instance(name)
    got = _run_instance(name, V, Faces, planes)
    for i, (g, e, p) in enumerate(zip(got, expected, planes)):
        assert isinstance(g, dict) and set(g.keys()) == KEYS, (
            f"[{name}] plane {i}={p}: keys {sorted(g) if isinstance(g, dict) else g}")
        assert int(g["loops"]) == e["loops"], (
            f"[{name}] plane {i}={p}: loops {g['loops']} != {e['loops']}")
        for key in ("area", "perimeter", "volume_positive", "volume_negative"):
            assert _close(float(g[key]), e[key]), (
                f"[{name}] plane {i}={p}: {key} {g[key]} != {e[key]}")


def test_ring_lobe():
    """Genus-1 tube with an asymmetric lobe: annular and multi-region sections,
    planes grazing or slicing exactly through grid vertices."""
    _check_instance("ring_lobe")


def test_x_tunnel():
    """Block bored through by a square tunnel (genus-1): several planes yield two
    boundary loops; volumes must split the bored solid exactly."""
    _check_instance("x_tunnel")


def test_l_prism():
    """Non-convex L-shaped prism: a single plane can carve disjoint regions and
    re-enter the solid; the reentrant corner lies exactly on cutting planes."""
    _check_instance("l_prism")
