# ToolsAuto Plan System

## 1. Khi nào phải có Plan?
Bắt buộc cho mọi thay đổi liên quan đến:
- Logic nghiệp vụ (business logic)
- Cấu trúc database hoặc schema
- Refactor hệ thống
- Thêm adapter, router, worker mới
- Bất kỳ thay đổi nào ảnh hưởng >2 file

Không cần Plan cho: sửa typo, thay đổi text hiển thị nhỏ, cập nhật comment.

---

## 2. Quy trình tạo Plan

### Bước 1 — Đặt tên và số
- Format: `PLAN-NNN-short-name.md`
- Số `NNN` tiếp nối số cuối cùng trong `plans/archive/`
- Lưu vào: `agents/plans/active/`

### Bước 2 — Điền template
Sử dụng `agents/templates/plan.template.md`. Bắt buộc điền đủ:
- **Goal**: Mục tiêu cụ thể, đo được
- **Context**: Hiện trạng và vấn đề
- **Scope / Out of Scope**: Ranh giới rõ ràng
- **Proposed Approach**: Các bước cụ thể
- **Risks**: Ít nhất 1 risk kỹ thuật
- **Validation Plan**: Kiểm tra bằng gì
- **Rollback Plan**: Nếu fail → làm gì
- **Related**: Link Task ID liên quan

### Bước 3 — Phê duyệt
Plan phải được user xác nhận (hoặc agent Antigravity duyệt) trước khi chuyển sang Execution.

---

## 3. Vòng đời của một Plan

```
Draft → Active → Executing → Done (→ Archive)
                           ↘ Cancelled (→ Archive)
```

- **Draft**: Đang viết, chưa duyệt
- **Active**: Đã duyệt, sẵn sàng execute
- **Executing**: Đang trong Phase 4
- **Done**: Verify xong, chuyển vào `plans/archive/`
- **Cancelled**: Không thực hiện nữa, chuyển vào `plans/archive/` với note lý do

---

## 4. Plan vs Task

| | Plan | Task |
|---|---|---|
| **Trả lời câu hỏi** | Làm *thế nào*? | Làm *gì*? |
| **Scope** | Giải pháp kỹ thuật toàn phần | Một đơn vị công việc cụ thể |
| **Người viết** | Antigravity / Claude | Antigravity |
| **Bắt buộc khi** | Thay đổi logic/cấu trúc | Mọi việc được giao |

Một Task có thể link đến 1 Plan. Một Plan có thể phục vụ nhiều Tasks.

---

## 5. Quy tắc thép cho Plans
- Không được execute khi Plan chưa tồn tại trong `agents/plans/active/`
- Không được mở rộng scope âm thầm (scope creep)
- Nếu thực tế thay đổi so với Plan → cập nhật Plan trước, rồi mới tiếp tục code
- Sau khi Done → archive ngay, không để Plan cũ trong `active/`
