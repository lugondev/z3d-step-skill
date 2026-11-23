"""FrameTile MK1 — parametric part engine (CadQuery / OpenCASCADE).

Every part is generated from ONE design standard (STANDARD below) so the whole set keeps
the same style and mates on the same 8 mm grid:

  * Grid 8 mm. Every screw axis passes through a CELL CENTER (4 + 8k mm from a part's datum
    edge), so any tile hole lines up with any connector hole.
  * Tiles: 4.0 mm thick, outline = "hole skeleton" (polygon through the hole centers) offset
    by 4 mm  ->  corner radius R4 concentric with the corner holes, and exactly 2.4 mm of wall
    between every perimeter hole and the edge. Rim 8 mm, inner window corners R2.
  * Fastener: M3, Ø3.2 clearance (nominal). Print model holes are compensated per profile.
  * Every part is modelled in its PRINT ORIENTATION (flat on the bed, Z up, no supports):
    horizontal holes are teardrops, nut slots open upward, bed edges get an elephant-foot chamfer.

Geometry conventions for 3D joints (see README):
  * C-90: a wall tile STANDS ON a floor tile (wall outer face flush with the floor end face).
    The connector sits in the inside corner; floor screw at 20 mm from the floor edge
    (cell #2), wall screw at 12 mm above the floor top (cell #1). Captive M3 nuts.
  * C-I / C-T / C-X: flat 4 mm splice plates for tiles butted edge-to-edge in one plane.
"""
from __future__ import annotations

import math
import pathlib
import sys
from dataclasses import dataclass, field

import cadquery as cq

ROOT = pathlib.Path(__file__).resolve().parent
SKILL_SCRIPTS = ROOT.parent / ".claude" / "skills" / "cad-step" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from tolerance import load_profiles, model_size  # noqa: E402

# --------------------------------------------------------------------------- standard
STANDARD = dict(
    grid=8.0,          # mm, module
    tile_t=4.0,        # tile thickness
    hole=3.2,          # M3 clearance (nominal, as printed)
    wall_min=2.4,      # min wall (6 perimeters @0.4)
    fillet_min=1.0,    # min corner radius in plan
    inner_r=2.0,       # window / inside corner radius
    rim=8.0,           # tile rim width (hole sits in the middle)
    brace=5.0,         # brace width of X / diagonal tiles
    conn=8.0,          # connector section (8 x 8)
    edge_round=0.6,    # cosmetic round on top edges
    ef_chamfer=0.4,    # elephant-foot chamfer on bed edges
    nut_af=5.5,        # M3 nut across flats (ISO 4032)
    nut_t=2.4,         # M3 nut thickness
    knuckle_gap=0.4,   # hinge axial clearance between knuckles
    tire_squeeze=0.4,  # TPU tire inner Ø smaller than rim seat Ø
)
DENSITY = {"fdm_pla": 1.24, "fdm_petg": 1.27, "fdm_abs": 1.04, "sla_resin": 1.15, "sls_pa12": 1.01, "mjf_pa12": 1.01}


class Ctx:
    """Holds the standard and (optionally) a print profile; turns nominal sizes into model sizes."""

    def __init__(self, std: dict | None = None, profile: str | None = None):
        self.S = dict(STANDARD)
        if std:
            self.S.update({k: float(v) for k, v in std.items() if k in STANDARD})
        self.profile_name = profile
        self.prof = load_profiles()[profile] if profile else None

    def m(self, size, feature):
        """model size for a feature that must print at `size` (nominal ctx: unchanged)."""
        if not self.prof:
            return size
        return round(model_size(size, feature, self.prof), 3)

    @property
    def hole_v(self):  # vertical M3 clearance hole
        return self.m(self.S["hole"], "hole")

    @property
    def hole_h(self):  # horizontal M3 clearance hole (teardrop)
        return self.m(self.S["hole"], "hole_h")

    @property
    def ef(self):
        return self.S["ef_chamfer"]


