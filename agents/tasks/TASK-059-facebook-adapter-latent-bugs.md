# TASK-059 — 3 lỗi ngầm trong `facebook/adapter.py` bị `except Exception` nuốt

- **Người làm**: Anti ra PLAN → Codex/Antigravity (backend, ngoài vai Claude Code)
- **Phát hiện**: 2026-09-07, khi soạn PLAN-059 (đọc code, chưa chạy thật)
- **Chặn bởi**: cần ≥1 account Facebook để chứng minh đỏ→xanh; chưa có thì chỉ vá được
  theo suy luận, không có proof
- **Liên quan**: PLAN-059 (tách adapter — KHÔNG sửa lỗi này trong đó)

## Vì sao đáng ghi riêng

Cả ba đều là `NameError`/`UnboundLocalError` — lỗi lập trình thuần, không phải Facebook
đổi giao diện — nhưng nằm trong `try/except Exception` nên **chưa bao giờ lộ ra log
dưới dạng lỗi**. Chúng sống được vì có nhánh fallback phía sau. Nghĩa là: một số đường
đi trong adapter mà tài liệu/tên hàm hứa là có, thực tế **chưa từng chạy**.

| # | Vị trí | Lỗi | Hậu quả hiện tại |
|---|---|---|---|
| (a) | `adapter.py:695` | `SessionLocal` không được import trong file | `NameError` bị nuốt → warning "Could not load job account"; nhánh lazy-load account chưa từng chạy |
| (b) | `adapter.py:2500-2502` | dùng `al_lower` nhưng chỉ gán `al_norm` | `NameError` mỗi candidate, `except: continue` → `_try_click_switcher_aria_label` **luôn False**; chuyển Page toàn đi đường fallback 3a2b/3a2/3b |
| (c) | `adapter.py:463-468` | `search_terms` chỉ gán khi `not recovery_btn`, nhưng vòng `for` chạy vô điều kiện | `UnboundLocalError` khi thấy nút "Tiếp tục"; `_switch_to_page_context:2609` gọi ngoài `try` → lan lên `publish()` thành lỗi `unexpected` |
| — | `adapter.py:3003` | dump HTML debug vào `BASE_DIR / "tests"` lúc runtime | rác trong thư mục test của repo |

## Cách chứng minh khi có account

1. Chạy `publish()` với `SAFE_MODE=true` (dừng trước nút Đăng), bật log DEBUG.
2. (b): tìm dòng `Switch via aria-label` trong log — **không bao giờ có** là xác nhận.
3. (c): mô phỏng phiên hết hạn để Facebook hiện nút "Tiếp tục" → thấy `UnboundLocalError`.
4. (a): tạo job không gắn sẵn `account` rồi xem có warning "Could not load job account".

Sửa xong phải chạy lại đúng 3 bước trên và thấy đường đi mới xuất hiện trong log.

## Không làm

- Không gộp vào PLAN-059 — plan đó là refactor không đổi hành vi, sửa lỗi là đổi hành vi.
- Không vá khi chưa có account: vá theo suy luận ở file 3.000 dòng không có test hành vi
  là đúng loại "xanh giả" đã ghi trong handoff 2026-09-05 (c).
