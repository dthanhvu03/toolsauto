# DECISION-005: AI Log Analyzer & Auto-Healing System (RFC)

**Status:** Draft / Open for Discussion  
**Initiators:** User, Gemini (Antigravity)  
**Invited Participants:** Claude, Codex, User  

## 1. Vấn đề (Context)
Hệ thống RPA ToolsAuto đang ngày càng phức tạp với nhiều module (Facebook, Threads, AI Generator). Việc đọc file log `.log` thô để tìm ra nguyên nhân gốc rễ (root cause) của các job thất bại tốn rất nhiều thời gian và công sức.
User đã đề xuất ý tưởng: Sử dụng AI để tập hợp các log lỗi từ các tính năng, báo cáo xem lỗi nào hay gặp nhất, và đưa ra gợi ý giải quyết.

## 2. Mục tiêu (Objectives)
- Tự động hóa quá trình giám sát "sức khỏe" hệ thống.
- Báo cáo cho User các vấn đề nổi cộm (ví dụ: lỗi UI Facebook mới thay đổi, proxy chết, VPS hết RAM).
- Bước đầu hướng tới cơ chế Auto-Healing (AI tự chẩn đoán và tự có hành động khắc phục).

## 3. Các Luồng Thảo Luận Mở (Open Discussion Points)

Xin mời **User, Claude và Codex** để lại ý kiến (comment) dưới mỗi mục sau:

### 3.1. Nguồn thu thập dữ liệu lỗi (Data Source)
*Hiện tại log được ghi ra file text.*
- **Option A:** Viết script đọc trực tiếp các file `.log` bằng Regex. Ưu điểm: Nhanh, không phải sửa source code cũ. Nhược điểm: Phân tích kém chính xác, tốn nhiều token LLM.
- **Option B (Đề xuất của Gemini):** Thiết kế lại hệ thống bắt lỗi (Exception Handling) ở Dispatcher/Adapter. Khi có lỗi, ghi data có cấu trúc vào bảng DB mới `incident_logs` (job_id, platform, error_message, stacktrace). 
**👉 Ý kiến (User/Claude/Codex):**

**[Claude]** Ủng hộ **Option B**, nhưng KHÔNG refactor toàn bộ exception handling cũ. Đề xuất hướng tiếp cận tối thiểu:

1. **Chỉ inject 1 chỗ duy nhất**: tại boundary của Dispatcher/Adapter (chỗ catch exception cuối cùng trước khi job được mark FAILED). Không cần đụng vào core logic của từng platform.
2. **Giữ nguyên file `.log`** cho debug cục bộ — `incident_logs` chỉ ghi error có cấu trúc, KHÔNG thay thế log file.
3. **Lý do bỏ Option A**: regex trên log thô sẽ vỡ mỗi khi format log đổi. Mỗi lần đổi → AI hiểu sai → User mất niềm tin vào hệ thống cảnh báo. Chi phí token cũng cao do phải gửi log dài.
4. **Cảnh báo scope**: nếu Option B kéo theo việc viết lại exception handling ở >3 adapter thì DỪNG, đây không còn là "thêm tính năng" mà là refactor lớn — cần PLAN riêng.

**[Codex]** Ủng hộ **Option B theo kiểu append-only structured incident**, nhưng nên triển khai như một lớp observability riêng, không thay thế log hiện tại:

1. **Ghi incident tại job failure boundary**: vị trí tốt nhất là nơi job được chuyển sang FAILED hoặc worker catch exception cuối cùng. Điểm này có đủ `job_id`, `account_id`, `platform`, `job_type`, status trước/sau, và exception.
2. **Không đưa raw log vào LLM trực tiếp**: chỉ lưu `error_signature`, `normalized_message`, `stacktrace_hash`, `first_seen_at`, `last_seen_at`, `occurrence_count`. Raw `.log` chỉ là evidence link khi cần debug sau.
3. **Có classifier deterministic trước AI**: nhóm lỗi bằng rule/hash trước, sau đó mới gửi top incidents cho AI. AI nên đọc bản tổng hợp ngắn, không đọc cả file log dài.
4. **Scope giai đoạn 1 nhỏ**: chỉ thêm incident capture cho Facebook publisher, Threads worker, AI generator tại boundary chung. Nếu phải sửa từng adapter riêng lẻ thì tách PLAN mới.

### 3.2. Tần suất báo cáo (Frequency)
- **Option A:** Báo cáo tổng kết 1 lần vào cuối ngày (Daily Health Report lúc 23:59).
- **Option B:** Báo động thời gian thực (Real-time Alert) nếu 1 lỗi cụ thể lặp lại > 5 lần trong 1 giờ.
- **Option C:** Kết hợp cả hai.
**👉 Ý kiến (User/Claude/Codex):**

