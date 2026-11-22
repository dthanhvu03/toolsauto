# PLAN-178 — Agent tìm khách và tương tác, dùng chung Threads Growth

> **Owner stopped20/11/2026 — PLAN185:** chủbot hủy toàn bộ agent tăngtrưởng để chọn hướng mới dựa research. Runtime2processstopped/PID0,growth.enabled=false,heartbeatđãxóa; khôngtựbậtlại. Giữcode/history/proof cũ bên dưới. Statusnàythaythế mọi chỉdẫn tiếp tục chạy nền trong PLAN.

## Metadata
| Field | Value |
|---|---|
| ID | PLAN-178 |
| Status | Execution verified. Anti sign-off and Claude handoff pending |
| Executor | Codex |
| Related Task | TASK-064 |
| Related Decisions | ADR-066, ADR-067; existing PLAN-159/171/172 |
| Created | 2026-11-19 |

## Authorization
Chủ bot yêu cầu thêm agent tìm khách và tương tác, sau đó trả lời trực tiếp **“Cho em lập PLAN và triển khai”** khi Codex hỏi ngoại lệ quy trình. Phạm vi đã trình bày: hai vai chạy nền trong Threads_Growth, tìm đúng nhu cầu và chống trùng; chỉ tương tác inbound bằng đúng tài khoản, chuyển việc tiền/đơn/bảo hành cho chủ bot. DM An Linh chưa bật trước khi sửa identity và xác minh inbox. Không giả danh Anti, không tự ký sign-off.

## Goal
Hai vai làm việc trong worker Threads_Growth hiện có, không thêm browser/sender tranh profile: acquisition tìm nhu cầu phù hợp từ scanner hiện có; engagement xử lý câu hỏi inbound trong hạn mức hiện tại. Có trạng thái tổng hợp theo vai để chủ bot thấy lúc nghỉ/chờ/đang làm/lỗi; không coi quét/nháp là khách mới.

## Context and verified baseline
- Read-only snapshot 04:48 VN: 37 bài AI Store <=24h, không có cơ hội mới đủ điều kiện; 10 bài approved có ngữ cảnh chưa phù hợp. Stored inbox có 21 cuộc chỉ metadata và lịch sử nội dung cũ, không chứng minh inbox live hiện trống.
- Threads_Growth online PID4169711; current scan override120min, quiet hours fallback00:30-06:30 VN; không tăng nhịp/quota. Accounts: us28qt cashbot/DM on; anlinh ai_store/DM off.
- dm_agent currently hardcodes @us28qt and both bot offers. Reusing it for another account without scoping is incorrect. PLAN-176 is aggregate-only and stays unchanged.
- Existing evaluator/runner and tests contain WIP; preserve all prior changes and modify only named feature blocks. No reset/checkout/stash.

## Scope
1. New app/features/threads/growth/acquisition.py: deterministic, evidence-based opportunity gate; reject job/recruitment/seller/free-only/already-served/unrelated contexts. AI Store acquisition matches the current CapCut offer, not every generic AI mention. Existing Cashbot flow remains scoped to shopper needs. Unit tests in tests/test_customer_acquisition.py.
2. Surgical evaluator.py/content.py prompt refinements: seller/helper voice, no invented personal purchase/use/testimonials, no unrelated product pitch or guarantee. Acquisition gate integrated in runner.py before model use and worker.py before sending old approved rows; do not mass rewrite/delete the existing queue.
3. dm_agent.py account/allowed-bot context, matching tracking links, deterministic human handoff for money/order/warranty/human requests and reply validation. Preserve inbound detection, dedupe, rate limits, hold and browser lifecycle. Tests in tests/test_customer_engagement.py and narrowly update existing DM tests if API expectations change.
4. worker.py integrates both named roles through existing scanner/queue/followup/DM lifecycle. Public inbound support cases route to owner rather than an AI sales answer. New customer_agents.py writes atomic aggregate-only role status under reports/customer-agents/status.json (no handles, thread IDs, text or PII). Tests in tests/test_customer_agent_runtime.py. No extra process/model loop.
5. Extend existing owner heartbeat to read the new status, with no additional schedule or customer actions. Record actual tests/runtime proof and handoff in PLAN/TASK/current-status/PLAN-172.

## Out of scope
No HTML/CSS, schema migration, financial/vendor/QR/order mutation, price/stock/product changes, cold DM/broadcast, quota/quiet-hour change, profile/cookie/login/checkpoint bypass, enabling An Linh DM, additional automatic original posts, commit/push. No forced scan or customer test message. Only the Threads_Growth process may be reloaded for the requested deployment after offline verification; no Store/Cashbot/Dashboard/supervisor restart.