# --------------------------------------------------------------------------- data
@dataclass
class Hole:
    c: tuple          # a point on the axis
    axis: str         # 'x' | 'y' | 'z'
    d: float          # nominal Ø
    span: tuple       # (start, end) along the axis
    tag: str = ""


@dataclass
class Body:
    name: str
    shape: cq.Shape
    blank: cq.Shape | None = None       # body before holes/slots (for wall checks)
    holes: list = field(default_factory=list)
    color: str = "#d9d9d6"
    kind: str = "tile"
    notes: list = field(default_factory=list)


@dataclass
class Part:
    code: str
    title: str
    bodies: list
    params: dict
    bom: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    family: str = "tile"


GREY, ORANGE, BLACK = "#d9d9d6", "#f07c1e", "#2b2b2b"


# --------------------------------------------------------------------------- helpers
def _wp(shape):
    return cq.Workplane("XY").add(shape)


def _solid(wp):
    v = wp.val() if isinstance(wp, cq.Workplane) else wp
    if isinstance(v, cq.Compound):
        sols = v.Solids()
        if len(sols) == 1:
            return sols[0]
    return v


def _finish(wp, ctx: Ctx, notes: list, top=True):
    """Round top edges (cosmetic) + elephant-foot chamfer on the bed face. Never fails the part."""
    r = ctx.S["edge_round"]
    if top and r > 0:
        for rr in (r, r * 0.5):
            try:
                wp = wp.faces(">Z").edges().fillet(rr)
                break
            except Exception:
                continue
        else:
            notes.append("top edge round skipped (geometry too tight)")
    if ctx.ef > 0:
        try:
            wp = wp.faces("<Z").edges().chamfer(ctx.ef)
        except Exception:
            notes.append("elephant-foot chamfer skipped")
    return wp


def _round_poly(pts, r_convex, r_concave):
    """closed polygon wire with convex corners R=r_convex and concave corners R=r_concave."""
    w = cq.Wire.makePolygon([cq.Vector(x, y, 0) for x, y in pts], close=True)
    w = w.offset2D(r_concave, "arc")[0]
    w = w.offset2D(-(r_concave + r_convex), "intersection")[0]
    return w.offset2D(r_convex, "arc")[0]


def _round_wire(w, r_convex, r_concave):
    """round every corner of a closed planar wire: convex -> r_convex, concave -> r_concave."""
    w = w.offset2D(r_concave, "arc")[0]
    w = w.offset2D(-(r_concave + r_convex), "intersection")[0]
    return w.offset2D(r_convex, "arc")[0]


def _extrude_wire(w, h):
    return cq.Workplane("XY").add(cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), cq.Vector(0, 0, h)))


