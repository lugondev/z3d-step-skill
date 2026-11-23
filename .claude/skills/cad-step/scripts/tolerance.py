"""Tolerance calculator for 3D-printed parts.

Subcommands
  iso   25H7 | 8g6                  ISO 286 limits of a size
  fit   25 H7/g6                    ISO fit: limits of hole & shaft, min/max clearance, fit type
  comp  "25H7" hole [-P fdm_pla]    compensate one toleranced dimension for printing:
                                    target size, MODEL size, printability verdict
        dims: 25H7 | 8g6 | 40±0.1 | 40+0.1-0.05 | 40 (general tol, --general m)
        feature: hole | hole_h | shaft | outer | inner | z | none
  pfit  8 slide [--mate bought|printed] [--axis v|h] [-P ..]
                                    design a printed fit: model Ø of hole (and shaft)
  stack "+20±0.1" "-15±0.2" ...     tolerance stack-up (worst case + RSS)
  table spec.yaml [-P ..] [--out params.json]
                                    whole spec: per-parameter model values + report
  profiles                          list printer profiles

All sizes in mm. Profiles: scripts/print_profiles.json, overridden by ~/.z3d-cad/print_profiles.json.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
USER_PROFILES = pathlib.Path.home() / ".z3d-cad" / "print_profiles.json"

# ---------------------------------------------------------------- ISO 286 tables (µm)
SIZES = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500]
IT = {
    4: [3, 4, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20],
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155],
    10: [40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400],
    12: [100, 120, 150, 180, 210, 250, 300, 350, 400, 460, 520, 570, 630],
    13: [140, 180, 220, 270, 330, 390, 460, 540, 630, 720, 810, 890, 970],
    14: [250, 300, 360, 430, 520, 620, 740, 870, 1000, 1150, 1300, 1400, 1550],
}
SHAFT_ES = {  # upper deviation of shafts d..h
    "d": [-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230],
    "e": [-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135],
    "f": [-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68],
    "g": [-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20],
    "h": [0] * 13,
}
SHAFT_EI = {  # lower deviation of shafts k..p
    "k": [0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5],  # IT4..IT7 only; 0 otherwise
    "m": [2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23],
    "n": [4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40],
    "p": [6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68],
}
ISO2768 = {  # linear general tolerances: (upper bound of range, f, m, c, v)
    "ranges": [3, 6, 30, 120, 400, 1000, 2000],
    "f": [0.05, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5],
    "m": [0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2],
    "c": [0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0],
    "v": [0.5, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0],
}


def _idx(d):
    if not 0 < d <= 500:
        raise ValueError(f"ISO 286 table here covers 0–500 mm, got {d}")
    return next(i for i, s in enumerate(SIZES) if d <= s)


def iso_limits(d: float, letters: str, grade: int):
    """Return (lower_dev, upper_dev) in mm for size d with e.g. ('H',7) or ('g',6)."""
    if grade not in IT:
        raise ValueError(f"IT{grade} not in table (IT4–IT14)")
    i = _idx(d)
    it = IT[grade][i]
    l = letters.lower()
    if letters[0].islower():  # shaft
        if l in SHAFT_ES:
            es = SHAFT_ES[l][i]
            ei = es - it
        elif l == "js":
            es, ei = it / 2, -it / 2
        elif l in SHAFT_EI:
            ei = SHAFT_EI[l][i] if (l != "k" or 4 <= grade <= 7) else 0
            es = ei + it
        else:
            raise ValueError(f"shaft deviation '{letters}' not supported (d e f g h js k m n p)")
        return ei / 1000, es / 1000
    # hole
    if l in SHAFT_ES:
        EI = -SHAFT_ES[l][i]
        ES = EI + it
    elif l == "js":
        ES, EI = it / 2, -it / 2
    elif l in ("k", "m", "n", "p"):
        delta = (IT[grade][i] - IT[grade - 1][i]) if (d > 3 and grade - 1 in IT) else 0
        ei_s = SHAFT_EI[l][i]
        if l == "k":
            ES = -ei_s + delta if grade <= 8 else 0
        elif l == "m":
            ES = -ei_s + delta if grade <= 8 else -ei_s
        elif l == "n":
            ES = -ei_s + delta if grade <= 8 else 0
        else:  # p
            ES = -ei_s + delta if grade <= 7 else -ei_s
        EI = ES - it
    else:
        raise ValueError(f"hole deviation '{letters}' not supported (D E F G H JS K M N P)")
    return EI / 1000, ES / 1000


def general_tol(d, cls="m"):
    for ub, t in zip(ISO2768["ranges"], ISO2768[cls]):
        if d <= ub:
            return t
    return ISO2768[cls][-1]


# ---------------------------------------------------------------- parsing
ISO_RE = re.compile(r"^\s*([\d.]+)\s*([A-Za-z]{1,2})\s*(\d{1,2})\s*$")
PM_RE = re.compile(r"^\s*([\d.]+)\s*(?:±|\+/-|\+-)\s*([\d.]+)\s*$")
UL_RE = re.compile(r"^\s*([\d.]+)\s*([+-][\d.]+)\s*/?\s*([+-][\d.]+)\s*$")


def parse_dim(s: str, general="m"):
    """-> dict(nominal, lo, hi, label) where lo/hi are deviations in mm."""
    s = s.strip().replace("Ø", "").replace("ø", "").replace(",", ".")
    if m := ISO_RE.match(s):
        d, let, g = float(m[1]), m[2], int(m[3])
        lo, hi = iso_limits(d, let, g)
        return dict(nominal=d, lo=lo, hi=hi, label=f"{d:g}{let}{g}", iso=let)
    if m := PM_RE.match(s):
        d, t = float(m[1]), float(m[2])
        return dict(nominal=d, lo=-t, hi=t, label=f"{d:g}±{t:g}")
    if m := UL_RE.match(s):
        d, a, b = float(m[1]), float(m[2]), float(m[3])
        return dict(nominal=d, lo=min(a, b), hi=max(a, b), label=s)
    try:
        d = float(s)
    except ValueError:
        raise ValueError(f"can't parse dimension '{s}'")
    t = general_tol(d, general)
    return dict(nominal=d, lo=-t, hi=t, label=f"{d:g} (ISO 2768-{general} ±{t:g})")


def tol_from_spec(nominal: float, tol):
    """spec 'tol' field: None | 'H7' | '±0.1' | '+0.1/-0' | [lo, hi]."""
    if tol is None:
        return parse_dim(str(nominal))
    if isinstance(tol, (list, tuple)):
        return dict(nominal=nominal, lo=float(min(tol)), hi=float(max(tol)), label=f"{nominal:g} {tol}")
    t = str(tol).strip()
    if re.match(r"^[A-Za-z]{1,2}\d{1,2}$", t):
        return parse_dim(f"{nominal}{t}")
    if t.startswith(("±", "+/-")):
        return parse_dim(f"{nominal}{t}")
    return parse_dim(f"{nominal}{t}")


# ---------------------------------------------------------------- profiles
def load_profiles():
    prof = json.loads((HERE / "print_profiles.json").read_text())
    prof.pop("_doc", None)
    if USER_PROFILES.exists():
        prof.update(json.loads(USER_PROFILES.read_text()))
    return prof


def get_profile(name):
    p = load_profiles()
    if name not in p:
        sys.exit(f"unknown profile '{name}'. Available: {', '.join(p)}")
    return p[name]


def model_size(target, feature, prof):
    """Size to put in CAD so the printed result is `target` (inverse of comp model)."""
    if feature in (None, "none", "z"):
        return target
    a, b = prof["comp"][feature]
    # actual = model + a + b*model  ->  model = (target - a) / (1 + b)
    m = (target - a) / (1 + b)
    s = prof.get("xy_scale_pct", 0.0)
    return m / (1 + s / 100) if s else m


def accuracy(size, prof):
    a, b = prof["accuracy"]
    return a + b * size


# ---------------------------------------------------------------- core: compensate one dim
def compensate(dim: dict, feature: str, prof: dict):
    d, lo, hi = dim["nominal"], dim["lo"], dim["hi"]
    band = hi - lo
    target = d + (lo + hi) / 2  # aim at the middle of the tolerance zone
    acc = accuracy(d, prof)
    res = dict(label=dim["label"], feature=feature, nominal=d, min=d + lo, max=d + hi,
               band=band, target=target, process_pm=acc)
    if feature == "z":
        layer = prof["layer"]
        q = round(target / layer) * layer
        res["model"] = target
        res["note"] = (f"height prints in {layer} mm layers → ≈{q:.3f}"
                       + ("" if abs(q - target) <= band / 2 else " (outside tolerance: change layer height or dimension)"))
        res["verdict"] = "OK" if abs(q - target) <= band / 2 and band >= 2 * acc else "CHECK"
        return res
    if feature in (None, "none"):
        res.update(model=d, verdict="nominal", note="not compensated (non-functional)")
        return res
    if band >= 2 * acc - 1e-9:
        res.update(model=model_size(target, feature, prof), verdict="OK",
                   note="printable as-is (after compensation)")
    elif band >= acc - 1e-9:
        res.update(model=model_size(target, feature, prof), verdict="MARGINAL",
                   note="tight for this process: calibrate the printer + test-print this feature")
    else:
        stock = prof["post_process_stock"]
        if feature in ("hole", "hole_h"):
            pre = model_size(d + lo - stock, feature, prof)
            how = f"print undersize Ø{d + lo - stock:.2f} then drill/ream to {dim['label']}"
        elif feature == "shaft":
            pre = model_size(d + hi + stock, feature, prof)
            how = f"print oversize Ø{d + hi + stock:.2f} then sand/turn to {dim['label']}"
        else:
            pre = model_size(target, feature, prof)
            how = "tolerance tighter than process: machine/sand after print, or relax the tolerance"
        res.update(model=pre, verdict="POST-PROCESS", note=how)
    return res


# ---------------------------------------------------------------- commands
def fmt(x, n=3):
    return f"{x:+.{n}f}" if isinstance(x, float) else str(x)


def cmd_iso(a):
    dim = parse_dim(a.dim)
    print(f"{dim['label']}: {dim['nominal'] + dim['lo']:.4f} … {dim['nominal'] + dim['hi']:.4f}  "
          f"(dev {dim["lo"] * 1000:+.1f} / {dim["hi"] * 1000:+.1f} µm, band {(dim['hi'] - dim['lo']) * 1000:.0f} µm)")


def cmd_fit(a):
    d = float(a.nominal)
    h, s = a.fit.split("/")
    hm = ISO_RE.match(f"{d}{h}")
    sm = ISO_RE.match(f"{d}{s}")
    hlo, hhi = iso_limits(d, hm[2], int(hm[3]))
    slo, shi = iso_limits(d, sm[2], int(sm[3]))
    cmax, cmin = (hhi - slo), (hlo - shi)
    kind = "clearance" if cmin >= 0 else ("interference" if cmax <= 0 else "transition")
    print(f"hole  Ø{d:g}{h}: {d + hlo:.4f} … {d + hhi:.4f}")
    print(f"shaft Ø{d:g}{s}: {d + slo:.4f} … {d + shi:.4f}")
    print(f"clearance: min {cmin * 1000:+.0f} µm, max {cmax * 1000:+.0f} µm  → {kind} fit")
    if a.profile:
        prof = get_profile(a.profile)
        acc = accuracy(d, prof)
        print(f"process {a.profile}: ±{acc:.2f} mm ≈ ±{acc * 1000:.0f} µm — "
              + ("ISO fit not achievable straight off the printer; use `pfit` for a print-native fit, "
                 "or post-process (ream/turn)." if acc * 2 > (hhi - hlo) else "achievable"))


def cmd_comp(a):
    prof = get_profile(a.profile)
    dim = parse_dim(a.dim, a.general)
    r = compensate(dim, a.feature, prof)
    print(f"{r['label']} [{a.feature}] on {a.profile}")
    print(f"  limits        : {r['min']:.3f} … {r['max']:.3f} (band {r['band']:.3f})")
    print(f"  target actual : {r['target']:.3f}")
    print(f"  process ±     : {r['process_pm']:.3f}")
    print(f"  MODEL size    : {r['model']:.3f}")
    print(f"  verdict       : {r['verdict']} — {r['note']}")


def cmd_pfit(a):
    prof = get_profile(a.profile)
    d = float(a.nominal)
    if a.fit not in prof["fits"]:
        sys.exit(f"fit must be one of {list(prof['fits'])}")
    c = prof["fits"][a.fit]
    hf = "hole_h" if a.axis == "h" else "hole"
    print(f"Ø{d:g} {a.fit} fit on {a.profile}: target actual clearance {c:+.2f} mm (diametral)")
    if a.mate == "bought":  # shaft is a bought part (rod, bearing, screw) at nominal
        h_t = d + c
        print(f"  shaft (bought, nominal) : Ø{d:.3f}")
        print(f"  hole  printed: actual Ø{h_t:.3f} → MODEL Ø{model_size(h_t, hf, prof):.3f}")
    elif a.mate == "bought-hole":  # printed pin into a bought/metal hole
        s_t = d - c
        print(f"  hole  (bought, nominal) : Ø{d:.3f}")
        print(f"  shaft printed: actual Ø{s_t:.3f} → MODEL Ø{model_size(s_t, 'shaft', prof):.3f}")
    else:
        h_t, s_t = d + c / 2, d - c / 2
        print(f"  hole  printed: actual Ø{h_t:.3f} → MODEL Ø{model_size(h_t, hf, prof):.3f}")
        print(f"  shaft printed: actual Ø{s_t:.3f} → MODEL Ø{model_size(s_t, 'shaft', prof):.3f}")
    acc = accuracy(d, prof)
    print(f"  expected spread ±{acc:.2f} per part → clearance range ≈ {c - 2 * acc:+.2f} … {c + 2 * acc:+.2f} "
          + ("(worst case; generic profile — calibrate to shrink this)" if "calibrated" not in prof["desc"]
             else "(worst case, calibrated profile)"))


def cmd_stack(a):
    tot, wc, rss = 0.0, 0.0, 0.0
    print(f"{'#':>2} {'dim':>16} {'sign':>4} {'nom':>9} {'±':>7}")
    for k, s in enumerate(a.dims, 1):
        s = s.strip()
        sign = -1 if s.startswith("-") else 1
        dim = parse_dim(s.lstrip("+-"), a.general)
        mid = dim["nominal"] + (dim["lo"] + dim["hi"]) / 2
        half = (dim["hi"] - dim["lo"]) / 2
        tot += sign * mid
        wc += half
        rss += half ** 2
        print(f"{k:>2} {dim['label']:>16} {'+' if sign > 0 else '-':>4} {mid:9.3f} {half:7.3f}")
    rss = math.sqrt(rss)
    print(f"result (mean): {tot:.3f}")
    print(f"worst case   : {tot - wc:.3f} … {tot + wc:.3f}  (±{wc:.3f})")
    print(f"RSS (stat.)  : {tot - rss:.3f} … {tot + rss:.3f}  (±{rss:.3f})")
    if a.profile:
        prof = get_profile(a.profile)
        # each printed dimension contributes process scatter too
        p = [accuracy(parse_dim(s.lstrip('+-'), a.general)['nominal'], prof) for s in a.dims]
        print(f"incl. process scatter ({a.profile}): worst ±{wc + sum(p):.3f}, RSS ±{math.sqrt(rss ** 2 + sum(x * x for x in p)):.3f}")


def cmd_table(a):
    import yaml

    spec = yaml.safe_load(pathlib.Path(a.spec).read_text())
    pname = a.profile or (spec.get("print") or {}).get("profile") or "fdm_pla"
    prof = get_profile(pname)
    general = (spec.get("print") or {}).get("general_tolerance_class", a.general)
    out, rows = {}, []
    for name, p in (spec.get("params") or {}).items():
        if not isinstance(p, dict) or not isinstance(p.get("value"), (int, float)):
            continue
        feat = p.get("feature", "none")
        if p.get("fit") and feat in ("hole", "hole_h", "shaft"):
            c = prof["fits"][p["fit"]]
            mate = p.get("mate", "bought")
            v = float(p["value"])
            if feat == "shaft":
                tgt = v - (c if mate == "bought-hole" else c / 2)
            else:
                tgt = v + (c if mate == "bought" else c / 2)
            mval = model_size(tgt, feat, prof)
            r = dict(label=f"{v:g} {p['fit']} fit ({mate})", feature=feat, target=tgt, model=mval,
                     verdict="FIT", note=f"clearance {c:+.2f} per {pname}", band=float("nan"))
        else:
            dim = tol_from_spec(float(p["value"]), p.get("tol"))
            if p.get("tol") is None and feat in ("none", None):
                out[name] = p["value"]  # keep ints as ints (counts, angles)
                continue
            r = compensate(dim, feat, prof)
        out[name] = round(r["model"], 3)
        rows.append((name, r))
    print(f"## Tolerance plan — profile `{pname}` ({prof['desc']})\n")
    print("| param | drawing | feature | target (printed) | MODEL | verdict | note |")
    print("|---|---|---|---|---|---|---|")
    for n, r in rows:
        print(f"| {n} | {r['label']} | {r['feature']} | {r['target']:.3f} | **{r['model']:.3f}** | {r['verdict']} | {r['note']} |")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(out, indent=2))
        print(f"\nmodel parameters written to {a.out}  (use: z3d.sh build model.py --params {a.out})")


def cmd_profiles(a):
    for k, v in load_profiles().items():
        src = "user" if USER_PROFILES.exists() and k in json.loads(USER_PROFILES.read_text()) else "default"
        print(f"{k:14s} [{src}] {v['desc']}  ±({v['accuracy'][0]}+{v['accuracy'][1]}·L)  fits={v['fits']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("iso"); s.add_argument("dim"); s.set_defaults(f=cmd_iso)
    s = sp.add_parser("fit"); s.add_argument("nominal"); s.add_argument("fit"); s.add_argument("-P", "--profile")
    s.set_defaults(f=cmd_fit)
    s = sp.add_parser("comp"); s.add_argument("dim"); s.add_argument("feature",
        choices=["hole", "hole_h", "shaft", "outer", "inner", "z", "none"])
    s.add_argument("-P", "--profile", default="fdm_pla"); s.add_argument("--general", default="m")
    s.set_defaults(f=cmd_comp)
    s = sp.add_parser("pfit"); s.add_argument("nominal"); s.add_argument("fit")
    s.add_argument("--mate", default="bought", choices=["bought", "bought-hole", "printed"])
    s.add_argument("--axis", default="v", choices=["v", "h"]); s.add_argument("-P", "--profile", default="fdm_pla")
    s.set_defaults(f=cmd_pfit)
    s = sp.add_parser("stack"); s.add_argument("dims", nargs="+"); s.add_argument("-P", "--profile")
    s.add_argument("--general", default="m"); s.set_defaults(f=cmd_stack)
    s = sp.add_parser("table"); s.add_argument("spec"); s.add_argument("-P", "--profile")
    s.add_argument("--out"); s.add_argument("--general", default="m"); s.set_defaults(f=cmd_table)
    s = sp.add_parser("profiles"); s.set_defaults(f=cmd_profiles)
    argv = sys.argv[1:]
    if argv and argv[0] == "stack" and "--" not in argv:  # let "-15±0.2" through as a value
        opts, dims, rest = [], [], argv[1:]
        while rest:
            x = rest.pop(0)
            if x in ("-P", "--profile", "--general") and rest:
                opts += [x, rest.pop(0)]
            else:
                dims.append(x)
        argv = ["stack", *opts, "--", *dims]
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
