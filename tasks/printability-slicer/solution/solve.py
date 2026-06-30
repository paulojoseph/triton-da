"""Reference solution for printability-slicer.

Reads /app/data/mesh.obj and /app/data/heights.json, computes the per-layer
slice report with exact rational arithmetic (fractions.Fraction) so that slice
planes passing through vertices and edges are handled without any tolerance, and
writes /app/result.json.
"""
import json
import math
from fractions import Fraction as F
from collections import defaultdict

DATA = "/app/data"
RESULT = "/app/result.json"


# ----------------------------------------------------------------- mesh I/O
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


# ------------------------------------------------------------- vector helpers
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def smul(s, a):
    return (s * a[0], s * a[1], s * a[2])


def side(n, d, p):
    return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] - d


def edge_cross(P, Q, sP, sQ):
    t = F(sP, sP - sQ)
    return (P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1]),
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
            cen = (F(p[0] + q[0] + r[0], 3), F(p[1] + q[1] + r[1], 3),
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


# --------------------------------------------------------------- 2D analysis
def section_loops_xy(V, Faces, h):
    n = (0, 0, 1)
    segs = []
    for i, j, k in Faces:
        _, seg = clip_triangle((V[i], V[j], V[k]), n, h, keep_negative=True)
        segs.extend(seg)
    loops3 = [L for L in assemble_loops(segs) if len(L) >= 3]
    return [[(p[0], p[1]) for p in L] for L in loops3]


def signed_area(poly):
    s = F(0)
    m = len(poly)
    for i in range(m):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % m]
        s += x1 * y2 - x2 * y1
    return s / 2


def point_in_poly(pt, poly):
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


def region_intervals(loops, xm):
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


def all_edges(loops):
    E = []
    for L in loops:
        m = len(L)
        for i in range(m):
            E.append((L[i], L[(i + 1) % m]))
    return E


def x_events(loopsA, loopsB):
    xs = set()
    for L in (loopsA + loopsB):
        for (x, y) in L:
            xs.add(x)
    EA, EB = all_edges(loopsA), all_edges(loopsB)
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


def measure_in_A_not_B(ysA, ysB):
    def intervals(ys):
        return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]
    total = F(0)
    for (a0, a1) in intervals(ysA):
        length = a1 - a0
        for (b0, b1) in intervals(ysB):
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                length -= (hi - lo)
        total += length
    return total


def overhang_area(loops_i, loops_prev):
    if not loops_i:
        return F(0)
    if not loops_prev:
        return sum(signed_area(L) for L in loops_i)
    xs = x_events(loops_i, loops_prev)
    acc = F(0)
    for a in range(len(xs) - 1):
        x0, x1 = xs[a], xs[a + 1]
        if x1 == x0:
            continue
        xm = (x0 + x1) / 2
        acc += (x1 - x0) * measure_in_A_not_B(
            region_intervals(loops_i, xm), region_intervals(loops_prev, xm))
    return acc


def analyze_layer(V, Faces, h, h_prev):
    loops = section_loops_xy(V, Faces, h)
    vb = volume_side(V, Faces, (0, 0, 1), h, True)
    if h_prev is None:
        lv = vb
    else:
        lv = vb - volume_side(V, Faces, (0, 0, 1), h_prev, True)
    if not loops:
        return {"regions": 0, "holes": 0, "area": 0.0, "perimeter": 0.0,
                "centroid": [0.0, 0.0], "overhang_area": 0.0,
                "layer_volume": float(lv)}
    reps = [L[0] for L in loops]
    regions = holes = 0
    for i in range(len(loops)):
        d = sum(1 for j, M in enumerate(loops)
                if i != j and point_in_poly(reps[i], M))
        if d % 2 == 0:
            regions += 1
        else:
            holes += 1
    net = sum(signed_area(L) for L in loops)
    area = abs(float(net))
    mx = my = F(0)
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
    else:
        oh = overhang_area(loops, section_loops_xy(V, Faces, h_prev))
    return {"regions": regions, "holes": holes, "area": area,
            "perimeter": perim, "centroid": [cx, cy],
            "overhang_area": float(oh), "layer_volume": float(lv)}


def main():
    V, Faces = read_obj(f"{DATA}/mesh.obj")
    with open(f"{DATA}/heights.json") as f:
        heights = json.load(f)
    out = []
    for idx, h in enumerate(heights):
        hp = heights[idx - 1] if idx > 0 else None
        out.append(analyze_layer(V, Faces, h, hp))
    with open(RESULT, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
