# PLAN-062 — Admin áp dụng phí và thuế dự phòng cho báo giá khách

| | |
|---|---|
| Trạng thái | **APPROVED (user, 2026-10-23)** — code xong, chờ restart và bấm thử |
| Executor | Claude Code (user trực tiếp giao) |
| Quyết định | ADR-047 |
| Phạm vi | `cashback_bot/` + test cashback |
| Ngoài phạm vi | Hồ sơ thuế cho đối soát (phần 2, làm khi có đơn thật), chi trả, công thức V1.1 |

## Vấn đề

Báo giá V1.2 lấy phí và thuế dự phòng từ `.env`. Khi chủ bot đổi loại hình (cá nhân → cá nhân kinh doanh → hộ kinh doanh), muốn đổi mức dự phòng phải sửa `.env` và restart. Màn "Thuế & phí" trong `/admin` chỉ lưu bản nháp `customer_effect=none`, không áp dụng được.

Loại hình không tự đổi công thức (TAX_PROFILES.md): ba loại đi cùng một công thức, chỉ khác số thuế. Thứ admin cần đổi là mức dự phòng, kèm nhãn loại hình và ngày hiệu lực.

## Thiết kế

### Dữ liệu
- Bảng mới `reserve_policies` (append-only): `account_kind`, `fee_bps`, `tax_reserve_bps`, `effective_at`, `created_by`, `created_at`. Không sửa hay xoá dòng cũ.
- Không đụng `policy_versions` (giữ ràng buộc `customer_effect='none'` cho hạng). Không DROP bảng nào.
- Bảng `reserve_drafts` giữ trạng thái wizard (nonce, hết hạn 10 phút).
- Chưa có dòng nào hiệu lực → dùng `.env` như hiện tại.

### Báo giá
- Mỗi lần báo giá V1.2, bot lấy dòng `reserve_policies` mới nhất có `effective_at ≤ bây giờ`. Không cần restart; mốc tương lai tự có hiệu lực đúng giờ.
- Link lưu `estimate_policy = v1.2-reserve-2026-10-23+r{id}` để biết đã dùng mức nào. Link cũ giữ số cũ.
- `/cachtinh` và màn admin hiện mức đang áp dụng thật.
- V1.1 đang chạy thì mức đã lưu chưa có tác dụng; màn admin ghi rõ.

### Wizard trong `/admin` → Thuế & phí
1. Chọn loại hình: Cá nhân / Cá nhân kinh doanh / Hộ kinh doanh.
2. Phí dự phòng: gõ % hoặc bấm "Giữ x%".
3. Thuế dự phòng: gõ % hoặc bấm "Giữ x%".
4. Hiệu lực: "Ngay bây giờ", "00:00 ngày mai", hoặc gõ `dd/mm` / `dd/mm HH:MM` (giờ VN, tối đa 365 ngày tới).
5. Xem trước: trước → sau, mô phỏng 100.000đ, tổng 27 link gần nhất trước → sau. `[✖️ Hủy] [✅ Áp dụng cho khách]`.

Giới hạn mỗi khoản 0–50%. Mọi lần áp dụng ghi `admin_change_audit` và hiện ở Lịch sử.

Bản nháp FEE/TAX kiểu cũ (`customer_effect=none`) bỏ khỏi giao diện; dữ liệu cũ giữ nguyên.

## Tiêu chí xong
- [x] Admin đổi thuế dự phòng trong Telegram, link mới dùng mức mới không cần restart.
- [x] Mốc tương lai chưa áp dụng trước giờ; tới giờ tự áp dụng.
- [x] Link cũ không đổi số; link mới ghi `+r{id}`.
- [x] `/cachtinh`, Tổng quan, Chính sách, Thuế & phí hiện đúng mức đang áp dụng.
- [x] Không có dòng `reserve_policies` thì hành vi y như hiện tại (`.env`).
- [x] Người không phải admin, chat nhóm, nonce sai, bản hết hạn đều bị chặn.
- [x] Migration thử trên bản sao DB; pytest cashback xanh.

## Proof / Log thực thi

### Claude Code — 2026-10-23

- `migrations/005_reserve_policies.sql`: bảng `reserve_policies` (append-only, CHECK 0–5000 bps, loại hình 3 giá trị) và `reserve_drafts`. `AdminPanel._connect` chạy kèm 004 (`CREATE IF NOT EXISTS`), không ALTER/DROP bảng cũ.
- `admin_reserve.py`: đọc mức đang áp dụng / sắp áp dụng, đọc ngày giờ VN, hoa hồng link gần nhất.
- `admin_policy.py`: wizard `c:rs:*` 4 bước + xem trước + áp dụng/hủy, nonce, hết hạn 10 phút, mở wizard mới hủy wizard cũ, nút bước đã qua hiện lại bước hiện tại, admin dán link Shopee giữa wizard không bị nuốt. Audit `reserve_apply`, lịch sử tiếng Việt. Bỏ bản nháp FEE/TAX kiểu cũ khỏi giao diện (dữ liệu `policy_versions` giữ nguyên).
- `admin_ui.py`: màn Thuế & phí mới (đang áp dụng, sắp áp dụng, mô phỏng có "Khách nhận"), các màn wizard.
- `service.py`: báo giá V1.2 và `/cachtinh` dùng mức đang áp dụng; link ghi `+r{id}`; lỗi đọc DB → báo lỗi, không lặng lẽ dùng `.env`.
- Docs: `POLICY_V12.md` mục đổi mức dự phòng, `TAX_PROFILES.md` mục đã có trên bot.
- Thử trên bản sao `data/backups/cashback-20261023T092624Z.sqlite`: đi hết wizard, áp dụng Hộ kinh doanh thuế 1,5% → `reserve_policies` 1 dòng, `active_reserve` đúng, `integrity_check` ok; xem trước 27 link: 470.205đ → 515.089đ.
- Test: `tests/test_cashback_reserve.py` (10 test) + cập nhật test cũ. Proof: `.venv/bin/python -m pytest tests/test_cashback_*.py -q` → **151 passed**.
