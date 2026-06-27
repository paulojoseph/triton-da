"""Reference solution for anatomical-cross-sections.

Reads /app/data/mesh.obj (closed, watertight, outward-oriented integer triangle
mesh) and /app/data/planes.json (array of [a,b,c,d]); writes /app/result.json
with loops / area / perimeter / volume_positive / volume_negative per plane.

Every geometric predicate is evaluated in exact rational arithmetic, so a plane
that passes exactly through vertices or edges is handled without tolerances or
perturbing the plane.
"""
import json
import math
from fractions import Fraction as F
from collections import defaultdict

MESH = "/app/data/mesh.obj"
PLANES = "/app/data/planes.json"
RESULT = "/app/result.json"


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def smul(s, a):
    return (s * a[0], s * a[1], s * a[2])


def side(n, d, p):
    return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] - d


def edge_cross(P, Q, sP, sQ):
    t = F(sP, sP - sQ)
    return (P[0] + t * (Q[0] - P[0]),
            P[1] + t * (Q[1] - P[1]),
            P[2] + t * (Q[2] - P[2]))


def clip_triangle(tri, n, d, keep_negative=True):
    pts = [tuple(F(c) for c in v) for v in tri]
    s = [side(n, d, p) for p in pts]
    if not keep_negative:
        s = [-x for x in s]
    out = []
    m = len(pts)
    for i in range(m):
        P, Q = pts[i], pts[(i + 1) % m]
        sP, sQ = s[i], s[(i + 1) % m]
        if sP <= 0:
            out.append(P)
        if (sP < 0 and sQ > 0) or (sP > 0 and sQ < 0):
            out.append(edge_cross(P, Q, sP, sQ))
    poly = []
    for p in out:
        if not poly or poly[-1] != p:
            poly.append(p)
    if len(poly) > 1 and poly[0] == poly[-1]:
        poly.pop()
    seg = []
    L = len(poly)
    for i in range(L):
        A, B = poly[i], poly[(i + 1) % L]
        if side(n, d, A) == 0 and side(n, d, B) == 0 and A != B:
            seg.append((A, B))
    return poly, seg


def volume_side(V, Faces, n, d, keep_negative):
    a, b, c = n
    for cand in ((b, -a, 0), (0, c, -b), (-c, 0, a)):
        if cand != (0, 0, 0):
            u = cand
            break
    u2 = dot(u, u)
    acc = F(0)
    for i, j, k in Faces:
        poly, _ = clip_triangle((V[i], V[j], V[k]), n, d, keep_negative)
        if len(poly) < 3:
            continue
        p0 = poly[0]
        for t in range(1, len(poly) - 1):
            p, q, r = p0, poly[t], poly[t + 1]
            areavec = smul(F(1, 2), cross(sub(q, p), sub(r, p)))
            cen = (F(p[0] + q[0] + r[0], 3),
                   F(p[1] + q[1] + r[1], 3),
                   F(p[2] + q[2] + r[2], 3))
            acc += dot(u, areavec) * dot(u, cen)
    return acc / u2


def assemble_loops(segments):
    edges = list(segments)
    out_map = defaultdict(list)
    for idx, (A, B) in enumerate(edges):
        out_map[A].append(idx)
    used = [False] * len(edges)
    loops = []
    for start in range(len(edges)):
        if used[start]:
            continue
        A0, B0 = edges[start]
        used[start] = True
        loop = [A0, B0]
        cur = B0
        while cur != A0:
            nxt = None
            for idx in out_map[cur]:
                if not used[idx]:
                    nxt = idx
                    break
            if nxt is None:
                break
            used[nxt] = True
            nb = edges[nxt][1]
            loop.append(nb)
            cur = nb
        if loop[-1] == loop[0]:
            loop.pop()
        loops.append(loop)
    return loops


def project2d(loop, ax):
    other = [i for i in range(3) if i != ax]
    return [(p[other[0]], p[other[1]]) for p in loop]


def signed_area2d(poly2):
    s = F(0)
    m = len(poly2)
    for i in range(m):
        x1, y1 = poly2[i]
        x2, y2 = poly2[(i + 1) % m]
        s += x1 * y2 - x2 * y1
    return s / 2


def analyze(V, Faces, plane):
    n = (plane[0], plane[1], plane[2])
    d = plane[3]
    segs = []
    for i, j, k in Faces:
        _, seg = clip_triangle((V[i], V[j], V[k]), n, d, keep_negative=True)
        segs.extend(seg)
    loops = [L for L in assemble_loops(segs) if len(L) >= 3]
    nmag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if not loops:
        nloops, area, perim = 0, 0.0, 0.0
    else:
        ax = max(range(3), key=lambda i: abs(n[i]))
        net = F(0)
        for L in loops:
            net += signed_area2d(project2d(L, ax))
        area = abs(float(net)) * nmag / abs(n[ax])
        perim = 0.0
        for L in loops:
            for i in range(len(L)):
                e = sub(L[(i + 1) % len(L)], L[i])
                perim += math.sqrt(float(dot(e, e)))
        nloops = len(loops)
    vneg = volume_side(V, Faces, n, d, keep_negative=True)
    vpos = volume_side(V, Faces, n, d, keep_negative=False)
    return {"loops": nloops, "area": area, "perimeter": perim,
            "volume_positive": float(vpos), "volume_negative": float(vneg)}


def read_obj(path):
    V, Faces = [], []
    with open(path) as f:
        for line in f:
            t = line.split()
            if not t:
                continue
            if t[0] == "v":
                V.append((int(t[1]), int(t[2]), int(t[3])))
            elif t[0] == "f":
                idx = [int(p.split("/")[0]) - 1 for p in t[1:4]]
                Faces.append((idx[0], idx[1], idx[2]))
    return V, Faces


def main():
    V, Faces = read_obj(MESH)
    with open(PLANES) as f:
        planes = json.load(f)
    result = [analyze(V, Faces, p) for p in planes]
    with open(RESULT, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
