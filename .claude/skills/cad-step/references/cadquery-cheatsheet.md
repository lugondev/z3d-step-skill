# CadQuery cheatsheet (CadQuery 2.x, mm)

## Contents
1. Workplanes & sketches  2. Solids ops  3. Holes  4. Selectors  5. Patterns
6. Fillet/chamfer/shell  7. Revolve, loft, sweep  8. Booleans & transforms
9. Assemblies  10. Common errors → fixes  11. Recipes

## 1. Workplanes & sketches
```python
cq.Workplane("XY")            # also "XZ" (front view plane), "YZ" (side plane)
cq.Workplane("XY", origin=(0, 0, 10))
wp.center(x, y)               # shift local origin
wp.moveTo(x, y).lineTo(x2, y2).threePointArc((x3, y3), (x4, y4)).close()
wp.polyline([(0,0),(40,0),(40,10),(10,30),(0,30)]).close()
wp.rect(w, h, centered=True); wp.circle(r); wp.slot2D(length, d, angle=0)
wp.polygon(nSides, diameter)  # circumscribed diameter
wp.ellipse(a, b); wp.spline([(x,y),...], includeCurrent=True)
wp.sagittaArc(endPoint, sag); wp.radiusArc(endPoint, r)   # r sign = side
# Note "XZ" workplane: local x = global X, local y = global Z, normal = -Y.
```
Sketch API (good for profiles with fillets on 2D vertices):
```python
s = (cq.Sketch().rect(60, 40).vertices().fillet(5)
       .push([(-20, 0), (20, 0)]).circle(4, mode="s"))
cq.Workplane("XY").placeSketch(s).extrude(8)
```

## 2. Solid ops
```python
.extrude(d)  .extrude(d, both=True)  .extrude(-d)  .extrude(d, taper=5)   # taper in deg
.extrude(until="next")   # up to next face
.cutBlind(-depth)  .cutThruAll()
.box(L, W, H, centered=(True, True, False))   # sits on Z=0
.cylinder(h, r, centered=(True, True, False))
.sphere(r)  .wedge(...)
```

## 3. Holes (true cylinders, drilled into the selected face normal)
```python
.faces(">Z").workplane().pushPoints([(x1,y1),(x2,y2)]).hole(d)              # through
.hole(d, depth)                                                               # blind
.cboreHole(d, cboreDiameter, cboreDepth)
.cskHole(d, cskDiameter, cskAngle=90)
```
Metric clearance (ISO 273 medium): M3 3.4, M4 4.5, M5 5.5, M6 6.6, M8 9, M10 11, M12 13.5.
Tap drill: M3 2.5, M4 3.3, M5 4.2, M6 5, M8 6.8, M10 8.5, M12 10.2.
Counterbore for SHCS (ISO 4762): M3 Ø6.5×3.3, M4 Ø8×4.4, M5 Ø10×5.4, M6 Ø11×6.4, M8 Ø15×8.6, M10 Ø18×10.8.

## 4. Selectors
```
">Z" top-most face    "<Z" bottom    ">X" "<Y" ...
"|Z" parallel to Z (vertical edges)  "#Z" perpendicular to Z
"%CIRCLE" "%LINE" "%PLANE" "%CYLINDER"   type filters
">Z[1]"  second from top   ">Z[-2]"
"not %CIRCLE"   "(>Z or <Z) and |X"     boolean combos
.faces(">Z").edges()  .edges("|Z and >X")
cq.selectors.BoxSelector((x0,y0,z0),(x1,y1,z1))  .edges(BoxSelector(...))
.workplane(centerOption="CenterOfBoundBox")   # default "ProjectedOrigin"
.workplane(offset=5)   .workplane(invert=True)
```
**Gotcha — local axes on a selected face:** on `<Z` (bottom) the workplane's local y = **-Y**;
on `>Y`/`<Y`/`>X`/`<X` faces local axes are rotated too. When placing features on non-top faces,
print `wp.plane.xDir, wp.plane.yDir` once, or verify with `z3d.sh inspect` (hole centers) after building.

