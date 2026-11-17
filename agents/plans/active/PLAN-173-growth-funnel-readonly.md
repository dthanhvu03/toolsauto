# PLAN-173 — Đo phễu hai bot theo nguồn, chỉ đọc

## Metadata
| Field | Value |
|---|---|
| ID | PLAN-173 |
| Status | Execution Verified; Anti sign-off + Claude handoff pending |
| Executor | Codex |
| Created by | Codex, ngoại lệ được chủ bot cho phép trực tiếp 2026-11-17 |
| Related Task | TASK-060 |
| Related ADR | ADR-067, ADR-063, ADR-056 |
| Created / Updated | 2026-11-17 |

## Authorization
Chủ bot đồng ý: «Cho phép ngoại lệ phạm vi trên» khi được hỏi cho Codex tự viết PLAN và triển khai backend báo cáo
phễu chỉ đọc. Không giả danh Antigravity, không tự điền Anti sign-off. Không đổi luồng khách đang thuộc PLAN-172.

## Goal
Báo cáo cohort khách mới theo bot và mã nguồn: bước sử dụng, chuyển đổi trong 24 giờ, quay lại sử dụng.
Có CLI JSON/text để chạy ngay; bản tóm tắt đi cùng báo cáo sáng sẵn có, không thêm lịch hay người nhận.

## Context
- PLAN-172 đã có growth_report, đếm tổng phễu; all_users có nguồn first-touch.
- Store ghi step:product/confirm lần đầu từ 16/11. Cashbot có link, click theo sub_id và đơn khớp khách.
- Mã nguồn đang dùng chung cho nhiều bài/reply: không thể gán chính xác từng khách về từng bài.
- Git có WIP ngoài phạm vi: evaluator.py, store_bot/bot.py, test_threads_growth.py, store_bot/chat_ai.py, test_store_chat_ai.py.

## Scope
- Mới cashback_bot/growth_funnel.py: đọc hai SQLite mode=ro; cohort [now-days, now), nhóm theo bot/nguồn; CLI.
- Sửa cashback_bot/growth_report.py: thêm tóm tắt phễu vào build(), giữ nguyên tick/outbox/lịch gửi.
- Mới tests/test_growth_funnel.py: dữ liệu tạm, kiểm đúng mẫu số, timezone, loại failed/refund/cancel và DB thiếu.
- Cập nhật PLAN/TASK/current-status với proof thực tế.

## Out of Scope
- Không sửa UI, bot/service/worker mua hàng, AI chat WIP, tiền, schema, dữ liệu nguồn, mã tracking.
- Không restart, không gửi tin tay, không gọi Shopee/FatCat/Buffer/AI; không commit WIP của agent khác.
- Không quy kết doanh thu tăng từ thử nghiệm; không giả dữ liệu lịch sử/per-post chưa được ghi.

## Proposed Approach
1. Đọc schema và quy tắc dữ liệu; xác định cohort và trạng thái thành công.
2. Tạo báo cáo chỉ đọc: số khách ở mỗi bước độc lập (QR là nhánh tùy chọn), khách đủ 24h mới vào mẫu số 24h;
   Store: đơn done/partial còn giá trị sau hoàn, mua >=2 đơn; Cashbot: link created, click khớp sub_id,
   đơn không huỷ, dùng link >=2 ngày VN. Không xuất tên/ID cá nhân trong JSON.
3. Thêm tóm tắt ngắn vào báo cáo sáng (giới hạn số nguồn/độ dài), giữ API cũ và lịch hiện có.
4. Test dữ liệu giả, regression báo cáo/khách, ruff; chạy CLI trực tiếp mode=ro trên DB thật, ghi số và giới hạn đo.

## Risks
| Risk | Mức | Xử lý |
|---|---|---|
| Z và +00:00 so chuỗi sai | Med | Parse datetime có timezone, dùng julianday lọc cohort |
| Khách chưa đủ 24h bị coi thất bại | Med | Mẫu số chỉ khách đã đủ 24h |
| Step mới chưa phủ lịch sử; đường mua không qua QR | Med | Ghi chú bước độc lập, không bịa strict funnel |
| Đơn cập nhật muộn, thiếu click hoặc không có timestamp | Med | Ghi giới hạn; không đổi nghĩa tiền, không dùng dữ liệu thiếu làm chuyển đổi 24h |
| DB một bot lỗi | Low | Trả lỗi + dữ liệu bot kia, không hiện số 0 như DB tốt |
| Nội dung Telegram >4096 | Low | Tóm tắt cố định tối đa 3 nguồn, kiểm độ dài |

