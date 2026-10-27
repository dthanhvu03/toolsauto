# Thiết kế hệ thống giữ chân khách — bot cashback

| | |
|---|---|
| Ngày | 2026-10-27 |
| Người viết | Claude Code (chủ bot yêu cầu: "nghiên cứu thiết kế thêm hệ thống giữ chân") |
| Trạng thái | **Đã tự phản biện (mục 0), lộ trình rút gọn.** Đợt 1 đã làm. Mọi tin chủ động gửi cho khách cần chủ bot duyệt cách gửi và nội dung |
| Phạm vi | Telegram + Zalo; Shopee + TikTok Shop |

## 0. Tự phản biện (đọc trước, thay lộ trình ở mục 9)

| # | Chỗ sai | Sửa |
|---|---|---|
| 1 | "13/16 chỉ dùng 1 ngày" là kết luận quá sớm: bot mới chạy 6 ngày, khách vào 25–26/10 chưa có thời gian quay lại. Mốc "14 ngày là người ngủ" có thể chỉ là nhịp mua Shopee bình thường | Đo 30 ngày rồi mới kết luận. Bảng 🔁 Giữ chân ghi "chưa tới" / "đang đo" thay vì 0% |
| 2 | Chữa triệu chứng. Khách quay lại khi **đã nhận tiền**, nhưng ví chưa mở lại bị xếp cuối (tầng E) | Ưu tiên đường tới khoản hoàn đầu tiên (mở ví) |
| 3 | Quá to so với 16 khách (5 tầng, migration, màn chiến dịch) | Dưới ~100 khách: chủ bot tự nhắn tay. Chưa xây tầng C / D |
| 4a | "Ghim thì bot hiện trong khung Chia sẻ của Shopee": chưa thử | Bỏ mẹo ghim cho tới khi thử được |
| 4b | Giờ yên lặng 21:30–8:00 chặn đúng giờ 0h của ngày sale | Khi làm tầng C: đêm sale được nhắc tới 0h |
| 4c | Nhắc link chưa dùng dựa vào click về trễ (4 giờ) và không đầy đủ: dễ nhắc nhầm người đã mua, dễ thấy "bị theo dõi" | Hoãn A2 |
| 4d | Nguồn tham khảo yếu; chưa so mức hoàn với các bot hoàn tiền khác ở VN | Nghiên cứu đối thủ |
| 5 | Trần 50 người / bot Zalo tới sớm hơn vấn đề giữ chân | Đặt lên trước |

**Lộ trình rút gọn:**
1. Câu chữ: mừng đơn đầu, câu mời quay lại cuối tin báo đơn. ✅ Đã làm 2026-10-27.
2. Thử 1 tin Zalo chủ động tới chủ bot. Chờ chủ bot xác nhận tài khoản.
3. ~~11.11: chủ bot tự nhắn tay.~~ Chủ bot yêu cầu tự thiết lập: đã làm nhắc mùa sale có duyệt từng lượt (`reports/CASHBACK_SALE_REMINDERS.md`).
4. Bảng 🔁 Giữ chân đo đúng (chưa tới / đang đo). ✅ Đã làm 2026-10-27.
5. Mở ví và xử lý trần 50 người Zalo.
6. So mức hoàn với các bot hoàn tiền khác.
7. ~~Từ ~100 khách mới xây tầng C / D.~~ Chủ bot duyệt làm sớm (2026-10-27): C = nhắc mùa sale, D gộp vào tin sale, A2 nhắc link chưa dùng có luật. Xem `reports/CASHBACK_SALE_REMINDERS.md`.

## 1. Hiện trạng (DB production, đọc ngày 2026-10-27)

| Chỉ số | Số |
|---|---|
| Khách đã tạo link | 16 (gồm tài khoản chủ bot) |
| Chỉ dùng đúng 1 ngày | **13 / 16** |
| Dùng từ 2 ngày trở lên | 3 |
| Khách có đơn thật | 4 |
| Tin chủ động đã gửi khách | 9 tin, **tất cả qua Telegram** (5 đơn mới, 4 cập nhật) · 1 tin bị chặn vì khách tắt |
| Tin chủ động qua Zalo | **0**: chưa biết Zalo Bot có cho bot nhắn trước hay không |

Giới hạn Zalo Bot gói Basic (xem `reports/CASHBACK_ZALO_BOT_RESEARCH.md`):
- **50 người dùng mỗi bot**;
- **3.000 tin mỗi tháng**.

