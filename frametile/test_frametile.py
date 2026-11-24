"""Sweep test: every part over a range of parameters, nominal + print profile, must build a valid
single solid per body and pass DRC (no FAIL). Templates/demo assemblies must be buildable (no overlap, screws clear, every screw grips 2 parts).

    ../.venv/bin/python test_frametile.py [--quick]
"""
import itertools
import sys
import time

import assembly as A
import drc
import engine as E

QUICK = "--quick" in sys.argv
SWEEP = {
    "T-S": [dict(n=n, m=m, holes=h) for n, m in [(3, 3), (5, 5), (8, 3), (12, 8), (2, 6)] for h in ("perimeter", "corners")],
    "T-W": [dict(n=n, m=m) for n, m in [(3, 3), (4, 7), (10, 10), (2, 2)]] + [dict(n=6, m=4, holes="alternate")],
    "T-D": [dict(n=n, m=m) for n, m in [(3, 3), (6, 3), (3, 9), (9, 9)]],
    "T-A": [dict(n=n, m=m, k=k) for n, m, k in [(5, 5, 2), (5, 5, 1), (6, 3, 3), (8, 4, 7), (4, 6, 2), (3, 3, 1)]],
    "T-U": [dict(n=n, m=m) for n, m in [(3, 3), (5, 6), (6, 5), (7, 8), (10, 10)]],
    "T-P": [dict(n=n, m=m, holes=h) for n, m in [(2, 2), (5, 5), (3, 8)] for h in ("grid", "perimeter")],
    "C-90": [dict(holes=h) for h in (1, 2, 3)],
    "C-T": [dict(arm=a) for a in (1, 2, 4)],
    "C-X": [dict(arm=a) for a in (1, 2, 3)],
    "C-I": [dict(arm=a) for a in (1, 3)],
    "C-L": [dict(arm=a) for a in (1, 3)],
    "H-180": [dict(n=n) for n in (2, 3, 6)],
    "M-H": [dict(boss_h=b) for b in (4, 8, 16)],
    "W-40": [dict(D=40, width=12), dict(D=60, width=16), dict(D=32, width=8)],
}
fails = 0
t0 = time.time()
for code, cases in SWEEP.items():
    if QUICK:
        cases = cases[:1]
    for params, prof in itertools.product(cases, (None, "fdm_pla")):
        t = time.time()
        try:
            ctx = E.Ctx(profile=prof)
            part = E.build_part(code, params, ctx)
            bad = [b.name for b in part.bodies if not (b.shape.isValid() and len(b.shape.Solids()) == 1)]
            rep = drc.check_part(part, ctx) if prof is None else {}
            fl = [f"{n}: {r['rule']} = {r['value']} {r['note']}" for n, rows in rep.items() for r in rows if r["status"] == "FAIL"]
            ok = not bad and not fl
            print(f"{'OK  ' if ok else 'FAIL'} {code:6} {str(params):40} {prof or 'nominal':8} {time.time() - t:4.1f}s",
                  "" if ok else (bad, fl))
            fails += not ok
        except Exception as e:
            print(f"ERR  {code:6} {params} {prof}: {type(e).__name__}: {e}")
            fails += 1
for name, fn in A.SCENES.items():
    if QUICK and name in ("rocket", "building"):
        continue
    t = time.time()
    sc = fn()
    bad = A.check_scene(sc)
    print(f"{'OK  ' if not bad else 'FAIL'} scene {name:9} {len(sc.items)} parts {len(sc.screws)} screws {time.time() - t:5.1f}s",
          bad[:5] if bad else "")
    fails += bool(bad)
print(f"\n{fails} failure(s) in {time.time() - t0:.0f}s")
sys.exit(1 if fails else 0)
