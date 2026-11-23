---
name: cad-vision
description: Analyze images to build 3D STEP models — read engineering/technical drawings (bản vẽ kỹ thuật: orthographic views, sections, dimensions, tolerances, GD&T, title blocks, hole callouts) and photos/sketches/renders of physical objects, extract a structured dimension spec, compute 3D-printing tolerances (ISO fits → print-compensated model sizes, fit design, printability verdicts), then model the part in CadQuery and verify it against the image. Use this whenever the user shares or points to an image/PDF/scan of a drawing, blueprint, sketch, or object photo and wants it modelled, measured, explained, or turned into STEP/STL ("dựng 3D từ bản vẽ", "từ ảnh này tạo file step", "phân tích bản vẽ", "đọc kích thước", "model this part from the picture"), even if they only ask to "read" or "analyze" the drawing.
---

# cad-vision — images & drawings → dimension spec → STEP

This skill does the *seeing*; the sibling **cad-step** skill does the *building*
(`../cad-step/scripts/z3d.sh` — build / render / inspect). Read cad-step's SKILL.md when you
get to modelling if it isn't already loaded.

The core loop is: **look → classify → extract spec (with tolerances) → confirm gaps →
tolerance plan for printing → model → render → compare with the image → fix**.

All parts are made to be **3D-printed**. That changes what "correct" means: the printable model
uses compensated sizes, not the drawing's nominal, and precision tolerances on the drawing may
not be printable at all. Reading tolerances is therefore as important as reading dimensions. The comparison step is what makes this work: your first reading of a
drawing will often miss a hidden feature or misplace a hole, and seeing the render side by side
with the original exposes that quickly.