## Validation Plan
- [x] Test phễu trên DB tạm: ranh giới thời gian/cohort/nguồn, trạng thái, 24h, repeat, DB thiếu, chỉ đọc.
- [x] Regression tests/test_growth_report.py và tests/test_bot_users.py.
- [x] Ruff 3 file backend; CLI --days 7 --json trên DB thật (không gửi).
- [x] Kiểm git diff/status giữ nguyên WIP; ghi kết quả và phần runtime pending.

## Rollback Plan
Chỉ gỡ import và khối tóm tắt mới trong growth_report.py; hai file mới có thể giữ không được gọi.
Không reset hay checkout file WIP. Không có thay đổi DB để rollback.

## Execution Notes
- Bước 1: schema trực tiếp mode=ro: Cashbot 58 users / 203 link_requests / 214 clicks / 24 conversions;
  Store 145 users / 27 topups / 20 orders (18 done, 2 failed). Đây là snapshot lúc khảo sát, chưa phải kết quả cohort.
- Bước 2: growth_funnel.py (194 dòng) đọc từng DB bằng mode=ro + transaction đọc nhất quán, không import luồng bot;
  JSON chỉ aggregate, không tên/ID. Nguồn không có mã ghi «không ghi nhận nguồn», không gán là khách tự vào.
- Bước 3: nối summary (tối đa 3 nguồn) vào build; tick/outbox giữ nguyên. Chặn tổng nội dung vượt 4000 ký tự bằng cách
  bỏ phần bổ sung nếu không đủ chỗ. Nhãn phễu cũ ghi rõ từ 00:00 VN; phần mới là rolling 7 ngày, ghi cả mốc bắt đầu/kết thúc.
- Bước 4: tests/test_growth_funnel.py 10 case (3 tham số invalid window) + regression báo cáo/khách/AI Cashbot/invite.
  Sửa lỗi mock trong test CLI sau lượt đầu, sau đó toàn bộ 33 test qua.
- Kết quả thật 2026-11-17 10:35 VN, cohort từ 10/11 10:35:

| Bot / nguồn | Khách mới | Bước chính hiện tại | Chuyển đổi <24h / khách đủ 24h | Quay lại |
|---|---:|---|---:|---:|
| Store tổng | 99 | 6 khách có đơn đã giao | 5/92 = 5.4% | 0 |
| Store threads_ai_price_anlinh | 55 | 1 khách có đơn | 1/50 = 2.0% | 0 |
| Store threads_ai_price | 20 | 2 khách có đơn | 2/19 = 10.5% | 0 |
| Store threads_ai_auto | 14 | 0 khách có đơn | 0/14 | 0 |
| Cashbot Telegram | 12 | 4 tạo link, 1 có click, 0 có đơn | 3/8 = 37.5% | 0 |
| Cashbot Zalo | 7 | 3 tạo link, 2 có click, 2 có đơn | 3/7 = 42.9% | 2 |
| Cashbot store_xsell | 2 | 0 tạo link | chưa đủ 24h (mẫu số 0) | 0 |

- Giới hạn diễn giải: Store hiện chỉ có 13 khách ghi xem món / 2 chọn số lượng, nhưng step mới ghi từ 16/11 nên không
  suy ra 86/99 chưa từng xem món. QR không bắt buộc. 24h Store là thời điểm đặt đơn hiện đã giao, không phải thời gian giao.
  Quay lại Store >=2 đơn; Cashbot >=2 ngày VN; không phải D7 retention. Trạng thái đọc là hiện tại, không backtest lịch sử.
- Đề xuất cho chủ vận hành PLAN-172: ưu tiên khảo sát khách nguồn threads_ai_price_anlinh trước khi thử biến thể tiếp theo;
  49/50 khách đủ 24h chưa đặt đơn đã giao trong 24h. Cỡ mẫu nhỏ, không khẳng định nguyên nhân/cải thiện từ thử nghiệm.
  Chưa thay copy, nhịp đăng, AI hay luồng mua.

## Verification Proof
Lệnh trong /home/vu/toolsauto, chỉ test DB tạm hoặc đọc mode=ro:

