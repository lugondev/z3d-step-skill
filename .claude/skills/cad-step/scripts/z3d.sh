#!/usr/bin/env bash
# z3d.sh — runner for the cad-step toolkit.
# Usage: z3d.sh <command> [args...]
#   commands: build | step2stl | stl2step | inspect | analyze-mesh | render | compare | tol | calibrate | setup
# Finds (or creates) a Python env that has CadQuery + trimesh, then runs the matching script.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

has_cad() { "$1" -c "import cadquery, trimesh, networkx, rtree" >/dev/null 2>&1; }

find_py() {
  local c
  for c in "${Z3D_PY:-}" "$PWD/.venv/bin/python" "$HOME/.z3d-cad/venv/bin/python"; do
    [[ -n "$c" && -x "$c" ]] && has_cad "$c" && { echo "$c"; return 0; }
  done
  return 1
}

setup_env() {
  local venv="${Z3D_VENV:-$HOME/.z3d-cad/venv}"
  echo "[z3d] creating CAD env at $venv (Python 3.12 + cadquery + trimesh)..." >&2
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 "$venv" >&2
    uv pip install --python "$venv/bin/python" cadquery trimesh numpy scipy matplotlib networkx rtree shapely fast-simplification >&2
  else
    local base; base="$(command -v python3.12 || command -v python3.11 || true)"
    [[ -z "$base" ]] && { echo "[z3d] need 'uv' or python3.11/3.12 (cadquery has no wheels for newer Python)" >&2; exit 1; }
    "$base" -m venv "$venv" && "$venv/bin/pip" install -q cadquery trimesh numpy scipy matplotlib networkx rtree shapely fast-simplification >&2
  fi
  echo "$venv/bin/python"
}

cmd="${1:-help}"; shift || true
if [[ "$cmd" == "setup" ]]; then PY="$(find_py || setup_env)"; echo "[z3d] python: $PY"; exit 0; fi
PY="$(find_py || setup_env)"

case "$cmd" in
  build)        exec "$PY" "$HERE/build.py" "$@" ;;
  step2stl)     exec "$PY" "$HERE/step2stl.py" "$@" ;;
  stl2step)     exec "$PY" "$HERE/stl2step.py" "$@" ;;
  inspect)      exec "$PY" "$HERE/inspect_model.py" "$@" ;;
  analyze-mesh) exec "$PY" "$HERE/mesh_analyze.py" "$@" ;;
  render)       exec "$PY" "$HERE/render.py" "$@" ;;
  compare)      exec "$PY" "$HERE/compare.py" "$@" ;;
  tol)          exec "$PY" "$HERE/tolerance.py" "$@" ;;
  calibrate)    exec "$PY" "$HERE/calibrate.py" "$@" ;;
  py)           exec "$PY" "$@" ;;
  *) sed -n '2,6p' "$0"; exit 1 ;;
esac
