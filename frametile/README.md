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
| Bo góc | ≥ R1 | góc ngoài tile R4 đồng tâm với lỗ góc, góc cửa sổ R2, chân tai C-90 R1 |
| In phẳng, không support | — | mọi chi tiết dựng sẵn theo hướng in; lỗ ngang làm teardrop; hốc đai ốc mở lên trên; vát 0.4 mm chống chân voi |

## Chi tiết
| Mã | Loại | Tham số |
|---|---|---|
| T-S / T-W / T-D / T-P | tile vuông: giằng chữ X / cửa sổ / giằng chéo / đặc | n, m, kiểu lỗ (perimeter · alternate · corners · grid) |
| T-A | tile hình thang (cạnh xiên) | n, m, k = số ô cạnh trên |
| T-U | tile vòm | n, m (cần m·8 − n·4 ≥ 8) |
| C-90 | ke góc mảnh: sống 3×3 + tai 3 mm xen kẽ (nằm / đứng), đầu tai R4 đồng tâm lỗ | số cặp vít (dài 16·n) |
| C-I / C-L / C-T / C-X | tấm nối phẳng 4 mm (thẳng / L / T / chữ thập) | số ô mỗi cánh |
| H-180 | bản lề 180°, 2 lá, chốt bằng vít M3 | dài n ô |
| M-H | moay-ơ: bích Ø32, 4 lỗ trên lưới, đai ốc trục nằm trong boss | cao boss |
| W-40 | bánh xe: vành (PLA) + lốp (TPU), quay trên trục M3 | Ø, bề rộng |

## Quy ước lắp 3D (C-90)
C-90 là **ke góc mảnh** (dài 16·n) đặt trong góc trong của hai tile vuông góc: một sống 3×3 chạy
dọc góc, các tai dày 3 mm luân phiên nằm trên tile B và dựng sát tile A, đầu tai bo R4 quanh lỗ
(thành 2.4 mm đều). Tai xen kẽ nên đai ốc của tai này nằm vào khoảng trống cạnh tai kia. Hai tile ghép
kiểu **"góc khuyết"**: mặt trong của tile này bắt đầu đúng ở mép tile kia, nên đường lỗ viền của cả
hai đều cách góc 4 mm. Vít của thanh cách mỗi mặt 4 mm nên rơi đúng lỗ viền ở **bất kỳ ô nào** dọc
cạnh. Vít M3×10 (tile 4 + tai 3 + đai ốc 2.4), đầu vít bên ngoài, đai ốc M3 lục giác bên trong. Sàn/mái nằm lọt trong vòng
tường; ở 4 góc đứng có rãnh khuyết 4×4 mm.

## Mẫu dựng sẵn (tab **Mẫu & lắp thử**)
| Mẫu | Kích thước | Gồm |
|---|---|---|
| Rover | 112×48 thân, bánh Ø40 | sàn T-W, nóc T-S, vách đặc T-P mang 4 cụm M-H + W-40, đầu/đuôi T-W, ke C-90 |
| Rocket | 48×48, cao 132 | đế + nắp T-P, tầng dưới T-P + 4 cánh T-A, tầng trên T-S, mũi chong chóng 4 lá T-A (nhọn ở mọi hướng), nối tầng bằng C-I |
| Building | 48×48, 3 tầng, cao 112 | tường cửa sổ T-W (tầng trệt 2 mặt giằng T-D), sàn T-P làm dải tầng, mái T-P, ke C-90 ở sàn, trần và 4 góc đứng |
| Hộp 5×5×5 | 48³ | 6 T-W + 12 C-90 |

Mỗi mẫu chỉ dùng chi tiết trong thư viện, mỗi họ chi tiết một màu nhựa gợi ý. App cắm vít đầy đủ (đầu vít, thân Ø3.0, đai ốc) vào mọi lỗ và kiểm tra 3 điều: không chi
tiết nào chồng nhau, không vít nào chạm vật liệu, **mỗi vít bắt ít nhất 2 chi tiết** (không lọt qua
cửa sổ). Nút "+ Thêm cả mẫu vào bộ in" chép BOM sang tab Bộ in để tải ZIP. Mẫu mới viết trong
`assembly.py` bằng các hàm `slab`, `wall`, `fin`, `bar`, `edge_bar`, `corner_bars`, `splice`, `wheel_unit`.

## Cấu trúc
```
engine.py         chuẩn + bộ sinh hình học (CadQuery), mọi chi tiết theo hướng in
drc.py            kiểm tra luật thiết kế trên hình học thật (thành lỗ, lưới, overhang, bám bàn in…)
assembly.py       mẫu dựng sẵn + cụm kiểm chứng + kiểm tra lắp được
server.py         HTTP server (stdlib) + API: /api/catalog /api/build /api/scene /api/kit
web/index.html    giao diện (Three.js): thư viện chi tiết, viewer 3D, DRC, dung sai, tải file, bộ in ZIP
test_frametile.py quét tham số
```
Bù dung sai dùng `print_profiles.json` của `cad-step`. Profile mặc định là ước lượng chung; nên in
coupon rồi chạy `z3d.sh calibrate`. Profile đã hiệu chuẩn sẽ tự hiện trong menu máy in.
