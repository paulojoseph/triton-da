"""Independent reference + hidden-instance generator for exact-halfspace-polytope.

`analyze`/`classify` compute the exact polytope and probe classification from a
half-space set. `make_instance` synthesizes a bounded full-3D polytope (a box
clipped by tilted cuts that produce rational vertices, plus redundant
half-spaces that must contribute no face) together with integer probe points,
and returns the expected output. All arithmetic is exact (fractions.Fraction).
"""
import json
import math
import random
from fractions import Fraction as F
from itertools import combinations


def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def det3(r0, r1, r2):
    return (r0[0]*(r1[1]*r2[2]-r1[2]*r2[1])
            - r0[1]*(r1[0]*r2[2]-r1[2]*r2[0])
            + r0[2]*(r1[0]*r2[1]-r1[1]*r2[0]))


def solve3(H3):
    A = [(h[0], h[1], h[2]) for h in H3]
    d = [h[3] for h in H3]
    D = det3(*A)
    if D == 0:
        return None
    Dx = det3((d[0], A[0][1], A[0][2]), (d[1], A[1][1], A[1][2]), (d[2], A[2][1], A[2][2]))
    Dy = det3((A[0][0], d[0], A[0][2]), (A[1][0], d[1], A[1][2]), (A[2][0], d[2], A[2][2]))
    Dz = det3((A[0][0], A[0][1], d[0]), (A[1][0], A[1][1], d[1]), (A[2][0], A[2][1], d[2]))
    return (F(Dx, D), F(Dy, D), F(Dz, D))


def side(h, p):
    return h[0]*p[0] + h[1]*p[1] + h[2]*p[2] - h[3]