def _cyl_z(x, y, d, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(d / 2).extrude(z1 - z0)


def _teardrop(d, length, axis, c):
    """horizontal hole solid (tip +Z, flat top so the top wall keeps its size)."""
    plane = "XZ" if axis == "y" else "YZ"
    r = d / 2
    a = math.radians(45)
    tx, tz = r * math.cos(a), r * math.sin(a)
    apex = r / math.sin(a)
    xr = tx * (apex - r) / (apex - tz)
    wp = cq.Workplane(plane)
    circ = wp.circle(r).extrude(length / 2, both=True)
    tip = wp.polyline([(-tx, tz), (tx, tz), (xr, r), (-xr, r)]).close().extrude(length / 2, both=True)
    return circ.union(tip).translate(c)


def _seg_bar(p, q, w, h, z0=-1.0):
    (x1, y1), (x2, y2) = p, q
    L = math.hypot(x2 - x1, y2 - y1)
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return (cq.Workplane("XY").box(L + w, w, h, centered=(True, True, False))
            .rotate((0, 0, 0), (0, 0, 1), ang).translate(((x1 + x2) / 2, (y1 + y2) / 2, z0)))


def _rounded_cut(window, braces, r, notes):
    """window solid minus braces, every piece's vertical edges rounded (= R on the window corners)."""
    pieces = window
    for b in braces:
        pieces = pieces.cut(b)
    out = []
    for s in pieces.solids().vals():
        done = False
        for rr in (r, r * 0.75, r * 0.5):
            try:
                out.append(_wp(s).edges("|Z").fillet(rr).val())
                done = True
                if rr < r:
                    notes.append(f"window corner R reduced to {rr:g}")
                break
            except Exception:
                continue
        if not done:
            out.append(s)
            notes.append("a window corner could not be rounded")
    return out


def _perimeter_holes(skel, G, mode):
    """hole centers along axis-aligned skeleton edges at cell pitch; vertices always."""
    pts = []
    n = len(skel)
    step = {"corners": 0, "perimeter": 1, "alternate": 2}[mode]
    for i in range(n):
        a, b = skel[i], skel[(i + 1) % n]
        pts.append(a)
        if step == 0:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs(dx) > 1e-6 and abs(dy) > 1e-6:
            continue  # slanted edge: vertices only
        L = abs(dx) + abs(dy)
        k = int(round(L / G))
        for j in range(step, k, step):
            t = j / k
            pts.append((a[0] + dx * t, a[1] + dy * t))
    uniq = []
    for p in pts:
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-3 for q in uniq):
            uniq.append((round(p[0], 4), round(p[1], 4)))
    return uniq


# --------------------------------------------------------------------------- tiles
TILE_KINDS = {
    "T-S": ("Square", "x"),
    "T-W": ("Window", "window"),
    "T-D": ("Diagonal", "diag"),
    "T-P": ("Plate", "plate"),
    "T-A": ("Angle", "angle"),
    "T-U": ("Arch", "arch"),
}


def make_tile(code, ctx: Ctx, n=5, m=5, holes="perimeter", k=None, **_):
    S, G = ctx.S, ctx.S["grid"]
    T, rim, notes = S["tile_t"], S["rim"], []
    n, m = int(n), int(m)
    W, H = n * G, m * G
    h = G / 2
    style = TILE_KINDS[code][1]

    if style == "arch":
        return _make_arch(ctx, n, m, holes, notes)

    if n < 2 or m < 2:
        raise ValueError("tile needs n, m >= 2 cells")
    if style == "angle":
        k = int(k if k is not None else max(2, n // 2))
        if not 1 <= k < n:
            raise ValueError("T-A: top length k must be 1 <= k < n")
        skel = [(h, h), (W - h, h), (k * G - h, H - h), (h, H - h)]
        if k == 1:  # top edge collapses to a point -> right triangle
            skel = [(h, h), (W - h, h), (h, H - h)]
    else:
        skel = [(h, h), (W - h, h), (W - h, H - h), (h, H - h)]

    blank = cq.Workplane("XY").polyline(skel).close().offset2D(h).extrude(T)
    if style != "plate" and min(n, m) >= 3 or style == "angle":
        try:
            window = (cq.Workplane("XY").workplane(offset=-1).polyline(skel).close()
                      .offset2D(-(rim - h), "intersection").extrude(T + 2))
            bw = S["brace"]
            braces = []
            if style == "x":
                braces = [_seg_bar(skel[0], skel[2], bw, T + 4, -2), _seg_bar(skel[1], skel[3], bw, T + 4, -2)]
            elif style == "diag":
                braces = [_seg_bar(skel[0], skel[2], bw, T + 4, -2)]
            for piece in _rounded_cut(window, braces, S["inner_r"], notes):
                blank = blank.cut(_wp(piece))
        except Exception as e:  # window too small for this size
            notes.append(f"no window ({type(e).__name__}): tile too small, printed solid")
    elif style != "plate":
        notes.append("tile < 3 cells: printed solid (no room for a window)")

    if holes == "grid" and style == "plate":
        hole_pts = [(G * i + h, G * j + h) for i in range(n) for j in range(m)]
    else:
        hole_pts = _perimeter_holes(skel, G, "perimeter" if holes == "grid" else holes)
    body = _drill_z(blank, hole_pts, ctx, T)
    body = _finish(body, ctx, notes)
    hl = [Hole((x, y, 0), "z", S["hole"], (0, T), "tile") for x, y in hole_pts]
    name = f"{code}_{n}x{m}" + (f"_k{k}" if style == "angle" else "")
    return Body(name, _solid(body), _solid(blank), hl, GREY, "tile", notes)


def _drill_z(blank, pts, ctx, T):
    body = blank
    if pts:
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).pushPoints(pts).circle(ctx.hole_v / 2).extrude(T + 2))
    return body


