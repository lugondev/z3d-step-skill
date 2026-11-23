---
name: cad-step
description: Create 3D CAD models as STEP files (parametric, via CadQuery/OpenCASCADE) for 3D printing, with tolerance calculation (ISO 286 fits, print compensation for holes/pins/heights per FDM/SLA/SLS profile, fit design, stack-ups, printer calibration), convert STEP to STL, and reverse STL/mesh back to STEP (faceted solid or a rebuilt parametric model). Use this whenever the user mentions dung sai, lắp ghép, tolerance, clearance, press fit, H7/g6, in 3D, or whenever the user wants to model a part, bracket, enclosure, flange, shaft, gear blank, plate with holes, or any mechanical solid; mentions .step/.stp/.stl files, "xuất STEP", "tạo file step", "dựng 3D", "chuyển stl sang step", "convert mesh to CAD", 3D printing export, or checking a CAD file's dimensions/volume — even if they don't say "CadQuery".
---

# cad-step — create STEP, STEP→STL, STL→STEP

All work goes through one runner that finds/creates a Python env with CadQuery + trimesh
(Python 3.12 venv; first run auto-installs into `~/.z3d-cad/venv` unless `./.venv` already has it):

```bash
Z3D=<this skill dir>/scripts/z3d.sh      # e.g. .claude/skills/cad-step/scripts/z3d.sh
$Z3D build model.py -o out/part.step [--stl out/part.stl] [--preview out/part.png] [-p L=120]
$Z3D step2stl in.step out.stl [--tol 0.01] [--ang 0.1] [--split] [--ascii]
$Z3D stl2step in.stl out.step [--no-unify] [--decimate 50000]
$Z3D inspect file.step|file.stl          # validity, bbox, volume, face types, holes (Ø + axis + center)
$Z3D analyze-mesh file.stl [--axis z] [--levels 7] [--at 2,5.5]   # design-intent recovery
$Z3D render file.step|stl -o view.png [--views iso,front,top,right]
$Z3D compare reference.stl candidate.step  # volume diff + surface deviation (Hausdorff)
$Z3D tol table spec.yaml --out print_params.json   # tolerance plan for 3D printing (see §0)
$Z3D tol comp "25H7" hole | pfit 8 slide | fit 25 H7/g6 | stack +50±0.2 -20±0.1 | iso 8g6 | profiles
$Z3D calibrate make calib/  |  calibrate fit calib/measure.csv --name my_printer
```

## 0. Parts are for 3D printing → tolerances are part of the job
Every part modelled here is meant to be 3D-printed, so the nominal drawing size is **not**
what goes into the printable model. Printers make holes small, pins big, quantize heights,
and can't hold ISO precision fits. For every functional dimension (holes, pins, mating faces,
slots, anything with a tolerance or a mating part):
1. Know the **process profile** (`tol profiles`; default `fdm_pla`). If the user hasn't said
   which printer/material, use the default, say so, and recommend calibration.
2. Decide **print orientation** first — it determines hole vs horizontal hole and Z dims.
3. Classify each dimension's feature type (hole / hole_h / shaft / outer / inner / z / none)
   and its tolerance (drawing value, ISO code, general tolerance, or a fit class).
4. Run `tol table` (or `tol comp` / `tol pfit` for single features) → model values + verdict
   (OK / MARGINAL / POST-PROCESS). Build with `--params`.
5. Add print details: elephant-foot chamfer on bed edges, teardrop for horizontal holes,
   inserts/nut traps instead of tapped threads (`printlib.py`).
6. Report the tolerance table and the action for every non-OK row.
Read `references/print-tolerances.md` for the model behind the numbers, fit tables, fastener
sizes, and how to translate drawing tolerances (H7 bores, GD&T) into print strategy.

Units are **millimetres** throughout. Convention: **Z up**, front view looks along +Y, so a
drawing's front view = XZ plane, top view = XY plane, right view = YZ plane.

## 1. Creating a STEP model

1. **Pin down the design.** Collect every driving dimension. If something important is
   missing (overall size, hole size, thread spec) and you can't infer it, make a sensible
   engineering assumption and list it in the script header under `Assumed:` — the user
   can then correct it with `-p`. Ask only when a guess would make the part useless.
