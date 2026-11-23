"""<Part name> — parametric CadQuery model.

Source  : <drawing no. / photo / user spec>
Units   : mm
Origin  : <e.g. center of bottom face>;  Z up; front view looks along +Y
Assumed : <list every dimension you guessed, so the user can correct it>

Build:  z3d.sh build this_file.py -o out/part.step --stl out/part.stl --preview out/part.png
"""
import cadquery as cq

# ---- parameters (all driving dimensions live here) -------------------------
P = dict(
    L=80.0,          # overall length (X)
    W=50.0,          # overall width  (Y)
    T=10.0,          # plate thickness (Z)
    hole_d=6.6,      # through hole Ø (M6 clearance)
    hole_inset=8.0,  # hole center distance from edges
    fillet_r=3.0,    # vertical corner radius
    chamfer=0.5,     # top edge chamfer
)
P.update(globals().get("OVERRIDES", {}))  # allows  build.py -p L=120

# ---- base body ------------------------------------------------------------
body = (
    cq.Workplane("XY")
    .box(P["L"], P["W"], P["T"], centered=(True, True, False))
    .edges("|Z").fillet(P["fillet_r"])
)

# ---- features ---------------------------------------------------------------
dx, dy = P["L"] / 2 - P["hole_inset"], P["W"] / 2 - P["hole_inset"]
body = (
    body.faces(">Z").workplane()
    .rect(2 * dx, 2 * dy, forConstruction=True).vertices()
    .hole(P["hole_d"])
)

# ---- finishing (fillets/chamfers last: they are the most fragile ops) ------
body = body.faces(">Z").edges("not %CIRCLE").chamfer(P["chamfer"])

result = body
