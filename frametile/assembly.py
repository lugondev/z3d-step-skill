"""Demo assemblies that prove the standard: parts placed by the grid rules, M3 screws inserted on
every connector hole axis, then checked for interference (screw vs. part, part vs. part)."""
from __future__ import annotations

import itertools

import cadquery as cq

import engine as E

M3_SHANK = 3.0


def _screw(p0, axis, length):
    d = {"x": "YZ", "y": "XZ", "z": "XY"}[axis]
    s = cq.Workplane(d).circle(M3_SHANK / 2).extrude(length).val()
    if axis == "y":
        s = s.mirror("XZ")
    return s.translate(cq.Vector(*p0))


def scene_corner(ctx=None, n=5):
    """floor tile + wall tile standing on it, joined by C-90s on cells j = 0, 2, 4."""
    ctx = ctx or E.Ctx()
    G = ctx.S["grid"]
    floor = E.make_tile("T-W", ctx, n=n, m=n).shape.translate(cq.Vector(0, 0, -4))
    # wall: tile (u,v,w) -> (x=w, y=u, z=v)
    wall = E.make_tile("T-W", ctx, n=n, m=n).shape
    wall = wall.rotate(cq.Vector(), cq.Vector(1, 0, 0), 90).rotate(cq.Vector(), cq.Vector(0, 0, 1), 90)
    items = [("floor T-W", floor, E.GREY), ("wall T-W", wall, E.GREY)]
    screws = []
    c90 = E.make_c90(ctx)
    for j in range(0, n, 2):
        # print (x,y,z) -> asm (x+4, -z + 8j+8, y)   (rotation about X, +90°)
        s = c90.shape.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90).translate(cq.Vector(4, G * j + G, 0))
        items.append((f"C-90 #{j}", s, E.ORANGE))
        yc = G * j + G / 2
        screws.append(("floor screw", _screw((20, yc, -4 - 0.5), "z", 4 + 8 + 0.5)))
        screws.append(("wall screw", _screw((-0.5, yc, 12), "x", 4 + 8 + 0.5)))
    return items, screws


def scene_splice(ctx=None, n=4):
    """four tiles meeting at one point, C-X splice under the joint."""
    ctx = ctx or E.Ctx()
    G = ctx.S["grid"]
    W = n * G
    items, screws = [], []
    for i, (sx, sy) in enumerate([(-1, -1), (0, -1), (-1, 0), (0, 0)]):
        t = E.make_tile("T-W", ctx, n=n, m=n).shape.translate(cq.Vector(sx * W, sy * W, 0))
        items.append((f"tile {i}", t, E.GREY))
    cx = E.make_splice("C-X", ctx, arm=2)
    items.append(("C-X", cx.shape.translate(cq.Vector(0, 0, -4)), E.ORANGE))
    for h in cx.holes:
        screws.append(("splice screw", _screw((h.c[0], h.c[1], -4.5), "z", 9)))
    return items, screws


def scene_wheel(ctx=None):
    """tile + M-H hub + W-40 wheel on the hub's M3 axle."""
    ctx = ctx or E.Ctx()
    G = ctx.S["grid"]
    tile = E.make_tile("T-P", ctx, n=5, m=5, holes="grid").shape.translate(cq.Vector(-20, -20, -4))  # center = cell center
    hub = E.make_hub(ctx)
    rim, tire = E.make_wheel(ctx)
    z = 4 + 8 + 0.5
    items = [("tile T-P", tile, E.GREY), ("M-H", hub.shape, E.ORANGE),
             ("W-40 rim", rim.shape.translate(cq.Vector(0, 0, z)), E.ORANGE),
             ("W-40 tire", tire.shape.translate(cq.Vector(0, 0, z + 1.2)), E.BLACK)]
    screws = [("axle", _screw((0, 0, -4.5), "z", 4 + 12 + 12 + 1))]
    for sx in (-1, 1):
        for sy in (-1, 1):
            screws.append(("mount", _screw((sx * G, sy * G, -4.5), "z", 8.5)))
    return items, screws


SCENES = {"corner": scene_corner, "splice": scene_splice, "wheel": scene_wheel}


PRESS_FITS = {frozenset({"W-40 rim", "W-40 tire"})}  # intended interference (TPU tire squeeze)


def check_scene(items, screws, tol=1e-2):
    rows = []
    for (na, a, _), (nb, b, _) in itertools.combinations(items, 2):
        if frozenset({na, nb}) in PRESS_FITS:
            continue
        v = a.intersect(b).Volume()
        if v > tol:
            rows.append(dict(a=na, b=nb, overlap=round(v, 3)))
    for ns, s in screws:
        for na, a, _ in items:
            v = s.intersect(a).Volume()
            if v > tol:
                rows.append(dict(a=ns, b=na, overlap=round(v, 3)))
    return rows


if __name__ == "__main__":
    for name, fn in SCENES.items():
        items, screws = fn()
        bad = check_scene(items, screws)
        print(name, "OK" if not bad else bad, f"({len(items)} parts, {len(screws)} screws)")
