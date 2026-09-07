# ADR-018 — Xưởng nội dung chạy được KHÔNG cần account Facebook (trạng thái `READY`)

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — hệ quả trực tiếp của giao việc "anh cần tải được nhiều nguồn"
  (ADR-017) và hướng C Owner chốt 2026-09-05 (xưởng nội dung + đăng tay)
- **Liên quan**: ADR-017, ADR-016, handoff 2026-09-05 (d)

## Bối cảnh

`processor._process_viral_materials` (dòng ~463): không có account Facebook
`is_active + login_status=ACTIVE` thì **return ngay**, trước cả bước tải. Lý do lịch sử:
sau reup, pipeline tạo `Job(account_id=…)` để đăng tự động, rồi mới đánh dấu material
`DRAFTED`.

Account duy nhất đã bị khoá vĩnh viễn và được vô hiệu trong DB (05/09). Hệ quả: **toàn
bộ xưởng nội dung đang đứng** — dán link (ADR-017) hay quét kênh đều tạo material NEW
rồi không ai xử lý. Điều này trái với hướng C Owner đã chốt: dùng tool cho xưởng nội
dung, đăng tay, tự động đăng để sau.

Handoff phiên này từng ghi "xưởng nội dung ✅ chạy" — **sai**, sửa ở đây.

## Quyết định

1. Thêm `ViralStatus.READY` = "tải + reup xong, **chưa có job**, sẵn sàng đăng tay".
2. `_process_viral_materials`: không có `default_account` → **không return**; vẫn tải +
   reup (+ các lớp ADR-016) như thường; tới bước tạo Job: không account ⇒ **bỏ tạo Job**,
   `mat.status = READY`, log info. Có account ⇒ đường cũ y nguyên (Job + `DRAFTED`).
3. UI `/app/viral`: badge `READY` màu riêng; hàng READY có nút **"Tải file"** (dùng
   `reup-preview` sẵn có) và **"Xem thumbnail"**; bộ lọc trạng thái có READY.
4. Sweep nền + nút "Xử lý mới" coi READY là **đã xong** (không nhặt lại). `process_material`
   từ chối READY như DRAFTED ("đã xử lý, tải file ở nút…").
5. Khi sau này có account: material READY → Job là việc riêng (PLAN sau); không làm ở đây.

## Phạm vi

| Việc | File |
|---|---|
| Enum | `app/constants.py` |
| Nhánh không account (≤15 dòng) | `app/features/viral_intake/processor.py` |
| Từ chối READY | `app/features/viral_intake/service.py` (`check_processable`) |
| Badge + nút tải + lọc | `app/templates/fragments/viral_row.html`, `app/templates/pages/app_viral.html`, `app/templates/fragments/app_viral_table.html` (nếu bộ lọc ở đó) |
| Test | `tests/test_viral_ready_without_account.py` (mới) |
| Proof | dán 1 link thật qua `add-link` trên Postgres thật → `READY` + file reup + thumbnail |

## Ngoài phạm vi

- Không tạo Job không account. Không đụng publisher/queue. Không đổi nghĩa REUP/DRAFTED.
- Không chuyển READY → Job khi có account (PLAN sau).
- Không sửa `strategic.py` / maintenance sweep ngoài việc coi READY là xong.

## Đường lùi

Bỏ nhánh không-account trong processor ⇒ hành vi cũ (return sớm). Material READY còn trong
DB chỉ là dữ liệu, không ảnh hưởng queue (không có Job nào trỏ tới).

## Hết hiệu lực

Sau proof: 1 link thật → `READY`, file reup mở được, nút "Tải file" hoạt động.