## 5. Patterns
```python
.rarray(xSpacing, ySpacing, xCount, yCount)          # rectangular, centered
.polarArray(radius, startAngle, angle, count)         # bolt circle
.rect(2*dx, 2*dy, forConstruction=True).vertices()   # 4 corners
.pushPoints(list_of_xy)
```

## 6. Fillet / chamfer / shell
```python
.edges("|Z").fillet(r)  .faces(">Z").edges().chamfer(c)  .chamfer(c1, c2)
.faces(">Z").shell(-wall)       # hollow, open on top face, wall inward
.shell(-wall) on solid with no face selected -> closed hollow
```

## 7. Revolve, loft, sweep
```python
# turned part: draw half-profile on XZ (x = radius, y = Z height), revolve about Z
prof = (cq.Workplane("XZ").polyline([(0,0),(20,0),(20,5),(8,5),(8,40),(0,40)]).close())
part = prof.revolve(360, (0,0,0), (0,1,0))   # axis given in LOCAL coords: local y == global Z
loft = (cq.Workplane("XY").rect(40,40).workplane(offset=30).circle(10).loft())
path = cq.Workplane("XZ").spline([(0,0),(20,30),(0,60)])
tube = cq.Workplane("XY").circle(5).circle(4).sweep(path)
```

## 8. Booleans & transforms
```python
a.union(b)  a.cut(b)  a.intersect(b)   # also a + b, a - b, a & b
.translate((x,y,z))  .rotate((0,0,0),(0,0,1), angleDeg)  .mirror("YZ")  .mirror("YZ", union=True)
```

## 9. Assemblies
```python
assy = (cq.Assembly(name="unit")
        .add(base, name="base", color=cq.Color("gray"))
        .add(lid, name="lid", loc=cq.Location((0,0,20)), color=cq.Color(0.2,0.4,0.8,1)))
result = assy        # build.py exports a multi-body STEP with names/colors
```

## 10. Common errors → fixes
| Error | Usual cause | Fix |
|---|---|---|
| `StdFail_NotDone` / `BRep_API: command not done` on fillet | radius ≥ adjacent face size, or fillet across a tangent chain | smaller r; fillet earlier/later; select fewer edges; use 2D sketch fillet instead |
| `ValueError: No pending wires` | extrude with no closed sketch | `.close()` the polyline; check you didn't consume the wire already |
| Feature on wrong side | workplane normal points the other way | use `.workplane(invert=True)` or negative extrude/cutBlind |
| Holes off-center | workplane origin is projected global origin | `centerOption="CenterOfBoundBox"` or explicit `.center()` |
| Shell fails | fillets present or thin regions | shell before fillets; reduce wall |
| Invalid after boolean | coincident faces | overlap tools by +0.01 mm past faces |

## 11. Recipes
**L-bracket**
```python
br = (cq.Workplane("XZ").polyline([(0,0),(60,0),(60,5),(5,5),(5,40),(0,40)]).close()
      .extrude(-30))   # XZ normal is -Y; extrude(-30) goes +Y (part spans Y 0..30)
# hole in the foot at global (X40, Y15). Bottom-face workplane has yDir = -Y, and the
# bbox center of the foot face is (30, 15) -> local offset (10, 0):
br = br.faces("<Z").workplane(centerOption="CenterOfBoundBox").pushPoints([(10, 0)]).hole(6.6)
```
**Flange (revolve + bolt circle)**
```python
f = (cq.Workplane("XY").circle(50).circle(15).extrude(10)
     .faces(">Z").workplane().polarArray(35, 0, 360, 6).hole(9))
```
**Enclosure box with lid lip**
```python
box = cq.Workplane("XY").box(100, 60, 40, centered=(True,True,False)).edges("|Z").fillet(4)
box = box.faces(">Z").shell(-2)
```
