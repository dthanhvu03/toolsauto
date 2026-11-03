# PLAN-133 — Xe Tết: hết khựng khi bắn pháo hoa, nhẹ GPU, nhạc không phụ thuộc luồng chính

- Status: Done — bước 1–7 đã nạp 8810 (anh duyệt 01/11).
- Executor: Claude Code (anh yêu cầu 01/11: «10 vai phản biện, giảm giật lag, tối ưu code, thuật toán» → «triển khai đi»)

## Đo trước khi sửa (01/11, máy thử 8811, Chromium SwiftShader, `?res=0.5`, chất lượng Cao, giả lập 6 sự kiện / giây)
- 30 % thời gian luồng chính là biên dịch shader (`getProgramInfoLog` 17 % + `getShaderInfoLog` 13 %), 24 long task > 50 ms.
- Sau khởi động: 25 lần link chương trình shader, 11 lần xoá, 12 lần link lại đúng mã đã biên dịch.
- Thủ phạm: pháo hoa (vật liệu mới mỗi chùm, `dispose()` → three xoá chương trình → chùm sau biên dịch lại; `bendTree`
  2 giây / lần đổi vật liệu đang bay sang bản «uốn»). Thêm: người đi bộ / túi quà mới tạo vẽ bản chưa uốn trước;
  cây đào / mai đầu ngõ dựng lần đầu lúc thả khách; three 0.187 bỏ `PCFSoftShadowMap` (tự đổi sang PCF ở lượt vẽ bóng đầu)
  nên biên dịch sẵn theo PCFSoft ra nhầm biến thể.
- Server không phải nguồn giật: `tick` 11 µs, `snapshot` 0,5 ms, `json.dumps` 0,1 ms; khung state 9,2 KB.
- Thứ tự ghé (`Network.plan`, tham lam) trên 3.000 chuyến thật: +3,1 % km so tối ưu nhưng tổng km chờ chỉ +0,84 % → giữ.

## Đã làm
1. `effects.ts`: pháo hoa dùng bể đối tượng — 10 quả + 10 chùm cấp sẵn (hình + vật liệu dùng lại, không `dispose`), uốn
   cùng lượt `bendTree` đầu tiên.
2. `scene.ts` `warmUp()`: hiện tạm mọi vật → `compileAsync` → ép dựng xong (`program.getUniforms()`, cho máy không có
   `KHR_parallel_shader_compile`) → một lượt vẽ (shader bóng đổ) → trả lại trạng thái ẩn / hiện. `main.ts` chờ warmUp xong
   mới nối server + chạy vòng vẽ. `shadowMap.type = PCFShadowMap` (hình như cũ). `addWalker` / túi quà uốn ngay khi tạo.
   `sets.ts`: dựng sẵn cả cây đào lẫn mai, `setPlace` chỉ bật / tắt.
3. Vệt quả pháo: cửa sổ trượt 8 điểm trên bộ đệm cấp sẵn (`copyWithin`), bỏ `clone()` + `push/shift` mỗi khung.
4. `music.ts`: bài tự sinh dựng sẵn bằng `OfflineAudioContext` (đuôi nốt cuối cộng vòng về đầu → lặp liền mạch), phát
   `AudioBufferSourceNode` lặp; giữ 2 bài gần nhất (Map theo thứ tự dùng, ~10 MB / bài); dựng lỗi → lên lịch nốt như cũ.
5. `main.ts`: vẽ theo lịch 33,3 ms (cộng dồn) thay ngưỡng «cách khung trước ≥ 31 ms».
6. `app.py`: `Outbox` mỗi màn hình — vòng game chỉ bỏ khung vào hàng; state mới ghi đè state cũ chưa gửi ngay tại chỗ (giữ
   thứ tự với sự kiện); JSON mã hoá một lần; tràn 64 khung hoặc gửi > 1 giây → đóng, overlay tự nối lại.

