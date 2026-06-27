"""Independent exact-arithmetic reference for anatomical-cross-sections.

Computes, for a plane a*x+b*y+c*z=d cutting a closed, watertight,
outward-oriented integer triangle mesh: the number of boundary loops of the
cross-section, its area (holes excluded), its perimeter, and the solid volume
on each side of the plane. All geometric predicates use exact rational
arithmetic (fractions.Fraction), so on-plane vertices and edges are handled
without any tolerance or perturbation.

Also builds the hidden grading meshes (polycubes) from scratch so the verifier
never reads any precomputed answer.
"""
from fractions import Fraction as F
from collections import defaultdict
import math


# ---------------------------------------------------------------- vector ops
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


def total_volume(V, Faces):
    s = 0
    for i, j, k in Faces:
        s += dot(V[i], cross(V[j], V[k]))
    return F(s, 6)


def side(n, d, p):
    return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] - d


def edge_cross(P, Q, sP, sQ):
    t = F(sP, sP - sQ)
    return (P[0] + t * (Q[0] - P[0]),
            P[1] + t * (Q[1] - P[1]),
            P[2] + t * (Q[2] - P[2]))


def clip_triangle(tri, n, d, keep_negative=True):
    """Sutherland-Hodgman clip of a triangle to the half-space {side<=0} (or
    {side>=0}). Returns the clipped polygon (rational points, in the triangle's
    winding order) and the list of directed on-plane boundary edges (A->B)."""
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
    """Exact volume of the solid on one side of the plane. Uses the divergence
    field G = u*(u.x) with u an integer vector parallel to the plane, so the
    planar cap contributes nothing and no cap reconstruction is needed."""
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
    """Join directed on-plane edges (A->B, inherited from each clipped triangle's
    outward winding) into closed loops. Outer boundaries and hole boundaries come
    out with opposite winding, so projected signed areas sum to the net area."""
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
    """Return {loops, area, perimeter, volume_positive, volume_negative}."""
    n = (plane[0], plane[1], plane[2])
    d = plane[3]
    segs = []
    for i, j, k in Faces:
        _, seg = clip_triangle((V[i], V[j], V[k]), n, d, keep_negative=True)
        segs.extend(seg)
    loops = assemble_loops(segs)
    loops = [L for L in loops if len(L) >= 3]
    nmag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if not loops:
        nloops = 0
        area = 0.0
        perim = 0.0
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


# ------------------------------------------------------------------- mesh IO
def write_obj(path, V, Faces):
    with open(path, "w") as f:
        f.write("# anatomical structure: integer-coordinate triangle mesh\n")
        for (x, y, z) in V:
            f.write(f"v {x} {y} {z}\n")
        for (i, j, k) in Faces:
            f.write(f"f {i + 1} {j + 1} {k + 1}\n")


def read_obj(path):
    V = []
    Faces = []
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


# ------------------------------------------------------- polycube generation
_FACE_SPECS = [
    ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
    ((1, 0, 0),  [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ((0, 1, 0),  [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
    ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ((0, 0, 1),  [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
]


def polycube_mesh(cells):
    """Boundary surface of a set of integer unit cells: watertight, manifold,
    outward-oriented triangle mesh with integer vertex coordinates."""
    cellset = set(cells)
    vindex = {}
    V = []

    def vid(p):
        if p not in vindex:
            vindex[p] = len(V)
            V.append(p)
        return vindex[p]
    Faces = []
    for (x, y, z) in sorted(cells):
        for (off, corners) in _FACE_SPECS:
            nb = (x + off[0], y + off[1], z + off[2])
            if nb in cellset:
                continue
            ids = [vid((x + c[0], y + c[1], z + c[2])) for c in corners]
            a, b, c, e = ids
            Faces.append((a, b, c))
            Faces.append((a, c, e))
    return V, Faces


def check_manifold(V, Faces):
    dircount = defaultdict(int)
    for (i, j, k) in Faces:
        for (a, b) in ((i, j), (j, k), (k, i)):
            dircount[(a, b)] += 1
    for (a, b), c in dircount.items():
        if c != 1 or dircount.get((b, a), 0) != 1:
            return False
    return True


# ------------------------------------------------------------ hidden shapes
def _ring(ow, oh, od, t):
    cells = set()
    for x in range(ow):
        for y in range(oh):
            for z in range(od):
                if t <= x < ow - t and t <= y < oh - t:
                    continue
                cells.add((x, y, z))
    return cells


def shape_ring_lobe():
    cells = _ring(14, 14, 7, 4)
    for x in range(14, 18):
        for y in range(5, 9):
            for z in range(1, 6):
                cells.add((x, y, z))
    return cells


def shape_x_tunnel():
    cells = set()
    for x in range(12):
        for y in range(9):
            for z in range(9):
                if 3 <= y < 6 and 3 <= z < 6:
                    continue
                cells.add((x, y, z))
    return cells


def shape_l_prism():
    cells = set()
    for x in range(12):
        for y in range(12):
            for z in range(6):
                if x >= 6 and y >= 6:
                    continue
                cells.add((x, y, z))
    return cells


# Planes pre-selected (offline) to be "regular": no face is coplanar with the
# plane and every on-plane contour vertex has in-degree == out-degree == 1, so
# the loop assembly is unambiguous. Each set spans loops 0/1/2 and includes a
# single-vertex grazing plane.
_INSTANCES = [
    ("ring_lobe", shape_ring_lobe, [
        [1, 1, 1, 1], [1, 2, 1, 8], [1, 2, 2, 34],
        [1, 1, 1, 16], [1, 2, 1, 26], [2, 2, 1, 34], [1, 1, -1, 28],
    ]),
    ("x_tunnel", shape_x_tunnel, [
        [1, 1, 1, 1], [1, 2, 1, 5], [1, 2, 2, 19],
        [1, 1, 1, 13], [2, 1, 2, 20], [3, 1, 1, 13], [1, 1, -1, 21],
    ]),
    ("l_prism", shape_l_prism, [
        [1, 1, 1, 1], [1, 2, 1, 11], [1, 2, 2, 26],
        [1, 1, 1, 19], [1, 2, 1, 25], [2, 2, 1, 31], [1, 1, -1, 18],
    ]),
]


def make_instance(name):
    """Build one hidden grading instance: (name, V, Faces, planes, expected)."""
    for nm, shapefn, planes in _INSTANCES:
        if nm != name:
            continue
        V, Faces = polycube_mesh(shapefn())
        assert check_manifold(V, Faces), f"{nm}: non-manifold mesh"
        expected = [analyze(V, Faces, p) for p in planes]
        return (nm, V, Faces, planes, expected)
    raise KeyError(name)


def make_instances():
    """Build every hidden grading instance."""
    return [make_instance(nm) for nm, _, _ in _INSTANCES]
