"""Analyze a mesh (STL/OBJ/...) to recover design intent for parametric rebuild.

Reports:
  * bounding box, volume, principal axes (is the part axis-aligned?)
  * dominant planes: normal + offset + area (step heights, wall faces)
  * cross-sections along an axis at several levels: each closed loop with
    area, bbox, and a circle fit (diameter + center) -> holes, bosses, shafts
  * a rotational-symmetry hint (is it a turned/revolved part?)

Usage:
  mesh_analyze.py part.stl [--axis z] [--levels 7] [--at 2.5,10] [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np  # noqa: E402

from _common import load_any_as_mesh  # noqa: E402

AX = {"x": 0, "y": 1, "z": 2}


def fit_circle(pts2):
    x, y = pts2[:, 0], pts2[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    b = x ** 2 + y ** 2
    (cx, cy, c), *_ = np.linalg.lstsq(A, b, rcond=None)
    r = float(np.sqrt(max(c + cx ** 2 + cy ** 2, 0)))
    res = np.abs(np.hypot(x - cx, y - cy) - r)
    return float(cx), float(cy), r, float(res.max() / r if r > 0 else 1)


def poly_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def dominant_planes(m, top=25):
    n = m.face_normals
    d = np.einsum("ij,ij->i", n, m.triangles[:, 0])
    scale = max(m.extents)
    key_n = np.round(n, 3)
    key_d = np.round(d / (scale * 1e-4)) * (scale * 1e-4)
    keys = np.c_[key_n, key_d]
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    areas = np.bincount(inv.ravel(), weights=m.area_faces)
    order = np.argsort(-areas)[:top]
    out = []
    for i in order:
        if areas[i] < 1e-3 * m.area:
            break
        nn = uniq[i, :3]
        out.append({"normal": nn.tolist(), "offset": round(float(uniq[i, 3]), 4),
                    "area": round(float(areas[i]), 3)})
    return out


def sections(m, axis, levels):
    ai = AX[axis]
    normal = np.zeros(3)
    normal[ai] = 1
    res = []
    for h in levels:
        origin = np.zeros(3)
        origin[ai] = h
        sec = m.section(plane_origin=origin, plane_normal=normal)
        if sec is None:
            res.append({"level": round(float(h), 4), "loops": []})
            continue
        loops = []
        for poly in sec.discrete:
            p3 = np.asarray(poly)
            others = [i for i in range(3) if i != ai]
            p2 = p3[:, others]
            if len(p2) < 4:
                continue
            area = poly_area(p2)
            cx, cy, r, rel = fit_circle(p2)
            entry = {"area": round(abs(area), 3),
                     "bbox": [p2.min(0).round(3).tolist(), p2.max(0).round(3).tolist()],
                     "coords": "".join("xyz"[i] for i in others)}
            if rel < 0.02:
                entry["circle"] = {"diameter": round(2 * r, 4), "center": [round(cx, 4), round(cy, 4)],
                                   "max_rel_err": round(rel, 4)}
            loops.append(entry)
        loops.sort(key=lambda e: -e["area"])
        # biggest loop = outer boundary, ones inside it = holes (heuristic)
        if loops:
            loops[0]["role"] = "outer"
            for e in loops[1:]:
                e["role"] = "inner/hole or separate island"
        res.append({"level": round(float(h), 4), "loops": loops})
    return res


def revolve_hint(m):
    """Check if sections perpendicular to the principal axis are concentric circles."""
    hints = {}
    for axis in "xyz":
        ai = AX[axis]
        lo, hi = m.bounds[0][ai], m.bounds[1][ai]
        lv = np.linspace(lo, hi, 7)[1:-1]
        secs = sections(m, axis, lv)
        ok = [all("circle" in l for l in s["loops"]) and s["loops"] for s in secs]
        hints[axis] = sum(bool(o) for o in ok) / len(ok)
    return hints


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--axis", default="z", choices=list("xyz"))
    ap.add_argument("--levels", type=int, default=7)
    ap.add_argument("--at", help="explicit comma-separated section levels")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    m = load_any_as_mesh(a.path)
    ai = AX[a.axis]
    lo, hi = m.bounds[0][ai], m.bounds[1][ai]
    if a.at:
        lv = [float(x) for x in a.at.split(",")]
    else:
        eps = (hi - lo) * 1e-3
        lv = np.linspace(lo + eps, hi - eps, a.levels).tolist()

    inertia_axes = m.principal_inertia_vectors
    report = {
        "file": a.path,
        "triangles": len(m.faces),
        "watertight": bool(m.is_watertight),
        "volume": round(float(m.volume), 4),
        "bbox_min": m.bounds[0].round(4).tolist(),
        "bbox_max": m.bounds[1].round(4).tolist(),
        "extents": m.extents.round(4).tolist(),
        "centroid": m.centroid.round(4).tolist(),
        "principal_axes": np.round(inertia_axes, 3).tolist(),
        "axis_aligned": bool(np.all(np.isclose(np.abs(inertia_axes).max(1), 1, atol=0.02))),
        "revolve_score_by_axis": revolve_hint(m),
        "dominant_planes": dominant_planes(m),
        "sections_axis": a.axis,
        "sections": sections(m, a.axis, lv),
    }
    if a.json:
        print(json.dumps(report, indent=1))
        return

    print(f"== mesh analysis: {a.path} ==")
    for k in ("triangles", "watertight", "volume", "bbox_min", "bbox_max", "extents", "centroid",
              "axis_aligned", "revolve_score_by_axis"):
        print(f"  {k:22s}: {report[k]}")
    print("  dominant planes (normal, offset = n·p, area):")
    for p in report["dominant_planes"]:
        print(f"    n={p['normal']}  d={p['offset']}  A={p['area']}")
    print(f"  sections along {a.axis}:")
    for s in report["sections"]:
        print(f"   @ {a.axis}={s['level']}: {len(s['loops'])} loop(s)")
        for l in s["loops"]:
            c = l.get("circle")
            cs = f" CIRCLE Ø{c['diameter']} at {l['coords']}={c['center']}" if c else ""
            print(f"      {l['role']:<30} area={l['area']:<10} bbox={l['bbox']}{cs}")


if __name__ == "__main__":
    main()
