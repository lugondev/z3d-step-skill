# Modelling from photos / renders / sketches without dimensions

## Contents
1. Describe before measuring  2. Getting scale  3. Measuring in the image
4. Perspective pitfalls  5. Decomposing into CAD features  6. Standard-size snapping
7. What to ask the user  8. Verification

## 1. Describe before measuring
Write a short feature inventory first — it keeps you from fixating on numbers too early:
- What is it, what does it do (bracket, knob, housing, adapter…)? Function hints at
  hidden geometry (a pulley has a bore + keyway; a bracket has mounting holes).
- Base shape (block / cylinder / plate / shell), symmetry (mirror planes, rotational, n-fold).
- Features: holes (through? countersunk?), slots, bosses, ribs, fillets, chamfers, text.
- Manufacturing method guess: CNC (sharp internal corners = radius of a tool, flat faces),
  3D print (layer lines, uniform walls, overhang ≤45°), injection moulded (draft angles,
  uniform walls, ribs, ejector marks), sheet metal (constant thickness, bend radii),
  turned (rotational symmetry). This determines wall thickness defaults and how to model it.
- What is **not visible** (back side, inside) — list as assumptions.

## 2. Getting scale (in priority order)
1. **User-supplied measurement** of any feature (ask for one if nothing else exists — a single
   caliper number fixes the whole model's scale).
2. **Reference object** in the photo, in the same plane & distance as the part:
   ISO credit card 85.60 × 53.98 mm; A4 paper 210 × 297; US letter 215.9 × 279.4;
   coins (VN 5000đ coin Ø25.5; €1 Ø23.25; US quarter Ø24.26); AA battery Ø14.5 × 50.5;
   cutting mat grid (usually 10 mm or 1 inch); ruler/caliper in frame (best).
3. **Standard features on the part**: screw heads (M3 SHCS head Ø5.5, M4 Ø7, M5 Ø8.5,
   M6 Ø10), nuts (M3 AF 5.5, M4 AF 7, M5 AF 8, M6 AF 10), bearings (608: 8×22×7;
   6200: 10×30×9), USB-C port 8.4 × 2.6, USB-A 12 × 4.5, 2020 aluminium extrusion,
   Arduino Uno board 68.6 × 53.4, Raspberry Pi 4 85 × 56.
4. Common product sizes (bottle caps, phone thickness) — weakest; mark `assumed`.

## 3. Measuring in the image
For precise pixel measurement don't eyeball — get coordinates:
```bash
Z3D=.claude/skills/cad-step/scripts/z3d.sh
$Z3D py -c "from PIL import Image; im=Image.open('photo.jpg'); print(im.size)"
# crop + upscale a region to read it better:
$Z3D py -c "from PIL import Image; im=Image.open('photo.jpg'); im.crop((x0,y0,x1,y1)).resize((W,H)).save('crop.png')"
```
Overlay a grid to read pixel positions off the image (then Read the result):
```bash
$Z3D py - <<'EOF'
from PIL import Image, ImageDraw
im = Image.open("photo.jpg").convert("RGB"); d = ImageDraw.Draw(im); step = 50
for x in range(0, im.width, step): d.line([(x,0),(x,im.height)], fill=(255,0,0) if x%250==0 else (255,180,180))
for y in range(0, im.height, step): d.line([(0,y),(im.width,y)], fill=(255,0,0) if y%250==0 else (255,180,180))
im.save("grid.png")
EOF
```
Then mm = px × (reference_mm / reference_px). Measure the reference along the same direction
and at the same depth as the feature.

## 4. Perspective pitfalls
- Only measurements **in a plane facing the camera** scale linearly. Prefer straight-on photos;
  ask for front/top/side photos if a critical dimension is foreshortened.
- Circles seen at an angle are ellipses: the **major axis** = true diameter.
- Objects closer to the camera look bigger; a reference object in front of the part
  overstates the scale → part comes out too small.
- Wide-angle phone lenses distort near the edges; measure near the image center.
- Thickness/depth from a single front photo is unknowable → ask or assume and mark it.

## 5. Decomposing into CAD features
Plan the build like a machinist: stock → main profile → removals → details. Express the plan
as a feature list in the spec before coding, e.g.:
```
1. base plate 60×40×5, corners R4
2. upright 40×5×30 at back edge (Y=+17.5), joined
3. 2× gusset triangles 15×15×3
4. 2× Ø4.5 holes in base (M4 clearance) at X=±20, Y=-5
5. slot 6×15 in upright, centered, Z=20
6. all outside edges fillet 0.5 (assumed)
```
Prefer symmetric modelling (center on mirror planes) — measured asymmetry under ~3 % is
usually photo error, not design intent.

## 6. Snap to design-intent values
People design with round numbers and standard parts. After converting pixels to mm:
- lengths → nearest 0.5 or 1 mm (or 1/16" if the object is clearly imperial);
- holes → nearest standard clearance/tap size (see cad-step cheatsheet);
- wall thickness for prints → 1.2 / 1.6 / 2.0 / 2.4 / 3.0; sheet metal → 0.8 / 1 / 1.5 / 2 / 3;
- angles → 15° multiples unless clearly otherwise.
Record both the raw estimate and the snapped value in the spec (`raw: 39.3, value: 40`).

## 7. What to ask the user (one message, only what matters)
- one real measurement for scale if there's no reference;
- hidden side/inside geometry if it affects function (is it hollow? holes on the back?);
- intended use (print? CNC? fit with a mating part?) when it changes tolerances/walls.
If the user wants speed over accuracy, skip asking, mark assumptions, and deliver.

## 8. Verification
Render the model from the same viewpoint as the photo (`--views iso` or `iso2`, or front/top
for straight-on photos) and compare silhouettes and feature placement. Check proportions
(ratios like length/height) more than absolute numbers — ratios are what the photo really
encodes. Iterate until features line up.
