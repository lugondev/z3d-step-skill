"""Helpers for 3D-printable CadQuery models. Importable from any model built with build.py:

    from printlib import PrintProfile, teardrop_hole, nut_trap, INSERT, SELF_TAP, NUT

    pp = PrintProfile("fdm_pla")             # or the profile named in your spec
    d_model = pp.hole(8.0, fit="slide")      # model Ø for a hole that slides on a Ø8 rod
    d_pin   = pp.shaft(5.0, fit="press")     # printed pin pressed into a Ø5 (bought) hole
    w_model = pp.size(20.0, "inner")         # slot that must print 20.0 wide
"""
from __future__ import annotations

import math

import cadquery as cq

from tolerance import get_profile, model_size

# heat-set insert holes (Ø hole, min depth) — typical for CNC-Kitchen/Ruthex style inserts.
# Always check the insert vendor's datasheet; these are starting points.
INSERT = {"M2": (3.2, 4.0), "M2.5": (3.6, 5.0), "M3": (4.0, 6.0), "M4": (5.6, 9.0), "M5": (6.4, 10.5), "M6": (8.0, 13.0)}
# pilot hole for screws threading directly into plastic (thread-forming), Ø
SELF_TAP = {"M2": 1.7, "M2.5": 2.1, "M3": 2.5, "M4": 3.4, "M5": 4.2, "M6": 5.0}
# hex nuts ISO 4032: (across flats, thickness)
NUT = {"M2": (4.0, 1.6), "M2.5": (5.0, 2.0), "M3": (5.5, 2.4), "M4": (7.0, 3.2), "M5": (8.0, 4.7), "M6": (10.0, 5.2), "M8": (13.0, 6.8)}
# clearance holes ISO 273 (fine, medium)
CLEARANCE = {"M2": (2.2, 2.4), "M2.5": (2.7, 2.9), "M3": (3.2, 3.4), "M4": (4.3, 4.5), "M5": (5.3, 5.5), "M6": (6.4, 6.6), "M8": (8.4, 9.0)}


class PrintProfile:
    def __init__(self, name="fdm_pla"):
        self.name = name
        self.p = get_profile(name)

    def clearance(self, fit):
        return self.p["fits"][fit]

    def size(self, target, feature):
        """Model size so the printed feature measures `target` (feature: hole|hole_h|shaft|outer|inner)."""
        return model_size(target, feature, self.p)

    def hole(self, nominal, fit="slide", horizontal=False, mate="bought"):
        """Model Ø of a printed hole that mates with a nominal-Ø shaft (bought: rod/bearing/screw)."""
        c = self.clearance(fit)
        tgt = nominal + (c if mate == "bought" else c / 2)
        return self.size(tgt, "hole_h" if horizontal else "hole")

    def shaft(self, nominal, fit="slide", mate="bought"):
        """Model Ø of a printed pin/boss going into a nominal-Ø hole (bought = metal/bearing bore)."""
        c = self.clearance(fit)
        tgt = nominal - (c if mate == "bought" else c / 2)
        return self.size(tgt, "shaft")

    def clearance_hole(self, screw="M3", grade="medium"):
        return self.size(CLEARANCE[screw][1 if grade == "medium" else 0], "hole")

    def insert_hole(self, screw="M3"):
        d, depth = INSERT[screw]
        return d, depth  # inserts are melted in — use the vendor Ø as modelled, no compensation

    def nut_trap_af(self, screw="M3", fit="snug"):
        return NUT[screw][0] + self.clearance(fit)

    @property
    def elephant_foot(self):
        return self.p.get("elephant_foot_chamfer", 0.0)


def teardrop_hole(d, length, plane="XZ", angle=45.0, flat_top=False):
    """Solid to CUT for a horizontal hole that prints without support.

    Built centred on the plane origin, extruded symmetrically by `length` along the plane normal.
    For plane="XZ" the hole axis is Y and the tip points +Z (up, the build direction).
    flat_top=True truncates the tip at the circle's top (bridge) — keeps the vertical size = d.
    """
    r = d / 2
    a = math.radians(angle)
    tx, tz = r * math.cos(a), r * math.sin(a)
    apex = r / math.sin(a)
    wp = cq.Workplane(plane)
    circ = wp.circle(r).extrude(length / 2, both=True)
    if flat_top:
        xr = tx * (apex - r) / (apex - tz)  # where the tangent lines cross z = r
        pts = [(-tx, tz), (tx, tz), (xr, r), (-xr, r)]
    else:
        pts = [(-tx, tz), (tx, tz), (0, apex)]
    tip = wp.polyline(pts).close().extrude(length / 2, both=True)
    return circ.union(tip)


def nut_trap(screw="M3", depth=None, fit="snug", pp: PrintProfile | None = None):
    """Hexagonal pocket solid (to cut), centred on origin, from Z=0 up to `depth`."""
    pp = pp or PrintProfile()
    af = pp.nut_trap_af(screw, fit)
    depth = depth or NUT[screw][1] + 0.2
    return cq.Workplane("XY").polygon(6, af / math.cos(math.pi / 6)).extrude(depth)