Tin giữ chân dùng chung hạn mức với tin trả lời. Khi gần chạm 50 người thì chặn trần này sẽ là vấn đề tăng trưởng lớn hơn cả chuyện giữ chân.

## 2. Vấn đề thật

Khách **không quên bot vì bot dở**. Khách quên vì lúc sắp bấm "Mua" họ đang ở trong app Shopee và nghĩ về món hàng, không nghĩ về tiền hoàn. Mua sắm lại không đều: có tuần mua 3 lần, có tháng không mua.

Vì vậy giữ chân **không phải là nhắn nhiều**, mà là:
1. **Có mặt đúng lúc sắp mua**: ghim cuộc trò chuyện, nhắc vào mùa sale.
2. **Mỗi lần chạm phải có giá trị**: báo đơn, báo tiền, mẹo săn sale. Không gửi tin "nhớ bọn mình không".
3. **Phần thưởng phải thật**: lần nhận tiền đầu tiên là lúc khách tin bot. Trước khi ví mở, phần thưởng chỉ là tinh thần.

## 3. Vòng thói quen và chỗ bot đang hở

| Bước | Ý nghĩa | Bot hiện nay | Cần thêm |
|---|---|---|---|
| 1. Nhắc nhớ | Lúc sắp mua thì nhớ ra bot | **Yếu**: chỉ có tin báo đơn | Ghim, nhắc mùa sale, nhắc link chưa dùng, gọi lại người ngủ |
| 2. Hành động | Dán link, có số tiền | Tốt, dưới 3 giây | Giữ nguyên |
| 3. Phần thưởng | Thấy tiền | **Thiếu**: ví chưa mở | Mừng đơn đầu tiên, tổng đã tích; sau khi mở ví là tiền thật |
| 4. Tích luỹ | Càng dùng càng lợi | Có hạng nhưng chưa bật, khách không thấy | Tiến độ lên hạng, tiến độ tới mức rút (sau khi mở ví) |

## 4. Hệ thống: 5 tầng

### Tầng A — Kích hoạt (ngày đầu)

| # | Khi nào | Tin (giọng "bạn thân biết săn sale") | Giới hạn |
|---|---|---|---|
| A1 | Ngay sau link **đầu tiên** của khách | 📌 Mẹo nhỏ: **ghim cuộc trò chuyện này lên đầu** nha. Lần sau thấy món ưng, bấm Chia sẻ → chọn bot là có link hoàn liền. | 1 lần / khách. Gửi kèm phản hồi link, không phải tin chủ động |
| A2 | Link đã tạo mà **24 giờ** chưa có click hoặc đơn | 🛒 Bạn còn để ý *[tên món]* không? Link hoàn vẫn dùng được nè, bấm là mua liền: *[link]* | **Tối đa 1 lần / link**, 1 lần / khách / ngày, không gửi ngoài khung 8:00–21:30 |
| A3 | Đơn **đầu tiên** được ghi nhận | 🎉 **Đơn đầu tiên của bạn đó!** Thêm vào tin báo đơn mới, không phải tin riêng | 1 lần / khách |

### Tầng B — Vòng đời đơn (đã có, chỉ sửa chữ)

- Cuối mỗi tin báo đơn (đơn mới, hoàn thành, được duyệt, vào ví) thêm 1 dòng mời quay lại, đổi luân phiên để khỏi nhàm:
  - "Lần sau mua gì, dán link vào đây để được hoàn tiếp nha."
  - "Có món đang ngắm? Gửi link qua bot trước khi chốt đơn nhé."
- Không tốn thêm tin, vì là tin đã có sẵn.

### Tầng C — Lịch mua sắm

- Lịch do admin nhập ở /admin (không cứng trong code), lưu trong `bot_state` hoặc `storage/db/config/`. Ví dụ:
  - ngày đôi: 11.11, 12.12;
  - giữa tháng: 15;
  - cuối tháng.
- Ngày cụ thể của từng đợt Shopee VN chưa xác minh được, admin tự nhập.
- **Tối đa 1 tin mỗi đợt**, gửi lúc khoảng 19:00–20:00 tối hôm trước.
- Mỗi đợt phải được **admin bấm "Duyệt gửi"** sau khi xem trước nội dung và số người nhận. Không có đợt nào tự gửi.
- Mẫu:
  > 🛒 **Mai 11.11 rồi, giỏ hàng full chưa?**
  > Nhớ dán link qua bot **trước khi chốt đơn** để được hoàn nha. Mua thẳng trong app là không được hoàn đâu đó.