def _make_arch(ctx, n, m, holes, notes):
    S, G = ctx.S, ctx.S["grid"]
    T, rim, h = S["tile_t"], S["rim"], G / 2
    W, H = n * G, m * G
    Ra = W / 2
    leg = H - Ra
    if n < 3 or leg < G:
        raise ValueError("T-U needs n >= 3 and m*8 - n*4 >= 8 (room for one leg hole)")
    outer = (cq.Workplane("XY").rect(W, leg, centered=False).extrude(T)
             .union(cq.Workplane("XY").center(W / 2, leg).circle(Ra).extrude(T))
             .intersect(cq.Workplane("XY").rect(W, H, centered=False).extrude(T)))
    outer = outer.edges("|Z").edges("<Y").fillet(h)
    inner = (cq.Workplane("XY").workplane(offset=-1).center(rim, -1).rect(W - 2 * rim, leg + 1, centered=False).extrude(T + 2)
             .union(cq.Workplane("XY").workplane(offset=-1).center(W / 2, leg).circle(Ra - rim).extrude(T + 2)))
    blank = outer.cut(inner)
    pts = [(h, h), (W - h, h)]
    step = {"corners": 0, "perimeter": 1, "alternate": 2}[holes]
    if step:
        y = h + step * G
        while y <= leg + 1e-6:
            pts += [(h, y), (W - h, y)]
            y += step * G
    if n % 2 == 1:
        pts.append((W / 2, H - h))  # apex is a cell center only for odd n
    body = _drill_z(blank, pts, ctx, T)
    body = _finish(body, ctx, notes)
    hl = [Hole((x, y, 0), "z", S["hole"], (0, T), "tile") for x, y in pts]
    return Body(f"T-U_{n}x{m}", _solid(body), _solid(blank), hl, GREY, "tile", notes)


# --------------------------------------------------------------------------- C-90 (3D corner)
def make_c90(ctx: Ctx, holes=1, **_):
    """L connector printed lying on its side. Print coords: arm along +X (floor screws, axis Y),
    post along +Y (wall screws, axis X), width 8 in Z.  Mount faces: arm y=0 (floor tile),
    post x=0 (wall tile)."""
    S, G = ctx.S, ctx.S["grid"]
    c, notes = S["conn"], []
    nh = int(holes)
    if nh < 1:
        raise ValueError("holes >= 1")
    Lp = 8 * nh + 16
    prof = [(0, 0), (Lp, 0), (Lp, c), (c, c), (c, Lp), (0, Lp)]
    blank = _extrude_wire(_round_poly(prof, S["fillet_min"], S["inner_r"]), c)
    zc = c / 2
    arm_x = [8 * i + 8 for i in range(1, nh + 1)]   # 16, 24, ...
    post_y = [8 * i + 4 for i in range(1, nh + 1)]  # 12, 20, ...
    body = blank
    hl = []
    af = ctx.m(S["nut_af"] + 0.1, "inner")
    nt = ctx.m(S["nut_t"] + 0.3, "inner")
    for x in arm_x:
        body = body.cut(_teardrop(ctx.hole_h, c * 2 + 2, "y", (x, c / 2, zc)))
        body = body.cut(_nut_slot(af, nt, "y", (x, c / 2 + 0.6, zc), c))
        hl.append(Hole((x, 0, zc), "y", S["hole"], (0, c), "floor screw"))
    for y in post_y:
        body = body.cut(_teardrop(ctx.hole_h, c * 2 + 2, "x", (c / 2, y, zc)))
        body = body.cut(_nut_slot(af, nt, "x", (c / 2 + 0.6, y, zc), c))
        hl.append(Hole((0, y, zc), "x", S["hole"], (0, c), "wall screw"))
    body = _finish(body, ctx, notes, top=False)
    floor = round(zc - S["nut_af"] / math.sqrt(3), 2)
    notes.append(f"captive-nut slots open on top; floor under nut tip {floor} mm (point only)")
    return Body(f"C-90_h{nh}", _solid(body), _solid(blank), hl, ORANGE, "connector", notes)