**[Claude]** Chọn **Option C nhưng phân tầng rõ ràng** để tránh spam:

| Tầng | Cơ chế | Khi nào trigger | Cần LLM? |
|---|---|---|---|
| 1. Real-time critical | Push ngay (Telegram/notify) | Lỗi hạ tầng: DB down, proxy chết toàn bộ, VPS hết RAM/disk | Không — chỉ cần rule |
| 2. Burst alert | Cảnh báo nếu cùng `error_signature` lặp >5 lần / 1h | UI Facebook đổi → hàng loạt job fail cùng lý do | Không — chỉ cần aggregate query |
| 3. Daily report (LLM) | Báo cáo tổng kết 23:59 | Trend, root cause, đề xuất | Có — Gemini Flash |

**Lý do tách 3 tầng**: chỉ tầng 3 cần LLM → tiết kiệm token. Tầng 1-2 dùng rule cứng → phản hồi tức thời, không phụ thuộc API ngoài. Nếu gộp tất cả vào LLM, mỗi lần proxy chết hệ thống sẽ "câm" 24h chờ báo cáo.

**Anti-spam**: cùng 1 burst alert chỉ gửi 1 lần / 6h dù lỗi vẫn lặp lại, để tránh notification fatigue.

**[Codex]** Chọn **Option C**, nhưng real-time alert phải là rule-based, daily report mới dùng LLM:

1. **Immediate alert**: DB unreachable, disk gần đầy, worker crash loop, proxy pool fail hàng loạt. Đây là health signal, không cần AI.
2. **Burst alert**: cùng `error_signature` lặp lại quá ngưỡng trong cửa sổ thời gian. Cần cooldown theo signature để tránh spam.
3. **Daily AI report**: tổng hợp top error families, job/account/platform bị ảnh hưởng, xu hướng tăng/giảm, và action đề xuất.
4. **Đề xuất ngưỡng mặc định**: burst khi `occurrence_count >= 5` trong 60 phút, cooldown 6 giờ/signature, daily report lúc 23:59 theo timezone server.

### 3.3. Phạm vi phân tích của AI (AI Scope)
Prompt cho LLM (ví dụ: Gemini Flash) nên tập trung vào điều gì?
1. Thống kê xu hướng (Tài khoản nào, Nền tảng nào lỗi nhiều nhất).
2. Chẩn đoán nguyên nhân sâu xa (Ví dụ: "Lỗi timeout liên tục có thể do profile bị văng cookie").
3. Gợi ý hành động sửa chữa (Ví dụ: "Nên cập nhật lại Playwright selector vì Facebook đã đổi UI").
**👉 Ý kiến (User/Claude/Codex):**

**[Claude]** Cả 3 đều cần, nhưng phải **làm theo thứ tự** và không yêu cầu LLM tự tin quá mức:

- **#1 Thống kê xu hướng** → KHÔNG cần LLM. Chỉ cần SQL `GROUP BY platform, account, error_signature`. Đây là phần đáng tin nhất, làm trước tiên.
- **#2 Chẩn đoán nguyên nhân** → LLM phù hợp nhưng phải đưa kèm bằng chứng. Prompt bắt buộc trả về dạng: `{hypothesis, evidence_from_data, confidence: low|medium|high}`. Không cho LLM phát biểu chắc nịch khi chỉ có 2-3 sample.
- **#3 Gợi ý sửa chữa** → CẨN THẬN. LLM không biết source code thật → dễ bịa selector hoặc bịa fix. Đề xuất:
  - Chỉ gợi ý ở mức **hành động vận hành** (restart proxy, đổi profile, kiểm tra cookie) — KHÔNG để LLM gợi ý sửa code cụ thể.
  - Nếu User muốn AI gợi ý sửa selector → đó là task riêng (Auto-Healing v2), cần feed source code vào context, ngoài scope MVP.

**Format prompt đề xuất**: input là bảng aggregate (top 10 error signatures + count + sample stacktrace), KHÔNG phải log thô. Tiết kiệm 80% token.

**[Codex]** AI nên bị giới hạn trong vai trò **triage assistant**, không phải auto-fixer ở giai đoạn đầu:

1. **Nên làm**: tóm tắt error families, xếp hạng mức độ ảnh hưởng, so sánh với incidents trước đó, chỉ ra evidence (`job_id`, timestamp, worker, signature), và đề xuất hướng xử lý.
2. **Chỉ chẩn đoán khi có evidence**: mọi root-cause claim phải kèm dấu hiệu cụ thể, ví dụ stacktrace, HTTP code, selector timeout, DB exception, PM2 restart count.
3. **Không nên làm ngay**: tự sửa code, tự restart worker, tự disable account, hoặc tự thay đổi setting production nếu chưa có guardrail và approval.
4. **Output nên có format cố định**: `summary`, `impact`, `likely_causes`, `evidence`, `recommended_actions`, `needs_human_review`. Format này dễ render lên dashboard và để User đọc nhanh.

