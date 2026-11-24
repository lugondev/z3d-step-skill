"""Assemblies and ready-made templates (box, rover, rocket, building).

Every template is built ONLY from catalog parts placed by the grid rules, with an M3 screw
(Ø3.0 shank) on every connector hole. check_scene() then proves the template is buildable:
  * no two parts overlap (except the intended TPU tire press fit),
  * no screw touches material (it really goes through holes),
  * every screw grips at least two parts (it is not passing through a window / air).

Joint convention ("notched corner"): two tiles meeting at 90° do not overlap. Each tile's inner
face starts where the other tile's edge is, so both perimeter hole lines are 4 mm from the inside
corner. A C-90 bracket (slim alternating tabs) sits in that corner; its screws are 4 mm from each
face, so it fits on any cell along the edge.  Floors/roofs sit inside the wall ring.
Fasteners are drawn whole (button head + shank + hex nut) so the check also catches a nut or a head
that hits a neighbouring part.
"""
from __future__ import annotations

import itertools
import json
from collections import Counter

import cadquery as cq
import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf

import engine as E

M3_SHANK = 3.0
G = 8.0
T = 4.0
X, Y, Z = np.eye(3)


def _v(a):
    return np.asarray(a, dtype=float)


def frame(shape: cq.Shape, origin, ex, ey) -> cq.Shape:
    """rigid placement: local x -> ex, local y -> ey, local z -> ex × ey, local 0 -> origin."""
    ex, ey = _v(ex), _v(ey)
    ez = np.cross(ex, ey)
    o = _v(origin)
    t = gp_Trsf()
    t.SetValues(ex[0], ey[0], ez[0], o[0], ex[1], ey[1], ez[1], o[1], ex[2], ey[2], ez[2], o[2])
    return cq.Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, t, True).Shape())


def _pt(origin, ex, ey, p):
    ex, ey = _v(ex), _v(ey)
    return _v(origin) + p[0] * ex + p[1] * ey + p[2] * np.cross(ex, ey)


def _screw(p0, direction, length):
    d = _v(direction)
    return cq.Solid.makeCylinder(M3_SHANK / 2, length, cq.Vector(*map(float, p0)), cq.Vector(*map(float, d)))


HEAD_D, HEAD_H, NUT_AF, NUT_T, GAP = 5.7, 1.65, 5.5, 2.4, 0.05   # ISO 7380 button head, ISO 4032 nut


def _hex(c, d, vtx, af, h):
    """hex prism, base centred at c, axis d, one vertex along vtx."""
    d, vtx = _v(d), _v(vtx)
    w = np.cross(d, vtx)
    R = af / np.sqrt(3)
    pts = [c + R * (np.cos(a) * vtx + np.sin(a) * w) for a in np.radians(np.arange(0, 360, 60))]
    wire = cq.Wire.makePolygon([cq.Vector(*map(float, q)) for q in pts], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), cq.Vector(*map(float, d * h)))


def _bolt(c, d, grip, vtx, nut=True):
    """M3 bolt through a 4 mm tile into a part `grip` thick. c = point on the joint face on the
    screw axis, d = direction tile -> part, vtx = nut vertex direction. Returns (compound, spec)."""
    c, d = _v(c), _v(d)
    L = T + grip + (NUT_T if nut else 0)
    spec = f"M3×{next(x for x in (6, 8, 10, 12, 16, 20, 25, 30) if x >= L)}"
    head0 = c - (T + GAP + HEAD_H) * d
    parts = [cq.Solid.makeCylinder(HEAD_D / 2, HEAD_H, cq.Vector(*map(float, head0)), cq.Vector(*map(float, d))),
             _screw(c - (T + 0.5) * d, d, T + 0.5 + grip + (NUT_T + 0.6 if nut else 0))]
    if nut:
        parts.append(_hex(c + (grip + GAP) * d, d, vtx, NUT_AF, NUT_T))
    return cq.Compound.makeCompound(parts), spec


class Face:
    """a vertical wall plane, described by its INNER face: corner origin, tangent t, inward normal."""

    def __init__(self, origin, t, nin):
        self.o, self.t, self.n = _v(origin), _v(t), _v(nin)

    def at(self, u, z, depth=0.0):
        """point on the inner face at (u along t, height z), moved `depth` inward."""
        return self.o + u * self.t + z * Z + depth * self.n