def _nut_slot(af, nt, axis, c, height):
    """drop-in hex nut slot: hex (flats vertical) + straight channel up through the top face."""
    R = af / math.sqrt(3)
    plane = "XZ" if axis == "y" else "YZ"
    ax = (0, 1, 0) if axis == "y" else (1, 0, 0)
    wp = cq.Workplane(plane)
    # polygon() puts a vertex on local +x; turn 90° about the slot axis -> vertices up/down,
    # flats vertical, so the channel width (= AF) stops the nut from turning
    hexs = wp.polygon(6, 2 * R).extrude(nt / 2, both=True).rotate((0, 0, 0), ax, 90)
    chan = wp.center(0, height / 2).rect(af, height).extrude(nt / 2, both=True)
    return hexs.union(chan).translate(c)


# --------------------------------------------------------------------------- splice plates
SPLICE_ARMS = {"C-I": ["+x", "-x"], "C-T": ["+x", "-x", "+y"], "C-X": ["+x", "-x", "+y", "-y"], "C-L": ["+x", "+y"]}


def make_splice(code, ctx: Ctx, arm=2, **_):
    """Flat plate centred on the point where tile seams meet (a cell corner). Arms are 2 cells wide
    and run along the seams; holes on every cell center inside the plate."""
    S, G = ctx.S, ctx.S["grid"]
    T, notes = S["tile_t"], []
    a = int(arm)
    if a < 1:
        raise ValueError("arm >= 1")
    La = G * (a + 1)
    rects = []
    for d in SPLICE_ARMS[code]:
        sgn = 1 if d[0] == "+" else -1
        if d[1] == "x":
            rects.append((0 if sgn > 0 else -La, -G, La, 2 * G))
        else:
            rects.append((-G, 0 if sgn > 0 else -La, 2 * G, La))
    rects.append((-G, -G, 2 * G, 2 * G))
    blank = None
    for x, y, w, hgt in rects:
        r = cq.Workplane("XY").center(x + w / 2, y + hgt / 2).rect(w, hgt).extrude(T)
        blank = r if blank is None else blank.union(r)
    outline = blank.faces("<Z").val().outerWire()
    blank = _extrude_wire(_round_wire(outline, G / 2, S["inner_r"]), T)
    pts = []
    for i in range(-a - 1, a + 1):
        for j in range(-a - 1, a + 1):
            x, y = G * i + G / 2, G * j + G / 2
            if any(rx + G / 2 - 1e-6 <= x <= rx + w - G / 2 + 1e-6 and ry + G / 2 - 1e-6 <= y <= ry + hh - G / 2 + 1e-6
                   for rx, ry, w, hh in rects):
                pts.append((x, y))
    body = _drill_z(blank, pts, ctx, T)
    body = _finish(body, ctx, notes)
    hl = [Hole((x, y, 0), "z", S["hole"], (0, T), "splice") for x, y in pts]
    return Body(f"{code}_a{a}", _solid(body), _solid(blank), hl, ORANGE, "connector", notes)


