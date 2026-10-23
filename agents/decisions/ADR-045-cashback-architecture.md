# ADR-045: Nền Cashback Bot là modular monolith, một cửa tính tiền

Ngày: 2026-10-23. Trạng thái: đã chốt cho code trong worktree `cursor/cashback-v12-architecture`. Chưa áp vào process đang chạy.

## Bối cảnh

`python -m cashback_bot` là một process Telegram. Production đang nạp code từ `/home/vu/toolsauto` lúc khởi động, không nạp lại khi file đổi. Công thức khách đang thấy là hoa hồng ước tính nhân 70%.

`money.py` và `calculator.py` cùng biết cách ra một số tiền. Membership 60/65/70 đã được chốt về hướng nhưng chưa được bật.

## Quyết định

Giữ một process và SQLite. Không microservice, không Postgres.

`pricing.py` là cửa duy nhất cho công thức:

- `quote_displayed_vnd` gọi `money.estimated_cashback`. Đây là số khách đang thấy.
- `estimate_cashback` là ước tính V1.2, chỉ khi caller đưa policy.
- `calculate_final_cashback` là số cuối, payable luôn trống khi chưa có lệnh chi.
- Thiếu dữ liệu để `None`, không điền 0.
- Snapshot link đọc số đã lưu, không tính lại.

`service.py` trong worktree này gọi cửa đó. Nhánh production chưa nhận thay đổi này.

Ba policy đứng riêng: thuế (`tax_profile.py`), cashback (snapshot trên link), hạng (`ranks.py` ở thư mục làm việc chính, chưa nối). Đơn cũ dùng snapshot đã gắn, không dùng hạng hiện tại.

Sub ID khớp đúng từng ký tự, phân biệt hoa thường.

## Schema

Đang có, và đủ cho tracking: `telegram_users`, `link_requests`, `bot_state`, `outbound_messages`, `admin_notifications`.

Chưa tạo thêm bảng. Sau này, khi có đơn thật, mới thêm conversion, settlement, entitlement, payout, progress. Các trạng thái click, conversion, hoa hồng đã duyệt, tiền Shopee đã trả, số được chi và số đã chi phải là các cột hoặc bảng khác nhau. `payable_vnd` để null khi chưa đủ chứng từ.

## Chưa làm

Không bật 60%. Không migrate SQLite đang chạy. Không nối Conversion Sync. Không ví.

Cắt sang V1.2 chỉ sau khi chủ bot duyệt câu hiển thị, backup, và chạy migration trên bản sao.