def ring(nx, ny):
    """the 4 walls around a floor footprint [0, 8nx] × [0, 8ny] (inner faces)."""
    Xm, Ym = G * nx, G * ny
    return {"A1": Face((0, 0, 0), Y, X), "A2": Face((Xm, 0, 0), Y, -X),
            "B1": Face((0, 0, 0), X, Y), "B2": Face((0, Ym, 0), X, -Y)}


class Scene:
    def __init__(self, title="", ctx=None):
        self.ctx = ctx or E.Ctx()
        self.title = title
        self.items = []          # (name, shape, color, blank)
        self.screws = []         # (name, shape, spec)
        self.press = set()       # frozenset of item names allowed to overlap
        self.bom = Counter()     # (code, params_json) -> qty
        self._cache = {}
        self.conn_color = None   # template colour for connectors (None = part default)

    # ---------------------------------------------------------------- part cache
    def _body(self, code, **params):
        key = (code, json.dumps(params, sort_keys=True))
        if key not in self._cache:
            self._cache[key] = E.build_part(code, params, self.ctx)
        part = self._cache[key]
        self.bom[(code, json.dumps(part.params, sort_keys=True))] += 1
        return part

    def _add(self, name, body, origin, ex, ey, color=None):
        sh = frame(body.shape, origin, ex, ey)
        bl = frame(body.blank, origin, ex, ey) if body.blank is not None else sh
        self.items.append((name, sh, color or body.color, bl))
        return sh

    # ---------------------------------------------------------------- placement
    def slab(self, code, n, m, z0, name, x0=0.0, y0=0.0, color=None, **kw):
        """horizontal tile with its lower face at z0."""
        b = self._body(code, n=n, m=m, **kw).bodies[0]
        self._add(name, b, (x0, y0, z0), X, Y, color)

    def wall(self, face: Face, code, n, m, z0, name, u0=0.0, flip=False, color=None, **kw):
        """tile standing in the wall plane: n cells along t starting at u0, m cells up from z0.
        flip=True turns the tile over (mirror image of an asymmetric tile, e.g. T-A)."""
        b = self._body(code, n=n, m=m, **kw).bodies[0]
        ex = -face.t if flip else face.t
        start = face.o + (u0 + (n * G if flip else 0)) * face.t + z0 * Z
        ez = np.cross(ex, Z)
        origin = start - T * face.n if ez @ face.n > 0 else start   # occupy the 4 mm behind the inner face
        self._add(name, b, origin, ex, Z, color)

    def fin(self, face: Face, code, u0, z0, name, color=None, **kw):
        """tile standing perpendicular to the wall, outside, its plane at t ∈ [u0, u0+4]."""
        b = self._body(code, **kw).bodies[0]
        out = -face.n
        start = face.o + T * out + u0 * face.t + z0 * Z
        ez = np.cross(out, Z)
        origin = start if ez @ face.t > 0 else start + T * face.t
        self._add(name, b, origin, out, Z, color)

    def bar(self, p, run, n1, n2, nh, name="C-90"):
        """C-90 corner bar from corner point p along `run` (16·nh long). n1, n2 = directions from
        each tile's mating face into the bar. Screws go through each tile into the bar.
        The bar is chiral: which tile gets the screw at 4 mm vs 12 mm from p follows from the
        corner's handedness (turning the bar end for end gives the same order)."""
        p, run, n1, n2 = _v(p), _v(run), _v(n1), _v(n2)
        if np.allclose(np.cross(n1, n2), run):
            a, b = n1, n2
        elif np.allclose(np.cross(n2, n1), run):
            a, b = n2, n1
        else:
            raise ValueError("bar: n1, n2, run must be orthogonal")
        body = self._body("C-90", holes=nh).bodies[0]
        self._add(f"{name} #{len(self.items)}", body, p, run, a, self.conn_color)
        tab = self.ctx.S["tab_t"]
        for h in body.holes:
            c = _pt(p, run, a, h.c)
            d = b if h.axis == "z" else a
            bolt, spec = _bolt(c, d, tab, run)
            self.screws.append((f"{name} screw", bolt, spec))

    def splice(self, code, arm, center, arm_dir, inward, name):
        """flat splice plate on the inner face of coplanar tiles, centred on the seam point."""
        b = self._body(code, arm=arm).bodies[0]
        ex, ez = _v(arm_dir), _v(inward)
        ey = np.cross(ez, ex)
        self._add(name, b, center, ex, ey, self.conn_color)
        for h in b.holes:
            c = _pt(center, ex, ey, h.c)
            bolt, spec = _bolt(c, ez, T, ex)
            self.screws.append((f"{name} screw", bolt, spec))

    def wheel_unit(self, face: Face, u, z, name):
        """M-H hub on the OUTER face of a wall at (u, z) + W-40 wheel on its axle."""
        out = -face.n
        c = face.at(u, z) + T * out
        ex = face.t
        ey = np.cross(out, ex)
        hub = self._body("M-H").bodies[0]
        self._add(f"{name} hub", hub, c, ex, ey)
        rim, tire = self._body("W-40").bodies
        zr = 4 + 8 + 0.5
        self._add(f"{name} rim", rim, c + zr * out, ex, ey)
        self._add(f"{name} tire", tire, c + (zr + 1.2) * out, ex, ey)
        self.press.add(frozenset({f"{name} rim", f"{name} tire"}))
        for sx in (-1, 1):
            for sy in (-1, 1):
                p = c + G * (sx * ex + sy * ey)
                self.screws.append((f"{name} mount", _screw(p - 4.5 * out, out, 8.5), "M3×10"))
        self.screws.append((f"{name} axle", _screw(c - 4.5 * out, out, 29.5), "M3×30"))

    # ---------------------------------------------------------------- box helpers
    def edge_bar(self, face: Face, u0, z_face, up, nh=1):
        """bar along the wall/slab edge: `up`=+1 slab below (floor), -1 slab above (ceiling)."""
        self.bar(face.at(u0, z_face), face.t, face.n, up * Z, nh, "C-90")

    def corner_bars(self, nx, ny, z0, nh):
        Xm, Ym = G * nx, G * ny
        for (x, y, sx, sy) in ((0, 0, 1, 1), (Xm, 0, -1, 1), (0, Ym, 1, -1), (Xm, Ym, -1, -1)):
            self.bar((x, y, z0), Z, sx * X, sy * Y, nh, "C-90")

    def bom_list(self):
        out = [dict(code=c, params=json.loads(p), qty=q) for (c, p), q in sorted(self.bom.items())]
        hw = Counter(spec for _, _, spec in self.screws)
        return out, [dict(item=f"Vít {k} + đai ốc M3", qty=v) for k, v in sorted(hw.items())]