# --------------------------------------------------------------------------- H-180 hinge
def make_hinge(ctx: Ctx, n=3, **_):
    """Two leaves printed flat. Axis along X at y=0, z=4 (Ø8 knuckles, D-shaped = no support).
    Leaf A (y<0) has the outer knuckles, leaf B (y>0) the middle one. Pin: M3 screw + nyloc."""
    S, G = ctx.S, ctx.S["grid"]
    T = S["tile_t"]
    n = int(n)
    if n < 2:
        raise ValueError("n >= 2 cells")
    R = G / 2
    Lh = n * G
    s = Lh / 3
    g = S["knuckle_gap"]
    cgap = R + 0.5           # leaf plate starts here (clears the other leaf's knuckle)
    Wl = 2 * G
    bodies = []
    for side in ("A", "B"):
        sg = -1 if side == "A" else 1
        notes = []
        y0, y1 = sorted((sg * cgap, sg * (cgap + Wl)))
        plate = cq.Workplane("XY").center(Lh / 2, (y0 + y1) / 2).rect(Lh, y1 - y0).extrude(T)
        plate = plate.edges("|Z").edges("<Y" if sg < 0 else ">Y").fillet(R)
        segs = [(0, s - g / 2), (2 * s + g / 2, Lh)] if side == "A" else [(s + g / 2, 2 * s - g / 2)]
        blank = plate
        for xa, xb in segs:
            yk0, yk1 = sorted((sg * (cgap + 0.01), -sg * R))
            box = cq.Workplane("XY").center((xa + xb) / 2, (yk0 + yk1) / 2).rect(xb - xa, yk1 - yk0).extrude(R)
            cyl = cq.Workplane("YZ").workplane(offset=xa).center(0, R).circle(R).extrude(xb - xa)
            blank = blank.union(box).union(cyl)
        body = blank.cut(_teardrop(ctx.hole_h, Lh + 2, "x", (Lh / 2, 0, R)))
        pts = [(G * i + G / 2, sg * (cgap + G / 2 + G * j)) for i in range(n) for j in range(2)]
        body = _drill_z(body, pts, ctx, T)
        body = _finish(body, ctx, notes, top=False)
        hl = [Hole((x, y, 0), "z", S["hole"], (0, T), "leaf") for x, y in pts]
        for xa, xb in segs:
            hl.append(Hole((xa, 0, R), "x", S["hole"], (xa, xb), "pin"))
        bodies.append(Body(f"H-180{side}_{n}", _solid(body), _solid(blank), hl, ORANGE, "motion", notes))
    return bodies


# --------------------------------------------------------------------------- M-H hub
def make_hub(ctx: Ctx, boss_h=8, **_):
    """Flange Ø32 x4 on the bed, boss Ø12 on top. Center = a cell center; 4 mount holes on the
    diagonal cell centers (±8, ±8). Axle: M3 bolt from under the tile, nut captured in the boss top."""
    S, G = ctx.S, ctx.S["grid"]
    T, notes = S["tile_t"], []
    bh = float(boss_h)
    D, Db = 4 * G, 12.0
    blank = cq.Workplane("XY").circle(D / 2).extrude(T).union(cq.Workplane("XY").circle(Db / 2).extrude(T + bh))
    pts = [(sx * G, sy * G) for sx in (-1, 1) for sy in (-1, 1)]
    body = _drill_z(blank, pts + [(0, 0)], ctx, T + bh)
    af = ctx.m(S["nut_af"] + 0.1, "inner")
    dep = S["nut_t"] + 0.2
    body = body.cut(cq.Workplane("XY").workplane(offset=T + bh - dep).polygon(6, 2 * af / math.sqrt(3)).extrude(dep + 1))
    body = _finish(body, ctx, notes)
    hl = [Hole((x, y, 0), "z", S["hole"], (0, T), "mount") for x, y in pts]
    hl.append(Hole((0, 0, 0), "z", S["hole"], (0, T + bh), "axle"))
    return Body("M-H", _solid(body), _solid(blank), hl, ORANGE, "motion", notes)


