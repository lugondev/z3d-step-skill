"""Inspect a STEP or STL file: validity, size, volume, face types, holes/cylinders.

Usage:
  inspect_model.py file.step|file.stl [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _common import load_mesh, load_step, print_report, shape_report  # noqa: E402


def cylinders(shape):
    """Group cylindrical faces by (radius, axis direction, axis location)."""
    groups = {}
    for f in shape.Faces():
        if f.geomType() != "CYLINDER":
            continue
        surf = f._geomAdaptor()
        cyl = surf.Cylinder()
        r = round(cyl.Radius(), 4)
        ax = cyl.Axis()
        d = ax.Direction()
        p = ax.Location()
        import numpy as np

        dv = np.array([d.X(), d.Y(), d.Z()])
        if dv[np.argmax(np.abs(dv))] < 0:  # canonical direction so ±axis faces group together
            dv = -dv
        dirv = tuple(round(float(c), 3) + 0.0 for c in dv)
        # project location onto the plane normal to the axis so coaxial faces group together
        pv = np.array([p.X(), p.Y(), p.Z()])
        pv = pv - pv.dot(dv) * dv
        key = (r, dirv, tuple(np.round(pv, 3)))
        bb = f.BoundingBox()
        g = groups.setdefault(key, {"diameter": round(2 * r, 4), "axis": dirv,
                                    "center": [round(float(x), 3) + 0.0 for x in pv], "faces": 0, "span": [1e9, -1e9]})
        g["faces"] += 1
        # length along axis from bbox projection
        lo = float(min(bb.xmin * dv[0] + bb.ymin * dv[1] + bb.zmin * dv[2], bb.xmax * dv[0] + bb.ymax * dv[1] + bb.zmax * dv[2]))
        hi = float(max(bb.xmin * dv[0] + bb.ymin * dv[1] + bb.zmin * dv[2], bb.xmax * dv[0] + bb.ymax * dv[1] + bb.zmax * dv[2]))
        g["span"] = [round(min(g["span"][0], lo), 3), round(max(g["span"][1], hi), 3)]
    return sorted(groups.values(), key=lambda g: -g["diameter"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ext = pathlib.Path(a.path).suffix.lower()

    if ext in (".step", ".stp"):
        shape = load_step(a.path)
        rep = shape_report(shape)
        rep["cylinders"] = cylinders(shape)
        if a.json:
            print(json.dumps(rep, indent=2))
            return
        cyl = rep.pop("cylinders")
        print_report(rep, a.path)
        if cyl:
            print("  cylindrical features (diameter, axis, center⊥axis, span along axis):")
            for c in cyl:
                print(f"    Ø{c['diameter']:<9} axis={c['axis']} center={c['center']} span={c['span']} faces={c['faces']}")
    else:
        m = load_mesh(a.path)
        rep = {
            "triangles": len(m.faces), "vertices": len(m.vertices),
            "watertight": bool(m.is_watertight), "winding_consistent": bool(m.is_winding_consistent),
            "volume": float(m.volume), "area": float(m.area),
            "bbox_min": m.bounds[0].round(4).tolist(), "bbox_max": m.bounds[1].round(4).tolist(),
            "extents": m.extents.round(4).tolist(), "bodies": len(m.split(only_watertight=False)),
        }
        if a.json:
            print(json.dumps(rep, indent=2))
        else:
            print_report(rep, a.path)
            e = max(m.extents)
            hint = "mm" if 5 < e < 2000 else ("m? (very small — maybe meters or inches)" if e <= 5 else "µm/odd scale?")
            print(f"  unit guess  : {hint}")


if __name__ == "__main__":
    main()
