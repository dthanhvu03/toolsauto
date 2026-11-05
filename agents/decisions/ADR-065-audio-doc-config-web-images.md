# ADR-065: Audio→Doc — cấu hình trên web, chia cảnh theo audio, ảnh internet có giấy phép

## Status
Accepted 05/11/2026 (chủ bot duyệt trực tiếp, PLAN-157). Bổ sung / thay một phần ADR-064.

## Context
POC ADR-064 viết cứng gần hết tham số (kịch bản MU–Roma, khung 1920×1080, preview 60s, cảnh 7s, phụ đề,
Ken Burns, luật quyền), chỉ nhận ảnh tải tay, không chọn ngôn ngữ. Chủ bot muốn: thời gian theo đúng audio tải lên,
chọn được ngôn ngữ, cảnh nào tải ảnh / cảnh nào lấy từ internet, mọi tham số chỉnh trên web không sửa code.

## Decision
1. **Cấu hình = `app/core/settings.py`**, section «Studio — Audio→Doc» (key `doc.*`), sửa ở /app/settings, lưu DB +
   nhật ký, `get()` cache 3s → không cần restart. Một chỗ đọc: `studio/doc/config.py` (`DocConfig`); module khác chỉ nhận
   `DocConfig`. Key nguồn ảnh là `is_secret` + `keep_blank`.
2. **Chia cảnh theo audio** (`doc/seed.py`): cảnh bám câu Whisper (gộp tới `shot_sec`, cắt quá `shot_max_sec`, gộp dưới
   `shot_min_sec`), đoạn ý tách ở khoảng lặng ≥ `beat_pause_sec` hoặc dài ≥ `beat_max_sec`; không lời → chia đều.
   Bản dựng mặc định toàn bộ audio (`preview_sec=0`). Bỏ kịch bản MU–Roma.
3. **Ngôn ngữ chọn khi tải lên** → `payload.language` → `analyze` truyền cho Whisper; trống / `auto` = tự nhận.
4. **Ảnh internet = gợi ý, người bấm chọn.** 5 nguồn (`doc/images/providers.py`): Wikimedia Commons, Openverse (không key),
   Pexels, Pixabay, Google Custom Search (cần key). Tìm khi mở cảnh (không quét cả bài), lưu kết quả vào DocState.
   AI (`AIUseCases`, purpose `doc_keywords`) đề xuất từ khóa từng cảnh ở bước `doc_plan`; lỗi AI → để trống.
5. **Quyền tự điền theo giấy phép** (`doc/images/licenses.py`): giấy phép trong `doc.auto_verify_licenses` (mặc định
   cc0, pdm, cc-by, cc-by-sa, pexels, pixabay) → `RIGHTS_VERIFIED` + bằng chứng = trang nguồn + link giấy phép;
   NC / ND → `RIGHTS_RESTRICTED`; Google / không rõ → `RIGHTS_UNKNOWN` (người tự kiểm). Ảnh tải tay mặc định `RIGHTS_UNKNOWN`.
6. **Ken Burns theo spec** (`ProjectSpec.motion: KenBurns`): graph vẫn là hàm thuần; tốc độ zoom tính theo giây
   (`zoom_per_sec / fps`). Mặc định = số cũ → dự án cũ không đổi.
7. **Dựng theo đoạn** (`render/__init__.py`): video toàn ảnh tĩnh quá `studio.segment_render_over` cảnh (mặc định 12)
   → dựng từng cảnh, ghép concat copy, lượt cuối 1 input. Lý do: mỗi input ffmpeg mở cùng lúc ~40 MB, bài 9 phút
   ~80 cảnh ≈ 3,6 GB — quá RAM máy (7,7 GB, không swap, sập 05/11).

## Giữ cố định trong code
Tên trạng thái quyền, tên chuyển động (kiểu dữ liệu); giới hạn 255 / 500 ký tự (cột DB); đuôi ảnh jpg / png / webp
(ffmpeg pipeline); đường dẫn lưu theo `paths.ROOT`; URL API các nguồn ảnh.

## Consequences
- Được: chủ bot tự chỉnh mọi thứ trên web; bài dài dựng được trên máy yếu; ảnh có nguồn + giấy phép ghi vào `credits.json`.
- Mất / nợ: dựng theo đoạn mã hoá 2 lần (chậm hơn); Google Images luôn phải kiểm quyền tay; DocState gắn theo asset audio
  (cùng file tải lại dùng lại bản chép lời cũ, kể cả khi chọn ngôn ngữ khác); chưa có tự kiểm chứng thông tin (fact-check).