# --------------------------------------------------------------------------- W-40 wheel
def make_wheel(ctx: Ctx, D=40, width=12, **_):
    """Rim (PLA, orange) + tire (TPU, black). Both print flat. Rim spins on the M3 axle (free fit)."""
    S = ctx.S
    D, Wd = float(D), float(width)
    wall = S["wall_min"]
    seat = D - 12.0                     # rim seat Ø = tire inner Ø (nominal)
    notes_r, notes_t = [], []
    # ---- rim
    ring = cq.Workplane("XY").circle(seat / 2).circle(seat / 2 - wall).extrude(Wd)
    lip = cq.Workplane("XY").circle(seat / 2 + 2).circle(seat / 2 - wall).extrude(1.2)
    hub = cq.Workplane("XY").circle(5).extrude(Wd)
    sp = None
    for ang in (45, 135):
        b = cq.Workplane("XY").box(seat - wall, 4, Wd * 0.75, centered=(True, True, False)).rotate((0, 0, 0), (0, 0, 1), ang)
        sp = b if sp is None else sp.union(b)
    rim_blank = ring.union(lip).union(hub).union(sp)
    bore_nom = 3.4
    bore = ctx.m(bore_nom, "hole")
    rim = rim_blank.cut(cq.Workplane("XY").workplane(offset=-1).circle(bore / 2).extrude(Wd + 2))
    rim = _finish(rim, ctx, notes_r, top=False)
    if ctx.prof:  # rim seat must print at nominal Ø
        notes_r.append("seat Ø compensated as outer feature")
    # ---- tire
    tid_nom = seat - S["tire_squeeze"]
    tid = ctx.m(tid_nom, "hole")
    tw = Wd - 1.2
    tire = cq.Workplane("XY").circle(D / 2).circle(tid / 2).extrude(tw)
    tire = tire.faces(">Z or <Z").edges(cq.selectors.RadiusNthSelector(1)).chamfer(1.0)
    gro = None
    for i in range(24):
        a = 360 / 24 * i
        b = (cq.Workplane("XY").box(2.0, 2.4, tw + 2, centered=(True, True, False)).translate((D / 2, 0, -1))
             .rotate((0, 0, 0), (0, 0, 1), a))
        gro = b if gro is None else gro.union(b)
    tire = tire.cut(gro)
    notes_t.append(f"TPU 95A; inner Ø {tid_nom:g} (−{S['tire_squeeze']:g} squeeze on Ø{seat:g} seat)")
    return [
        Body("W-40_rim", _solid(rim), _solid(rim_blank),
             [Hole((0, 0, 0), "z", bore_nom, (0, Wd), "axle (free)")], ORANGE, "motion", notes_r),
        Body("W-40_tire", _solid(tire), None, [], BLACK, "motion", notes_t),
    ]


# --------------------------------------------------------------------------- catalog
CATALOG = {
    "T-S": dict(title="Tile Square (X brace)", family="tile", params=dict(n=5, m=5, holes="perimeter")),
    "T-W": dict(title="Tile Window", family="tile", params=dict(n=5, m=5, holes="perimeter")),
    "T-D": dict(title="Tile Diagonal", family="tile", params=dict(n=5, m=5, holes="perimeter")),
    "T-A": dict(title="Tile Angle", family="tile", params=dict(n=5, m=5, k=2, holes="perimeter")),
    "T-U": dict(title="Tile Arch", family="tile", params=dict(n=5, m=6, holes="perimeter")),
    "T-P": dict(title="Tile Plate (solid)", family="tile", params=dict(n=5, m=5, holes="grid")),
    "C-90": dict(title="Corner 90°", family="connector", params=dict(holes=1)),
    "C-T": dict(title="T Joint (splice)", family="connector", params=dict(arm=2)),
    "C-X": dict(title="Cross (splice)", family="connector", params=dict(arm=2)),
    "C-I": dict(title="Inline (splice)", family="connector", params=dict(arm=2)),
    "C-L": dict(title="Flat L (splice)", family="connector", params=dict(arm=2)),
    "H-180": dict(title="Hinge 180°", family="motion", params=dict(n=3)),
    "M-H": dict(title="Hub", family="motion", params=dict(boss_h=8)),
    "W-40": dict(title="Wheel Ø40", family="motion", params=dict(D=40, width=12)),
}
PARAM_SPEC = {
    "n": dict(label="n (ô theo X)", type="int", min=2, max=40),
    "m": dict(label="m (ô theo Y)", type="int", min=2, max=40),
    "k": dict(label="k (ô cạnh trên)", type="int", min=1, max=39),
    "holes": dict(label="Lỗ viền", type="enum", options=["perimeter", "alternate", "corners", "grid"]),
    "arm": dict(label="Độ dài cánh (ô)", type="int", min=1, max=8),
    "boss_h": dict(label="Cao boss (mm)", type="float", min=4, max=24),
    "D": dict(label="Ø ngoài (mm)", type="float", min=32, max=120),
    "width": dict(label="Bề rộng (mm)", type="float", min=6, max=40),
}
PARAM_SPEC_BY_PART = {"C-90": {"holes": dict(label="Số lỗ mỗi cánh", type="int", min=1, max=6)},
                      "H-180": {"n": dict(label="Dài (ô)", type="int", min=2, max=12)}}