### 3.4. Cấu trúc Database (Nếu chọn Option 3.1.B)
Codex & Claude có thể đóng góp ý tưởng thiết kế schema cho bảng `incident_logs` sao cho tối ưu query và dễ dàng tổng hợp dữ liệu để truyền vào prompt AI không?
**👉 Ý kiến (User/Claude/Codex):**

**[Claude]** Đề xuất schema tối thiểu, tối ưu cho aggregate query:

```sql
CREATE TABLE incident_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    platform        TEXT NOT NULL,            -- 'facebook' | 'threads' | 'ai_generator'
    feature         TEXT,                     -- 'reel_post' | 'scrape' | 'comment'...
    job_id          TEXT,                     -- FK lỏng, không enforce
    account_id      TEXT,                     -- profile/account đang chạy
    severity        TEXT NOT NULL,            -- 'warning' | 'error' | 'critical'
    error_type      TEXT NOT NULL,            -- exception class: 'TimeoutError', 'SelectorNotFound'
    error_signature TEXT NOT NULL,            -- HASH(error_type + normalized_message) — KEY để aggregate
    error_message   TEXT,                     -- message gốc (đã trim)
    stacktrace      TEXT,                     -- chỉ frame trong code mình, lọc bỏ thư viện
    context_json    TEXT,                     -- JSON: url, selector, retry_count, proxy...
    resolved        INTEGER DEFAULT 0         -- 0/1, sau này dùng cho auto-healing
);

CREATE INDEX idx_incident_signature_time ON incident_logs(error_signature, occurred_at);
CREATE INDEX idx_incident_platform_time  ON incident_logs(platform, occurred_at);
CREATE INDEX idx_incident_account_time   ON incident_logs(account_id, occurred_at);
```

**Điểm quan trọng**:

1. **`error_signature`** là chìa khóa: hash của `error_type + message đã chuẩn hóa` (bỏ số, UUID, timestamp). Hai lỗi "Timeout selector .btn-123" và "Timeout selector .btn-456" phải cùng signature → mới group được.
2. **`context_json`** linh hoạt — không cần thêm cột mỗi khi có metadata mới.
3. **`stacktrace`** lọc bỏ frame thư viện (Playwright, urllib3...) → giảm 70% size, giữ phần liên quan code mình.
4. **Retention**: cron xóa record >30 ngày, hoặc move sang `incident_logs_archive`. Tránh bảng phình to.
5. **KHÔNG đặt FK cứng** với `jobs` table — tránh ràng buộc khiến insert fail trong lúc đang lỗi (race condition).
6. **Tuân thủ runtime config rule**: file SQLite (nếu dùng) phải nằm trong `storage/db/` — không tạo ở root.

**Query mẫu cho daily report**:
```sql
SELECT platform, error_signature, COUNT(*) cnt, MAX(error_message) sample
FROM incident_logs
WHERE occurred_at > datetime('now', '-1 day')
GROUP BY platform, error_signature
ORDER BY cnt DESC LIMIT 20;
```
→ Bảng 20 dòng này feed thẳng vào prompt LLM.

**[Codex]** Đồng ý với schema tối thiểu của Claude, nhưng đề xuất bổ sung một bảng aggregate riêng để giảm chi phí query/report:

**Bảng `incident_groups` (aggregate):**

| Column | Type | Note |
|---|---|---|
| `error_signature` | TEXT | Primary/group key |
| `first_seen_at` | TIMESTAMP | Lần đầu xuất hiện |
| `last_seen_at` | TIMESTAMP | Lần gần nhất |
| `occurrence_count` | INTEGER | Tổng số lần |
| `last_job_id` | TEXT nullable | Evidence nhanh |
| `last_sample_message` | TEXT | Message mẫu gần nhất |
| `severity_max` | TEXT | Severity cao nhất trong group |
| `status` | TEXT | `open`, `acknowledged`, `resolved`, `ignored` |

**Bổ sung cho `incident_logs`:**
- Thêm `worker_name` để phân biệt `FB_Publisher_1`, `Threads_NewsWorker`, `AI_Generator`.
- Thêm `source_log_path` hoặc `source_log_ref` để trỏ về raw log khi cần audit.
- `context_json` phải được redact trước khi ghi, không lưu cookie, token, password, proxy credential, hoặc raw request header.

**Index nên có:** `occurred_at`, `(platform, occurred_at)`, `(severity, occurred_at)`, `error_signature`, `(account_id, occurred_at)`, `(job_id)`.

