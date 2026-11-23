"""Convert STEP -> STL.

Usage:
  step2stl.py in.step out.stl [--tol 0.01] [--ang 0.1] [--ascii] [--split]

--tol   linear deflection in mm (smaller = finer mesh, bigger file). 0.01 is print quality.
--ang   angular deflection in radians.
--split write one STL per solid (out_1.stl, out_2.stl, ...).
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _common import load_mesh, load_step, print_report, shape_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--tol", type=float, default=0.01)
    ap.add_argument("--ang", type=float, default=0.1)
    ap.add_argument("--ascii", action="store_true")
    ap.add_argument("--split", action="store_true")
    a = ap.parse_args()

    shape = load_step(a.inp)
    print_report(shape_report(shape), f"input {a.inp}")

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    targets = [(shape, out)]
    if a.split and len(shape.Solids()) > 1:
        targets = [(s, out.with_name(f"{out.stem}_{i + 1}{out.suffix}")) for i, s in enumerate(shape.Solids())]

    for s, p in targets:
        s.exportStl(str(p), a.tol, a.ang, a.ascii)
        m = load_mesh(p)
        print(f"STL written: {p}  triangles={len(m.faces)}  watertight={m.is_watertight}  "
              f"volume={m.volume:.4f}")


if __name__ == "__main__":
    main()