- Người nhận: khách đã từng tạo link, không tắt mục "Nhắc mùa sale", không chặn bot.

### Tầng D — Gọi lại người ngủ

| Mốc | Tin | Sau đó |
|---|---|---|
| 14 ngày không dùng | 👋 Lâu rồi không thấy bạn ghé. Lần sau mua Shopee nhớ gửi link qua đây nha, bot vẫn hoàn như cũ. | — |
| 30 ngày không dùng | Tin cuối, kèm cách tắt nhắc | **Dừng hẳn.** Không nhắc nữa cho tới khi khách tự quay lại |

- Nếu trùng tuần có đợt sale (tầng C) thì bỏ tin tầng D, chỉ gửi tin sale.

### Tầng E — Tích luỹ (chỉ bật **sau khi mở ví**)

- **Tiến độ tới mức rút**: "Còn 3.500đ nữa là rút được". Người ta có xu hướng cố hoàn thành khi thấy mình đã gần đích.
- **Hạng thành viên**: "Còn 2 đơn nữa lên hạng Bạc". Ngưỡng hạng hiện **chưa duyệt** (`ranks.THRESHOLD_SETS`), chủ bot phải chốt trước.
- **Giới thiệu bạn bè**: hai bên cùng được thưởng khi người được giới thiệu có đơn đầu tiên hợp lệ. Đây là chính sách tiền, chủ bot quyết mức thưởng và nguồn tiền.
- Trước khi mở ví **không hiện** các mục này: có ví mà không rút được thì phản tác dụng.

## 5. Rào chắn chống spam (bắt buộc, áp cho cả hệ thống)

| Rào | Quy tắc |
|---|---|
| Ngân sách | Tối đa **2 tin chủ động / tuần / khách**, không tính tin báo đơn khách đã bật |
| Giờ yên lặng | Không gửi từ 21:30 tới 8:00 (giờ VN). Tới giờ đó thì dời sang sáng hôm sau |
| Tắt một chạm | Thêm mục **"Nhắc mua sắm"** vào 🔔 Thông báo (bảng `customer_notification_prefs`). Mọi tin tầng A2, C, D có dòng cuối "Tắt nhắc: /thongbao" |
| Dừng khi im lặng | Khách không phản hồi 2 tin nhắc liên tiếp thì dừng tầng C và D với khách đó |
| Chặn bot | Có `notify_blocked_at` thì không gửi gì nữa |
| Chống trùng | Mỗi tin có `event_key` theo khách và đợt (ví dụ `remind:sale:2026-11-11:<user>`), dùng cơ chế sẵn có của `notify_dispatch` |
| Zalo | Tính tin nhắc vào hạn mức 3.000 tin / tháng; còn dưới 20% thì chỉ gửi tin báo đơn |

## 6. Giọng nói

| Chỗ | Giọng | Ví dụ |
|---|---|---|
| Chào mừng, mẹo, nhắc sale, mừng đơn | Gần gũi, vui, từ phổ biến lâu dài (*chốt đơn, săn sale, hời, ting ting*) | 🔔 Ting ting! Đơn mới về rồi nha |
| Số tiền, điều kiện, lỗi, ví, điều khoản | Rõ, nghiêm, không đùa | 💰 Hoàn dự kiến: khoảng 48.675đ |
| Không dùng | Từ lóng ngắn hạn (*bestie, toang, slay, 💀*), phóng đại tiền ("hoàn tận…", 🤑) | — |

Lý do: rào cản số 1 là **sợ lừa đảo**. Giọng càng "trend" quanh chuyện tiền thì càng giống trang lừa đảo.

## 7. Đo lường

Thêm vào 🎯 Mục tiêu / 📊 insights (chỉ đọc):

| Chỉ số | Cách tính |
|---|---|
| Quay lại 7 ngày / 30 ngày | Khách tạo link ở ngày N có tạo link mới trong N+1…N+7 / N+30 |
| Link → click → đơn | `link_requests` → `shopee_clicks` (theo sub_id) → `shopee_conversions` |
| Hiệu quả từng loại nhắc | Khách nhận tin nhắc có tạo link trong 48 giờ sau đó không |
| Tỷ lệ tắt / chặn | Tắt mục "Nhắc mua sắm", `notify_blocked_at` sau tin nhắc. **Tỷ lệ chặn > 5% sau một đợt thì dừng loại tin đó** |