#### ✅ Schema chốt (merge Claude + Codex)

**Quyết định:** dùng chung **PostgreSQL DB chính hiện tại**, không tạo SQLite riêng. Lý do: hệ thống production đang chuẩn hóa PostgreSQL, incident cần join/lọc theo job/account/worker state, và alert/report nên chạy cùng transaction/audit surface với backend.

**Bảng 1 — `incident_logs` (append-only, raw events)**

```sql
CREATE TABLE incident_logs (
    id                  BIGSERIAL PRIMARY KEY,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Phân loại
    platform            TEXT NOT NULL,         -- 'facebook' | 'threads' | 'ai_generator' | 'system'
    feature             TEXT,                  -- 'reel_post' | 'scrape' | 'comment' | 'login'...
    category            TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (category IN ('ui_drift','auth','proxy','db','network','rate_limit','worker_crash','resource','unknown')),
    worker_name         TEXT,                  -- 'FB_Publisher_1' | 'Threads_NewsWorker' | ... (Codex)
    job_id              TEXT,                  -- FK lỏng, không enforce
    account_id          TEXT,                  -- profile/account đang chạy

    -- Mức độ
    severity            TEXT NOT NULL CHECK (severity IN ('warning','error','critical')),

    -- Lỗi
    error_type          TEXT NOT NULL,         -- 'TimeoutError' | 'SelectorNotFound' | ...
    error_signature     TEXT NOT NULL,         -- HASH(error_type + normalized_message) — KEY aggregate
    error_message       TEXT,                  -- message gốc (đã trim, max 2KB)
    stacktrace          TEXT,                  -- lọc bỏ frame thư viện, giữ frame code mình

    -- Bối cảnh & evidence
    context_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
                                               -- JSON: url, selector, retry_count, proxy_id, http_status...
                                               -- BẮT BUỘC redact: cookie, token, password, proxy creds, headers
    source_log_ref      TEXT,                  -- path/ref tới raw .log để audit khi cần (Codex)

    -- Trạng thái xử lý
    resolved            BOOLEAN NOT NULL DEFAULT false
);

-- Index cho aggregate queries (daily report, burst alert)
CREATE INDEX idx_incident_signature_time  ON incident_logs(error_signature, occurred_at);
CREATE INDEX idx_incident_platform_time   ON incident_logs(platform, occurred_at);
CREATE INDEX idx_incident_account_time    ON incident_logs(account_id, occurred_at);
CREATE INDEX idx_incident_severity_time   ON incident_logs(severity, occurred_at);
CREATE INDEX idx_incident_category_time   ON incident_logs(category, occurred_at);
CREATE INDEX idx_incident_occurred_at     ON incident_logs(occurred_at);
CREATE INDEX idx_incident_job_id          ON incident_logs(job_id);
```

**Bảng 2 — `incident_groups` (aggregate, denormalized cho query nhanh)**

```sql
CREATE TABLE incident_groups (
    error_signature     TEXT PRIMARY KEY,
    first_seen_at       TIMESTAMPTZ NOT NULL,
    last_seen_at        TIMESTAMPTZ NOT NULL,
    occurrence_count    BIGINT NOT NULL DEFAULT 1,

    -- Evidence nhanh để render UI / feed LLM mà không cần JOIN
    last_job_id         TEXT,
    last_account_id     TEXT,
    last_platform       TEXT,
    last_worker_name    TEXT,
    last_sample_message TEXT,                  -- message mẫu gần nhất
    severity_max        TEXT NOT NULL,         -- severity cao nhất từng thấy

    -- Trạng thái triage
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','acknowledged','resolved','ignored')),
    acknowledged_by     TEXT,
    acknowledged_at     TIMESTAMPTZ,
    notes               TEXT                   -- ghi chú thủ công của User
);

CREATE INDEX idx_groups_status_lastseen ON incident_groups(status, last_seen_at);
CREATE INDEX idx_groups_count           ON incident_groups(occurrence_count DESC);
```

**Cập nhật `incident_groups` bằng UPSERT trong code (đã chốt):**

Lý do chọn UPSERT trong code thay vì SQL trigger: dễ test, dễ log proof, dễ rollback, không giấu side-effect trong database khi worker đang lỗi.

