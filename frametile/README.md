# FrameTile Studio (MK1)

Webapp chạy local để sinh **khung (tile) và chốt (connector)** của hệ FrameTile MK1. Mọi chi tiết
dùng chung một chuẩn thiết kế nên luôn lắp được với nhau. Mỗi lần tạo chi tiết, app xuất STEP/STL
danh nghĩa và bản đã bù dung sai in, đồng thời chạy kiểm tra luật thiết kế (DRC) trên hình học thật.

```bash
cd frametile
../.venv/bin/python server.py            # hoặc: ../.claude/skills/cad-step/scripts/z3d.sh py server.py
# mở http://127.0.0.1:8765
../.venv/bin/python test_frametile.py    # quét toàn bộ tham số + 3 cụm lắp (≈3–5 phút); --quick cho nhanh
```
Không cần cài thêm gói nào ngoài môi trường CadQuery của skill `cad-step`. Three.js đã nằm sẵn trong `web/vendor/` nên app chạy được khi không có mạng.

## Chuẩn thiết kế (khoá cứng)
| Luật | Giá trị | Cách engine đảm bảo |
|---|---|---|
| Lưới | 8 mm | kích thước tile = 8·n; **mọi trục vít đi qua tâm ô (4 + 8k)** |
| Bulông | M3, lỗ Ø3.2 danh nghĩa | bản in: lỗ đứng/ngang được bù theo profile máy in |
| Dày tile | 4.0 mm | = 20 lớp × 0.2 |
| Thành | ≥ 2.4 mm | viền tile = khung xương lỗ offset 4 mm, nên lỗ cách mép đúng 2.4 mm; DRC đo lại bằng hình vành khuyên |
| Bo góc | ≥ R1 | góc ngoài tile R4 đồng tâm với lỗ góc, góc cửa sổ R2, C-90 R1/R2 |
| In phẳng, không support | — | mọi chi tiết dựng sẵn theo hướng in; lỗ ngang làm teardrop; khe đai ốc mở lên trên; vát 0.4 mm chống chân voi |

## Chi tiết
| Mã | Loại | Tham số |
|---|---|---|
| T-S / T-W / T-D / T-P | tile vuông: giằng chữ X / cửa sổ / giằng chéo / đặc | n, m, kiểu lỗ (perimeter · alternate · corners · grid) |
| T-A | tile hình thang (cạnh xiên) | n, m, k = số ô cạnh trên |
| T-U | tile vòm | n, m (cần m·8 − n·4 ≥ 8) |
| C-90 | chốt góc 3D, 2 đai ốc M3 nằm trong khe | số lỗ mỗi cánh |
| C-I / C-L / C-T / C-X | tấm nối phẳng 4 mm (thẳng / L / T / chữ thập) | số ô mỗi cánh |
| H-180 | bản lề 180°, 2 lá, chốt bằng vít M3 | dài n ô |
| M-H | moay-ơ: bích Ø32, 4 lỗ trên lưới, đai ốc trục nằm trong boss | cao boss |
| W-40 | bánh xe: vành (PLA) + lốp (TPU), quay trên trục M3 | Ø, bề rộng |

## Quy ước lắp 3D (C-90)
Tile tường **đứng trên** tile sàn, mặt ngoài tường thẳng hàng với mép sàn. C-90 nằm ở góc trong:
vít sàn ở ô thứ 3 tính từ mép (cách mép 20 mm), vít tường ở ô thứ 2 tính từ mặt sàn (cao 12 mm).
Vít M3×16 + đai ốc thả vào khe. Tab **Lắp thử** dựng cụm này (cùng cụm C-X và bánh xe), cắm vít Ø3.0
vào mọi lỗ và kiểm tra va chạm.

## Cấu trúc
```
engine.py         chuẩn + bộ sinh hình học (CadQuery), mọi chi tiết theo hướng in
drc.py            kiểm tra luật thiết kế trên hình học thật (thành lỗ, lưới, overhang, bám bàn in…)
assembly.py       cụm lắp kiểm chứng + kiểm tra va chạm
server.py         HTTP server (stdlib) + API: /api/catalog /api/build /api/scene /api/kit
web/index.html    giao diện (Three.js): thư viện chi tiết, viewer 3D, DRC, dung sai, tải file, bộ in ZIP
test_frametile.py quét tham số
```
Bù dung sai dùng `print_profiles.json` của `cad-step`. Profile mặc định là ước lượng chung; nên in
coupon rồi chạy `z3d.sh calibrate`. Profile đã hiệu chuẩn sẽ tự hiện trong menu máy in.
