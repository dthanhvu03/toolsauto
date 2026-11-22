# Agent tương tác khách — lượt đầu

Thời điểm kiểm tra: **19/11/2026 04:48:09 giờ Việt Nam (UTC+07)**.

## Kết quả

**0 trường hợp mới đủ chứng cứ để soạn/gửi trả lời trong snapshot; 0 nháp, 0 handoff mới, 0 hành động với khách.** Đây là kết luận giới hạn trong lịch sử DB, không phải xác nhận inbox live không có khách mới.

| Phạm vi đã đọc | Số lượng | Kết quả |
|---|---:|---|
| DM thread metadata | 28 | 5 có tin shop sau inbound cuối; 2 đã ghi skip; 21 chỉ metadata |
| DM log | 36 | 14 inbound, 5 outbound, 17 note |
| Follow-up đã lưu | 14 | 4 answered, 10 skipped, 0 failed |
| Inbound chưa xử lý có nội dung và đủ chứng cứ trong DB | 0 | Không có case hợp lệ để tạo nháp mới |
| Quá cũ trên 14 ngày được chứng minh từ DB | 0 | Không có trong log đã lưu; timestamp DB là lúc ghi nhận, không phải thời điểm gốc khách gửi |

## Phân loại đã kiểm chứng

- **Reply draft: 0.** Không dựng câu hỏi/khách giả để lấp hàng việc.
- **Handoff mới: 0.** Không có complaint/order/payment case chưa xử lý trong log có nội dung.
- **Skip theo lịch sử: 2.** Hai câu xác nhận ngắn đã được worker ghi skip; agent lượt này không cập nhật trạng thái.
- **Đã có phản hồi theo lịch sử: 5 cuộc.** Các cuộc này có outbound sau inbound cuối; không nhắn lại chỉ vì `dm_threads.status=open`.
- **`pending_live_verification`: 21 cuộc chỉ có metadata, không có DM log, `handled_sig` rỗng.** Không có nội dung để kết luận cần trả lời, đã đáp hay có nhu cầu mua. Các dòng này không được tính là backlog hợp lệ hoặc khách tiềm năng.
- **Follow-up: không có backlog đã lưu.** Cả 14 dòng đều answered/skipped; không có failed/pending. Chỉ nhìn lịch sử này không phát hiện được bình luận mới chưa được browser thu thập.

| Case mờ | Tuổi bản ghi inbound | Nhu cầu tóm tắt | Xử lý lượt này |
|---|---|---|---|
| `case-1e3ba77d04` | 125.0 giờ từ lần ghi nhận | Câu xác nhận ngắn; lịch sử đã ghi `skip` | Không cần nháp theo snapshot; không đánh dấu lại |
| `case-9ae9515b56` | 123.0 giờ từ lần ghi nhận | Câu xác nhận ngắn; lịch sử đã ghi `skip` | Không cần nháp theo snapshot; không đánh dấu lại |

## Độ mới và việc cần xác minh

- DM log mới nhất: **14/11/2026 01:51:10 VN**, cách lúc kiểm tra khoảng **122.9 giờ**. Các inbound có nội dung trong log được ghi nhận khoảng 123.0–125.0 giờ trước.
- Thread metadata được cập nhật gần nhất: **19/11/2026 00:24:00 VN**. Cập nhật metadata không chứng minh đã có tin mới hoặc có nhu cầu mua.
- `pending_live_verification`: cần lượt thu thập inbox/comment live được phép trước khi khẳng định có/không có inbound mới. Lượt này không mở browser, API hay gọi AI; không coi các case là đã xử lý.
- Không áp giới hạn 14 ngày lên tuổi `updated_at` như thể đó là tuổi nội dung thật. Đây là giới hạn của snapshot.

## Khóa tài khoản và phạm vi

- `us28qt`: enabled=true, DM=true.
- `anlinh`: enabled=true, DM=false.

- Identity hiện có trong prompt DM bị khóa vào **@us28qt**. **An Linh DM=false**; không tự bật hoặc dùng prompt đó cho tài khoản khác.
- Không tạo cold DM, broadcast, follow-up chủ động, QR, đơn hàng, hoàn tiền, giao dịch nhà cung cấp hoặc thay đổi queue/config/runtime.
- Không có nháp mới nên không trích giá/tồn kho hoặc hứa bảo hành. FAQ đã đối chiếu: `store_bot/chat_ai.py:61-74` và `dm_agent.py` — trả lời đúng câu hỏi, hướng khách xem thông tin trong bot, không hỏi mật khẩu/OTP/thẻ, việc tiền/đơn/bảo hành cần chủ shop.
- Nguồn đối chiếu: `app/features/threads/growth/dm_agent.py`, `dm.py`, `storage.py`, `worker.py`; `store_bot/chat_ai.py`; PLAN-171; ADR-067. Chỉ đọc các phần liên quan.

## Proof chỉ đọc

Kết nối SQLite bằng URI `data/threads_growth.sqlite?mode=ro`, bật `PRAGMA query_only=ON`, đọc trong một transaction và rollback khi xong. Không khởi tạo `GrowthStorage` vì constructor có thể tạo/migrate DB.

Lệnh kiểm chứng cốt lõi đã chạy:

```python
c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
c.execute("PRAGMA query_only=ON")
c.execute("BEGIN")
# SELECT direction, COUNT(*) FROM dm_messages GROUP BY direction
# SELECT COUNT(*) FROM dm_threads
# SELECT status, COUNT(*) FROM followups GROUP BY status
c.rollback()
```


Output thực tế (đã bỏ thông tin khách):

```json
{
  "query_only": 1,
  "dm_threads": 28,
  "dm_messages": 36,
  "directions": {"in": 14, "out": 5, "note": 17},
  "answered_threads": 5,
  "skip_threads": 2,
  "metadata_only_threads": 21,
  "unresolved_actionable_snapshot": 0,
  "followups": {"answered": 4, "skipped": 10},
  "drafts": 0,
  "new_handoffs": 0,
  "customer_actions": 0
}
```


Artifact chỉ chứa case hash, tuổi bản ghi và nhu cầu tóm tắt; không có tên/username/ID khách, raw DM, chi tiết đơn hoặc credentials. Không lưu bản sao DB hay raw transcript.
