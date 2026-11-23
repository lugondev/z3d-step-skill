"""Compare two models (STEP or STL, any mix): size, volume, and surface deviation.

Typical use: verify a parametric rebuild (STEP) against the original scan/STL.

Usage:
  compare.py reference.stl candidate.step [--samples 20000]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np  # noqa: E402

from _common import load_any_as_mesh  # noqa: E402


def one_way(a, b, n):
    import trimesh

    pts, _ = trimesh.sample.sample_surface(a, n)
    _, dist, _ = trimesh.proximity.closest_point(b, pts)
    return dist


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ref")
    ap.add_argument("cand")
    ap.add_argument("--samples", type=int, default=20000)
    a = ap.parse_args()
    A, B = load_any_as_mesh(a.ref, 0.01), load_any_as_mesh(a.cand, 0.01)
    print(f"{'':14s}{'reference':>28s}{'candidate':>28s}")
    print(f"{'extents':14s}{str(A.extents.round(3).tolist()):>28s}{str(B.extents.round(3).tolist()):>28s}")
    print(f"{'bbox min':14s}{str(A.bounds[0].round(3).tolist()):>28s}{str(B.bounds[0].round(3).tolist()):>28s}")
    print(f"{'volume':14s}{A.volume:>28.3f}{B.volume:>28.3f}")
    dv = (B.volume - A.volume) / A.volume * 100 if A.volume else float('nan')
    print(f"volume diff   : {dv:+.2f}%")
    d1, d2 = one_way(A, B, a.samples), one_way(B, A, a.samples)
    print(f"ref→cand dist : mean {d1.mean():.4f}  p95 {np.percentile(d1, 95):.4f}  max {d1.max():.4f}")
    print(f"cand→ref dist : mean {d2.mean():.4f}  p95 {np.percentile(d2, 95):.4f}  max {d2.max():.4f}")
    print(f"Hausdorff     : {max(d1.max(), d2.max()):.4f}")
    if max(d1.max(), d2.max()) > 0.01 * np.linalg.norm(A.extents):
        print("NOTE: max deviation > 1% of diagonal — features missing/misplaced or a pose mismatch "
              "(check bbox min: the rebuild may need translating).")


if __name__ == "__main__":
    main()