## Proof (01/11, bản sao `xe_tet` trong scratchpad build riêng, chạy 8811 — `dist/` của 8810 không đụng)
- Link shader sau khởi động: 25 → **0** trong 150 giây (qua bến / đường / trạm / thả khách); khởi động 18 → 24 chương trình
  (biên dịch sẵn, trước đó PCFSoft làm ra 41).
- CPU luồng chính (đo từ giây 20, 40 giây): bận 42 % → **8 %**; `getProgramInfoLog` 17 % → 0; phần còn lại là `(program)`
  (SwiftShader giả lập GPU bằng CPU) + dọn rác.
- Pháo hoa: ảnh 2 đợt liên tiếp nổ đủ màu có đuôi, nổ xong ẩn, đợt sau dùng lại bể. Nhạc: đỉnh 0,93 qua AnalyserNode khi
  xe đứng bến (máy xe tắt). 0 lỗi trang.
- Nhịp khung mô phỏng (rAF lệch ±0,75 ms): 60 / 75 / 100 / 120 / 144 / 165 Hz → 30,1 khung/giây (cũ 30 / 25 / 25 / 30 /
  28,8 / 27,8).
- pytest 117 passed (thêm 2 test `Outbox`); ruff + tsc + build sạch; e2e control_panel PASS 28 / FAIL 0 / JS errors [];
  ux_scenarios ERRORS [] NOTES (không có).
- Ghi chú: 1 / 31 lần chạy pytest đỏ `test_music_upload_and_delete_from_control` (bộ nhớ đệm theo mtime thư mục nhạc) —
  có sẵn từ trước, 15 / 15 lần trên code gốc và 15 / 15 lần code mới đều xanh; không liên quan PLAN này.

## Bước 7 — theo số đo thật của anh (01/11, Chrome Windows, chất lượng Cao)
- Đường 30 khung/s (362–367 lần vẽ), trạm dừng ~25 người 30 khung/s (609), trạm dừng ~40 người + «bao cả xe» **22 khung/s**
  (772 lần vẽ, 235k tam giác). Nhà ven đường / Lambert không phải chỗ nghẽn → bỏ; nghẽn là đám đông ở trạm.
- Mỗi người đi bộ ~11 lần vẽ (thân + 4 tay chân + vệt bóng giả, thêm 5 ở lượt bóng thật). Tên đè nhau do xếp chỗ trùng:
  16 ghế xếp xoay vòng (`turn % 16`), hàng WC từ người thứ 10 đứng chồng một điểm (`Math.min(i, 8)`).
- Anh chọn (01/11): **bỏ bóng thật của người** (đã có vệt bóng giả dưới chân) + **xếp chỗ không trùng + đẩy nhãn**.
  1. Người không đổ bóng thật (cả người chờ ở bến, gia đình đầu ngõ): 11 → 6 lần vẽ / người.
  2. Trạm: cấp chỗ bằng danh sách chỗ trống (ghế trống trước, hết ghế thì đứng quanh bàn), về xe thì trả chỗ; hàng WC
     xuống dòng mỗi 9 người.
  3. Nhãn tên người đi bộ còn chạm nhau thì đẩy lệch lên (xếp từ dưới màn hình lên, kích thước nhãn đo một lần).
- Không làm: Lambert, gộp khối nhà, mặc định «Vừa» (Cao đủ 30 khung/s ngoài trạm đông).
- Proof bước 7 (8811, bản sao build riêng): trạm 0 người 328 lần vẽ → 45 người 598 (~6 / người, trước ~11); ảnh 10 / 16 /
  22 giây sau đợt comment: tên ở sân đứng ăn + hàng WC tách được, góc quầy / 16 ghế sát nhau vẫn chật khi 45 người tới
  trong 7 giây (nhãn đẩy tối đa 140 px). pytest 117, ruff + tsc sạch, e2e control_panel 28/28, ux_scenarios 0 lỗi.
- Bộ nhớ: overlay 12 phút / 8 chuyến — hình 208 → 367 rồi đứng (dựng vùng một lần), ảnh 59, heap 26 MB → không rò.
  Server 6 giờ giả lập 15.000 người xem → 8,7 MB (~300 B / người xem).
