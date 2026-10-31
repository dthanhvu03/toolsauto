# PLAN-109: DocType — loại dữ liệu cấu hình trên web (kiểu Frappe)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-109 |
| **Status** | Approved — anh giao 31/10 («tổ chức các doctype sao cho linh hoạt», chọn «Kiểu DocType như Frappe») |
| **Executor** | Claude Code (anh giao trực tiếp, cùng ràng buộc ngoại lệ ADR-061: PLAN trước, đúng scope, migration chỉ thêm) |
| **Created** | 2026-10-31 |

---

## Goal
Thêm một loại dữ liệu mới (thư viện hook, kiểu caption, bộ nhận diện kênh, danh mục sản phẩm…) **không cần sửa code,
không cần migration**: định nghĩa DocType trên web (trường, kiểu, bắt buộc, liên kết, bảng con) → có ngay danh sách +
form nhập + API. Feature khác (Studio) đọc bản ghi qua service ở `app/core`.

## Thiết kế
- **Lưu trữ:** 2 bảng mới (migration chỉ thêm).
  - `doctypes`: `name` (slug, duy nhất), `label`, `module`, `description`, `fields` (JSON), `is_child`, `title_field`,
    `naming` (`autoincrement` | `field:<tên trường>`), thời gian.
  - `doc_records`: `doctype`, `name` (duy nhất trong doctype), `data` (JSON), thời gian. Bảng con lưu trong `data`
    của bản ghi cha (danh sách dòng) — không tách bảng.
- **Kiểu trường:** `data` (chữ ngắn), `text`, `int`, `float`, `check`, `select` (options), `date`, `datetime`, `link` (trỏ
  bản ghi DocType khác), `table` (dòng của DocType con), `json`. Thuộc tính: `required`, `default`, `unique`,
  `in_list_view`, `read_only`, `description`.
- **Kiểm dữ liệu:** dựng từ định nghĩa mỗi lần ghi (pydantic không cần — hàm kiểm thuần): ép kiểu, bắt buộc, options,
  `unique` trong DocType, `link` phải tồn tại, `table` kiểm theo DocType con. Trường lạ trong dữ liệu gửi lên → lỗi.
- **Đổi định nghĩa:** thêm trường thoải mái; bỏ trường → dữ liệu cũ giữ nguyên (ẩn); đổi kiểu → kiểm lại khi bản ghi
  được sửa. Xoá DocType chỉ khi **không còn bản ghi** và không DocType nào trỏ tới (không bao giờ xoá dữ liệu kéo theo).
- **Lớp:** engine `app/core/doctype/` (models dùng chung `app.core.database.models`, service thuần) → API
  `app/platform/doctype_api/` → SPA `frontend/src/features/doctype/` (Hệ thống → DocType; danh sách / form chung).
- **Dùng từ feature:** `app.core.doctype.service.list_records(db, doctype, …)` / `get_record(…)`.

## Scope
- P1 (lần này): models + migration, service + kiểm dữ liệu, API, SPA (trình dựng DocType, danh sách, form chung có bảng
  con / liên kết), test, chạy trên máy thật (backup trước).
- P2 (sau, khi anh có loại dữ liệu cụ thể): nối Studio đọc một DocType (vd thư viện hook / kiểu caption).

## Out of Scope
- Phân quyền theo DocType, workflow duyệt, lịch sử phiên bản, script tuỳ biến (Frappe server script) — tool một người dùng.
- Chuyển bảng cũ (studio_templates, runtime_settings…) sang DocType.

## Validation
- `pytest tests/test_doctype_*.py` (kiểm kiểu, bảng con, link, unique, đổi định nghĩa, chặn xoá), ruff, lint-imports, tsc + build,
  trình duyệt thật (tạo DocType → nhập bản ghi), migration lên / xuống trên SQLite tạm + `alembic check`.

## Rollback
Không bật trang = không ảnh hưởng gì. Bảng mới để nguyên vô hại; `alembic downgrade` khi bảng rỗng.

---

## Execution Notes
- ✅ **P1 code xong (31/10), commit cục bộ — CHƯA chạy trên máy thật** (lệnh backup + migration + restart bị chặn quyền, chờ anh).
  - `app/core/database/models/doctype.py` (`DocType`, `DocRecord`) + migration `w0e7f8a9b0c1` (chỉ CREATE TABLE / INDEX).
  - `app/core/doctype/schema.py` (kiểm định nghĩa + ép kiểu + bắt buộc / default, thuần), `service.py` (CRUD, link tồn tại,
    unique, bảng con, đặt tên `autoincrement` / `field:x`, chặn xoá khi còn bản ghi / đang bị link — kể cả link trong bảng con).
  - `app/platform/doctype_api/router.py`: `/api/doctypes`, `/api/doc/{doctype}` (+ `/options`); 422 kèm lỗi từng trường.
  - SPA `frontend/src/features/doctype/`: Dữ liệu (danh sách DocType), trình dựng (bảng trường: kiểu, lựa chọn / đích, mặc định,
    bắt buộc, không trùng, hiện ở danh sách, đổi thứ tự), danh sách bản ghi (tìm, phân trang), form chung (ô theo kiểu, link = ô
    chọn, bảng con = lưới dòng, lỗi tô đỏ đúng ô). Sidebar SPA + Jinja: Hệ thống → «Dữ liệu (DocType)».

**Verification Proof**:
```
$ unshare -n pytest tests/test_doctype.py -q → 25 passed
$ ruff / lint-imports (không chuỗi vỡ mới) / tsc / npm run build → ok
$ alembic trên SQLite tạm: upgrade → check (No new upgrade operations) → downgrade → upgrade
# Trình duyệt (web tạm 127.0.0.1:8799 + SQLite riêng): tạo «Thư viện hook» trên trình dựng (chữ, chọn 1, liên kết Kênh, bảng con
# Dòng hook) → lưu → form thiếu bắt buộc báo 2 lỗi cùng lúc (trường chính + ô bảng con) → điền → lưu /doc/hook/1 → danh sách,
# form 390 px; 0 lỗi JS. Sửa sau khi xem: báo lỗi bảng con cùng đợt, bỏ cột tiêu đề lặp, cột Kiểu rộng hơn.
```
**Để chạy trên máy thật:** `python manage.py db backup --keep 14` → `venv/bin/alembic upgrade head` → `pm2 restart Web_Dashboard`.