SCREWS = {"tile+splice": "M3×12", "tile+C-90": "M3×16", "hinge pin": "M3×{L}", "hub axle": "M3×{L}"}


def build_part(code: str, params: dict | None = None, ctx: Ctx | None = None) -> Part:
    ctx = ctx or Ctx()
    if code not in CATALOG:
        raise ValueError(f"unknown part {code}")
    p = dict(CATALOG[code]["params"])
    p.update({k: v for k, v in (params or {}).items() if k in p})
    fam = CATALOG[code]["family"]
    bom = []
    if code in TILE_KINDS:
        bodies = [make_tile(code, ctx, **p)]
        bom.append("Vít M3×12 + đai ốc (ghép splice C-I/C-T/C-X/C-L), M3×16 (ghép C-90)")
    elif code == "C-90":
        bodies = [make_c90(ctx, **p)]
        nh = int(p["holes"])
        bom.append(f"{2 * nh}× vít M3×16 + {2 * nh}× đai ốc M3 (nhét vào khe trên đỉnh)")
    elif code in SPLICE_ARMS:
        bodies = [make_splice(code, ctx, **p)]
        bom.append(f"{len(bodies[0].holes)}× vít M3×12 + đai ốc M3")
    elif code == "H-180":
        bodies = make_hinge(ctx, **p)
        L = int(p["n"]) * 8
        bom.append(f"1× vít chốt M3×{_screw_len(L + 2.4 + 1)} + đai ốc nyloc; {4 * int(p['n'])}× M3×12 bắt lá vào tile")
    elif code == "M-H":
        bodies = [make_hub(ctx, **p)]
        bom.append(f"4× M3×12 bắt tile; trục: M3×{_screw_len(4 + 4 + float(p['boss_h']) + float(CATALOG['W-40']['params']['width']) + 3)} + 2 đai ốc (1 nằm trong boss, 1 nyloc)")
    elif code == "W-40":
        bodies = make_wheel(ctx, **p)
        bom.append("Lốp in TPU 95A, vành in PLA/PETG; quay trơn trên trục M3 của M-H")
    return Part(code, CATALOG[code]["title"], bodies, p, bom, [], fam)


def _screw_len(L):
    for s in (6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50):
        if s >= L:
            return s
    return int(math.ceil(L / 5) * 5)


def layout(bodies, gap=6.0):
    """place several bodies side by side along X (for a combined STEP / viewer)."""
    out, x = [], 0.0
    for b in bodies:
        bb = b.shape.BoundingBox()
        out.append(b.shape.translate(cq.Vector(x - bb.xmin, -bb.ymin if len(bodies) > 1 else 0, 0)))
        x += bb.xlen + gap
    return out
