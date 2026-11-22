# TASK-076 — Vá caption AI để status cụ thể và gợi được trò chuyện

## Metadata

| Field | Value |
|---|---|
| ID | TASK-076 |
| Status | In Progress — code steps 0–8 and isolated sample batches complete; Codex preliminary 14/15 threshold, sample 2061 pending; Claude review, rollout, and Anti sign-off pending |
| Priority | P1 |
| Owner | Chủ bot giao trực tiếp lập PLAN; Anti review pending |
| Executor | Codex |
| Related Plan | PLAN-190-caption-context-and-conversation-repair.md |
| Created / Updated | 2026-11-21 VN |

## Objective

Sửa lỗi ngữ cảnh/style/prompt để caption mới bám nội dung, có ý cụ thể cho người đọc phản hồi; có proof kỹ thuật và15mẫu nháp được review trước rollout.

## Scope

Đợt1: baseline test AI; giữ context/part; thống nhất prompt, thêm conversation; đăng ký style; nối niche đúng đích nếu có; chống trùng gần đây có giới hạn ở material.

Đợt2 độc lập: sửa sandbox AI Studio, JSON contract API đơn giản, Threads formatter giữ ý/câu hỏi. Danh sách file và gate từng bước ở PLAN190; mỗi lỗi tối đa3file tính cả test.

## Out of Scope

UI/schema/provider/queue/customerflow/tiền, sinh lại caption cũ hàng loạt, đăng/tương tác, restart hoặc bật growth, can thiệp monitor/agent của PLAN189. Map niche/audience chung Buffer+Studio và history/diversity xuyên toàn bộ caller cần scope/PLAN riêng vì vượt3file; gate cơ học chung ở orchestrator thuộc PLAN190 nhưng không tương đương history cho mọi caller.

## Acceptance Criteria

- [x] AC1 — Plain context, title marker và chỉ dẫn phần con vào prompt đúng; không nhân đôi hoặc coi dữ liệu nguồn là chỉ dẫn hệ thống.
- [x] AC2 — Mỗi style có một budget hợp cap; non-sales không bị ép Facebook Ads/FOMO/keyword CTA; không bắt mọi bài có dấu hỏi.
- [x] AC3 — ai.caption_style đăng ký đúng; conversation chọn được; explicitstyle ưu tiên; DB tạm kiểm default/override/invalid; không đổi live setting trong test.
- [x] AC4 — Material chỉ nhận niche có mapping đúng đích; Buffer/Studio thiếu metadata được ghi unknown; không đoán nhân khẩu từ tên page.
- [x] AC5 — Material history chỉ cùng page, loại bản đang sửa; tối đa1rewrite; caption xấu/trùng hết lượt không ghi đè caption cũ hoặc schedule/notifier success; caller cũ/schema không gãy.
- [x] AC6 — Sandbox không lỗi missingmethod, dùng đúng persona/input; API đơn giản giữ JSON/response contract; Threads giữ câu hỏi/ý chính và mandatoryfooter hoặc trả không có draft.
- [x] AC7 — Test/compile/Ruff/diff có output thật; baseline test cũ minh bạch; không gọi network/ghi DB/runtime thật từ test.
- [ ] AC8 — 15mẫu cố định review tối thiểu8/10 mỗi mẫu và factual2/2; lỗi giữ pending. Không khẳng định tăng tương tác khi chưa có metric xuất bản.
- [ ] AC9 — WIP khác được giữ; rollout/rollback setting có before-after và caller coverage rõ; Claude verify + Anti sign-off trước Done/archive theo workflow.

## Blockers / Dependencies

Lập plan đã được chủ bot yêu cầu trực tiếp. Chủ bot đã giao triển khai; review 15 mẫu và rollout vẫn pending. Không giả plan được approve hay source đã sửa. Dữ liệu niche/audience riêng Buffer/Studio hiện chưa có, được tách rõ khỏi phần sửa hẹp.

## Execution Notes / Verification Proof

- Code steps 0–8 complete with proof. Isolated fixed-sample generation and Codex preliminary review complete: 14/15 meet threshold, but 2061 scores 6/10; AC8 remains FAIL/PENDING. Claude review, rollout/style readback, and Anti sign-off: PENDING.
- Baseline audit thật: `reports/ai-caption-audit-20261121/AUDIT.md`.
- PLAN190 mô tả chi tiết thứ tự, filebudget, lệnh verify và rollback; chưa có proof bản vá.

## Status History

| Date | Status | Note |
|---|---|---|
| 2026-11-21 VN | Planned | Chủ bot yêu cầu lập kế hoạch sau audit; tạo PLAN190/TASK076, chưa code/live action |

## Execution Update — 2026-11-22