def order_face(h, pts, ids):
    n = (h[0], h[1], h[2])
    ax = max(range(3), key=lambda t: abs(n[t]))
    o = [t for t in range(3) if t != ax]
    proj = sorted(set((pts[t][o[0]], pts[t][o[1]], ids[t]) for t in range(len(pts))))
    if len(proj) < 3:
        return [m for (_x, _y, m) in proj]

    def cz(O, A, B):
        return (A[0]-O[0])*(B[1]-O[1]) - (A[1]-O[1])*(B[0]-O[0])
    lower = []
    for p in proj:
        while len(lower) >= 2 and cz(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(proj):
        while len(upper) >= 2 and cz(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    chain = lower[:-1] + upper[:-1]
    return [m for (_x, _y, m) in chain]


def analyze(H):
    m = len(H)
    verts = []
    seen = set()
    for i, j, k in combinations(range(m), 3):
        p = solve3((H[i], H[j], H[k]))
        if p is None or any(side(h, p) > 0 for h in H) or p in seen:
            continue
        seen.add(p)
        verts.append(p)
    active = [frozenset(t for t in range(m) if side(H[t], verts[vi]) == 0)
              for vi in range(len(verts))]
    faces = []
    face_sizes = []
    for t in range(m):
        vids = [vi for vi in range(len(verts)) if t in active[vi]]
        if len(vids) < 3:
            continue
        ordered = order_face(H[t], [verts[vi] for vi in vids], vids)
        if len(ordered) < 3:
            continue
        faces.append((t, ordered))
        face_sizes.append(len(ordered))
    used_v = set()
    edges = set()
    for t, ordered in faces:
        L = len(ordered)
        for q in range(L):
            a, b = ordered[q], ordered[(q+1) % L]
            edges.add((min(a, b), max(a, b)))
            used_v.add(a)
    vol6 = F(0)
    if faces:
        ref = verts[next(iter(used_v))]
        for t, ordered in faces:
            outn = (H[t][0], H[t][1], H[t][2])
            poly = [verts[vi] for vi in ordered]
            nchk = cross(sub(poly[1], poly[0]), sub(poly[2], poly[0]))
            if dot(nchk, outn) < 0:
                poly = poly[::-1]
            a = poly[0]
            for q in range(1, len(poly)-1):
                vol6 += dot(sub(a, ref), cross(sub(poly[q], ref), sub(poly[q+1], ref)))
    volume = abs(vol6) / 6
    return {"num_vertices": len(used_v), "num_edges": len(edges),
            "num_faces": len(faces), "face_sizes": sorted(face_sizes),
            "volume": volume, "verts": verts, "used": used_v, "faces": faces, "H": H}


def classify(info, q):
    H = info["H"]
    q = tuple(F(c) for c in q)
    s = [side(h, q) for h in H]
    if any(x > 0 for x in s):
        return "outside"
    if all(x != 0 for x in s):
        return "inside"
    for vi in info["used"]:
        if info["verts"][vi] == q:
            return "vertex"
    for t, ordered in info["faces"]:
        poly = [info["verts"][vi] for vi in ordered]
        L = len(poly)
        for u in range(L):
            a, b = poly[u], poly[(u+1) % L]
            ab = sub(b, a); aq = sub(q, a)
            if cross(ab, aq) == (0, 0, 0):
                d2 = dot(ab, ab); tt = dot(aq, ab)
                if 0 <= tt <= d2:
                    return "edge"
    return "face"


def expected_output(H, queries):
    info = analyze(H)
    vol = info["volume"]
    return {
        "num_vertices": info["num_vertices"],
        "num_edges": info["num_edges"],
        "num_faces": info["num_faces"],
        "face_sizes": info["face_sizes"],
        "volume": vol.numerator / vol.denominator,
        "classification": [classify(info, q) for q in queries],
    }


def _box(A, B, C):
    return [(-1, 0, 0, 0), (1, 0, 0, A), (0, -1, 0, 0), (0, 1, 0, B),
            (0, 0, -1, 0), (0, 0, 1, C)]


def make_instance(seed):
    """Return (halfspaces, queries, expected)."""
    rng = random.Random(seed)
    A = rng.randint(10, 18); B = rng.randint(10, 18); C = rng.randint(10, 18)
    H = _box(A, B, C)
    cx, cy, cz = F(A, 2), F(B, 2), F(C, 2)
    for _ in range(rng.randint(2, 5)):
        a = rng.randint(-2, 2); b = rng.randint(-2, 2); c = rng.randint(-2, 2)
        if (a, b, c) == (0, 0, 0):
            a = 1
        corner = (rng.choice([0, A]), rng.choice([0, B]), rng.choice([0, C]))
        vc = a*corner[0] + b*corner[1] + c*corner[2]
        vctr = a*cx + b*cy + c*cz
        frac = F(rng.randint(55, 80), 100)
        de = vctr + frac*(vc - vctr)
        if vc > vctr:
            H.append((a, b, c, math.floor(de)))
        else:
            H.append((-a, -b, -c, math.ceil(-de)))
    for _ in range(rng.randint(1, 3)):
        a = rng.randint(-2, 2); b = rng.randint(-2, 2); c = rng.randint(-2, 2)
        if (a, b, c) == (0, 0, 0):
            c = 1
        H.append((a, b, c, 10000))
    rng.shuffle(H)
    info = analyze(H)
    # Build a probe set with balanced coverage of all five classes. Box faces sit
    # on integer planes (x=0, x=A, ...), so integer points placed on them land on
    # the solid's faces/edges; integer polytope vertices give the 'vertex' cases.
    buckets = {c: [] for c in ("inside", "outside", "vertex", "edge", "face")}
    for vi in info["used"]:
        v = info["verts"][vi]
        if all(x.denominator == 1 for x in v):
            buckets["vertex"].append([int(x) for x in v])
    cand = []
    for _ in range(500):
        if rng.random() < 0.5:
            cand.append([rng.randint(0, A), rng.randint(0, B), rng.randint(0, C)])
        else:
            coord = rng.randint(0, 2)
            p = [rng.randint(0, A), rng.randint(0, B), rng.randint(0, C)]
            p[coord] = rng.choice([0, [A, B, C][coord]])
            cand.append(p)
    for _ in range(60):
        cand.append([rng.randint(-3, A+3), rng.randint(-3, B+3), rng.randint(-3, C+3)])
    cap = {"inside": 8, "outside": 8, "vertex": 12, "edge": 8, "face": 8}
    for q in cand:
        c = classify(info, q)
        if len(buckets[c]) < cap[c]:
            buckets[c].append(q)
    queries = []
    for c in ("inside", "face", "edge", "vertex", "outside"):
        queries.extend(buckets[c])
    seenq = set(); qs = []
    for q in queries:
        key = tuple(q)
        if key not in seenq:
            seenq.add(key); qs.append(q)
    rng.shuffle(qs)
    expected = expected_output(H, qs)
    return H, qs, expected


def write_data(directory, H, queries):
    import os
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "halfspaces.json"), "w") as f:
        json.dump([list(h) for h in H], f)
    with open(os.path.join(directory, "queries.json"), "w") as f:
        json.dump([list(q) for q in queries], f)
