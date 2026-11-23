"""Render a STEP/STL into a multi-view PNG (iso + front + top + right, orthographic)
so the model can be checked visually (e.g. compared against a drawing or photo).

Views follow the usual Z-up convention:
  front = looking along +Y (from -Y), top = looking down -Z, right = looking along -X (from +X).

Usage:
  render.py part.step -o part.png [--views iso,front,top,right] [--size 1400]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection  # noqa: E402

# (elev, azim, view-direction vector pointing from camera into the scene)
VIEWS = {
    "iso": (30, -60, None),
    "iso2": (30, 120, None),
    "front": (0, -90, None),
    "back": (0, 90, None),
    "top": (90, -90, None),
    "bottom": (-90, -90, None),
    "right": (0, 0, None),
    "left": (0, 180, None),
}


def cam_dir(elev, azim):
    e, a = np.radians(elev), np.radians(azim)
    return np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])


def _edges_of_shape(shape, n=72):
    segs = []
    for e in shape.Edges():
        try:
            if e.geomType() == "LINE":
                pts = [e.startPoint(), e.endPoint()]
            else:
                pts = e.positions(np.linspace(0, 1, n).tolist())
            P = np.array([[p.x, p.y, p.z] for p in pts])
            segs.extend(zip(P[:-1], P[1:]))
        except Exception:
            pass
    return segs


def _draw(ax, V, F, segs, view, title):
    elev, azim, _ = VIEWS[view]
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    c = cam_dir(elev, azim)
    light = c + np.array([0.3, -0.2, 0.5])
    light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.clip(np.abs(n @ light), 0, 1)
    base = np.array([0.55, 0.68, 0.85])
    colors = np.c_[np.outer(shade, base), np.ones(len(shade))]
    pc = Poly3DCollection(tri, facecolors=colors, edgecolors="none", linewidths=0)
    ax.add_collection3d(pc)
    # edges are drawn without hidden-line removal: in ortho views they act like a
    # drawing's visible+hidden lines; in iso views they'd just clutter, so skip them.
    if segs and not view.startswith("iso"):
        ax.add_collection3d(Line3DCollection(segs, colors="k", linewidths=0.6))
    lo, hi = V.min(0), V.max(0)
    ctr, span = (lo + hi) / 2, (hi - lo).max() / 2 * 1.05
    ax.set_xlim(ctr[0] - span, ctr[0] + span)
    ax.set_ylim(ctr[1] - span, ctr[1] + span)
    ax.set_zlim(ctr[2] - span, ctr[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.set_proj_type("ortho")
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.tick_params(labelsize=6)


def render_arrays(V, F, segs, out, views=("iso", "front", "top", "right"), size=1400, title=""):
    k = len(views)
    cols = 2 if k > 1 else 1
    rows = int(np.ceil(k / cols))
    fig = plt.figure(figsize=(size / 100, size / 100 * rows / cols))
    for i, v in enumerate(views):
        ax = fig.add_subplot(rows, cols, i + 1, projection="3d")
        _draw(ax, V, F, segs, v, v)
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out, dpi=100)
    plt.close(fig)


def render_shape(shape, out, views=("iso", "front", "top", "right"), size=1400, title="", tol=None):
    bb = shape.BoundingBox()
    tol = tol or max(bb.DiagonalLength * 2e-3, 1e-3)
    verts, tris = shape.tessellate(tol, 0.3)
    V = np.array([[p.x, p.y, p.z] for p in verts])
    F = np.array(tris)
    render_arrays(V, F, _edges_of_shape(shape), out, views, size, title)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--views", default="iso,front,top,right", help=",".join(VIEWS))
    ap.add_argument("--size", type=int, default=1400)
    a = ap.parse_args()
    views = [v.strip() for v in a.views.split(",") if v.strip()]
    for v in views:
        if v not in VIEWS:
            sys.exit(f"unknown view {v}; choose from {list(VIEWS)}")
    ext = pathlib.Path(a.path).suffix.lower()
    if ext in (".step", ".stp"):
        from _common import load_step

        render_shape(load_step(a.path), a.out, views, a.size, pathlib.Path(a.path).name)
    else:
        from _common import load_mesh

        m = load_mesh(a.path)
        if len(m.faces) > 80_000:
            try:
                m = m.simplify_quadric_decimation(face_count=80_000)
            except Exception:
                pass
        # draw only "feature" edges (sharp creases), like a CAD edge display
        fe = m.vertices[m.face_adjacency_edges[m.face_adjacency_angles > np.radians(30)]] \
            if len(m.face_adjacency) else []
        render_arrays(np.asarray(m.vertices), np.asarray(m.faces), list(fe), a.out, views, a.size,
                      pathlib.Path(a.path).name)
    print(f"preview written: {a.out}")


if __name__ == "__main__":
    main()
