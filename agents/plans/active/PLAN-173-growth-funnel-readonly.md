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
| Created / Updated | 2026-11-17 / 2026-11-18 |

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


## Follow-up 2026-11-18 — CapCut measurement and content preparation
- Owner requested attracting users, then approved continuing three concrete steps: measure after the CapCut pivot, prepare truthful product-specific content, inspect where new customers stop. Codex executes this read-only extension under that direct instruction; no change to Claude-owned PLAN-172 customer experiments.
- Scope: new cashback_bot/store_campaign.py read-only aggregate CLI; tests/test_store_campaign.py; sanitized evidence and publish-ready drafts in reports/capcut-20261118/; update PLAN-173/TASK-060/current-status.
- Report uses an explicit since timestamp, selected product, optional source prefix and admin exclusions. Count overall/product stages separately, track only new-customer cohort, mature 24h denominator, QR statuses and net-of-refund delivered orders. Date cutoff is an observation boundary, not proof of CapCut attribution or causal lift. Existing first product/confirm marker is incomplete historical evidence.
- Content must use current catalog facts and validated existing deep-link behavior. Do not fabricate official status, discounts, testimonials, usage/buyer count, warranty, stock guarantee or paid campaign outcomes.
- No publishing/DM/broadcast, customer-flow/config/schema mutation, vendor/AI call, restart, commit/push or change to existing worker quotas. Posting requires a concrete audience/account/content authorization.
- Verify synthetic DB tests, read-only connection and missing DB behavior; run on actual SQLite without PII, save reproducible aggregate snapshot and precise next steps. No benefit claim until real registrations/orders occur.

### Follow-up execution / proof — 2026-11-18
- New cashback_bot/store_campaign.py: CLI báo cáo theo mốc thời gian và sản phẩm, SQLite mode=ro + read transaction; phân biệt overall/selected product, first-touch source, QR state, đơn done/partial sau hoàn, mẫu số đủ 24h. Không import bot/worker hay ghi DB; JSON không xuất thông tin cá nhân.
- tests/test_store_campaign.py kiểm offset/ranh giới, source prefix literal, loại admin, refund/failed, QR và đơn độc lập, exact 24h, DB thiếu không bị tạo, kết nối chặn ghi và CLI validation. Regression báo cáo hiện có cùng chạy.
- Reproducible evidence: reports/capcut-20261118/snapshot.py + cohort-proof.json; audit_runtime.py + runtime-audit.json; README.md và CONTENT.md. Snapshot lọc admin từ cấu hình nhưng không ghi ID ra artifact.
- Live 18/11 **14:36:02 VN**, cửa sổ từ commit 649d42e lúc **09:01:59 VN**: Threads-source cohort mới **1**, product/confirm/QR/paid/order **0**, đủ 24h **0**, doanh thu đơn sau hoàn **0đ**. SQL độc lập khớp 1. Không gọi đây là khách do CapCut đem lại: mốc commit chưa xác nhận activation/per-post attribution.
- Context 7 ngày trước mốc: Threads-source **91 khách**, **3 khách có đơn giao**, doanh thu sau hoàn **180.200đ**; riêng CapCut #2 **0 đơn trong cohort**. Không so hai cửa sổ khác độ dài để kết luận lift. Marker chỉ giữ lần đầu, thiếu marker không chứng minh bỏ màn.
- Catalog #2 sync14:35:50 VN: giá34.000đ, giá vốn ghi31.360đ, spread2.640đ trước chi phí, tồn cache25; cần recheck trước xuất bản.
- Runtime read-only 14:30 VN: approved Store25 (22 tạo trước commit,4 có từ CapCut);10 nhắc món khác không nhắc CapCut (heuristic). Store post-commit2 reply đăng,1 nhắc CapCut. Không sửa/reject hàng chờ. Worker online từ09:00:32 VN trước commit87giây; overrides CapCut khớp code defaults, chưa chứng minh mọi module tĩnh reload.
- Link buy_2 mở đúng món nhưng nguồn first-touch generic kenh; link threads_ai_* mở catalog. Không ghép payload chưa được hỗ trợ hoặc khẳng định đo được riêng bài. Own-post branch hiện chỉ phục vụ Cashbot. Nội dung mới là bản nháp, chưa đăng/gửi; tránh lời kể đã mua và so sánh giá chưa có căn cứ trong hook hiện tại.