## Step 0 — get the image in view
- Image file (png/jpg/webp): Read it directly. Crop/zoom when text is small: use the
  cad-step python (`z3d.sh py -c ...` with PIL from matplotlib's deps, or `sips` on macOS)
  to crop regions (title block, a dense view) and Read the crops at higher scale. Dimension
  text misread at low resolution is the #1 source of errors.
- PDF: render pages to PNG (`pdftoppm -r 200` if available, else `sips -s format png`), then Read.
- Several images of one object (front/side/top photos): read all before deciding anything.

## Step 1 — classify the input
| Type | Signs | Go to |
|---|---|---|
| Engineering drawing | title block, orthographic views, dimension lines, scale, projection symbol | `references/drawing-reading.md` |
| Hand sketch with dimensions | freehand lines, numbers, maybe one or two views | drawing-reading.md (lenient: ignore line-type rules, trust numbers over proportions) |
| Photo / render of an object | perspective, shading, background, no dimension lines | `references/photo-modeling.md` |
| Mixed (photo + a few measurements from the user) | | photo-modeling.md, measurements override estimates |

Read the matching reference before extracting — it has the checklists (projection angle,
hidden lines, section hatching, thread/hole callouts, scale estimation from photos) that
prevent the classic mistakes.

## Step 2 — extract a structured spec
Write the spec as a YAML file next to the outputs (template: `templates/part_spec.yaml`).
Every dimension gets a `source`:
- `drawing` — read directly from a dimension on the drawing
- `derived` — computed from other dimensions (e.g. 100 − 2×10)
- `measured` — scaled from the image (photo pixels or an undimensioned drawing feature)
- `assumed` — engineering guess (standard size, typical wall thickness…)
- `user` — given by the user in chat

This matters because the user needs to know which numbers to trust. A model built from a
fully-dimensioned drawing and one guessed from a phone photo look equally precise as STEP
files; the spec is the only place that difference is visible.

For every functional dimension also record:
- `feature`: hole (vertical axis in print orientation) | hole_h (horizontal axis) | shaft |
  outer | inner (slot/pocket width) | z (height in print direction) | none
- `tol`: exactly as on the drawing — ISO code (`H7`, `g6`), `±0.1`, `+0.2/-0`; omit to use the
  general tolerance from the title block (ISO 2768-m default)
- `fit` + `mate` instead of `tol` when the drawing gives no tolerance but the feature obviously
  mates with something (bearing seat → press, shaft hole → slide; mate: bought|printed|bought-hole)
Plus the `print:` block (process profile, orientation), units, projection angle (1st/3rd), scale,
material/finish notes, GD&T that matters for function, and **open questions**.

## Step 3 — resolve gaps (ask sparingly)
Summarize what you read in a compact table (feature → value → source) and list the open
questions. Ask the user only about things that change the part materially and can't be
inferred: an overall size for a photo with no scale reference, an ambiguous view arrangement,
an illegible critical dimension. For everything else pick a sensible default, mark it
`assumed`, and continue — the user can correct it later via `-p name=value` because every
spec value becomes a parameter.

## Step 3b — tolerance plan for printing
Follow cad-step §0 and `../cad-step/references/print-tolerances.md`:
1. Choose the print orientation (largest flat face on the bed, critical bores vertical if
   possible) and set `feature` types accordingly.
2. `z3d.sh tol table spec.yaml --out out/print_params.json` → table of target/model/verdict.
3. For each POST-PROCESS or MARGINAL row decide the action (ream, insert, test print, change
   to a print-native fit) and, if the decision belongs to the user (e.g. Ø25 H7 on FDM: ream or
   change the design?), ask in the same message as other open questions.
4. Show the user the table — it is the core deliverable alongside the STEP.

## Step 4 — model
Follow cad-step §1. Map spec → `P` dict one-to-one (same names), put the drawing number and
the assumption list in the script header. Choose the origin/datums the drawing uses so that
dimensions translate to coordinates without arithmetic. Respect the view mapping:
front view = XZ, top view = XY, right/left view = YZ (Z up).

## Step 5 — verify against the image (don't skip)
1. `z3d.sh build part.py -o out/part.step --preview out/part.png` (nominal) and
   `z3d.sh build part.py -o out/part_print_<profile>.step --stl out/part_print_<profile>.stl --params out/print_params.json`
   (printable). Verify geometry on the nominal build; for a drawing also
   render the matching views: `z3d.sh render out/part.step -o out/views.png --views front,top,right`
   (use `left` instead of `right` for a 1st-angle drawing if that's what the sheet shows).
2. Read both the original image and the render. Check feature by feature: every visible and
   hidden line on the drawing has a counterpart; hole counts and positions; section shapes;
   overall proportions for photos.
3. `z3d.sh inspect out/part.step` — compare bbox with overall dimensions and the hole list
   (Ø, axis, center) with the hole callouts.
4. Fix and repeat until it matches. Two or three rounds is normal.

## Step 6 — deliver
- `part.step` (nominal), `part_print_<profile>.step/.stl` (compensated), the model `.py`,
  `spec.yaml`, `print_params.json`
- the tolerance table, with the action for every non-OK row, the profile used, and a note to
  calibrate (`z3d.sh calibrate make`) if the profile is generic
- A short summary in the user's language: what the part is, key dimensions, **which values are
  assumed/measured** (so they know what to check), anything on the drawing you couldn't model
  (knurling, cosmetic threads, text engraving, surface finish) and how it was handled.

## Honest limits to tell the user
- From a single photo, dimensions are estimates (typically ±5–15 % even with a reference
  object). Say so; recommend 2–3 caliper measurements of the critical features.
- STEP stores one size per feature: the printable STEP holds compensated sizes, the nominal
  STEP the drawing sizes. Tolerances themselves live in the spec/tolerance table.
- ISO precision fits (H7, g6…) are tens of µm; FDM scatters ±0.1–0.2 mm. Those features need
  post-processing or a design change — say so plainly instead of pretending the print will hit them.
- Freeform/organic surfaces (car bodies, figurines) from photos can only be approximated.