```text
.venv/bin/python -m pytest tests/test_growth_funnel.py tests/test_growth_report.py tests/test_bot_users.py tests/test_cashback_chat_ai.py tests/test_store_cashbot_invite.py tests/test_cashback_invite_nudge.py -q
.................................                                        [100%]
33 passed in 5.65s

.venv/bin/python -m ruff check cashback_bot/growth_funnel.py cashback_bot/growth_report.py tests/test_growth_funnel.py
All checks passed!

git diff --check
(no output; exit 0)

.venv/bin/python -m cashback_bot.growth_funnel --days 7 --json
generated_at: 2026-11-17T03:33:00.483836+00:00
since: 2026-11-10T03:33:00.483836+00:00
errors: []
exit 0
```

Đối chiếu bằng SQL độc lập trên Store: COUNT cohort users + EXISTS orders done/partial có total>refunded,
lọc julianday(created_at) >= joined_at và < now; mẫu số mature = joined_at <= now-1 ngày:

```text
store_independent_sql= {'customers': 99, 'buyers': 6, 'mature': 92}
independent_sql_vs_report=PASS
daily_report_chars= 1185 funnel_included= True elapsed_sec= 0.024
generated_at= 2026-11-17T03:35:01.238256+00:00
errors= []

git diff --numstat -- app/features/threads/growth/evaluator.py store_bot/bot.py tests/test_threads_growth.py
50  2  app/features/threads/growth/evaluator.py
52  2  store_bot/bot.py
27  1  tests/test_threads_growth.py
```

WIP trên trùng thống kê đầu phiên (52/54/28 dòng diff); không sửa hai file chat_ai WIP. Các file mới PLAN/TASK/test
không bị gitignore (git check-ignore không có output, exit 1 = không match).

## Anti Sign-off Gate
Reviewed by: Pending Antigravity. Chưa archive, chưa mark Done.

## Handoff Note
**Execution Done. Cần Claude Code verify + handoff.**

- CLI chạy được ngay: `.venv/bin/python -m cashback_bot.growth_funnel --days 7 --json` (bỏ --json để xem text).
- Chưa commit/push; chỉ scope trên + tài liệu. Chủ bot đã restart cashback-bot 17/11 10:37:40 VN, proof bên dưới.
  Runtime gửi sáng sau restart chưa verify. Không cần restart Store/Zalo/Threads/Dashboard cho thay đổi này.
- Anti review sign-off và Claude handoff còn pending; không archive PLAN/TASK.

### Post-restart proof — chủ bot restart 17/11, Codex chỉ đọc
```text
systemctl show cashback-bot --property=ActiveState,SubState,MainPID,ExecMainStartTimestamp,WorkingDirectory,ExecStart
MainPID=1340047
ExecMainStartTimestamp=Tue 2026-11-17 03:37:40 UTC
ExecStart=... /home/vu/toolsauto/.venv/bin/python -m cashback_bot
WorkingDirectory=/home/vu/toolsauto
ActiveState=active
SubState=running

systemctl show cashback-bot --property=ExecMainStatus,NRestarts
NRestarts=0
ExecMainStatus=0

tail logs/cashback_bot.log
2026-11-17 03:37:42,717 [Cashback] INFO setMyCommands ok
2026-11-17 03:37:43,674 [Cashback] INFO setMyDescription ok
2026-11-17 03:37:44,598 [Cashback] INFO setMyShortDescription ok
2026-11-17 03:37:45,529 [Cashback] INFO setMyCommands admin ok
2026-11-17 03:37:45,529 [Cashback] INFO start db=./data/cashback.sqlite rate=70 max_age_h=3 allowlist=1 public=True admin_notify=True
2026-11-17 03:37:45,533 [Cashback] INFO shopee auto sync enabled=True interval_min=240 reconcile_lookup=False max=10

DB mode=ro:
growth_report_day= ('2026-11-17',)
recent_reports= [('growth_report:2026-11-17', 'sent', '2026-11-17T01:00:25Z', '2026-11-17T01:00:29Z', 0),
 ('growth_report:2026-11-16', 'sent', '2026-11-16T01:28:16Z', '2026-11-16T01:28:33Z', 0)]
```
Số 0 cuối là has_funnel: báo cáo hôm nay đã gửi 08:00:29 VN trước khi triển khai, chưa có phễu mới.
Startup sau thời điểm sửa hai module (10:33:57 VN), không lỗi startup trong log; poller import growth_report và gọi
growth_report.tick trong vòng lặp. Không dùng việc này để khẳng định đã gửi phễu mới. Dự kiến bản 18/11 từ 08:00 VN
có phần mới nếu service chạy và cấu hình giữ nguyên; chưa có delivery proof, không xoá state/gửi lại thủ công.