~~~text
PYTHONPATH=. .venv/bin/python reports/capcut-20261118/snapshot.py
observed_at=2026-11-18T07:36:02.301588+00:00
independent_sql_matches=true
cohort.customers=1; not_yet_24h=1; selected_product.stages={product:0,confirm:0,qr:0,paid:0,order:0}
exit 0

.venv/bin/python -m pytest -q tests/test_store_campaign.py tests/test_growth_funnel.py tests/test_growth_report.py
.................                                                        [100%]
17 passed in 3.10s

.venv/bin/python -m ruff check cashback_bot/store_campaign.py tests/test_store_campaign.py reports/capcut-20261118/audit_runtime.py reports/capcut-20261118/snapshot.py
All checks passed!

git diff --check
(no output; exit 0)
~~~

- Next coordinated scope: duyệt hàng chờ cũ với PLAN-172; chọn account/content để phát hành; thống nhất link vừa mở đúng món vừa giữ campaign source nếu cần. Chưa thay flow/config/queue/schema, gọi vendor/AI, gửi tin, restart, commit/push.
- **Execution Done. Cần Claude Code verify + handoff.** Đây là hoàn tất phần đo/chuẩn bị, không phải hoàn tất mục tiêu tăng user. Anti sign-off/handoff pending; chưa Done/archive.

- Final content check: content_exists=True; draft_count=5; draft_characters=[251,296,292,189,212], all<=470; exit0. Final git diff --check exit0. Các bản nháp chưa đăng/gửi.

## Follow-up 2026-11-18 — Tracked CapCut trial (direct owner authorization)

### Authorization / assignment
Owner approved the concrete proposal: “oke em triển kahai thử đi em”, then “rồi em” after tool recovery. Codex executes this bounded feature extension under that direct instruction. It supersedes the prior read-only boundary only for the files/actions below; no Antigravity sign-off is fabricated. Notify PLAN-172 owner through a coordination note before customer-entry code changes. Existing T1/T2, payment/refund/price/stock and customer nudges stay outside this extension.

### Scope / sequence
1. store_bot/bot.py + tests/test_store_bot.py: additive buy_<positive-id>_<source> payload, source ASCII [a-z0-9_]{1,32}, full payload<=64. Preserve old buy_<id>, source-only and first-touch semantics; opening link must never buy, create QR or spend balance. Invalid new payloads do not open a product or write a campaign source.
2. app/features/threads/growth/config.py + tests/test_threads_growth.py: register only the explicit original-post trial source threads_ai_cc18_anlinh_p1 to AI Store/no A-B variant/anlinh, channel bài riêng for existing conversion aggregation. Do not change automatic A/B URLs, roles or quotas.
3. reports/capcut-20261118/: trial manifest, concrete seller-voice post based on current catalog, isolated fake transport/temporary-DB end-to-end smoke, read-only baseline and evidence. Review the existing Store queue and record specific decisions; do not blanket-delete/reject content using keyword heuristics.
4. Validate tests/lint/diff and verify runtime deployment prerequisites. Prepare one original CapCut post on the existing An Linh Store account, respecting session/account status and existing quota; no customer DM/broadcast or reply to unrelated strangers. Record exact content/account/source/actual outcome. No purchase/FatCat buy/QR/production test-user injection. No extra worker or auto-publishing scheduler, no quota changes, no ads/discounts.
5. Runtime restart, if still restricted by ADR067, must be presented as a concrete final step to owner after tested work is ready; never publish an unsupported link before the new handler is live. No commit/push requested for this increment. Anti/Claude review remains pending.

