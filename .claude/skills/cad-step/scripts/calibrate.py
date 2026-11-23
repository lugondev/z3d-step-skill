"""Printer calibration for tolerance compensation.

  calibrate.py make out_dir [--name my_printer]
      -> coupon.step/.stl  (print it with the settings you will use for real parts)
      -> measure.csv       (fill the 'measured' column with caliper readings)
  calibrate.py fit measure.csv --name my_printer [--base fdm_pla] [--desc "..."]
      -> fits comp[a,b] per feature + accuracy from residuals,
         saves profile into ~/.z3d-cad/print_profiles.json

Coupon (110 × 46 × 4 plate, print flat, Z up). measure.csv lists where each feature is:
  y=30 row : vertical holes Ø3, 5, 8, 10, 12, 16 (left → right)
  y=12 row : pins Ø3, 5, 8, 10 (8 high)
  right end: small wall with horizontal teardrop holes Ø5, 8; slots 4 and 8 wide
  plate outer size 110 × 46
Measure each hole/pin twice at 90° and enter the average.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np  # noqa: E402

from tolerance import USER_PROFILES, load_profiles  # noqa: E402

HOLES = [3, 5, 8, 10, 12, 16]
PINS = [3, 5, 8, 10]
HHOLES = [5, 8]
SLOTS = [4, 8]
L, W, T = 110.0, 46.0, 4.0


def make(out_dir: pathlib.Path):
    import cadquery as cq

    from printlib import teardrop_hole

    out_dir.mkdir(parents=True, exist_ok=True)
    plate = cq.Workplane("XY").box(L, W, T, centered=(False, False, False))
    xs = np.linspace(8, 8 + 15 * (len(HOLES) - 1), len(HOLES))
    rows = []
    for x, d in zip(xs, HOLES):
        plate = plate.cut(cq.Workplane("XY").center(x, 30).circle(d / 2).extrude(T))
        rows.append(("hole", d, f"vertical hole row (y=30), x={x:.0f}"))
    for x, d in zip(xs, PINS):
        plate = plate.union(cq.Workplane("XY", origin=(0, 0, T)).center(x, 12).circle(d / 2).extrude(8))
        rows.append(("shaft", d, f"pin row (y=12), x={x:.0f}"))
    # wall with horizontal holes (axis along Y), standing on the plate at the far right
    wx0 = 92.0
    wall = cq.Workplane("XY").box(16, 6, 22, centered=(False, False, False)).translate((wx0, 2, T))
    for z, d in zip((T + 6, T + 15), HHOLES):
        wall = wall.cut(teardrop_hole(d, 20, plane="XZ").translate((wx0 + 8, 5, z)))
        rows.append(("hole_h", d, f"horizontal hole in wall, z={z:.0f} (measure HORIZONTAL width)"))
    plate = plate.union(wall)
    # slots (inner width) near the right end, long along Y
    for cx, w in zip((96.0, 104.0), SLOTS):
        plate = plate.cut(cq.Workplane("XY").center(cx, 32).rect(w, 14).extrude(T))
        rows.append(("inner", w, f"slot centred x={cx:.0f}, y=32 (measure width along X)"))
    rows.append(("outer", L, "plate length X"))
    rows.append(("outer", W, "plate width Y"))
    shape = plate.val()
    cq.exporters.export(shape, str(out_dir / "coupon.step"))
    shape.exportStl(str(out_dir / "coupon.stl"), 0.005, 0.05)
    with open(out_dir / "measure.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["feature", "nominal", "measured", "where"])
        for feat, d, where in rows:
            w.writerow([feat, d, "", where])
    print(f"coupon: {out_dir / 'coupon.stl'}  (and .step)\nfill in: {out_dir / 'measure.csv'}")
    print("print flat, same material/slicer settings as real parts; turn OFF slicer XY/hole compensation "
          "(or keep it on for both calibration and production — just be consistent).")


def fit(csv_path, name, base, desc):
    rows = [r for r in csv.DictReader(open(csv_path)) if r["measured"].strip()]
    if not rows:
        sys.exit("no measurements filled in")
    profs = load_profiles()
    prof = json.loads(json.dumps(profs.get(base) or profs["fdm_pla"]))
    resid = []
    print(f"{'feature':8s} {'n':>3s} {'a (mm)':>8s} {'b':>8s}")
    for feat in ("hole", "hole_h", "shaft", "outer", "inner"):
        pts = [(float(r["nominal"]), float(r["measured"])) for r in rows if r["feature"] == feat]
        if not pts:
            continue
        x = np.array([p[0] for p in pts])
        err = np.array([p[1] - p[0] for p in pts])
        if len(set(x)) >= 3 and feat != "outer":
            b, a = np.polyfit(x, err, 1)
        else:
            a, b = float(err.mean()), 0.0
        prof["comp"][feat] = [round(float(a), 4), round(float(b), 5)]
        resid += list(err - (a + b * x))
        print(f"{feat:8s} {len(pts):3d} {a:+8.3f} {b:+8.4f}   errors: {np.round(err, 3).tolist()}")
    if len(resid) >= 4:
        sd = float(np.std(resid, ddof=1))
        prof["accuracy"] = [round(max(2 * sd, 0.02), 3), prof["accuracy"][1] / 2]
        print(f"residual σ = {sd:.3f} mm → accuracy ±{prof['accuracy'][0]} (+{prof['accuracy'][1]}·L)")
    prof["desc"] = desc or f"calibrated from {pathlib.Path(csv_path).name} (base {base})"
    USER_PROFILES.parent.mkdir(parents=True, exist_ok=True)
    user = json.loads(USER_PROFILES.read_text()) if USER_PROFILES.exists() else {}
    user[name] = prof
    USER_PROFILES.write_text(json.dumps(user, indent=2, ensure_ascii=False))
    print(f"saved profile '{name}' to {USER_PROFILES}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("make"); s.add_argument("out_dir")
    s = sp.add_parser("fit"); s.add_argument("csv"); s.add_argument("--name", required=True)
    s.add_argument("--base", default="fdm_pla"); s.add_argument("--desc")
    a = ap.parse_args()
    if a.cmd == "make":
        make(pathlib.Path(a.out_dir))
    else:
        fit(a.csv, a.name, a.base, a.desc)


if __name__ == "__main__":
    main()
