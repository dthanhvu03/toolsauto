# ADR-024 — Chống trùng nội dung: bỏ qua chép Drive thừa + phát hiện video trùng ở tầng material

- **Ngày**: 2026-09-08
- **Trạng thái**: **ĐÃ DUYỆT** — Owner hỏi "có quét trùng không", nghe phân tích rồi chốt "cả 2"
- **Liên quan**: ADR-023 (chép Drive), ADR-017/018/019, PLAN-041 (guard theo hash ở tầng **job**)

## Bối cảnh

Rà 2026-09-08, tool chống trùng ở **hai tầng**, và thiếu đúng tầng ở giữa:

| Tầng | Hiện có | Bắt được gì |
|---|---|---|
| Link | `viral_materials.url` UNIQUE + chuẩn hoá | Dán lại / quét lại cùng URL |
| **Nội dung ở tầng material** | **KHÔNG có** | — |
| Nội dung ở tầng job | `sha256` + 2 unique index (ADR-020) | Cùng file lên cùng một Page |

Hệ quả thật: cùng một video xuất hiện ở hai kênh nguồn ⇒ **hai material, tải hai lần, chạy
ffmpeg hai lần, chép Drive hai bản**. Và mỗi lần bấm *Reup lại* là **tải lên Drive lại từ
đầu** dù nội dung y hệt (video ~30 MB).

**Điểm quan trọng về kỹ thuật:** `sha256` chỉ bắt file **giống hệt từng byte**. Cùng một
video đăng lại ở nền tảng khác luôn bị mã hoá lại ⇒ sha256 khác nhau ⇒ **sha256 gần như
không bao giờ bắt được ca Owner quan tâm**. Thứ bắt được là **pHash** (băm tri giác theo
khung hình) — và tool **đã có sẵn** `VideoProtector.extract_phash(path, num_frames=5)`
dùng `imagehash.phash`, hiện chỉ dùng cho bằng chứng bản quyền. Nên ADR này dùng **cả hai**:
sha256 cho ca giống hệt (rẻ, chắc chắn), pHash cho ca mã hoá lại.

## Quyết định

### 1. Chép Drive: bỏ qua khi bản đích đã y hệt
`offsite.copy_out`: trước khi `copy2`, nếu file đích **đã tồn tại và cùng kích thước** ⇒ bỏ
qua, ghi log `debug`, trả về đường dẫn đích. Tiết kiệm băng thông khi *Reup lại* hoặc chạy
lại cùng material. Không so nội dung vì tên file đã gắn `material_id` — cùng tên + cùng cỡ
là cùng bản.

### 2. Phát hiện trùng ở tầng material
- Hai cột mới trên `viral_materials`: `content_hash` (sha256 file **nguồn** sau khi tải) và
  `phash` (TEXT, JSON `{"1.23s": "hex", …}` của 5 khung).
- Tính **ngay sau khi tải xong, TRƯỚC khi reup** — mục đích chính là **không tốn ffmpeg**.
- So với các material đã có (`READY`, `DRAFTED`, `REUP`):
  - trùng `content_hash` ⇒ trùng chắc chắn;
  - hoặc pHash: so từng khung theo thứ tự, lấy **trung vị** khoảng cách Hamming, `<= 8`
    (trên 64 bit) ⇒ coi là trùng. Ngưỡng để trong `SettingSpec` để Owner chỉnh.
- Trùng ⇒ `status = ViralStatus.DUPLICATE` (**trạng thái mới**), `last_error` ghi
  `"Trùng nội dung với #N"`, xoá file vừa tải, **không** reup, **không** tạo job.
- `DUPLICATE` không nằm trong tập sweep nhặt (`NEW`/`REUP`/`FAILED`) nên không bị xử lý lại.

### 3. UI
Badge `DUPLICATE` màu trung tính + tooltip "trùng với #N"; thêm vào bộ lọc trạng thái và
dãy chip đếm; hàng trùng không có nút Tải file (không có file).

## Phạm vi

| Việc | File |
|---|---|
| Bỏ qua chép thừa | `app/core/storage/offsite.py` |
| Enum trạng thái | `app/constants.py` |
| 2 cột + migration | `app/core/database/models/viral.py`, `alembic/versions/<new>_material_dedup.py` (head `m1b8c9d0e1f2`) |
| Tính hash + so trùng | `app/features/viral_intake/processor.py`, helper mới `app/features/viral_intake/dedup.py` |
| Ngưỡng pHash | `app/core/settings.py` (`viral.phash_max_distance`, mặc định 8) |
| Badge + lọc + đếm | `app/templates/fragments/viral_row.html`, `app_viral_table.html`, `pages/app_viral.html` |
| Test | `tests/test_material_dedup.py`, `tests/test_offsite_video.py` (bổ sung) |

## Ngoài phạm vi

- Không đụng guard/index ở tầng job (ADR-020 giữ nguyên).
- Không so trùng **âm thanh**.
- Không gộp/xoá material trùng đã có sẵn trong DB (chỉ áp cho video mới từ đây).
- Không dọn bản cũ bên Drive (nợ ADR-012).

## Hết hiệu lực

Sau proof: (a) chép Drive lần hai cùng file ⇒ bỏ qua, không tải lên lại; (b) đưa **cùng một
video qua hai URL khác nhau** ⇒ material thứ hai thành `DUPLICATE`, **không chạy ffmpeg**,
ghi rõ trùng với #N.