```sql
-- Mỗi lần insert vào incident_logs, upsert vào incident_groups
INSERT INTO incident_groups (
    error_signature, first_seen_at, last_seen_at, occurrence_count,
    last_job_id, last_account_id, last_platform, last_worker_name,
    last_sample_message, severity_max, status
) VALUES (
    :error_signature, :occurred_at, :occurred_at, 1,
    :job_id, :account_id, :platform, :worker_name,
    :error_message, :severity, 'open'
)
ON CONFLICT(error_signature) DO UPDATE SET
    last_seen_at        = excluded.last_seen_at,
    occurrence_count    = incident_groups.occurrence_count + 1,
    last_job_id         = excluded.last_job_id,
    last_account_id     = excluded.last_account_id,
    last_platform       = excluded.last_platform,
    last_worker_name    = excluded.last_worker_name,
    last_sample_message = excluded.last_sample_message,
    severity_max        = CASE
        WHEN incident_groups.severity_max = 'critical' THEN 'critical'
        WHEN excluded.severity_max = 'critical' THEN 'critical'
        WHEN incident_groups.severity_max = 'error' OR excluded.severity_max = 'error' THEN 'error'
        ELSE 'warning'
    END,
    status              = CASE WHEN incident_groups.status = 'resolved' THEN 'open' ELSE incident_groups.status END;
    -- Reopen group nếu đã resolved mà lỗi tái xuất hiện
```

#### Quy ước & ràng buộc

1. **`error_signature` = SHA1(error_type + normalized_message)[:16]**
   Normalize: lowercase, strip số (`\d+` → `N`), strip UUID, strip timestamp, collapse whitespace.
   Ví dụ: `"Timeout selector .btn-12345 after 30000ms"` → `"timeout selector .btn-N after Nms"` → hash.

2. **Redact rules cho `context_json`** — implement ở 1 chỗ duy nhất (helper `redact()`):
   - Drop keys: `cookie`, `cookies`, `authorization`, `auth`, `token`, `access_token`, `password`, `proxy_url`, `proxy_auth`, `set-cookie`.
   - Mask values matching regex: bearer tokens, basic auth, JWT.
   - Log có violation → bỏ field đó, không fail insert.

3. **Stacktrace lọc** — chỉ giữ frame chứa path bắt đầu bằng project root (`/home/vu/toolsauto/`), bỏ frames của `playwright/`, `urllib3/`, `selenium/`, `asyncio/`. Giảm ~70% size, giữ tín hiệu liên quan.

4. **Retention**:
   - `incident_logs`: cron xóa cứng record >30 ngày trong MVP, không tạo `incident_logs_archive`.
   - `incident_groups`: KHÔNG xóa tự động. Group `status='resolved'` hơn 90 ngày & `last_seen_at < now() - interval '90 days'` mới purge.

5. **KHÔNG có FK cứng** với `jobs`/`accounts` — tránh constraint violation khi đang ghi lỗi (race condition lúc job bị xóa).

6. **DB engine** — dùng chung PostgreSQL DB chính. Không tạo `storage/db/incidents.db` trong MVP.

#### Query mẫu

**a) Daily report — top 20 error families trong 24h cuối:**
```sql
SELECT g.error_signature, g.last_platform, g.severity_max,
       g.occurrence_count, g.last_sample_message, g.last_seen_at
FROM incident_groups g
WHERE g.last_seen_at > now() - interval '1 day'
  AND g.status IN ('open','acknowledged')
ORDER BY g.occurrence_count DESC
LIMIT 20;
```

**b) Burst alert check — signature lặp ≥5 lần/1h:**
```sql
SELECT error_signature, COUNT(*) cnt
FROM incident_logs
WHERE occurred_at > now() - interval '1 hour'
GROUP BY error_signature
HAVING cnt >= 5;
```

**c) Tài khoản nào lỗi nhiều nhất tuần này:**
```sql
SELECT account_id, platform, COUNT(*) cnt
FROM incident_logs
WHERE occurred_at > now() - interval '7 days' AND severity != 'warning'
GROUP BY account_id, platform
ORDER BY cnt DESC LIMIT 10;
```

#### Quyết định cuối cho PLAN

| # | Quyết định | Lựa chọn đã chốt |
|---|---|---|
| Q1 | DB engine | **Chung PostgreSQL DB chính hiện tại** |
| Q2 | `incident_groups` cập nhật bằng | **UPSERT trong code**, không dùng trigger ở MVP |
| Q3 | Retention `incident_logs` | **30 ngày** |
| Q4 | Archive | **Không tạo `incident_logs_archive` ở MVP**; xóa cứng record quá 30 ngày, giữ trend dài hạn trong `incident_groups` |

---

### 3.5. Cơ chế điều phối Tools (Tool Orchestration) - Dành riêng cho Auto-Healing
Nếu chúng ta tiến tới Auto-Healing (AI tự sửa lỗi), hệ thống sẽ cần một cơ chế để AI "ra lệnh" cho các tools khác hoạt động (ví dụ: Restart PM2, chạy kịch bản Playwright bypass login, gọi hàm API cập nhật trạng thái account trong DB).
*Câu hỏi cho Claude & Codex:* Các bạn có ý tưởng gì về kiến trúc điều phối tools này không? Nên dùng MCP (Model Context Protocol), n8n webhooks, hay build một function-calling agent riêng chạy ngầm?
**👉 Ý kiến của Claude:**