### Risks / proof / rollback
- First-touch applies only to new users: existing users do not get re-attributed. Missing first product marker does not prove drop-off. No claim of conversion lift from a tiny sample.
- Malformed, non-ASCII, huge IDs/overlength and duplicate start must be covered. A source code in a URL is an acquisition label, not authentication.
- A logged-out/checkpointed/busy profile prevents the live publish step. A timeout with uncertain posting result must be recorded as unknown, never blindly retried.
- Test on temp SQLite and mocked Telegram/FatCat, include report + code_map attribution. Save actual command outputs and sanitized aggregates only.
- Rollback only new parsing branch and trial mapping; preserve old URLs and unrelated WIP. No schema change and no production DELETE/DROP/archive.

### Owner approval and isolated restart — 2026-11-18
- Owner explicitly answered: «Cho em restart riêng store-bot» to the concrete restart + one prepared trial question. This authorizes only this service restart, superseding ADR067 restart restriction for this action; no other service restart authorized.
- Final related suite (including full fake QR/payment/delivery journey for the tracked entry):243 passed in22.77s; Ruff All checks passed!; git diff --check exit0. Fake transport/vendor + temporary SQLite only; no real transaction.
~~~text
sudo -n systemctl restart store-bot
systemctl show store-bot --property=ActiveState,SubState,MainPID,ExecMainStartTimestamp,NRestarts,ExecMainStatus
MainPID=3966961
NRestarts=0
ExecMainStartTimestamp=Wed 2026-11-18 09:11:03 UTC
ExecMainStatus=0
ActiveState=active
SubState=running
~~~

### Original-post vs reply limits clarification
- Code review of runner.posting_quota + worker.post_own confirms16/day limit counts replies in growth_posts only. Original posts use own_posts slots separately. The initial readiness gate treating reply quota as a block on the owner-approved original post was overly broad and has been removed; reply counts remain visible. No limit/role change or extra reply.
- Owner-authorized exactly one original An Linh post is recorded through reports/capcut-20261118/publish_trial.py using existing GrowthBrowser. This is a bounded operational artifact, not a new worker/scheduler: read-only preflight by default, explicit --publish, live identity check, SQLite own_posts unique attempt fence, unknown on ambiguous result and no blind retry; browser context manager closes resources.

