"""Build a CadQuery model script into STEP (and optionally STL + preview PNG).

The model script must assign its final geometry to a variable named `result`
(cq.Workplane, cq.Shape, or cq.Assembly). Parameters can be overridden from the
command line with  -p name=value ; the script receives them in a dict OVERRIDES
(use  P.update(globals().get("OVERRIDES", {}))  as in the template).

Usage:
  build.py model.py -o part.step [--stl part.stl] [--preview part.png] [-p L=120 -p hole_d=8.5]
           [--params print_params.json]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import runpy
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import cadquery as cq  # noqa: E402

from _common import die, print_report, shape_report  # noqa: E402


def parse_val(s: str):
    try:
        return ast.literal_eval(s)
    except Exception:
        return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("-o", "--out", required=True, help="output .step path")
    ap.add_argument("--stl", help="also export STL here")
    ap.add_argument("--tol", type=float, default=0.01, help="STL linear deflection (mm)")
    ap.add_argument("--ang", type=float, default=0.1, help="STL angular deflection (rad)")
    ap.add_argument("--preview", help="also render a multi-view PNG here")
    ap.add_argument("-p", "--param", action="append", default=[], help="override name=value")
    ap.add_argument("--params", help="JSON file of overrides (e.g. from `z3d.sh tol table spec.yaml --out`); -p wins")
    a = ap.parse_args()

    overrides = {}
    if a.params:
        import json

        overrides.update(json.loads(pathlib.Path(a.params).read_text()))
    for kv in a.param:
        if "=" not in kv:
            die(f"bad -p '{kv}', expected name=value")
        k, v = kv.split("=", 1)
        overrides[k.strip()] = parse_val(v.strip())

    g = runpy.run_path(a.model, init_globals={"OVERRIDES": overrides, "cq": cq}, run_name="__z3d__")
    if "result" not in g:
        die("model script did not define `result`")
    res = g["result"]

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(res, cq.Assembly):
        try:
            res.export(str(out))  # cadquery >= 2.5
        except AttributeError:
            res.save(str(out))
        shape = res.toCompound()
    else:
        if isinstance(res, cq.Workplane):
            vals = [v for v in res.vals() if isinstance(v, cq.Shape)]
            if not vals:
                die("`result` Workplane holds no shapes")
            shape = vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
        elif isinstance(res, cq.Shape):
            shape = res
        else:
            die(f"unsupported result type {type(res)}")
        cq.exporters.export(shape, str(out), exportType="STEP")

    rep = shape_report(shape)
    print_report(rep, f"STEP written: {out}")
    if not rep["valid"]:
        print("WARNING: shape failed BRep validity check — fix before delivering.", file=sys.stderr)
    if rep["solids"] == 0:
        print("WARNING: no solids (surface/wire only?) — STL/3D-print will fail.", file=sys.stderr)

    if a.stl:
        shape.exportStl(a.stl, a.tol, a.ang)
        print(f"  STL written : {a.stl}")
    if a.preview:
        from render import render_shape

        render_shape(shape, a.preview, title=out.name)
        print(f"  preview     : {a.preview}")


if __name__ == "__main__":
    main()
