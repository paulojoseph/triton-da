"""Independent exact-arithmetic reference for printability-slicer.

For a horizontal plane z = h cutting a closed, watertight, outward-oriented
integer triangle mesh, this computes per layer: the number of disjoint solid
pieces (regions) and holes of the cross-section, its filled area, perimeter and
area centroid, the overhang area relative to the previous layer, and the solid
volume deposited between the previous layer and this one.  Every geometric
predicate uses exact rational arithmetic (fractions.Fraction); planes that pass
through vertices and edges are handled exactly, with no tolerance or
perturbation.

The hidden grading meshes (sheared polycubes) are built here from scratch so the
verifier never reads any precomputed answer.
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
    """Sutherland-Hodgman clip of a triangle to a half-space; returns the clipped
    polygon (rational points) and the directed on-plane boundary edges."""
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
    """Exact volume of the solid on one side of the plane, using the divergence
    field G = u*(u.x) with u parallel to the plane so the planar cap contributes
    nothing (no cap reconstruction needed)."""
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
    """Join directed on-plane edges into closed loops (outer and hole boundaries
    come out with opposite winding)."""
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


# ------------------------------------------------------------ 2D cross-section
def section_loops_xy(V, Faces, h):
    """The z=h cross-section contour as a list of loops of rational (x,y)."""
    n = (0, 0, 1)
    segs = []
    for i, j, k in Faces:
        _, seg = clip_triangle((V[i], V[j], V[k]), n, h, keep_negative=True)
        segs.extend(seg)
    loops3 = assemble_loops(segs)
    loops3 = [L for L in loops3 if len(L) >= 3]
    return [[(p[0], p[1]) for p in L] for L in loops3]


def _signed_area(poly):
    s = F(0)
    m = len(poly)
    for i in range(m):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % m]
        s += x1 * y2 - x2 * y1
    return s / 2


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    m = len(poly)
    for i in range(m):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % m]
        if (y1 > y) != (y2 > y):
            xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xint:
                inside = not inside
    return inside


def _nesting_depth(loops):
    reps = [L[0] for L in loops]
    depth = []
    for i in range(len(loops)):
        d = 0
        for j, M in enumerate(loops):
            if i != j and _point_in_poly(reps[i], M):
                d += 1
        depth.append(d)
    return depth


def _region_intervals(loops, xm):
    ys = []
    for L in loops:
        m = len(L)
        for i in range(m):
            x1, y1 = L[i]
            x2, y2 = L[(i + 1) % m]
            if (x1 < xm) != (x2 < xm):
                t = (xm - x1) / (x2 - x1)
                ys.append(y1 + t * (y2 - y1))
    ys.sort()
    return ys


def _all_edges(loops):
    E = []
    for L in loops:
        m = len(L)
        for i in range(m):
            E.append((L[i], L[(i + 1) % m]))
    return E


def _x_events(loopsA, loopsB):
    xs = set()
    for L in (loopsA + loopsB):
        for (x, y) in L:
            xs.add(x)
    EA, EB = _all_edges(loopsA), _all_edges(loopsB)
    for (a, b) in EA:
        for (c, dd) in EB:
            (ax, ay), (bx, by) = a, b
            (cx, cy), (dx_, dy_) = c, dd
            r0, r1 = bx - ax, by - ay
            s0, s1 = dx_ - cx, dy_ - cy
            den = r0 * s1 - r1 * s0
            if den == 0:
                continue
            ex, ey = cx - ax, cy - ay
            s = (ex * s1 - ey * s0) / den
            u = (ex * r1 - ey * r0) / den
            if 0 <= s <= 1 and 0 <= u <= 1:
                xs.add(ax + s * (bx - ax))
    return sorted(xs)


def _measure_in_A_not_B(ysA, ysB):
    def intervals(ys):
        return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]
    A = intervals(ysA)
    B = intervals(ysB)
    total = F(0)
    for (a0, a1) in A:
        length = a1 - a0
        for (b0, b1) in B:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                length -= (hi - lo)
        total += length
    return total


def overhang_area(loops_i, loops_prev):
    """Exact area( region_i \\ region_prev ) via a vertical slab sweep; the
    measure is piecewise linear between event abscissae so the midpoint rule is
    exact."""
    if not loops_i:
        return F(0)
    if not loops_prev:
        return sum(_signed_area(L) for L in loops_i)
    xs = _x_events(loops_i, loops_prev)
    acc = F(0)
    for a in range(len(xs) - 1):
        x0, x1 = xs[a], xs[a + 1]
        if x1 == x0:
            continue
        xm = (x0 + x1) / 2
        acc += (x1 - x0) * _measure_in_A_not_B(
            _region_intervals(loops_i, xm), _region_intervals(loops_prev, xm))
    return acc


def volume_below(V, Faces, h):
    return volume_side(V, Faces, (0, 0, 1), h, keep_negative=True)


def analyze_layer(V, Faces, h, h_prev=None):
    loops = section_loops_xy(V, Faces, h)
    if not loops:
        lv = volume_below(V, Faces, h)
        if h_prev is not None:
            lv = lv - volume_below(V, Faces, h_prev)
        return {"regions": 0, "holes": 0, "area": 0.0, "perimeter": 0.0,
                "centroid": [0.0, 0.0], "overhang_area": 0.0,
                "layer_volume": float(lv)}
    depth = _nesting_depth(loops)
    regions = sum(1 for d in depth if d % 2 == 0)
    holes = sum(1 for d in depth if d % 2 == 1)
    net = sum(_signed_area(L) for L in loops)
    area = abs(float(net))
    mx = F(0); my = F(0)
    for L in loops:
        m = len(L)
        for i in range(m):
            x1, y1 = L[i]
            x2, y2 = L[(i + 1) % m]
            cr = x1 * y2 - x2 * y1
            mx += (x1 + x2) * cr
            my += (y1 + y2) * cr
    cx = float(mx / (6 * net)) if net != 0 else 0.0
    cy = float(my / (6 * net)) if net != 0 else 0.0
    perim = 0.0
    for L in loops:
        m = len(L)
        for i in range(m):
            x1, y1 = L[i]
            x2, y2 = L[(i + 1) % m]
            perim += math.sqrt(float((x2 - x1) ** 2 + (y2 - y1) ** 2))
    if h_prev is None:
        oh = F(0)
        lv = volume_below(V, Faces, h)
    else:
        loops_prev = section_loops_xy(V, Faces, h_prev)
        oh = overhang_area(loops, loops_prev)
        lv = volume_below(V, Faces, h) - volume_below(V, Faces, h_prev)
    return {"regions": regions, "holes": holes, "area": area,
            "perimeter": perim, "centroid": [cx, cy],
            "overhang_area": float(oh), "layer_volume": float(lv)}


def analyze(V, Faces, heights):
    out = []
    for idx, h in enumerate(heights):
        hp = heights[idx - 1] if idx > 0 else None
        out.append(analyze_layer(V, Faces, h, hp))
    return out


# ------------------------------------------------------------------- mesh I/O
def write_obj(path, V, Faces):
    with open(path, "w") as f:
        f.write("# integer-coordinate closed triangle mesh\n")
        for (x, y, z) in V:
            f.write(f"v {x} {y} {z}\n")
        for (i, j, k) in Faces:
            f.write(f"f {i + 1} {j + 1} {k + 1}\n")


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


# ------------------------------------------------------- polycube + shearing
_FACE_SPECS = [
    ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
    ((1, 0, 0),  [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ((0, 1, 0),  [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
    ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ((0, 0, 1),  [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
]


def polycube_mesh(cells):
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


def shear(V, M):
    return [(M[0][0] * x + M[0][1] * y + M[0][2] * z,
             M[1][0] * x + M[1][1] * y + M[1][2] * z,
             M[2][0] * x + M[2][1] * y + M[2][2] * z) for (x, y, z) in V]


def check_manifold(V, Faces):
    dircount = defaultdict(int)
    for (i, j, k) in Faces:
        for (a, b) in ((i, j), (j, k), (k, i)):
            dircount[(a, b)] += 1
    for (a, b), c in dircount.items():
        if c != 1 or dircount.get((b, a), 0) != 1:
            return False
    return True


# ------------------------------------------------------------- hidden shapes
def _box(a, b, c):
    return {(x, y, z) for x in range(a) for y in range(b) for z in range(c)}


def shape_l_bracket():
    cells = set()
    for x in range(6):
        for y in range(6):
            for z in range(9):
                if x >= 3 and y >= 3:
                    continue
                cells.add((x, y, z))
    return cells


def shape_box_tunnel():
    """A block with a rectangular bore running along x: cross-sections form an
    annulus (one region, one hole) through the middle of the part."""
    cells = set()
    for x in range(8):
        for y in range(6):
            for z in range(6):
                if 2 <= y < 4 and 2 <= z < 4:
                    continue
                cells.add((x, y, z))
    return cells


def shape_twin_towers():
    """Two towers joined by a low bridge: layers split into two regions higher
    up, one region near the base."""
    cells = set()
    for x in range(8):           # base slab + bridge
        for y in range(4):
            for z in range(2):
                cells.add((x, y, z))
    for (x0, x1) in ((0, 3), (5, 8)):   # two towers
        for x in range(x0, x1):
            for y in range(4):
                for z in range(2, 8):
                    cells.add((x, y, z))
    return cells


# z' = 2x + y + z spreads vertices over z-levels and tilts every face, so an
# integer plane z'=h passes through few vertices and no whole face.
_SHEAR = [[1, 0, 0], [0, 1, 0], [2, 1, 1]]

# Heights pre-selected (offline) to be 'regular': no face lies in the plane and
# every on-plane contour vertex has in-degree == out-degree == 1, so the loop
# assembly is unambiguous, yet the planes still pass exactly through vertices.
_INSTANCES = [
    ("l_bracket", shape_l_bracket, [6, 9, 12, 15, 17, 19, 22]),
    ("box_tunnel", shape_box_tunnel, [4, 7, 10, 13, 16, 19, 22]),
    ("twin_towers", shape_twin_towers, [4, 7, 10, 13, 16, 19, 22]),
]


def make_instance(name):
    for nm, shapefn, heights in _INSTANCES:
        if nm != name:
            continue
        V, Faces = polycube_mesh(shapefn())
        V = shear(V, _SHEAR)
        assert check_manifold(V, Faces), f"{nm}: non-manifold mesh"
        expected = analyze(V, Faces, heights)
        return (nm, V, Faces, heights, expected)
    raise KeyError(name)


def make_instances():
    return [make_instance(nm) for nm, _, _ in _INSTANCES]
