# PLAN-127 — Xe Tết: nhạc riêng từng xe + tiếng hiệu ứng

- Status: Done (chờ anh nghe thử)
- Executor: Claude Code (anh chốt 01/11: nguồn nhạc «cả hai», phạm vi «nhạc riêng từng xe» + «tiếng hiệu ứng»)

## Vấn đề

Overlay chưa có âm thanh nào. TikTok LIVE tắt tiếng / báo vi phạm khi phát nhạc có bản quyền (bài Tết nổi tiếng).

## Scope

1. **Nhạc có sẵn — tự sinh bằng code** (Web Audio): giai điệu ngũ cung, tiếng đàn tranh / sáo / trống / mõ, mỗi bài một
   hạt giống + nhịp + điệu khác nhau. Là nhạc của mình nên không vướng bản quyền, không phải tải file của ai.
2. **Nhạc của anh:** tải lên ngay trên `/control` (anh đề xuất 01/11; mp3 / ogg / m4a / wav, ≤ 200 MB / file, 🗑 xoá, chọn bài cho từng xe bằng danh sách thả xuống) hoặc
   chép vào `storage/media/xe_tet/music/` → server tự đưa vào danh sách.
3. **Mỗi xe một đài:** xe chính và từng xe tăng cường có bài riêng; tiếng phát theo xe đang chiếu. Admin (`/control`):
   bật / tắt nhạc, qua bài từng xe; âm lượng nhạc / hiệu ứng chung (lưu ở `storage/db/config/xe_tet.json`).
4. **Tiếng hiệu ứng (tự sinh):** còi xe khi xuất bến / sắp chạy ở trạm, pháo hoa, tiếng máy theo tốc độ, vào hầm nhạc bị
   «bịt» lại, «ting» khi có vé (giới hạn tần suất).
5. Trình duyệt chặn tự phát tiếng tới khi có cú bấm: overlay hiện 🔇 nhỏ tới khi bấm một lần; README ghi cờ Chrome
   `--autoplay-policy=no-user-gesture-required` cho cửa sổ live.

## Kiểm

Test server (bài theo từng xe, qua bài, bật / tắt, danh sách file); dựng nhạc offline (OfflineAudioContext) đo không
câm / không vỡ tiếng; e2e; ảnh bảng điều khiển.

## Proof (01/11)

- 6 bài tự sinh dựng offline 20 giây / bài (Chromium, OfflineAudioContext): không đoạn im nào ≥ 1 giây, đỉnh ≤ 0,39 ở âm
  lượng 0,5 (không vỡ tiếng); hạ sáo 0,22 → 0,13 cho đều tai với đàn tranh. File nghe thử «Xuân về trên phố» (20 giây).
- Trang live: 🔇 hiện tới khi bấm một lần rồi ẩn; /control đổi bài + tắt nhạc xe chính + kéo âm lượng: state đổi đúng, 0 lỗi.
- `pytest` 93 passed (thêm: mỗi xe một đài + tiếng theo xe đang chiếu; danh sách bài = bài tự sinh + file nhạc, bỏ file
  không phải nhạc; API qua bài / tắt nhạc / âm lượng kẹp 0–1). E2E bảng điều khiển 28/28. `ruff` + `tsc` + build sạch.
- Tải lên trên /control (Chromium thật): tải «Nhạc thử của anh.wav» → hiện trong danh sách → ⏭ Bài cho xe chính →
  màn hình live tải /music/… (206) → 🗑 xoá; 0 lỗi. Test: trùng tên không ghi đè, `../` không thoát thư mục, sai đuôi /
  rỗng → 400, quá cỡ → 413 (không để lại file dở). 94 test, e2e 28/28.
- Không kiểm được bằng tai trên máy chủ (không loa) — anh nghe thử trên máy anh.
