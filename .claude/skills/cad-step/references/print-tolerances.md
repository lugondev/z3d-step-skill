# Tolerances for 3D-printed parts

## Contents
1. Why printed parts need compensation  2. The calculation model  3. Workflow with `z3d.sh tol`
4. Translating drawing tolerances  5. Print-native fits  6. Fasteners in plastic
7. Orientation & process effects  8. Stack-ups  9. Calibration  10. Reporting

## 1. Why
A printer does not reproduce CAD geometry exactly, and the error is systematic by feature type:
- **Holes come out small** (FDM: −0.1…−0.3 mm on Ø): extrusion width bulges inward, polygonal
  STL facets cut the circle, and the first layers squish (elephant foot).
- **Horizontal holes** (axis parallel to the bed) are worse: the top sags (bridging) → smaller
  and egg-shaped vertically. Teardrop/flat-top shapes fix the sag.
- **Pins and outer sizes come out slightly big** (+0.05…+0.1).
- **Heights are quantized** to the layer height and the first layer is squashed.
- Materials shrink (ABS/ASA ~0.5–0.7 %, PETG ~0.3 %, PLA ~0.2 %).
So the CAD model for a print is not the drawing's nominal: it is the size that *prints* to the
required size. The drawing stays the source of truth; the model gets compensated values.