### Tracked-link trial — execution verified and one post published
- Backend additive /start branch (18-line diff), tests/test_store_bot.py regression + fake full journey: accepts positive bounded ASCII ID/source, rejects invalid/overlength/overflow, preserves legacy links and is_new/first-touch. Opening never creates QR/order/spends balance. No schema or pricing/payment code change.
- Explicit source registration maps trial to AI Store / An Linh / bài riêng with variant None; existing A/B URLs and aggregates preserved. Independent review found no blocking parser or mapping bugs.
- Actual related validation:
~~~text
.venv/bin/python -m pytest -q tests/test_threads_growth.py tests/test_store_bot.py tests/test_store_campaign.py tests/test_growth_funnel.py tests/test_growth_report.py tests/test_store_nudge.py tests/test_store_cashbot_invite.py
243 passed in22.77s
.venv/bin/python -m ruff check store_bot/bot.py tests/test_store_bot.py app/features/threads/growth/config.py tests/test_threads_growth.py cashback_bot/store_campaign.py tests/test_store_campaign.py reports/capcut-20261118/*.py
All checks passed!
git diff --check
exit0
~~~
- Restart specifically owner-approved above. Post-start log:2026-11-18 09:11:06,969 [Store] INFO store bot @aipass_shop_bot sẵn sàng (nguồn FatCat: bật, chat_ai: bật). Existing service sync continued normally; no manual vendor/purchase test was made.
- Readiness16:19VN: blocked_checks=[], account ACTIVE, profile unlocked, price34.000đ and cached availability; fresh service PID3966961 loaded handler after edit. Baseline new trial source0customers.
- Concrete original post273characters in trial-manifest.json. Publication exact account verified live. First invocation stopped before create_post due @ prefix normalization mismatch (recorded not_published). Corrected @ normalization and only retried the proven pre-create failure. Second invocation called create_post once; saved unknown on missing permalink, never retried publication. Read-only verification found exact full text+price+unique source on own profile and correct permalink; outcome updated posted. No extra customer message/DM/reply or quota/role change.
- Verified post: https://www.threads.com/@anlinh_08_10/post/Df4LF2IFIlg . Proof trial-publication.json + trial-verification.json; exactly1 own_posts trial row posted; profile_locked=false afterward. Existing automated own_posts remainsfalse for An Linh.
- Manual queue review of27approved Store replies (reply copy only, original posts not read) saved sanitized per-ID recommendations in queue-review.json. No queue mutation:13offtopic,5outdated,3testimonial,3unverifiedclaim,3CapCut candidates needing original context/warranty check. These are recommendations, not approval to post.
- Final read-only source measurement16:26:39VN: errors=[],0customers/QR/orders/revenue,0mature24h, conversionnull. New post must not be classified success/failure from this immediate sample; no click/impression tracking before Telegram Start. Published_at is attempt start, not exact publish-second.
- Re-run measurement with PYTHONPATH=. .venv/bin/python reports/capcut-20261118/measure_trial.py . No recurring job created or extra report recipient. Dashboard process still needs separate reload for its new source mapping; CLI already loads current code.
- **Execution Done. Cần Claude Code verify + handoff.** Scoped implementation/restart/one-post trial done; growth outcome pending observation. No commit/push requested or performed, no archive/Done or fabricated Anti sign-off.

### Monitoring requested by owner — 18/11/2026
- Owner: «em theo dõi báo cáo cho anh nhé». Created active heartbeat in this chat: theo-d-i-t-th-capcut, every15minutes, read-only campaign measurement via measure_trial.py, compare prior aggregate snapshot. Notify meaningful new customers/orders or measurement/runtime errors; assess first mature24h cohort after publication. No new publishing/DM/purchase/restart or campaign expansion authorization. Automation tool returned Created automation in the app, statusACTIVE; view rendered card.

### Owner-requested specialist team — 18/11/2026
- Owner requested several agents to act as contributors and specialists and do work. Dispatch three parallel roles under this campaign: content contributor, conversion specialist, measurement/economics analyst. Deliver concrete artifacts in reports/capcut-20261118/team/ and a consolidated action report. These are AI task roles, not real employees or credentials.
- Scope: read existing code/proof and current aggregated metrics/catalog; prepare truthful copy, identify conversion issues with file/line evidence, compare exact-source results and per-unit economics. Documents only, no new product/backend edits, no customer/private data export, no external posting/DM/broadcast, purchases/vendor/AI calls, service/config/queue/price mutations or commit/push. Publishing authorization remains limited to the already completed one-post trial. No new recurring schedule is implied.

### Specialist team output / verification — 18/11/2026
- Three agents completed separate content/conversion/measurement deliverables in reports/capcut-20261118/team/. Root consolidated TEAM-REPORT.md and reviewed evidence, no production changes.
- Content:3drafts+2reply,253/300/252/190/207characters, all<=470; unpublished. Same trial link must not be reused to claim per-draft attribution.
- Conversion:3evidenced points (BHFconditions, delivery expectation vs waiting_funds, welcome context),3customerquestions,2bounded proposed experiments with stoprules, not executed. Code/current features separated from unproven causes.
- Read-only fresh measurement17:17:40VN source0new/QR/orders,0revenue, mature24h0/ratenull. SQL17:19:59 exactsource=prefix=report0. Catalogprice34000/cost31360/spread2640beforeothercosts; no netprofit/budgetclaim.
- Artifact check5/5 nonempty, JSONparse/independent_SQLmatchPASS; root draftlengthcheckPASS; git diff --check exit0. No backend/test/runtime/queue/price changes or external sends; source diffs same as prior milestone.
- **Execution Done. Cần Claude Code verify + handoff.** Team first work cycle completed; source monitoring heartbeat runs every15minutes. Not archived/Done; no commit/push.

### Monitoring cadence updated by owner — 18/11/2026
- After owner confirmed «có em», active heartbeat theo-d-i-t-th-capcut updated in app to every15minutes. Local automation.toml verified statusACTIVE, target thread unchanged, prompt preserved with read-only/alert-only scope.
- This is scheduled check-ins, not three continuously running model processes. If no meaningful data change, prompt suppresses repeated reports.
