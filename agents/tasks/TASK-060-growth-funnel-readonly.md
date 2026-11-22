# TASK-060 — Báo cáo phễu theo nguồn cho hai bot

## Metadata
| Field | Value |
|---|---|
| ID | TASK-060 |
| Status | Verified — Anti sign-off / Claude handoff pending |
| Priority | P1 |
| Executor | Codex — ngoại lệ chủ bot duyệt trực tiếp 2026-11-17 |
| Related Plan | PLAN-173 |
| Created / Updated | 2026-11-17 / 2026-11-18 |

## Objective
Đo nguồn khách và điểm chưa sử dụng hai bot bằng dữ liệu hiện có, có CLI kiểm được ngay và tóm tắt báo cáo sáng.

## Scope / Out of Scope
Theo PLAN-173. Chỉ đọc SQLite, không sửa luồng khách/tiền/schema/UI hay thử nghiệm PLAN-172.

## Blockers
Không có cho execution đã được chủ bot duyệt. Anti sign-off/handoff và restart production chờ sau execution.

## Acceptance Criteria
- [x] Báo cáo theo bot/nguồn với bước sử dụng, chuyển đổi 24h đúng mẫu số và khách quay lại.
- [x] Không đếm failed/cancel/refund toàn phần là thành công; timezone và cửa sổ cohort đúng.
- [x] DB thiếu trả lỗi rõ, DB còn lại vẫn báo cáo; không ghi DB, không gọi API/gửi tin.
- [x] Tóm tắt nối báo cáo sáng hiện có; CLI JSON/text dùng được; không lộ tên/ID khách.
- [x] Test + lint + số liệu mode=ro thật ghi vào PLAN và current-status.

## Execution Notes / Verification Proof
Code: cashback_bot/growth_funnel.py mới, growth_report.py nối summary và ghi rõ hai cửa sổ thời gian,
tests/test_growth_funnel.py mới. Không sửa WIP của agent khác.

```text
.venv/bin/python -m pytest tests/test_growth_funnel.py tests/test_growth_report.py tests/test_bot_users.py tests/test_cashback_chat_ai.py tests/test_store_cashbot_invite.py tests/test_cashback_invite_nudge.py -q
33 passed in 5.65s
.venv/bin/python -m ruff check cashback_bot/growth_funnel.py cashback_bot/growth_report.py tests/test_growth_funnel.py
All checks passed!
.venv/bin/python -m cashback_bot.growth_funnel --days 7 --json
exit 0; errors=[]
store_independent_sql= {'customers': 99, 'buyers': 6, 'mature': 92}
independent_sql_vs_report=PASS
daily_report_chars= 1185 funnel_included= True elapsed_sec= 0.024
generated_at= 2026-11-17T03:35:01.238256+00:00
```

Chi tiết số liệu, định nghĩa và hạn chế ở PLAN-173. Chủ bot restart 17/11 10:37:40 VN: active/running,
PID 1340047, NRestarts=0, log đăng ký profile và startup OK. Báo cáo 17/11 đã sent 08:00:29 VN trước bản mới,
state growth_report_day=2026-11-17 nên không gửi lại. Chờ bản 18/11 từ 08:00 VN để verify delivery phễu mới.
**Execution Done. Cần Claude Code verify + handoff.**

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-11-17 | In Progress | Chủ bot cho phép Codex tự viết PLAN và execute phạm vi đã nêu; Anti sign-off để chờ review |
| 2026-11-17 | Verified | 33 tests + ruff + CLI DB thật + SQL đối chiếu; chưa mark Done/archive |
| 2026-11-17 | Verified | Chủ bot restart; service startup OK. Delivery báo cáo mới 18/11 còn pending |

## Follow-up 2026-11-18 — đo riêng CapCut và chuẩn bị nội dung
- Chủ bot yêu cầu thu hút user rồi đồng ý tiếp tục đo sau pivot, chuẩn bị nội dung đúng món và khảo sát điểm chưa sử dụng; thực thi extension chỉ đọc của PLAN-173, không sửa thử nghiệm PLAN-172.
- Thêm store_campaign.py + test; CLI theo mốc/product/source, loại admin tùy chọn, phân biệt các bước và mẫu số24h. Reproducer snapshot.py tự lọc admin từ cấu hình, không xuất ID.
- DB thật14:36 VN: sau mốc code09:01:59 VN có1 khách mới nguồn Threads,0 marker xem món/QR/đơn,0 khách đủ24h; SQL độc lập khớp. Chưa có attribution hoặc bằng chứng tăng user nhờ CapCut.
- Runtime14:30 VN:25 Store approved,22 cũ trước mốc,4 nhắc CapCut;10 nhắc món khác không CapCut theo keyword. Không sửa hàng chờ/config/worker. buy_2 mở đúng món nhưng nguồn kenh, chưa giữ campaign code.
- Proof:17 tests passed in3.10s; ruff All checks passed!; git diff --check exit0. Chi tiết số liệu/lệnh: PLAN-173 và reports/capcut-20261118/README.md; JSON tổng hợp và script chạy lại cùng thư mục.
-3 bài và2 reply mẫu trong CONTENT.md là bản nháp chưa đăng; kiểm lại giá/tồn trước xuất bản. Không gửi tin/post/broadcast, gọi vendor/AI, đổi flow/schema, restart, commit/push.
- **Execution Done. Cần Claude Code verify + handoff.** Đo/chuẩn bị hoàn tất; acquisition chưa có kết quả mới được chứng minh, Anti sign-off/handoff pending.

## Follow-up tracked trial — 18/11 execution verified / published
- Owner approved tracked product link + small CapCut trial, then explicitly authorized restart of store-bot only. Scope extensionPLAN173 and coordinationPLAN172 recorded before code.
- Additive buy_<id>_<source> branch + bounded validation/legacy/first-touch tests; one explicit source threads_ai_cc18_anlinh_p1 maps to An Linh / bài riêng / variantNone. No schema/payment/price/quota/role change.
-243relatedtests passed in22.77s; full fake payment/delivery preserves source and buys once. RuffAllcheckspassed; diffcheckexit0. Real restart16:11VN:PID3966961, active/running,NRestarts0; startupreadylogverified.
- One original post actually published and independently read back: https://www.threads.com/@anlinh_08_10/post/Df4LF2IFIlg . Exactfulltext/source/price match;1create_post call and1postedDBrecord; no reply/DM/broadcast. Adapter initial permalink uncertainty resolved read-only, no duplicate publication.
- queue-review.json records recommendations for27approved Store replies without mutations. trial-measurement.json16:26VN: source0newcustomers/QR/orders,0mature24h; no growth outcome claim. measure_trial.py reruns aggregate read-only.
- Proof/content/runtime details reports/capcut-20261118/TRIAL.md and PLAN173. No commit/push, Dashboard mapping reload still pending; no archive/Done.
- **Execution Done. Cần Claude Code verify + handoff.** Trial deployed/published; acquisition outcome waits observation.