## 2. The calculation model (what `tolerance.py` does)
For each dimension with feature type *f* (hole, hole_h, shaft, outer, inner, z):
1. **Target** = middle of the tolerance zone (nominal + (lower + upper)/2). Aiming at the middle
   gives the most margin both ways. For ISO codes (H7, g6…) the limits come from ISO 286; for
   untoleranced dimensions from the general tolerance (ISO 2768-m by default, or the title block's).
2. **Model size** solves `printed = model + a_f + b_f·model` for the target, using the profile's
   `comp[f] = [a, b]`, then removes material shrink (`xy_scale_pct`) if set.
3. **Verdict** compares the tolerance band with the process scatter `±(a + b·L)`:
   - band ≥ 2×scatter → **OK**: print as modelled.
   - scatter ≤ band < 2×scatter → **MARGINAL**: calibrate, test-print that feature first.
   - band < scatter → **POST-PROCESS**: the print can't hold it. Holes are printed undersize by
     `post_process_stock` and drilled/reamed; pins printed oversize and sanded/turned. Or the
     tolerance is relaxed / a metal insert or bushing is used — suggest that to the user.
   ISO precision fits (IT6–IT8, 10–40 µm) are almost always POST-PROCESS on FDM (±0.1–0.2 mm).
4. **Z dims**: not compensated, but reported as the nearest layer multiple; if that falls
   outside the tolerance, change the dimension or the layer height.

## 3. Workflow
```bash
Z3D=.claude/skills/cad-step/scripts/z3d.sh
$Z3D tol profiles                           # pick the process; default fdm_pla
$Z3D tol iso 25H7                           # ISO limits
$Z3D tol fit 25 H7/g6 -P fdm_pla            # fit analysis + printability
$Z3D tol comp "25H7" hole -P fdm_pla        # one dimension → model size + verdict
$Z3D tol pfit 8 slide --mate bought         # design a fit with a Ø8 steel rod
$Z3D tol stack +50±0.2 -20±0.1 -29.5±0.1 -P fdm_pla   # gap stack-up
$Z3D tol table spec.yaml --out print_params.json        # all params at once (markdown table)
$Z3D build part.py -o part.step --params print_params.json
```
In model code, `from printlib import PrintProfile, teardrop_hole, nut_trap, INSERT, SELF_TAP`
(works for any script run by `z3d.sh build`).

Keep **two parameter sets** clear: the spec's `value` = drawing nominal; `print_params.json`
= compensated model values. Name the STEP accordingly (`part_print_fdm_pla.step`) so nobody
mistakes the compensated model for the nominal design. Deliver the nominal STEP too when the
user may machine or re-print on a different process.

## 4. Translating drawing tolerances
| Drawing says | Feature | What to do |
|---|---|---|
| Ø25 H7 bore | hole | POST-PROCESS on FDM/SLS (ream). On SLA often MARGINAL. Ask what mates with it: if it's a bearing/rod, a print-native press/slide fit (§5) is usually what the user really wants. |
| Ø8 g6 pin | shaft | print oversize + sand, or replace with a steel dowel pressed into a printed hole |
| 40 ±0.1 | outer/inner | FDM MARGINAL → calibrate; SLA OK |
| 40 (no tol, ISO 2768-m ±0.3) | outer | OK, compensate |
| 4× Ø6.6 THRU (clearance) | hole | clearance holes are forgiving: compensate to land at nominal–+0.2 |
| M6 tapped | — | don't print fine threads: insert (heat-set) or tap a drilled hole (`SELF_TAP`) |
| Flatness / position GD&T | — | record; note warping risk on large flat FDM parts (brim, enclosure, PETG/ASA) |
| Ra 0.8 | — | not achievable as-printed; note post-processing |
Positions (PCD, hole spacing, center distances) are not diameter features: don't apply hole
compensation to them; they are affected only by scale (`outer` slope / shrink).

## 5. Print-native fits (diametral clearance actually achieved; see profile `fits`)
| Fit | FDM | SLA | SLS/MJF | Use |
|---|---|---|---|---|
| press | −0.10 | −0.05 | −0.10 | bearings, magnets, dowels pressed in |
| transition | 0.00 | 0.00 | +0.05 | locating, removable with force |
| snug | +0.10 | +0.05 | +0.15 | lids, plugs, alignment |
| slide | +0.20 | +0.10 | +0.30 | shafts that rotate/slide, hinges |
| free | +0.40 | +0.20 | +0.50 | loose assemblies, screws through |
| print_in_place | +0.50 | +0.30 | +0.60 | parts printed already assembled (gap per side ≈ half) |
`--mate bought` = the other part is a metal/standard part at nominal (all clearance on the
printed side). `--mate printed` = both printed (split the clearance). Bearings: press for the
outer race into a printed housing; the bore of a printed hub on a steel shaft: snug/press.
For press fits in FDM, add a 0.5–1 mm lead-in chamfer and consider crush ribs (3–6 small ribs
whose tips give the interference) instead of a full-circle interference — far more forgiving.

## 6. Fasteners in plastic
- **Heat-set inserts** (best for repeated assembly): hole Ø from the vendor (`printlib.INSERT`,
  e.g. M3 Ø4.0 × 6 deep), wall around ≥ 1.5–2 mm, no compensation (the insert melts in).
- **Thread-forming screws** directly in plastic: pilot `SELF_TAP` (M3 → Ø2.5), boss OD ≥ 2.2×d.
- **Captive nuts**: hex pocket AF + `snug` clearance (`nut_trap`), +0.2 depth.
- **Clearance holes**: ISO 273 medium (M3 Ø3.4, M4 Ø4.5, M5 Ø5.5) then compensate as a hole.
- Printed threads: only ≥ M8 or coarse custom threads, with 0.2–0.3 radial clearance.

## 7. Orientation & process effects
- Decide the **print orientation before compensating**: it decides hole vs hole_h, which
  dims are Z (quantized), and where strength is weak (layers split under tension across Z).
- Elephant foot: chamfer bottom edges by `elephant_foot_chamfer` (0.3–0.5 FDM) on any edge
  that must mate or measure accurately.
- Horizontal holes Ø > ~5 mm: `teardrop_hole(..., flat_top=True)` keeps the vertical size close
  to nominal and avoids supports. For critical horizontal bores, re-orient or ream.
- Minimum wall = profile `min_wall` (≈ 2 extrusion widths FDM); minimum hole `min_hole`.
- Large flat FDM parts warp: flatness tolerances need ribs, brims, enclosure or a different material.
- Export STL with fine tessellation (`--tol 0.01`) — coarse STL facets make holes smaller.
- If the slicer has its own "XY hole compensation / horizontal expansion", either turn it off
  or calibrate with it on — never compensate twice.

## 8. Stack-ups
For assemblies (gap between a lid and a box, total length of a stack of printed parts), list
the chain with signs and run `tol stack`. Worst case = guaranteed; RSS = realistic with many
parts. Add `-P profile` to include process scatter for printed dimensions. If the worst-case gap
can go negative, increase the nominal gap or make one part adjustable.

## 9. Calibration (strongly recommended — generic profiles are ±0.1–0.2 mm guesses)
```bash
$Z3D calibrate make calib/           # coupon.stl + measure.csv
# print with production settings, measure with calipers, fill measure.csv
$Z3D calibrate fit calib/measure.csv --name my_mk4_pla --base fdm_pla
$Z3D tol profiles                    # my_mk4_pla now available (stored in ~/.z3d-cad/)
```
After calibration the scatter usually drops to ±0.03–0.06 mm on FDM, turning many MARGINAL
features into OK. Re-calibrate when changing material, nozzle, or slicer profile.

## 10. Reporting to the user
Always include the tolerance table (`tol table` output) with: drawing value, feature type,
printed target, **model value**, verdict, and the action for each MARGINAL/POST-PROCESS row
(test print, ream to size, use insert…). State the profile used and whether it is calibrated.
