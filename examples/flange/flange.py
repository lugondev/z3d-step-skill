"""Hub flange FL-075 — parametric CadQuery model.

Source  : drawing.png (DWG FL-075, 1st angle, 1:1, S45C)
Units   : mm
Origin  : bore axis, bottom face of flange at Z=0; Z up
Assumed : edge break 0.5 applied to outer flange edges only (bore edges left sharp for the H7 fit)
"""
import cadquery as cq

P = dict(flange_d=100.0, flange_t=12.0, hub_d=50.0, total_h=30.0, bore_d=25.0,
         pcd=75.0, n_holes=6, hole_d=9.0, hole_start_deg=90.0, hub_chamfer=1.0, edge_break=0.5)
P.update(globals().get("OVERRIDES", {}))

# turned body: half profile on XZ (local x = radius, local y = Z), revolved about Z
r_f, r_h, r_b = P["flange_d"] / 2, P["hub_d"] / 2, P["bore_d"] / 2
prof = [(r_b, 0), (r_f, 0), (r_f, P["flange_t"]), (r_h, P["flange_t"]),
        (r_h, P["total_h"]), (r_b, P["total_h"])]
body = cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0))

# bolt holes on PCD
body = (body.faces("<Z").workplane(centerOption="CenterOfBoundBox")
        .polarArray(P["pcd"] / 2, -P["hole_start_deg"], 360, int(P["n_holes"]))
        .hole(P["hole_d"]))

# finishing
body = body.faces(">Z").edges(cq.selectors.RadiusNthSelector(1)).chamfer(P["hub_chamfer"])  # hub OD top edge
body = body.edges(cq.selectors.BoxSelector((-60, -60, -1), (60, 60, P["flange_t"] + 1))) \
           .edges("%CIRCLE").edges(cq.selectors.RadiusNthSelector(-1)).chamfer(P["edge_break"])  # flange OD edges

result = body
