# z3d-step-skill

Hai skill cho Claude Code (trong `.claude/skills/`):

| Skill | Làm gì |
|---|---|
| **cad-step** | Tạo model STEP có tham số (CadQuery/OpenCASCADE) để in 3D, **tính dung sai in 3D** (ISO 286, bù kích thước theo công nghệ in, thiết kế lắp ghép, chuỗi kích thước, hiệu chuẩn máy in), STEP → STL, STL → STEP |
| **cad-vision** | Phân tích bản vẽ kỹ thuật / ảnh chụp vật thể → spec kích thước + dung sai (YAML) → bảng dung sai in 3D → dựng STEP danh nghĩa + STEP/STL đã bù → render so với ảnh gốc |

## Cài đặt
Lần chạy đầu tiên tự tạo môi trường Python 3.12 tại `~/.z3d-cad/venv` (cần `uv` hoặc python3.11/3.12):
```bash
.claude/skills/cad-step/scripts/z3d.sh setup
```
Muốn dùng skill ở mọi project: copy hai thư mục `cad-step` và `cad-vision` vào `~/.claude/skills/`.

## Lệnh
```bash
Z3D=.claude/skills/cad-step/scripts/z3d.sh
$Z3D build model.py -o out/part.step --stl out/part.stl --preview out/part.png -p L=120
$Z3D step2stl in.step out.stl --tol 0.01
$Z3D stl2step in.stl out.step
$Z3D inspect file.step            # kích thước, thể tích, danh sách lỗ (Ø, trục, tâm)
$Z3D analyze-mesh file.stl        # mặt phẳng chính, mặt cắt, fit đường tròn → dựng lại có tham số
$Z3D render file.step -o v.png --views iso,front,top,right
$Z3D compare ref.stl rebuilt.step # sai lệch thể tích + bề mặt

# Dung sai in 3D
$Z3D tol profiles                          # fdm_pla, fdm_petg, fdm_abs, sla_resin, sls_pa12, mjf_pa12 (+ profile đã hiệu chuẩn)
$Z3D tol iso 25H7                          # tra dung sai ISO 286
$Z3D tol fit 25 H7/g6 -P fdm_pla           # phân tích lắp ghép + in được không
$Z3D tol comp "25H7" hole                  # 1 kích thước → kích thước model + kết luận OK/MARGINAL/POST-PROCESS
$Z3D tol pfit 8 slide --mate bought        # lỗ trượt trên trục thép Ø8 → Ø model
$Z3D tol stack +50±0.2 -20±0.1 -29.5±0.1   # chuỗi kích thước (worst case + RSS)
$Z3D tol table spec.yaml --out print_params.json   # cả bản vẽ → bảng dung sai + tham số model
$Z3D build part.py -o part_print.step --params print_params.json

# Hiệu chuẩn máy in (nên làm — profile mặc định chỉ là giá trị ước lượng)
$Z3D calibrate make calib/                 # in coupon.stl, đo bằng thước kẹp, điền measure.csv
$Z3D calibrate fit calib/measure.csv --name may_in_cua_toi
```
Trong model: `from printlib import PrintProfile, teardrop_hole, nut_trap, INSERT` (lỗ lắp ghép, lỗ ngang teardrop, hốc đai ốc, lỗ insert nhiệt).

## Ví dụ
`examples/flange/`: bản vẽ mặt bích → `spec.yaml` (có dung sai) → `tol table` → `out/print_params.json` → `out/flange.step` (danh nghĩa) + `out/flange_print.step/.stl` (đã bù cho FDM PLA).

## Ví dụ prompt
- "Tạo file STEP tấm đế 120×80×8, 4 lỗ M6 cách mép 10, bo góc R5"
- "Chuyển `part.step` sang STL để in 3D"
- "Chuyển `scan.stl` sang STEP" / "dựng lại `bracket.stl` thành model có tham số"
- "Dựng 3D từ bản vẽ này để in PETG: `drawing.png`"
- "Lỗ lắp vòng bi 608 in FDM thì vẽ Ø bao nhiêu?"
- "Từ ảnh chụp cái giá đỡ này tạo file STEP, chiều rộng thật là 40mm"
