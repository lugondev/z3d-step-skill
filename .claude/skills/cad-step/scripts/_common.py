"""Shared helpers for the cad-step scripts (loading STEP/STL, shape stats)."""
from __future__ import annotations

import pathlib
import sys

import cadquery as cq
import numpy as np


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_step(path: str) -> cq.Shape:
    """Load a STEP file and return a single Shape (Compound if several solids)."""
    wp = cq.importers.importStep(str(path))
    shapes = [v for v in wp.vals() if isinstance(v, cq.Shape)]
    if not shapes:
        die(f"no geometry found in {path}")
    return shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)


def load_mesh(path: str):
    import trimesh

    m = trimesh.load(str(path), force="mesh", process=True)
    if m.is_empty:
        die(f"empty mesh: {path}")
    return m


def shape_to_mesh(shape: cq.Shape, tol: float = 0.05, ang: float = 0.2):
    """Tessellate a BRep shape into a trimesh.Trimesh."""
    import trimesh

    verts, tris = shape.tessellate(tol, ang)
    v = np.array([[p.x, p.y, p.z] for p in verts], dtype=float)
    f = np.array(tris, dtype=np.int64)
    return trimesh.Trimesh(v, f, process=True)


def load_any_as_mesh(path: str, tol: float = 0.05):
    ext = pathlib.Path(path).suffix.lower()
    if ext in (".step", ".stp"):
        return shape_to_mesh(load_step(path), tol)
    return load_mesh(path)


def bbox_str(bb) -> str:
    return (f"X[{bb.xmin:.3f}, {bb.xmax:.3f}] Y[{bb.ymin:.3f}, {bb.ymax:.3f}] "
            f"Z[{bb.zmin:.3f}, {bb.zmax:.3f}]  size {bb.xlen:.3f} x {bb.ylen:.3f} x {bb.zlen:.3f}")


def shape_report(shape: cq.Shape) -> dict:
    bb = shape.BoundingBox()
    solids = shape.Solids()
    rep = {
        "valid": bool(shape.isValid()),
        "solids": len(solids),
        "shells": len(shape.Shells()),
        "faces": len(shape.Faces()),
        "edges": len(shape.Edges()),
        "volume": float(shape.Volume()),
        "area": float(shape.Area()),
        "bbox": bbox_str(bb),
        "size": [bb.xlen, bb.ylen, bb.zlen],
    }
    types: dict[str, int] = {}
    for f in shape.Faces():
        t = f.geomType()
        types[t] = types.get(t, 0) + 1
    rep["face_types"] = types
    return rep


def print_report(rep: dict, title: str = ""):
    if title:
        print(f"== {title} ==")
    for k, v in rep.items():
        if isinstance(v, float):
            v = f"{v:.4f}"
        print(f"  {k:12s}: {v}")