2. **Write the model script** by copying `templates/part_template.py`. Rules that keep models
   robust and editable:
   - All driving dimensions in the `P` dict at the top; geometry derives from them.
   - Pick an origin that matches how the part is dimensioned (datum faces/center of a bore),
     so drawing dimensions map 1:1 to coordinates.
   - Order: base body → material removal (pockets, holes) → additions → fillets/chamfers last.
     Fillets are the most failure-prone op in OpenCASCADE; doing them last and selecting
     edges precisely avoids most `StdFail_NotDone` errors.
   - Use real hole ops (`hole`, `cboreHole`, `cskHole`) so holes stay true cylinders.
   - Threads: model the tap-drill/major diameter, note the thread in the header/name
     (cosmetic threads aren't stored in STEP anyway). Model real helical threads only on request.
   - Assemblies: build parts separately, combine with `cq.Assembly` (names + colors), assign to `result`.
   - See `references/cadquery-cheatsheet.md` for selectors, sketch API, revolve/loft/sweep,
     patterns, and fixes for common errors. Read it when the part goes beyond boxes and holes.
3. **Build** with `--preview`, then **look at the PNG** (Read it) and check the printed report:
   `valid: True`, `solids: 1` (or the number expected), bbox matches the overall dimensions,
   holes listed by `inspect` match the spec. Fix and rebuild until they do — the report is
   how you catch a hole on the wrong face or a fillet that silently changed the size.
4. **Deliver**: the nominal `.step` and the print-compensated `.step`/`.stl`
   (`part_print_<profile>.*`), the model `.py` (the editable source), the tolerance table
   (§0), and the list of assumptions.

## 2. STEP → STL

`$Z3D step2stl in.step out.stl`. Tolerance guidance: `--tol 0.01 --ang 0.1` for FDM/SLA
printing (default); `0.001` for very small/precise parts; `0.1` for quick previews or huge
parts. Report triangle count + `watertight` (should be True for a valid solid). For a
multi-body STEP, use `--split` when the user wants one STL per part.

## 3. STL → STEP (reverse)

Decide which mode the user needs; when unclear, do Mode A and offer Mode B.

**Mode A — faceted solid (fast, exact to the mesh).** `$Z3D stl2step in.stl out.step`.
Each triangle becomes a planar face, coplanar ones are merged, result is a valid closed
solid that any CAD will open. Good for: putting a scan/printable mesh into a CAD assembly,
boolean ops, measuring. Limits: curved surfaces stay faceted (not real cylinders), so holes
can't be edited as holes. Meshes > ~200k triangles: use `--decimate 50000` first (warn the
user it loses detail). Check the printed volume against the mesh volume.

**Mode B — parametric rebuild (editable, true geometry).** Use when the user wants an
editable part, "real" holes/fillets, or the STL is a mechanical part (prismatic/turned):
1. `$Z3D inspect in.stl` → size, units guess, watertight. If extents look like metres or
   inches (tiny numbers), confirm units before modelling.
2. `$Z3D analyze-mesh in.stl --axis z` (repeat on x/y as needed) → dominant planes give
   step heights & wall positions; section loops with `CIRCLE Ø..` give holes/bosses with
   centers; `revolve_score_by_axis` ≈1 on an axis means a turned part → model with `revolve`.
   Use `--at` to slice exactly through features you want to measure.
3. `$Z3D render in.stl -o ref.png` and look at it to understand the shape.
4. Write the CadQuery model **in the same coordinate frame** as the mesh (use the bbox
   min/max and the measured centers directly), round measured values to plausible design
   values (Ø6.62 → Ø6.6 M6 clearance, 49.98 → 50) and say so.
5. Build, then `$Z3D compare in.stl rebuilt.step`. Target: volume diff < 1–2 %, p95
   deviation small relative to part size. Large max deviation usually means a missing
   feature — slice at that region and iterate.

Organic shapes (sculptures, scanned faces, figurines) can't be meaningfully rebuilt
parametrically — use Mode A and say why.

## Troubleshooting quick list

- `valid: False` after build → usually a self-intersecting sketch or a fillet bigger than the
  adjacent face; reduce radius or fillet fewer edges. `shape.fix()` can heal small issues.
- Hole/feature landed on the wrong face → re-check the face selector (`>Z`, `<Y` …) and
  that `workplane()` was called after selecting the face.
- `ModuleNotFoundError` → run `$Z3D setup`; cadquery needs Python ≤ 3.12 (the runner handles it).
- Huge STEP from stl2step → that's expected for curved meshes; Mode B gives a small file.
