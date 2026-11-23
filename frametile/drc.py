"""Design-rule check (DRC) for FrameTile parts — every rule of the standard, measured on the
real geometry (not just the parameters)."""
from __future__ import annotations

import math

import cadquery as cq
import numpy as np

from engine import STANDARD, Body, Ctx, Part

AX = {"x": cq.Vector(1, 0, 0), "y": cq.Vector(0, 1, 0), "z": cq.Vector(0, 0, 1)}


def _annulus(h, r_in, r_out):
    a0, a1 = h.span
    L = a1 - a0
    base = {"x": "YZ", "y": "XZ", "z": "XY"}[h.axis]
    wp = cq.Workplane(base)
    ring = wp.circle(r_out).circle(r_in).extrude(L).val()
    # move ring so it starts at span[0] along the axis and is centred on the hole axis
    c = list(h.c)
    i = "xyz".index(h.axis)
    c[i] = a0
    if h.axis == "y":  # XZ workplane extrudes along -Y
        ring = ring.mirror("XZ")
    return ring.translate(cq.Vector(*c))


def wall_around(h, blank: cq.Shape, wall_min: float):
    """smallest wall (mm) around hole h inside the blank, searched to 0.05 mm, capped at wall_min."""
    r = h.d / 2

    def ok(t):
        if t <= 0:
            return True
        ann = _annulus(h, r + 0.01, r + t)
        lost = ann.cut(blank).Volume()
        return lost < 1e-3 * ann.Volume() + 1e-4

    if ok(wall_min - 0.02):
        return wall_min, True
    lo, hi = 0.0, wall_min - 0.02
    for _ in range(7):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return round(lo, 2), False


def hole_spacing(holes, wall_min):
    worst = None
    for i, a in enumerate(holes):
        for b in holes[i + 1:]:
            if a.axis != b.axis:
                continue
            k = "xyz".index(a.axis)
            if min(a.span[1], b.span[1]) <= max(a.span[0], b.span[0]):
                continue
            d = math.dist([v for j, v in enumerate(a.c) if j != k], [v for j, v in enumerate(b.c) if j != k])
            if d < 1e-6:
                continue
            web = d - (a.d + b.d) / 2
            if worst is None or web < worst:
                worst = web
    return worst


def printability(shape: cq.Shape):
    """bed contact, overhang (>45° from vertical, not on the bed) and bridge areas from the mesh."""
    verts, tris = shape.tessellate(0.02, 0.15)
    V = np.array([[p.x, p.y, p.z] for p in verts])
    F = np.array(tris)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a)
    area = np.linalg.norm(n, axis=1) / 2
    nz = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    zmin = V[:, 2].min()
    zc = (a[:, 2] + b[:, 2] + c[:, 2]) / 3
    down = nz < -math.cos(math.radians(44))  # overhang flatter than 45° from vertical (1° slack)
    on_bed = zc < zmin + 1e-3
    touches = np.minimum(np.minimum(a[:, 2], b[:, 2]), c[:, 2]) < zmin + 1e-3
    down &= ~(touches & (nz > -0.8))  # 45° elephant-foot chamfer facets start on the bed: self-supporting
    flat = nz < -0.999
    bed = float(area[down & on_bed].sum())
    bridge = float(area[down & flat & ~on_bed].sum())
    over = float(area[down & ~flat & ~on_bed].sum())
    return bed, bridge, over