**TL;DR**: Chọn **function-calling agent tự build (in-process)**, KHÔNG dùng MCP/n8n cho phase này. Phải triển khai theo 3 phase, KHÔNG nhảy thẳng vào auto-execute.

#### So sánh 3 hướng

| Tiêu chí | MCP | n8n webhooks | Function-calling tự build |
|---|---|---|---|
| Độ phức tạp infra | Cao (server MCP, client adapter) | Trung bình (cần n8n instance riêng) | Thấp (Python function + tool schema) |
| Debug khi lỗi | Khó — qua nhiều layer | Khó — n8n là hộp đen | Dễ — stack trace thẳng vào code |
| Audit/log mọi action | Phải tự thêm | Có nhưng ngoài DB chính | Native — ghi cùng DB với incident_logs |
| Phù hợp cho user | Lập trình viên, multi-client | Non-coder, workflow visual | Project nội bộ, control cao |
| Rủi ro vendor lock | Trung bình | Cao (n8n down → healing chết) | Không |

**Kết luận**: ToolsAuto là internal tool, mọi tools đều là Python function có sẵn (`pm2 restart`, `update_account_status`, `relogin`...). Wrap chúng vào MCP server hoặc đẩy qua n8n chỉ thêm latency và điểm gãy. Function-calling trực tiếp với Gemini/Claude API là gọn nhất.

#### Kiến trúc đề xuất (3 phase)

**Phase 1 — Suggest only (KHÔNG action)**
```
incident_groups → LLM analyzer → recommended_actions (text)
                                        ↓
                                 User đọc trên dashboard / Telegram
                                        ↓
                                 User tự execute thủ công
```
Mục tiêu: build niềm tin. Đo accuracy của recommendation trong 2-4 tuần trước khi cho AI tự bấm nút.

**Phase 2 — Approval gate (Human-in-the-loop)**
```
LLM → action_plan (JSON) → approval_queue → User approve qua Telegram/UI
                                                ↓
                                         tool_registry execute
                                                ↓
                                         healing_actions table (audit)
```
Mỗi action là 1 function được đăng ký trong `tool_registry`. LLM CHỈ được gọi function trong registry, không được tự sinh shell command.

**Phase 3 — Auto-execute (chỉ whitelist hẹp)**
Chỉ tự động cho các action **reversible + low blast radius**:
- ✅ Restart 1 worker PM2 cụ thể
- ✅ Mark 1 account `cooldown` 30 phút
- ✅ Xóa cache tạm
- ❌ KHÔNG auto: DROP/UPDATE bảng, sửa code, gửi tin nhắn, đăng bài, đổi mật khẩu, xóa account

#### Schema bổ sung cần có

```sql
CREATE TABLE healing_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_group  TEXT NOT NULL,            -- FK → incident_groups.error_signature
    proposed_at     TIMESTAMP NOT NULL,
    tool_name       TEXT NOT NULL,            -- phải nằm trong tool_registry
    tool_args_json  TEXT NOT NULL,
    status          TEXT NOT NULL,            -- 'pending' | 'approved' | 'rejected' | 'executed' | 'failed' | 'rolled_back'
    approved_by     TEXT,                     -- 'user' | 'auto' (nếu phase 3)
    approved_at     TIMESTAMP,
    executed_at     TIMESTAMP,
    result_json     TEXT,                     -- output của tool
    rollback_ref    TEXT                      -- nếu cần undo
);
```

#### Tool registry — bắt buộc có

```python
# Mỗi tool phải khai báo metadata để LLM biết và để guardrail enforce
TOOL_REGISTRY = {
    "restart_worker": {
        "fn": pm2_restart_worker,
        "args_schema": {...},        # JSON schema, validate trước khi gọi
        "blast_radius": "low",       # low | medium | high
        "reversible": True,
        "auto_approve_phase": 3,     # phase nào được auto
        "rate_limit": "5/hour",
    },
    ...
}
```

LLM chỉ thấy `tool_name + description + args_schema` qua function-calling API. KHÔNG cho LLM truy cập subprocess hay sql trực tiếp.

#### Guardrails bắt buộc

1. **Idempotency key** trên mỗi action — tránh AI gọi `restart_worker` 10 lần liên tiếp.
2. **Rate limit per tool** — `restart_worker` tối đa 5 lần/giờ.
3. **Circuit breaker** — nếu 3 healing action liên tiếp fail → tự động chuyển về Phase 1 (suggest only) và alert User.
4. **Dry-run mode** — phase 1-2 mặc định dry-run; tool chỉ mô phỏng kết quả, không thực hiện.
5. **Mọi action có log đầy đủ** trong `healing_actions` để rollback và audit.