## Steps
1. Capture baseline; implement/test the acquisition and account-scoped engagement pieces independently.
2. Integrate worker role state, send-time acquisition gate and inbound support handoff; verify mocked cycle and regression tests.
3. Run all related tests, Ruff, py_compile and diff checks. Perform read-only real DB replay (no AI/sends) and status checks.
4. Reload only Threads_Growth to load approved code, preserving current roles and quiet hours. Verify PID/start time/status artifact/process health and other process PIDs unchanged. While quiet hours are active, report paused status honestly; live natural customer-event proof stays pending until observed.
5. Update existing heartbeat and durable evidence; leave Anti/Claude sign-off pending.

### Integration refinement before edits
- Add a backward-compatible offset argument to storage.py:approved_queue (read SELECT only, no schema change), and bounded rotating pagination in worker.py. Merely skipping the first20 invalid approved rows would otherwise starve valid rows behind them. Root owns this additional integration file.
- Narrowly update old fixture data in tests/test_threads_growth.py to explicit genuine buyer contexts where the test purpose is queue/variant/quota behavior; preserve existing WIP assertions and add negative tests for the stricter eligibility contract.
- Replace the two old AI Store examples in cli.py with CapCut buyer examples so the isolated CLI demo continues to exercise both bot targets.

## Risks and controls
- Filter false negatives: use explicit normalized demand signals, test accented/unaccented variants and legitimate buyer questions; preserve reasons and audit counts. Filters do not infer a sale or causality.
- Existing approved backlog: revalidate at send time without changing old rows en masse. Blocked rows stay visible for owner review.
- Account/bot contamination: explicit account/allowlist context and output link/bot validation; unknown/disabled account fails closed. An Linh DM remains false.
- Snapshot freshness: do not label old DB history a live inbox scan; quiet-hours status is paused, not error and not success.
- Worker crash/status write failure: status writes atomic/best-effort, do not stop browser cleanup or turn a reporting error into repeated sends. Existing single-worker/browser lifecycle and delivery dedupe remain.
- No new source writes are delegated to the same file concurrently; workers share the repo.

## Verification
Mocked AI/browser and temporary SQLite only for tests. Cover positive/negative opportunity boundaries, old approved blocking, unchanged quotas, seller-voice prompts, account-specific identity/links, cross-bot rejection, deterministic handoff, already-answered/no-inbound behavior, and atomic redacted status for quiet/disabled/no-ready/error/active cycles. Run existing Threads/DM/psych/conversion/supervisor tests as relevant. Real runtime proof must distinguish code loaded and quiet status from actual customer delivery; do not fabricate inbound or post a smoke message.

## Rollback
Stop/reload only Threads_Growth with a reviewed surgical patch reverting the PLAN-178 code blocks; preserve unrelated WIP and existing DB/queue/history. Do not git reset or delete customer state. Status artifacts can remain as proof. No production data rollback is needed for pure gating/scoping.

## Execution and verification — 19/11/2026

1. Acquisition checks shopping intent before calling AI and checks both the original post and draft before sending. The worker reads the current approval again before sending and validates the account's tracking link. Held rows stay in the queue for review. The SQLite replay at 05:21 VN used mode=ro and returned query_only=1. It held 24 approved AI Store rows: 13 no matching product, 6 no purchase need, 3 recruitment, 1 offer mismatch, 1 support dispute. The only recent suitable post in the replay was already posted.
2. Engagement checks the enabled role and bot before replying to inbound messages. Public replies and DMs send support cases to the shop owner even when the reply quota is exhausted. The worker suppresses further requests to an unavailable AI provider for the current pass while continuing support triage. Status exposes account aliases, role states, aggregate counts and error types.
3. Related pytest suite returned **328 passed in 31.76s** across Threads Growth, DM, the three customer agent test files, psychology guidance, Threads login, CapCut supervisor, campaign, funnel and growth report. Ruff returned **All checks passed!**. Python compilation, ecosystem syntax and git diff --check returned exit 0.
4. At 05:24:33 VN, pm2 restart Threads_Growth changed PID 4169711 to 1149851. PM2 reported online and zero unstable restarts. Other PM2 and systemd bot PIDs and the account role file matched the pre-reload snapshot. Status from the new PID reported quiet_hours for both roles. At 05:27:02 VN the heartbeat was 05:26:48 VN with no active cycle. The configured quiet period ends at 06:30 VN. Natural scan, reply and conversion outcomes still need observation.
5. The existing heartbeat update returned ACTIVE. Readback confirmed the same chat, 15-minute interval and the new aggregate status path. Live status is reports/customer-agents/status.json and the deployment snapshot is reports/customer-agents/runtime-proof.json.

## Handoff
**Execution Done. Cần Claude Code verify + handoff.** Anti sign-off and Claude handoff remain pending. Keep the PLAN and TASK active. Track the first natural cycle separately from deployment health.
