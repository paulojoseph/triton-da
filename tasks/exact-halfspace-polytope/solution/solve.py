"""Reference solution for exact-halfspace-polytope.

Reads /app/data/halfspaces.json (list of [a,b,c,d], meaning a*x+b*y+c*z <= d)
and /app/data/queries.json (list of [x,y,z] integer probe points), computes the
bounded convex polytope defined by the half-spaces, and writes /app/result.json.

All geometry is exact: candidate vertices are the rational meets of plane
triples, kept only if they satisfy every inequality. Faces are the half-spaces
whose plane meets the polytope in a 2D region (redundant half-spaces contribute
nothing). Volume and the classification of probe points are exact.
"""
import json
from fractions import Fraction as F
from itertools import combinations

HALFSPACES = "/app/data/halfspaces.json"
QUERIES = "/app/data/queries.json"
RESULT = "/app/result.json"


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
        if p is None:
            continue
        if any(side(h, p) > 0 for h in H):
            continue
        if p in seen:
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


def main():
    with open(HALFSPACES) as f:
        H = [tuple(row) for row in json.load(f)]
    with open(QUERIES) as f:
        queries = json.load(f)
    info = analyze(H)
    vol = info["volume"]
    result = {
        "num_vertices": info["num_vertices"],
        "num_edges": info["num_edges"],
        "num_faces": info["num_faces"],
        "face_sizes": info["face_sizes"],
        "volume": vol.numerator / vol.denominator,
        "classification": [classify(info, q) for q in queries],
    }
    with open(RESULT, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