A/B giọng nói chỉ có ý nghĩa khi có khoảng 50–100 khách mới mỗi nhóm. Hiện chưa đủ, nên chọn giọng theo cảm nhận về tệp khách.

## 8. Kỹ thuật (để Anti / Codex lập PLAN)

- **Dùng lại:**
  - `notify_dispatch`: hàng đợi, `event_key` chống trùng, `customer_block_reason`, tuỳ chọn của khách, kênh Zalo bằng ID âm;
  - `poller._periodic`: việc định kỳ tách riêng, lỗi không chặn việc khác;
  - `insights`: số liệu chỉ đọc.
- **Thêm:**
  - cột `reminders` trong `customer_notification_prefs` (cần migration, phần của Codex) + category `reminder` trong `notify_dispatch`;
  - module mới **`engagement.py`** (tên `retention.py` đã dùng cho thời hạn lưu dữ liệu). Hàm thuần chọn người nhận theo từng tầng + kiểm rào chắn ở mục 5, rồi đưa vào hàng đợi bằng `enqueue_event`;
  - lịch sale và nội dung đợt: lưu `bot_state.engagement_campaigns`, màn admin `c:eg:*` để nhập, xem trước, xem số người nhận, **Duyệt gửi**. Ghi lịch sử duyệt;
  - câu chữ đặt trong `messages.py`, để `zalo_render.PHRASES` đổi câu bấm nút sang Zalo như các tin khác.
- **Tầng A1, A3, B** chỉ sửa câu chữ trong tin đã có: không cần migration, không gửi thêm tin. Phần này Claude Code làm được ngay.

## 9. Lộ trình đề xuất

| Đợt | Nội dung | Ai làm | Cần chủ bot |
|---|---|---|---|
| 1 | A1 ghim, A3 mừng đơn đầu, B câu mời quay lại | Claude Code | Duyệt câu chữ |
| 2 | Kiểm Zalo Bot có cho nhắn trước: gửi 1 tin thử tới **Zalo của chủ bot** | Claude Code | Duyệt cho gửi 1 tin thử |
| 3 | Mục "Nhắc mua sắm" + rào chắn + tầng C có nút Duyệt gửi. **Phải xong trước 10/11 để kịp 11.11** | Codex (migration, việc nền) + Claude Code (màn admin, chữ) | Duyệt PLAN, nhập lịch, duyệt nội dung đợt |
| 4 | A2 nhắc link chưa dùng, D gọi lại người ngủ | Codex + Claude Code | Duyệt |
| 5 | E tiến độ / hạng / giới thiệu: **sau khi mở ví** | Sau | Chốt ngưỡng hạng, mức thưởng giới thiệu |

## 10. Rủi ro

- **Zalo có thể không cho bot nhắn trước.** Khi đó tầng A2, C, D chỉ chạy trên Telegram; trên Zalo chỉ còn tầng A1, A3, B (tin trả lời).
- **Trần 50 người / bot Zalo.** Gần chạm trần thì phải tính bot Zalo thứ hai hoặc gói Pro (chưa mở bán).
- **Nhắn quá tay thì khách chặn bot**, mất luôn kênh báo đơn. Vì vậy rào chắn ở mục 5 là bắt buộc, không phải tuỳ chọn.
- **Dữ liệu còn ít** (16 khách): các chỉ số ở mục 7 chỉ để theo dõi xu hướng, chưa đủ để kết luận.

## Nguồn tham khảo

- Branch, chương trình giới thiệu ShopBack (thưởng hai bên khi người được giới thiệu có đơn đầu tiên): https://v2.iotone.com/case-study/leveraging-iot-for-effective-referral-programs-a-case-study-of-shopback/c4206
- Wildfire, thưởng cá nhân hoá giúp người dùng ngủ quay lại: https://www.wildfire-corp.com/blog/incentives-rewards-program-participation
- Shopee, lịch sale cố định hằng tháng và các ngày đôi: https://shopee.vn/blog/khi-nao-shopee-sale/
- Giới hạn Zalo Bot gói Basic: `reports/CASHBACK_ZALO_BOT_RESEARCH.md`
