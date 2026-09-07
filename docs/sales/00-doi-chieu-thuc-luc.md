# Đối chiếu lời quảng cáo với code thật

> Rà ngày **2026-09-05** trên `main`. Mục đích: mỗi câu trong mô tả bán hàng phải
> truy được về một bằng chứng. Trước khi thêm bất kỳ dòng nào vào mô tả combo, thêm
> một dòng vào bảng này trước.

## Thang mức độ

| Mức | Nghĩa | Được phép nói gì với khách |
|---|---|---|
| **A** | Đã chạy thật, có bằng chứng | Quảng cáo bình thường |
| **B** | Code xong, test xanh, **chưa chạy thật** | Nói kèm "mới, đang hoàn thiện" |
| **C** | Chỉ đúng một phần | **Phải nêu rõ giới hạn** |
| **D** | Hỏng hoặc chưa có | **Không được nhắc như tính năng** |

---

## Bảng đối chiếu

| Tính năng | Mức | Bằng chứng |
|---|---|---|
| Đăng Reels Facebook | **A** | 3 job `POST` = `DONE` trong DB (29–31/07/2026) |
| Tự động comment dưới bài | **A** | 1 job `COMMENT` = `DONE` (30/07/2026) |
| Đăng bài feed (chữ / chữ + ảnh) | **A** | Owner xác nhận thấy bài trên Page `kids0810` (PLAN-049). Lưu ý: gọi adapter trực tiếp, chưa qua hàng đợi |
| Tải video khi dán link (TikTok/YT/FB/IG) | **A** | 11 `viral_materials` xử lý xong, `status=DRAFTED`, **0 lỗi** |
| Tìm video viral **TikTok** theo từ khoá | **A** | `discovery_scraper.search_hashtag()` chạy qua yt-dlp |
| Ghép intro/outro, thumbnail, chống trùng | **A** | `reup_processor` + `intro_service`, cùng 11 material trên |
| AI viết caption (Gemini) | **C** | **Hạ từ A ngày 2026-09-07.** 7 job `DRAFT` kia còn nguyên placeholder `[AI_GENERATE] …` — là bằng chứng *đang chờ AI*, không phải AI đã chạy. Chỉ job 7 (`DONE`, 07/2026, VPS) có caption giống AI viết. Ở máy local: `GOOGLE_API_KEY` sai loại (không phải key `AIza…`) → Gemini **401**, thiếu `faster_whisper`, 9Router tắt. Chuỗi fallback có trong code nhưng chưa có bằng chứng chạy được ở local |
| Hàng đợi, hẹn giờ, cooldown, giới hạn ngày | **A** | `claim_next_job` chạy thật; `daily_limit=3` trên account |
| Bảng điều khiển web | **A** | `app/platform/dashboard_shell` |
| Thông báo Telegram | **C** | Code có; nhưng `.env` local **không có** `TELEGRAM_BOT_TOKEN`/`CHAT_ID` → gửi trả 404 (kiểm 2026-09-07). Chỉ chạy được khi cấu hình lại |
| **Bài feed qua hàng đợi** | **B** | PLAN-052, test xanh. Trước đó job FEED nằm PENDING vĩnh viễn. Chưa chạy thật |
| **Đăng Story** | **B** | PLAN-054, 23 test. `story_composer.py`. **Chưa chạm Facebook thật** |
| **Comment kèm ảnh** | **B** | PLAN-055, 12 test + migration. Chưa chạy thật |
| **Video dài (chờ theo dung lượng)** | **B** | PLAN-056, 9 test, trần 7 phút. Chưa chạy thật |
| **Lấy `post_url` bài feed** | **B** | PLAN-053, 14 test. Chưa chạy thật |
| Tìm video theo từ khoá — **YouTube, Facebook** | **C** | `discovery_scraper` **chỉ có TikTok**. Hai nguồn này chỉ tải được khi dán link |
| Quản lý nhiều tài khoản | **C** | Code có, nhưng DB **chỉ từng có 1 account facebook**. Chưa kiểm chứng nhiều account |
| Instagram / TikTok / Threads | **C** | Có adapter với `publish()`, nhưng **0 account** nào thuộc 3 nền tảng này. Chưa chạy lần nào |
| **Link rút gọn đếm click** | — | **Đã gỡ 2026-09-07 (ADR-015).** Đếm click bằng Sub ID Shopee / sub1 AccessTrade trong chính URL affiliate |
| **Gắn giỏ hàng / sản phẩm** | **D** | **0 dòng code.** TASK-055 mới là khảo sát, chưa khảo sát |
| Tìm video **Douyin** | **D** | Không hỗ trợ. Chặn theo vùng + cần chữ ký request, phải có proxy Trung Quốc |
| Link bấm được **trong Story** | **D** | Chưa ai kiểm chứng Facebook có cho phép không |

---

## Quy tắc giữ bảng này khỏi lạc hậu

1. Mục **B** chỉ được nâng lên **A** khi đã chạy thật trên Facebook, và ghi ngày +
   bằng chứng vào đây. **Test xanh không đủ để nâng.**
2. Mục **D** không được xuất hiện trong bất kỳ tài liệu bán hàng nào — kể cả dạng
   "sắp có".
3. Mục **C** khi nhắc tới **bắt buộc kèm giới hạn** trong cùng một câu.
4. Sửa mô tả combo thì sửa bảng này trước.

## Việc cần làm để nâng hạng

- **AI caption C → A**: Owner đặt `GEMINI_API_KEY` thật (dạng `AIza…`) vào `.env`,
  bật stack (`ai_generator` nay đã nằm trong stack local — ADR-013), thấy ≥1 job
  `DRAFT` có caption thật thay cho placeholder `[AI_GENERATE]`.
- **Telegram C → A**: đặt `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, nhận được 1 tin.

- **5 mục B → A**: cần Owner mở trình duyệt chạy thật một lần cho mỗi luồng
  (Story, comment kèm ảnh, video dài, bài feed qua hàng đợi, lấy post_url).
  Ước tính ~30 phút cho cả 5.
- **Đếm click**: không còn link rút gọn (ADR-015). Owner đặt Sub ID Shopee / sub1
  AccessTrade vào chính URL affiliate khi lưu link — sàn tự đếm click và đơn.
- **Giỏ hàng D → ?**: khảo sát trước, đừng code mù (TASK-055).
