"""Convert STL (mesh) -> STEP (B-rep solid), "faceted" reverse conversion.

Each triangle becomes a planar face; faces are sewn into a closed shell and made
into a solid. With --unify (default on) coplanar triangles are merged, so flat
regions become single faces — prismatic parts come out clean, curved surfaces
stay faceted. For a true parametric reconstruction (real cylinders/fillets) use
analyze-mesh + rebuild in CadQuery (see SKILL.md "Mode B").

Usage:
  stl2step.py in.stl out.step [--no-unify] [--sew-tol 1e-3] [--max-faces 200000]
                              [--decimate N]
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import cadquery as cq  # noqa: E402
import numpy as np  # noqa: E402
from OCP.BRepBuilderAPI import (  # noqa: E402
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
)
from OCP.gp import gp_Pnt  # noqa: E402
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid  # noqa: E402
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain  # noqa: E402
from OCP.TopAbs import TopAbs_SHELL  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

from _common import die, load_mesh, print_report, shape_report  # noqa: E402


def mesh_to_shape(mesh, sew_tol: float, unify: bool):
    sew = BRepBuilderAPI_Sewing(sew_tol)
    V = mesh.vertices
    pts = [gp_Pnt(*map(float, v)) for v in V]
    bad = 0
    for tri in mesh.faces:
        poly = BRepBuilderAPI_MakePolygon(pts[tri[0]], pts[tri[1]], pts[tri[2]], True)
        if not poly.IsDone():
            bad += 1
            continue
        mf = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if mf.IsDone():
            sew.Add(mf.Face())
        else:
            bad += 1
    if bad:
        print(f"  skipped {bad} degenerate triangles")
    sew.Perform()
    sewed = sew.SewedShape()

    solids = []
    exp = TopExp_Explorer(sewed, TopAbs_SHELL)
    while exp.More():
        shell = TopoDS.Shell_s(exp.Current())
        ms = BRepBuilderAPI_MakeSolid(shell)
        if ms.IsDone():
            fix = ShapeFix_Solid(ms.Solid())
            fix.Perform()
            solids.append(cq.Shape.cast(fix.Solid()))
        exp.Next()

    if not solids:
        print("WARNING: no closed shell — exporting sewn surfaces (mesh not watertight).")
        shape = cq.Shape.cast(sewed)
    else:
        shape = solids[0] if len(solids) == 1 else cq.Compound.makeCompound(solids)

    if unify:
        u = ShapeUpgrade_UnifySameDomain(shape.wrapped, True, True, False)
        u.SetLinearTolerance(sew_tol)
        u.SetAngularTolerance(1e-4)
        u.Build()
        merged = cq.Shape.cast(u.Shape())
        if not merged.isValid():  # unify can leave bad tolerances/wires; heal them
            fx = ShapeFix_Shape(merged.wrapped)
            fx.Perform()
            merged = cq.Shape.cast(fx.Shape())
        if merged.isValid():
            shape = merged
        else:
            print("WARNING: face merging produced an invalid shape; keeping un-merged triangles.")
    return shape


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--no-unify", action="store_true")
    ap.add_argument("--sew-tol", type=float, default=None, help="default: 1e-5 * bbox diagonal")
    ap.add_argument("--max-faces", type=int, default=200_000)
    ap.add_argument("--decimate", type=int, default=0, help="simplify mesh to N faces first")
    a = ap.parse_args()

    mesh = load_mesh(a.inp)
    print(f"input {a.inp}: triangles={len(mesh.faces)} watertight={mesh.is_watertight} "
          f"volume={mesh.volume:.4f} extents={np.round(mesh.extents, 4).tolist()}")
    if not mesh.is_watertight:
        mesh.fill_holes()
        mesh.fix_normals()
        print(f"  repaired: watertight={mesh.is_watertight}")
    if a.decimate and len(mesh.faces) > a.decimate:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=a.decimate)
            print(f"  decimated to {len(mesh.faces)} triangles")
        except Exception as e:  # needs fast-simplification
            print(f"  decimation unavailable ({e}); pip install fast-simplification")
    if len(mesh.faces) > a.max_faces:
        die(f"{len(mesh.faces)} triangles > --max-faces {a.max_faces}; use --decimate or raise the limit")

    tol = a.sew_tol or max(1e-6, 1e-5 * float(np.linalg.norm(mesh.extents)))
    t0 = time.time()
    shape = mesh_to_shape(mesh, tol, not a.no_unify)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, str(out), exportType="STEP")
    rep = shape_report(shape)
    print_report(rep, f"STEP written: {out}  ({time.time() - t0:.1f}s)")
    if abs(rep["volume"] - mesh.volume) > 0.01 * abs(mesh.volume):
        print(f"WARNING: volume differs from mesh ({mesh.volume:.4f}) by >1% — check normals/holes.")


if __name__ == "__main__":
    main()