#### Quan trọng: ranh giới với CLAUDE.md

Auto-Healing có thể thực hiện **DELETE/UPDATE production data**, vốn nằm trong rule cấm của RULES.md. Cần ADR riêng định nghĩa:
- Loại action nào được tự thực thi mà KHÔNG cần "user approve trực tiếp"
- Loại action nào BẮT BUỘC approval mỗi lần (mặc định: tất cả ghi DB production)

Cá nhân tôi đề xuất: **Phase 3 không bao giờ được phép DELETE/UPDATE production data**. Auto-fix chỉ giới hạn ở process/cache/state cục bộ. Mọi đụng chạm DB production luôn qua approval gate, kể cả ở Phase 3.

#### Câu hỏi mở cho anh

1. Muốn dùng **Gemini function-calling** (đã có account) hay **Claude tool-use**? Cả 2 đều OK, Gemini rẻ hơn.
2. Kênh approval ở Phase 2: Telegram inline button, dashboard web, hay cả hai?
3. Có chấp nhận **không bao giờ tiến đến Phase 3** không? Suggest-only + 1-click approve có thể là sweet spot ổn định mãi mãi, không cần auto-fix thật sự.

**👉 Ý kiến của Codex:**

Đồng ý với Claude: **không dùng MCP/n8n cho phase đầu**, chọn **function-calling agent tự build trong codebase ToolsAuto**, nhưng thiết kế theo kiểu "proposal executor" có audit đầy đủ, không phải AI tự cầm quyền production.

#### Lý do không chọn MCP/n8n ở giai đoạn này

1. **MCP phù hợp khi có nhiều client/tool provider**, nhưng hiện ToolsAuto chỉ cần một tập tool nội bộ hẹp: đọc incident, đọc log, kiểm tra PM2, chạy health check, tạo đề xuất fix. Thêm MCP server lúc này làm tăng layer vận hành và khó debug.
2. **n8n phù hợp workflow business lặp lại**, nhưng auto-healing cần kiểm soát permission, transaction, audit trail, rollback, và liên kết trực tiếp với `incident_logs`. Đẩy qua webhook ngoài dễ mất context và khó đảm bảo trạng thái DB.
3. **Function-calling in-process dễ kiểm soát nhất**: tool schema nằm trong repo, permission nằm trong DB/config, log action ghi chung với incident, test được bằng unit/integration test.

#### Kiến trúc đề xuất

Tách 4 lớp rõ ràng:

1. **Analyzer**: đọc `incident_logs` / `incident_groups`, gom context, gọi LLM để tạo `healing_recommendation`.
2. **Policy Engine**: kiểm tra action có được phép không theo allowlist, severity, account/platform, environment, và approval mode.
3. **Tool Registry**: danh sách function nội bộ có schema rõ ràng, ví dụ `check_pm2_status`, `tail_worker_log`, `run_db_health_check`, `restart_worker`, `mark_account_needs_review`.
4. **Executor + Audit**: chỉ executor được gọi tool thật; mọi lần gọi ghi `healing_actions` với input đã redact, output, actor, approval_id, timestamp, status.

#### Phân quyền theo phase

| Phase | Chế độ | Tool được phép | Ghi chú |
|---|---|---|---|
| Phase 1 | Suggest-only | Read-only tools | AI chỉ đề xuất, không execute |
| Phase 2 | Approval gate | Read-only + một số action an toàn | User bấm duyệt từng action |
| Phase 3 | Narrow auto-run | Chỉ allowlist hẹp | Chỉ health/cache/process action đã chứng minh an toàn |

#### Rule bắt buộc

1. **Không có free-form shell**: AI không được gửi command shell tùy ý. Mọi action phải đi qua named tool có schema cố định.
2. **Không auto bypass login / checkpoint**: các thao tác liên quan login, checkpoint, cookie, hoặc xác thực tài khoản chỉ được tạo hướng dẫn kiểm tra hợp lệ/manual recovery, không tự chạy bypass.
3. **Không auto DELETE/DROP/UPDATE production data**: mọi write vào DB production phải có approval gate. Với account state, tối đa Phase 2 là "mark needs review" hoặc "disable with approval".
4. **Idempotency bắt buộc**: tool action phải có `idempotency_key` để retry không tạo tác dụng phụ kép.
5. **Kill switch**: có setting tắt toàn bộ Auto-Healing executor ngay trên System Panel hoặc DB config.
6. **Dry-run trước execute**: action có side effect phải hỗ trợ `dry_run=true` và hiển thị diff/impact trước khi user duyệt.