- Status: Code steps 0–8 complete with proof; 15-sample review, rollout/readback, Claude verification, and Anti sign-off remain pending.
- Two test modules now import the current AI modules. Baseline command: env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_ai_pipeline.py tests/test_ai_pipeline_async.py tests/test_ai_use_cases.py tests/test_material_caption.py -q → **44 passed, 6 failed, 5 warnings in 9.77s**. Both test modules collect; one sync assertion is stale against current transport config, and five async cases require a pytest async plugin absent from this environment. No production/provider code changed and no live AI call made.


### Step 1 proof — 2026-11-22

- Prompt contract tests: 3 passed in 1.75s. py_compile, Ruff, and git diff --check passed. Plain context, title/boost markers, part cues, empty context, and untrusted-source instruction are covered with mocked AI.


### Step 2 proof — 2026-11-22

- Prompt contract tests: 11 passed in 1.47s. py_compile, Ruff, and git diff --check passed. Coverage includes all six style budgets, non-sales role, factual sales guardrails, and unknown-style fallback.


### Step 3 proof — 2026-11-22

- Temporary SQLite setting tests: 3 passed in 1.31s. py_compile, Ruff, and git diff --check passed. No migration/config default change; invalid values are rejected.


### Step 4 proof — 2026-11-22

- Material caption suite: 30 passed in 9.73s. py_compile, Ruff, and git diff --check passed. Exact page mapping passes; wrong target, missing source account, and missing account metadata all remain unknown.


### Step 5 proof — 2026-11-22

- Material tests: 36 passed in 5.69s. Prompt/style regressions: 14 passed in 2.93s. py_compile, Ruff, and git diff --check passed. History remains target-page scoped; invalid output gets at most one rewrite and never schedules as success.


### Step 6A proof — 2026-11-22

- AI Studio contract tests: 4 passed in 1.25s. Plain/fenced JSON parses; malformed JSON returns existing tuple; mocked pipeline failure preserves exception behavior. py_compile, Ruff, and git diff --check passed.


### Step 6B proof — 2026-11-22

- AI Studio tests: 6 passed in 2.36s. Persona/niche and synthetic test data are separated; fixed sample claim removed; UI JSON keys retained. py_compile, Ruff, and git diff --check passed. All responses mocked.

### Step 7 proof — 2026-11-22

- Simple-caption API service tests: 3 passed in 1.45s. Draft is serialized in an untrusted data block; non-CaptionPayload results are rejected; caption/meta response and hashtag formatting are preserved. py_compile, Ruff, and git diff --check passed; facade mocked.
- Status: Steps 0–7 complete. Step 8 pending after review of existing Threads formatter diff; fixed 15-sample review, rollout setting/readback, Claude verification, and Anti sign-off remain pending.


### Step 8 proof — 2026-11-22

- Baseline SHA256 before Step 8: content.py 3c62b3c14da75abe3b02385da103b529722c0d5e2e7fa637ca956b21728b22dc; test_threads_growth.py 0892c57a46fcd8836065706a4f6eea6ce94b5ee8a86c884f1ae28715a604dd64. Existing WIP was reviewed and preserved.
- Threads suite: 100 passed in 7.55s. Questions/opening and mandatory cart/link content survive shortening; impossible-to-fit item/link drafts are skipped. py_compile, Ruff, and git diff --check passed; AI mocked.
- Code implementation steps 0–8 complete. The required fixed 15-sample review, live style setting/readback, Claude verification, and Anti sign-off are still pending. No production setting or runtime action taken.

### Final regression gate — 2026-11-22

- AI Studio + simple-caption API + Threads: 109 passed in 4.92s. This gate used mocks/offline fixtures; no AI network or runtime call.

### Handoff update — 2026-11-22

- Codex execution for steps 0–8 is complete; AC1–AC7 have implementation and offline proof recorded above. AC8–AC9 remain pending because fixed 15-sample review, Claude verification, rollout/style readback, and Anti sign-off have not occurred.
- Next owner/action: Claude Code reviews the 15 fixed samples and changed surfaces, then records handoff/current-status. Anti must complete the sign-off gate before this task can be marked Done or archived. No live setting, worker, or publishing action is authorized by this handoff.

### Sample batch update — 2026-11-22

- Fixed sample set: 15 (five life, five fashion, five other), manifest and source hashes recorded in `reports/ai-caption-repair-20261121/sample_manifest.json`.
- Isolated generation produced 15 initial drafts plus one revision for each of eight initial failures: **23/30** facade calls. Primary provider returned HTTP 400 `chat_completions_disabled`; configured 9Router Gemini 3.8 Flash fallback generated the drafts. RPA/browser fallback was blocked; no live settings, caption rows, schedule, worker, or runtime changed.
- Codex preliminary review: 14/15 meet 8/10 and factual 2/2; sample 2061 is 6/10 and remains pending. Full evidence: `reports/ai-caption-repair-20261121/review.md` and `drafts.json`.
- Prompt contract proof after narrow Step 2 adjustment: 12 passed in 1.49s; py_compile, Ruff, and git diff --check passed. AC8 unchecked. Claude review and Anti sign-off remain required before rollout or Done/archive.