# ==================================================================== templates
def t_corner(ctx=None):
    """two 5×5 tiles at 90° joined by C-90 bars along the whole edge (cells 1-2 and 3-4)."""
    sc = Scene("Góc 90°", ctx)
    sc.slab("T-W", 5, 5, -T, "floor T-W")
    f = ring(5, 5)["A1"]
    sc.wall(f, "T-W", 5, 5, 0, "wall T-W")
    sc.edge_bar(f, 8, 0, +1)
    sc.edge_bar(f, 24, 0, +1)
    return sc


def t_splice(ctx=None):
    sc = Scene("Nối phẳng C-X", ctx)
    n = 4
    W = n * G
    for i, (sx, sy) in enumerate([(-1, -1), (0, -1), (-1, 0), (0, 0)]):
        sc.slab("T-W", n, n, 0, f"tile {i}", x0=sx * W, y0=sy * W)
    sc.splice("C-X", 2, (0, 0, 0), X, -Z, "C-X")
    return sc


def t_box(ctx=None, n=5):
    """closed cube: floor + roof + 4 walls, 12 C-90 bars (4 floor, 4 roof, 4 vertical corners)."""
    sc = Scene(f"Hộp {n}×{n}×{n}", ctx)
    H = n * G
    sc.slab("T-W", n, n, -T, "floor")
    sc.slab("T-W", n, n, H, "roof")
    for k, f in ring(n, n).items():
        sc.wall(f, "T-W", n, n, 0, f"wall {k}")
        sc.edge_bar(f, 16, 0, +1)
        sc.edge_bar(f, 16, H, -1)
    sc.corner_bars(n, n, 8, (n - 1) // 2)
    return sc


# template palette: one filament colour per part family, so a template reads as a designed object
WHITE, LIGHT, DARK, ACCENT = "#eeece6", "#c9ccd0", "#4a5059", "#f07c1e"


def t_rover(ctx=None):
    """4-wheel rover: chassis 14×6 cells (112×48), solid side walls carrying 4 hub+wheel units.
    Hubs sit 3 cells in from the ends so their Ø32 flange clears the corner-bracket screw heads."""
    sc = Scene("Rover", ctx)
    sc.conn_color = DARK
    nx, ny, nz = 14, 6, 3
    H = nz * G
    sc.slab("T-W", nx, ny, -T, "chassis floor", color=DARK)
    sc.slab("T-S", nx, ny, H, "deck T-S", color=ACCENT)
    R = ring(nx, ny)
    for k, f in R.items():
        side = k.startswith("B")
        sc.wall(f, "T-P" if side else "T-W", nx if side else ny, nz, 0, f"{'side' if side else 'end'} {k}",
                color=WHITE if side else LIGHT, **({"holes": "grid"} if side else {}))
        u0 = 48 if side else 16           # between the hub flanges (cells 6-7)
        sc.edge_bar(f, u0, 0, +1)
        sc.edge_bar(f, u0, H, -1)
    sc.corner_bars(nx, ny, 8, 1)
    for k in ("B1", "B2"):
        for u in (28, 84):
            sc.wheel_unit(R[k], u, 12, f"wheel {k}-{u}")
    return sc


def nose_faces(n):
    """4 upright planes through the centre of an n×n top, turned 90° apart (pinwheel): each holds a
    right-triangle T-A with its tall edge on the axis. Adjacent fins only touch, never overlap."""
    c = n * G / 2
    o = (c, c, 0)
    return [Face(o, Y, -X), Face(o, -X, -Y), Face(o, -Y, X), Face(o, X, Y)]


def t_rocket(ctx=None):
    """square rocket 6×6 cells: solid lower stage with 4 fins, X-braced upper stage, a top cap and a
    4-blade pinwheel nose that reads as a point from every side."""
    sc = Scene("Rocket", ctx)
    sc.conn_color = DARK
    n = 6
    W = n * G
    Htop = 80
    sc.slab("T-P", n, n, -T, "base plate", holes="grid", color=DARK)
    sc.slab("T-P", n, n, Htop, "top cap", holes="grid", color=DARK)
    R = ring(n, n)
    for k, f in R.items():
        sc.wall(f, "T-P", n, 5, 0, f"lower {k}", holes="grid", color=WHITE)
        sc.wall(f, "T-S", n, 5, 40, f"upper {k}", color=WHITE)
        # floor bracket: its outer screw head must stay clear of the fin (u 20-24) and fin bracket (u 24-32).
        # The wall screw sits 12 mm from the bracket start when nin × Z == t, else 4 mm -> pick the start cell.
        sc.edge_bar(f, 24 if np.allclose(np.cross(f.n, Z), f.t) else 8, 0, +1)   # wall screw at u=36 or u=12
        sc.edge_bar(f, 16, Htop, -1)                                              # cap joint
        sc.splice("C-I", 1, f.at(W / 2, 40), f.t, f.n, f"stage splice {k}")
        sc.fin(f, "T-A", 20, -8, f"fin {k}", n=4, m=5, k=1, color=ACCENT)
        sc.bar(f.at(24, 0) - T * f.n, Z, -f.n, f.t, 2, "fin C-90")    # u 24-32, outside
    sc.corner_bars(n, n, 8, 4)
    for i, f in enumerate(nose_faces(n)):
        sc.wall(f, "T-A", 3, 5, Htop + T, f"nose {i}", k=1, color=ACCENT)
        sc.edge_bar(f, 8, Htop + T, +1)                                           # outer 2 cells of the blade
    return sc


def t_building(ctx=None, stories=3):
    """3-storey tower 6×6 cells: window walls, dark floor slabs as bands, solid roof."""
    sc = Scene("Building", ctx)
    sc.conn_color = DARK
    n, hs = 6, 4
    Hs = hs * G
    R = ring(n, n)
    sc.slab("T-P", n, n, -T, "ground slab", holes="grid", color=DARK)
    for s in range(stories):
        z0 = s * (Hs + T)
        top = z0 + Hs
        last = s == stories - 1
        sc.slab("T-P", n, n, top, "roof" if last else f"slab {s + 1}", holes="grid", color=ACCENT if last else DARK)
        for k, f in R.items():
            code = "T-D" if s == 0 and k in ("A1", "A2") else "T-W"     # braced ground floor on two sides
            sc.wall(f, code, n, hs, z0, f"S{s + 1} {k} {code}", color=WHITE if code == "T-W" else LIGHT)
            sc.edge_bar(f, 24, z0, +1)      # floor joint (cells 3-4)
            sc.edge_bar(f, 8, top, -1)      # ceiling joint (cells 1-2) -> never shares a slab hole
        sc.corner_bars(n, n, z0 + 8, 1)
    return sc


TEMPLATES = {"rover": t_rover, "rocket": t_rocket, "building": t_building, "box": t_box}
DEMOS = {"corner": t_corner, "splice": t_splice}
SCENES = {**TEMPLATES, **DEMOS}


# ==================================================================== checks
def _bb_overlap(a, b, tol=0.01):
    A, B = a.BoundingBox(), b.BoundingBox()
    return (A.xmin < B.xmax - tol and B.xmin < A.xmax - tol and A.ymin < B.ymax - tol and B.ymin < A.ymax - tol
            and A.zmin < B.zmax - tol and B.zmin < A.zmax - tol)


def check_scene(sc: Scene, tol=1e-2):
    """buildability check. Screws are tested in one batched boolean per part (fast); a per-screw
    pass only runs on a part where the batch found a collision."""
    rows = []
    items = sc.items
    for (na, a, _, _), (nb, b, _, _) in itertools.combinations(items, 2):
        if frozenset({na, nb}) in sc.press or not _bb_overlap(a, b):
            continue
        v = a.intersect(b).Volume()
        if v > tol:
            rows.append(dict(kind="chồng hình", a=na, b=nb, overlap=round(v, 3)))
    grip = [0] * len(sc.screws)
    sbb = [s.BoundingBox() for _, s, _ in sc.screws]
    for na, a, _, blank in items:
        idx = [i for i, (_, s, _) in enumerate(sc.screws) if _bb_overlap(s, blank)]
        if not idx:
            continue
        comp = cq.Compound.makeCompound([sc.screws[i][1] for i in idx])
        if comp.intersect(a).Volume() > tol:
            for i in idx:
                v = sc.screws[i][1].intersect(a).Volume()
                if v > tol:
                    rows.append(dict(kind="vít chạm vật liệu", a=sc.screws[i][0], b=na, overlap=round(v, 3)))
        vol = Counter()
        for piece in comp.intersect(blank).Solids():
            c = piece.Center()
            for i in idx:
                bb = sbb[i]
                if bb.xmin - 1e-3 <= c.x <= bb.xmax + 1e-3 and bb.ymin - 1e-3 <= c.y <= bb.ymax + 1e-3 \
                        and bb.zmin - 1e-3 <= c.z <= bb.zmax + 1e-3:
                    vol[i] += piece.Volume()
                    break
        for i, v in vol.items():
            if v > 1.0:
                grip[i] += 1
    for i, g in enumerate(grip):
        if g < 2:
            rows.append(dict(kind="vít không bắt đủ 2 chi tiết", a=sc.screws[i][0], b=f"bắt {g}", overlap=0))
    return rows


if __name__ == "__main__":
    import sys
    import time
    for name in sys.argv[1:] or SCENES:
        t0 = time.time()
        sc = SCENES[name]()
        bad = check_scene(sc)
        parts, hw = sc.bom_list()
        print(f"{name:9} {'OK' if not bad else 'FAIL'} {len(sc.items)} parts, {len(sc.screws)} screws, "
              f"{time.time() - t0:.1f}s", bad[:6] if bad else "")
        print("   ", [(p['code'], p['params'], p['qty']) for p in parts], hw)