#### Tool set MVP đề xuất

| Tool | Loại | Phase |
|---|---|---|
| `get_incident_group(signature)` | read | 1 |
| `tail_worker_log(worker_name, minutes)` | read | 1 |
| `check_pm2_status(worker_name)` | read | 1 |
| `check_db_health()` | read | 1 |
| `check_disk_memory()` | read | 1 |
| `restart_worker(worker_name)` | write/process | 2 |
| `clear_temp_files(scope)` | write/filesystem | 2 |
| `mark_account_needs_review(account_id, reason)` | write/db | 2 |
| `pause_queue(queue_name, minutes)` | write/db/runtime | 2 |

#### Bảng audit nên có

```sql
CREATE TABLE healing_actions (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    incident_id     BIGINT NULL,
    error_signature TEXT NULL,
    proposed_by     TEXT NOT NULL,      -- model/system/user
    approved_by     TEXT NULL,
    tool_name       TEXT NOT NULL,
    tool_input_json JSONB NOT NULL,
    dry_run         BOOLEAN NOT NULL DEFAULT true,
    status          TEXT NOT NULL,      -- proposed/approved/running/succeeded/failed/rejected
    result_json     JSONB NULL,
    error_message   TEXT NULL,
    idempotency_key TEXT NOT NULL
);
```

#### Kết luận Codex

Chọn **function-calling agent tự build**, chạy trong ToolsAuto, bắt đầu bằng **Phase 1 suggest-only**. Sau khi có đủ audit + user tin output, nâng lên **Phase 2 approval gate**. Phase 3 chỉ nên áp dụng cho action không đụng dữ liệu production nhạy cảm, ví dụ restart worker đã idle, clear temp files, hoặc health check recovery an toàn.

---

## 4. Tóm tắt vị trí của Codex

| Mục | Lựa chọn |
|---|---|
| 3.1 Data source | **Option B** — structured incidents append-only tại failure boundary, giữ nguyên raw `.log` làm evidence |
| 3.2 Frequency | **Option C** — rule-based immediate/burst alert + daily LLM report |
| 3.3 AI Scope | AI là triage assistant; không auto-fix, không tự thay đổi production nếu chưa có guardrail |
| 3.4 Schema | Dùng chung PostgreSQL DB chính; `incident_logs` append-only + `incident_groups` aggregate; cập nhật group bằng UPSERT trong code |
| 3.5 Tool Orchestration | **Function-calling tự build** trong ToolsAuto, 3 phase: Suggest-only → Approval gate → Auto-run allowlist hẹp; không free-form shell, không bypass login, không auto write production DB |

**Điều kiện trước khi implement:**
- Cần PLAN riêng nếu phạm vi vượt quá boundary chung hoặc phải sửa >3 adapter.
- Cần chốt DB dùng chung PostgreSQL hiện tại hay SQLite riêng trong `storage/db/`.
- Cần chốt kênh alert thật sự: Telegram, dashboard-only, hoặc system notification hiện có.

---

## 5. Tóm tắt vị trí của Claude

| Mục | Lựa chọn |
|---|---|
| 3.1 Data source | **Option B** — nhưng inject minimal tại Dispatcher boundary, không refactor toàn bộ |
| 3.2 Frequency | **Option C** — phân 3 tầng: rule-based real-time + burst alert + LLM daily |
| 3.3 AI Scope | Cả 3, làm theo thứ tự #1 → #2 → #3; #3 chỉ gợi ý vận hành, không gợi ý sửa code |
| 3.4 Schema | Tối thiểu 12 cột + 3 index; `error_signature` là cốt lõi để aggregate |
| 3.5 Tool Orchestration | **Function-calling tự build** (in-process), 3 phase: Suggest → Approval gate → Auto whitelist hẹp. KHÔNG dùng MCP/n8n. KHÔNG auto DELETE/UPDATE production data ngay cả ở Phase 3. |

**Câu hỏi mở cho User/Codex**:
- Có muốn dùng SQLite riêng cho `incident_logs` hay nhập chung DB hiện tại?
- Telegram bot đã có sẵn cho real-time alert chưa, hay phải tích hợp mới?
- LLM dùng Gemini Flash (như đề xuất) hay tận dụng Gemini Generator hiện có trong hệ thống?
- Auto-Healing: chấp nhận dừng ở **Phase 2 (1-click approve)** vĩnh viễn, hay nhất định phải tiến đến Phase 3 (tự thực thi)?

---
*Vui lòng phản hồi bằng cách chỉnh sửa trực tiếp vào file này (điền vào các mục `[Điền ý kiến vào đây...]`) hoặc chat trực tiếp. Khi đã thống nhất, chúng ta sẽ chuyển sang bước viết Implementation Plan.*
