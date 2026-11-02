# PLAN-139 — Xe Tết: cả đám đông vẽ một lượt

- Status: Code + đo xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: hỏi vẽ / ảnh / GIF cái nào nhẹ; em đề xuất bước 1 gom người; anh «oke em làm bước 1»)

## Vấn đề
Mỗi người đi bộ / đứng = khối thân + 4 tay chân + vệt bóng = 6 lượt vẽ. Trạm dừng ~40 người ≈ 240 lượt → máy anh 22 khung/s
(đường 30).

## Cách làm
- Không chụp thành ảnh phẳng (camera nhìn từ trên cao / bên hông sẽ lộ hình dán). Dùng vẽ lặp (instancing) người 3D thật:
  một khối người mẫu đủ mọi phần (nón lá, mũ len, ba lô), mỗi người có số riêng: màu áo / quần / mũ / ba lô, kiểu mũ, độ vung
  tay chân, tay vẫy. Shader tô màu, xoay tay chân quanh vai / hông, co phần không có về 0; uốn theo đường như mọi vật.
- `makePerson` trả nhóm rỗng làm mỏ neo (vị trí, nhãn tên, thùng quà đội đầu giữ như cũ); vào cảnh → có trong đám đông, rời
  cảnh → ra (sự kiện added / removed, không rò). Mỗi khung: tính ma trận cả cảnh một lần → chép vào bản vẽ lặp → vẽ.
- Đầu trên gối trong xe giữ cách cũ.
- Phạm vi: `art.ts`, `scene.ts`, `bend.ts` (tách `bendShader` dùng chung).

## Proof
- Đo trên 8811 (SwiftShader, `scratchpad/crowd_measure.py`, cùng kịch bản bản cũ / mới):
  | Cảnh | Bản cũ | Bản mới |
  |---|---|---|
  | Bến trống (5 người cảnh nền) | 257 lượt vẽ | 229 |
  | Bến 24 người lên xe | 395 | 229 |
  | Trạm dừng trống | 193 | 194 |
  | Trạm dừng 40 người | 433 | 196 |
  Số tam giác tăng (127k → 154k) vì mỗi người mang cả nón / mũ / ba lô đã co về 0 — tam giác suy biến, card không tô.
  Khung/s trên SwiftShader (vẽ bằng CPU) không phản ánh máy anh; cần anh đo `/?fps=1` trên GPU thật.
- Ảnh so cũ / mới: người giữ nguyên nón lá, mũ len + quả bông, ba lô, màu áo; gia đình ở cổng, người đi bộ, thả khách đúng.
- `npm run build` (tsc) sạch; e2e control_panel 28/28 (lần chạy cùng lúc UX: 27/28 «khoảng cách +0,2» — bấm thu phóng chờ
  0,8 giây lúc máy bận, chạy riêng đạt), ux_scenarios 0 lỗi, 0 lỗi JS.