def check_body(body: Body, part_code: str, ctx: Ctx | None = None):
    S = (ctx or Ctx()).S
    G, wall_min = S["grid"], S["wall_min"]
    rows = []

    def add(rule, ok, value, note=""):
        rows.append(dict(rule=rule, status="OK" if ok is True else ("WARN" if ok is None else "FAIL"), value=value, note=note))

    shp = body.shape
    add("Solid hợp lệ (BRep valid, 1 khối)", shp.isValid() and len(shp.Solids()) == 1,
        f"valid={shp.isValid()}, solids={len(shp.Solids())}")
    bb = shp.BoundingBox()
    if body.kind == "tile" or part_code in ("C-I", "C-T", "C-X", "C-L"):
        add("Độ dày tile = 4.0 mm", abs(bb.zlen - S["tile_t"]) < 1e-3, f"{bb.zlen:.2f} mm")
        on = all(abs(v - G * round(v / G)) < 0.05 for v in (bb.xlen, bb.ylen))
        add("Kích thước theo lưới 8 mm (L = 8×n)", on, f"{bb.xlen:.1f} × {bb.ylen:.1f} mm")
        off = [h for h in body.holes if h.axis == "z" and
               any(abs(((v - (bb.xmin if j == 0 else bb.ymin)) - G / 2) / G - round(((v - (bb.xmin if j == 0 else bb.ymin)) - G / 2) / G)) > 1e-3
                   for j, v in enumerate(h.c[:2]))]
        add("Tâm lỗ nằm trên tâm ô lưới (4 + 8k)", not off, f"{len(body.holes) - len(off)}/{len(body.holes)} lỗ")
    if body.holes:
        dmin = min(h.d for h in body.holes)
        add("Lỗ M3 clearance Ø3.2 (danh nghĩa)", all(abs(h.d - S["hole"]) < 1e-6 or "free" in h.tag for h in body.holes),
            f"Ø{dmin:g}" + (" (trục quay: lắp lỏng Ø3.4)" if any("free" in h.tag for h in body.holes) else ""))
    if body.blank is not None and body.holes:
        worst, bad = wall_min, []
        # fast path: all annuli in one boolean; per-hole search only if something is lost
        anns = [_annulus(h, h.d / 2 + 0.01, h.d / 2 + wall_min - 0.02) for h in body.holes]
        lost = cq.Compound.makeCompound(anns).cut(body.blank).Volume()
        if lost > 1e-3 * sum(a.Volume() for a in anns) + 1e-4:
            for h in body.holes:
                w, ok = wall_around(h, body.blank, wall_min)
                worst = min(worst, w)
                if not ok:
                    bad.append(f"{h.tag}@({h.c[0]:.0f},{h.c[1]:.0f},{h.c[2]:.0f}) {w:.2f}")
        add(f"Thành quanh lỗ ≥ {wall_min:g} mm", not bad, f"min {worst:.2f} mm", "; ".join(bad[:4]))
        web = hole_spacing(body.holes, wall_min)
        if web is not None:
            add(f"Vách giữa 2 lỗ ≥ {wall_min:g} mm", web >= wall_min - 1e-6, f"{web:.2f} mm")
    outer_r = S["fillet_min"] if part_code == "C-90" else G / 2
    add(f"Bo góc ≥ R{STANDARD['fillet_min']:g}", min(S["fillet_min"], S["inner_r"]) >= STANDARD["fillet_min"],
        f"ngoài R{outer_r:g}, trong R{S['inner_r']:g}" if part_code not in ("M-H", "W-40") else "chi tiết tròn")
    bed, bridge, over = printability(shp)
    add("In phẳng: mặt tiếp xúc bàn in", bed > 20, f"{bed:.0f} mm²")
    add("Không cần support (overhang > 45°)", over < 2.0, f"{over:.1f} mm²",
        "cầu (bridge) ngang: %.0f mm²" % bridge if bridge > 0.5 else "")
    if "nut tip" in " ".join(body.notes):
        add("Đáy khe đai ốc", None, "≈0.8 mm tại đỉnh lục giác", "chỉ là 1 điểm; in ≥ 4 lớp đáy")
    return rows


def check_part(part: Part, ctx: Ctx | None = None):
    out = {}
    for b in part.bodies:
        out[b.name] = check_body(b, part.code, ctx)
    return out


def summary(rep):
    st = [r["status"] for rows in rep.values() for r in rows]
    return "FAIL" if "FAIL" in st else ("WARN" if "WARN" in st else "PASS")
