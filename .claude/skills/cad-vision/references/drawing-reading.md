# Reading engineering drawings

## Contents
1. First pass: sheet layout  2. Projection angle  3. Line types  4. Views, sections, details
5. Dimensions & symbols  6. Holes, threads, callouts  7. Tolerances, GD&T, finish
8. Reconstructing 3D from views  9. Checklist before modelling

## 1. First pass: sheet layout
Read the **title block** first (usually bottom-right): part name, drawing no., material,
**units** (mm default for ISO; inch for ANSI unless stated), **scale** (1:1, 2:1, 1:2…),
general tolerance (ISO 2768-m etc.), projection symbol, revision, sheet "1 of N".
Then the notes block ("ALL FILLETS R1", "BREAK SHARP EDGES 0.5×45°", "UNLESS OTHERWISE
SPECIFIED") — these silently apply to every edge and are easy to forget.

## 2. Projection angle
The truncated-cone symbol in the title block decides where views sit:
- **First angle (ISO/EU/Asia, incl. Vietnam TCVN by default)**: top view is placed **below**
  the front view; the left-side view is placed on the **right** of the front view.
  Symbol: trapezoid (cone side view) on the left, concentric circles on the **right**.
- **Third angle (US/ANSI, Japan JIS uses 1st/3rd per sheet)**: top view **above** front;
  right-side view on the **right**. Symbol: concentric circles on the **left**, trapezoid on the right.
Either way, each individual view looks the same (top view: +Y toward the top of the sheet) —
only the placement differs, so the angle mainly decides *which side* a side view shows.
If no symbol: infer from layout consistency (does a hole seen in the top view line up with
hidden lines in the front view when the top view is above or below?). State which you chose.

Mapping into the model (Z up, front = looking along +Y):
- front view → XZ plane (horizontal = X, vertical = Z)
- top view → XY plane (horizontal = X, vertical = Y; the far/back side +Y is at the top of the view)
- view from the right (looking along −X) → YZ plane, horizontal axis = +Y to the right
- view from the left (looking along +X) → YZ plane, horizontal axis = +Y to the left
Verify with one asymmetric feature before trusting the mapping.

## 3. Line types (ISO 128)
| Line | Meaning |
|---|---|
| continuous thick | visible edges/outlines |
| continuous thin | dimension/extension/leader lines, hatching, thread roots (on visible threads) |
| dashed | **hidden edges** — internal holes, pockets, back-side features |
| chain thin (long-dash-dot) | center lines, axes of symmetry, pitch circles (bolt circle!) |
| chain thick | surfaces with special requirements |
| chain thin with thick ends | **cutting plane** for a section; arrows show viewing direction; letters A–A |
| freehand/zigzag thin | break lines (part is shortened in the view — dimensions still true) |

## 4. Views, sections, details
- **Full section A–A**: cut along the cutting plane; hatched areas = solid material cut.
  Unhatched regions inside the outline = hollow or a feature behind the plane.
- **Half section**: symmetric part, one half sectioned. **Offset section**: cutting plane
  steps to pass through several features. **Revolved/removed section**: cross-section of
  a rib/arm drawn in place or nearby.
- **Detail view** (circle + letter, "DETAIL B 5:1"): enlarged; dimensions are true size,
  only the drawing scale differs.
- **Auxiliary view**: projected perpendicular to an inclined face — gives true shape of that face.
- Ribs/webs are conventionally **not hatched** when cut lengthwise.
- A circle with hatched ring in a section = a bore through that location.

## 5. Dimensions & symbols
| Symbol | Meaning |
|---|---|
| Ø20 | diameter |
| R5 | radius; `CR` controlled radius; `SR`/`SØ` spherical |
| □12 | square section 12×12 |
| 4× / 4 HOLES / 4-Ø6 | repeated feature count |
| ⌴ (counterbore), ⌵ (countersink), ↧ (depth) | hole features (ANSI) |
| 2×45° or C2 | chamfer 2 mm × 45° (C2 is common on JIS/Asian drawings) |
| (25) | reference dimension — derived, not for manufacturing; use only to check |
| 25 boxed | basic (theoretically exact) dimension for GD&T |
| EQS / EQ SP | equally spaced |
| TYP | typical: applies to all similar features |
| THRU | through all |
| PCD 80 / BC Ø80 | pitch/bolt circle diameter |
| ⟂ ∥ ⌖ ◎ etc. | GD&T characteristics (see §7) |
| ~ or approx | approximate |
- **Chain vs baseline vs ordinate** dimensioning: ordinate dims (0, 15, 40, 72 from a datum)
  give coordinates directly → set the model origin at that datum.
- Angles: degrees; `30°` with arc dimension line.
- Missing dimension? Look in other views, notes, "TYP" on a sibling feature, or derive from
  a chain. Scaling off the drawing is the last resort → mark `measured`.

## 6. Holes, threads, callouts
- `M8×1.25 - 6H ↧15 / Ø6.8 ↧18` → tapped M8 fine-pitch? (1.25 is coarse for M8), thread
  depth 15, drill Ø6.8 depth 18. Model the Ø6.8 drill to 18 (+118° drill point only if asked),
  record the thread in the spec. Option: model the major Ø8 to depth 15 if the user prefers.
- `4× Ø9 THRU ⌴ Ø15 ↧9` → counterbored hole (`cboreHole(9, 15, 9)`).
- `Ø6.6 THRU ⌵ Ø12×90°` → countersunk (`cskHole(6.6, 12, 90)`).
- Thread conventions on drawings: external thread = thick line at major Ø, thin at minor;
  internal = thin line at major Ø (3/4 circle in end view), thick at minor (drill) Ø.
- `G1/4`, `Rc1/4`, `NPT 1/4` = pipe threads — note them; model the tap drill.
- Hole on a PCD: `6× Ø11 EQS on PCD 100` → `polarArray(50, start, 360, 6)`; start angle from
  the drawing (often a hole on the vertical/horizontal centerline or offset 30°).

## 7. Tolerances, GD&T, finish
Record but model nominal unless asked. Exception: for fits like `Ø20 H7` / `Ø20 g6`, nominal
Ø20 is correct; if the user wants "mean-of-tolerance" geometry for printing/CNC CAM,
compute it and mark `derived`.
- Datum letters (A, B, C in boxes on features) → these are good choices for the model origin/axes.
- Surface finish Ra 1.6 / √ symbols: note only.
- Weld symbols (on weldments): note; model weld beads only on request.

## 8. Reconstructing 3D from views
1. Identify the **dominant view** (most informative outline, usually front) and the build
   strategy: extrude a profile (prismatic), revolve a half-profile (turned: center line +
   Ø dims), or a combination (base extrude + cuts from other directions).
2. For each feature in one view, find it in the others by projecting along alignment lines
   (features align horizontally between front & side, vertically between front & top).
   A circle in the top view + two dashed vertical lines in the front view = vertical hole;
   depth = length of the dashed lines.
3. Dashed lines that don't match any visible feature = internal geometry (pocket, cross-hole).
4. Sloped line in one view + rectangle in another = inclined face; look for an auxiliary view.
5. Curves in the side view where a cylinder meets a plane = intersection curves — they come
   for free from the boolean; don't model them.
6. When two interpretations are possible (classic ambiguity with only two views), pick the
   one consistent with all dimensions and function, and mention the alternative.

## 9. Checklist before modelling
- [ ] units, scale, projection angle recorded
- [ ] overall envelope (L × W × H) known and sums of chain dimensions agree with it
- [ ] every hole: count, Ø, depth/THRU, position (from which datum), cbore/csk/thread
- [ ] every pocket/slot/step: width, depth, position
- [ ] general notes applied (default fillets/chamfers)
- [ ] sections understood (what's hollow)
- [ ] open questions listed; assumptions marked
