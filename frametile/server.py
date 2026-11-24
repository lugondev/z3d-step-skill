"""FrameTile Studio — local web app (stdlib only) around the FrameTile engine.

    ../.venv/bin/python server.py [--port 8765] [--host 127.0.0.1]
    open http://127.0.0.1:8765

API
  GET  /api/catalog                      parts, parameter specs, standard, print profiles
  POST /api/build  {code, params, profile, std}
                                         -> nominal + print-compensated STEP/STL, DRC, tolerance table
  POST /api/scene  {name, profile}       -> demo assembly (STL per part) + interference check
  POST /api/kit    {items:[{code,params,qty}], profile, std}
                                         -> zip with every part (STEP+STL, nominal + print) + BOM.csv
  GET  /files/<key>/<file>               download generated files
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import mimetypes
import pathlib
import threading
import time
import traceback
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import cadquery as cq

import assembly as A
import drc
import engine as E

HERE = pathlib.Path(__file__).resolve().parent
WEB = HERE / "web"
CACHE = HERE / "out" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()  # OpenCASCADE is not thread-safe: one build at a time
STL_TOL, STL_ANG = 0.02, 0.2  # 0.02 mm chord error: far below FDM resolution, ~4x smaller files


STD_EDITABLE = ("rim", "brace", "inner_r", "edge_round", "ef_chamfer", "wall_min", "knuckle_gap", "tire_squeeze")


def _clean_std(std):
    return {k: float(v) for k, v in (std or {}).items() if k in STD_EDITABLE and v not in (None, "")}


def _key(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:14]


def _export(shape: cq.Shape, path: pathlib.Path):
    if path.suffix == ".step":
        cq.exporters.export(shape, str(path), exportType="STEP")
    else:
        cq.exporters.export(shape, str(path), exportType="STL", tolerance=STL_TOL, angularTolerance=STL_ANG)


def tol_table(ctx_print: E.Ctx, code: str):
    S = ctx_print.S
    rows = [
        ("Lỗ M3 đứng (in phẳng)", "hole", S["hole"], ctx_print.hole_v),
        ("Lỗ M3 ngang (teardrop)", "hole_h", S["hole"], ctx_print.hole_h),
    ]
    if code == "M-H":
        rows.append(("Khe/hốc đai ốc M3 (AF)", "inner", S["nut_af"] + 0.1, ctx_print.m(S["nut_af"] + 0.1, "inner")))
    if code == "W-40":
        rows.append(("Lỗ trục bánh (lắp lỏng M3)", "hole", 3.4, ctx_print.m(3.4, "hole")))
        rows.append(("Lỗ trong lốp TPU (ép)", "hole", 28 - S["tire_squeeze"], ctx_print.m(28 - S["tire_squeeze"], "hole")))
    out = []
    for name, feat, nom, mod in rows:
        out.append(dict(feature=name, type=feat, nominal=round(nom, 3), model=round(mod, 3), delta=round(mod - nom, 3)))
    return out


def build(code, params, profile, std):
    std = _clean_std(std)
    key = _key(dict(code=code, params=params, profile=profile, std=std, v=7))
    d = CACHE / key
    meta = d / "meta.json"
    if meta.exists():
        return json.loads(meta.read_text())
    t0 = time.time()
    with LOCK:
        ctx_n = E.Ctx(std)
        part = E.build_part(code, params, ctx_n)
        rep = drc.check_part(part, ctx_n)
        variants = [("nominal", part)]
        ctx_p = None
        if profile and profile != "none":
            ctx_p = E.Ctx(std, profile)
            variants.append((f"print_{profile}", E.build_part(code, params, ctx_p)))
        d.mkdir(parents=True, exist_ok=True)
        files, bodies = [], []
        base = part.bodies[0].name.split("_")[0] if len(part.bodies) > 1 else part.bodies[0].name
        for vname, p in variants:
            for b in p.bodies:
                for ext in ("step", "stl"):
                    fn = f"{b.name}_{vname}.{ext}"
                    _export(b.shape, d / fn)
                    files.append(dict(label=f"{b.name} · {vname} · {ext.upper()}", url=f"/files/{key}/{fn}",
                                      variant=vname, ext=ext, body=b.name))
            if len(p.bodies) > 1:
                fn = f"{base}_set_{vname}.step"
                _export(cq.Compound.makeCompound(E.layout(p.bodies)), d / fn)
                files.append(dict(label=f"Cả bộ · {vname} · STEP", url=f"/files/{key}/{fn}", variant=vname, ext="step", body="set"))
        view_variant = variants[-1][0]
        dens = E.DENSITY.get(profile or "", 1.24)
        offs = E.layout(part.bodies, gap=8.0)
        for b, placed in zip(part.bodies, offs):
            bb = b.shape.BoundingBox()
            pb = placed.BoundingBox()
            vol = b.shape.Volume()
            bodies.append(dict(name=b.name, color=b.color, kind=b.kind,
                               stl=f"/files/{key}/{b.name}_{view_variant}.stl",
                               offset=[pb.xmin - bb.xmin, pb.ymin - bb.ymin, 0],
                               size=[round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)],
                               volume=round(vol / 1000, 2), mass=round(vol / 1000 * dens, 1),
                               holes=len(b.holes), notes=b.notes))
        res = dict(key=key, code=code, title=part.title, params=part.params, profile=profile, view_variant=view_variant,
                   bodies=bodies, files=files, drc=rep, summary=drc.summary(rep), bom=part.bom,
                   tol=tol_table(ctx_p, code) if ctx_p else [], seconds=round(time.time() - t0, 2))
        meta.write_text(json.dumps(res, ensure_ascii=False))
        return res


def scene(name, profile):
    key = _key(dict(scene=name, v=6))
    d = CACHE / key
    meta = d / "meta.json"
    if meta.exists():
        return json.loads(meta.read_text())
    if name not in A.SCENES:
        raise ValueError(f"unknown scene {name}")
    with LOCK:
        t0 = time.time()
        sc = A.SCENES[name]()
        bad = A.check_scene(sc)
        d.mkdir(parents=True, exist_ok=True)
        parts = []
        for i, (n, s, col, _) in enumerate(sc.items):
            fn = f"p{i}.stl"
            _export(s, d / fn)
            parts.append(dict(name=n, color=col, stl=f"/files/{key}/{fn}"))
        # all screws in ONE mesh (keeps the viewer light)
        fn = "screws.stl"
        _export(cq.Compound.makeCompound([s for _, s, _ in sc.screws]), d / fn)
        parts.append(dict(name="screws", color="#8a9099", stl=f"/files/{key}/{fn}", screw=True))
        fn = f"template_{name}.step"
        asm = cq.Assembly()
        for i, (n, s, col, _) in enumerate(sc.items):
            asm.add(s, name=f"{i}_{n}".replace(" ", "_").replace("#", ""), color=cq.Color(col))
        asm.save(str(d / fn))
        bom, hw = sc.bom_list()
        bb = cq.Compound.makeCompound([s for _, s, _, _ in sc.items]).BoundingBox()
        res = dict(key=key, name=name, title=sc.title, template=name in A.TEMPLATES, parts=parts,
                   n_parts=len(sc.items), interference=bad, ok=not bad, screws=len(sc.screws),
                   bom=bom, hardware=hw, size=[round(bb.xlen), round(bb.ylen), round(bb.zlen)],
                   step=f"/files/{key}/{fn}", seconds=round(time.time() - t0, 1))
        meta.write_text(json.dumps(res, ensure_ascii=False))
        return res


def kit(items, profile, std):
    std = _clean_std(std)
    key = _key(dict(kit=items, profile=profile, std=std, v=5))
    zpath = CACHE / f"frametile_kit_{key}.zip"
    if zpath.exists():
        return dict(url=f"/files/_/{zpath.name}")
    results = [(it, build(it["code"], it.get("params", {}), profile, std)) for it in items]
    bom = io.StringIO()
    w = csv.writer(bom)
    w.writerow(["code", "body", "qty", "params", "size_mm", "volume_cm3", "mass_g", "drc", "hardware"])
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for it, r in results:
            qty = int(it.get("qty", 1))
            for b in r["bodies"]:
                w.writerow([r["code"], b["name"], qty, json.dumps(r["params"]), "x".join(map(str, b["size"])),
                            b["volume"], b["mass"], r["summary"], " | ".join(r["bom"])])
            for f in r["files"]:
                src = CACHE / r["key"] / f["url"].rsplit("/", 1)[1]
                z.write(src, f"{f['variant']}/{src.name}")
        z.writestr("BOM.csv", bom.getvalue())
        z.writestr("STANDARD.json", json.dumps({**E.STANDARD, **(std or {})}, indent=2))
    return dict(url=f"/files/_/{zpath.name}")


class H(BaseHTTPRequestHandler):
    server_version = "FrameTileStudio/1.0"

    def log_message(self, fmt, *args):
        print("[http]", fmt % args)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, p: pathlib.Path, download=False):
        if not p.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        data = p.read_bytes()
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix in (".js", ".mjs"):
            ctype = "text/javascript"
        if p.suffix in (".step", ".stl"):
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/catalog":
            from tolerance import load_profiles

            spec = {c: {k: {**E.PARAM_SPEC.get(k, {}), **E.PARAM_SPEC_BY_PART.get(c, {}).get(k, {})} for k in v["params"]}
                    for c, v in E.CATALOG.items()}
            return self._json(dict(catalog=E.CATALOG, spec=spec, standard=E.STANDARD,
                                   profiles={k: v.get("desc", "") for k, v in load_profiles().items()},
                                   scenes=list(A.SCENES), templates=list(A.TEMPLATES), std_editable=STD_EDITABLE))
        if path.startswith("/files/"):
            parts = path.split("/")
            if len(parts) != 4 or ".." in parts:
                return self.send_error(HTTPStatus.BAD_REQUEST)
            _, _, key, fn = parts
            p = (CACHE / fn) if key == "_" else (CACHE / key / fn)
            dl = "dl=1" in (urlparse(self.path).query or "")
            return self._file(p.resolve(), download=dl)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        p = (WEB / rel).resolve()
        if WEB not in p.parents and p != WEB / "index.html":
            return self.send_error(HTTPStatus.FORBIDDEN)
        return self._file(p)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/build":
                return self._json(build(req["code"], req.get("params", {}), req.get("profile"), req.get("std") or {}))
            if path == "/api/scene":
                return self._json(scene(req["name"], req.get("profile")))
            if path == "/api/kit":
                return self._json(kit(req["items"], req.get("profile"), req.get("std") or {}))
            return self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as e:
            traceback.print_exc()
            return self._json(dict(error=f"{type(e).__name__}: {e}"), 400)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-warm", action="store_true", help="do not pre-build templates at startup")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"FrameTile Studio → http://{a.host}:{a.port}")
    if not a.no_warm:
        threading.Thread(target=_warm, daemon=True).start()
    srv.serve_forever()


def _warm():
    """pre-build templates so the first click is instant (results are cached on disk)."""
    for name in A.SCENES:
        try:
            t0 = time.time()
            r = scene(name, None)
            print(f"  template {name}: {'OK' if r['ok'] else 'FAIL'} ({time.time() - t0:.0f}s)", flush=True)
        except Exception as e:  # never kill the server
            print(f"  template {name}: {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
