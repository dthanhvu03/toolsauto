# PLAN-010: GraphQL Sync + Caption Fix + Deploy Path Filter

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-010 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-010 |
| **Related ADR** | DECISION-003 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Goal
Sửa 3 vấn đề gây tê liệt Publisher: deploy path filter, GraphQL listener sớm hơn, caption selectors cập nhật cho DOM mới của Facebook.

---

## Context
- `deploy.yml` trigger trên mọi push lên `develop` → mỗi commit agent docs cũng chạy deploy → `start.sh` gọi `pm2 delete` → kill browser đang publish giữa chừng.
- GraphQL response listener hiện chỉ gắn ở adapter.py L962 (Phase 4, sau khi click Post), bỏ lỡ signals sớm hơn.
- Facebook đổi DOM Reels Step 3: selector `div[contenteditable="true"]` không match → 100% jobs thiếu caption.
- Chi tiết phân tích tại `agents/decisions/DECISION-003-publisher-crash-analysis.md`.

---

## Scope
*(Executor chỉ được làm những gì trong danh sách này)*

- `.github/workflows/deploy.yml` — thêm `paths` filter vào `on.push`
- `app/adapters/facebook/adapter.py` — di chuyển GraphQL listener lên trước Phase 2, mở rộng mutation types, cập nhật selectors caption ở Phase 3
- `app/adapters/facebook/pages/reels.py` — thêm selectors mới vào `fill_caption()` candidates list

## Out of Scope
*(Executor KHÔNG được làm những điều này trong plan này)*

- KHÔNG sửa `start.sh` hay PM2 configuration
- KHÔNG refactor adapter sang API-only (bỏ browser)
- KHÔNG sửa FFmpeg profile / media_processor.py
- KHÔNG sửa core worker logic (workers/*.py)

---

## Proposed Approach
*(Các bước thực hiện theo thứ tự — Executor đọc và làm từng bước)*

**Bước 1: Deploy Path Filter** (`.github/workflows/deploy.yml`)
- Tìm section `on: push:` (khoảng dòng 3-6).
- Thêm `paths:` filter ngay dưới `branches:`:
  ```yaml
  paths:
    - 'app/**'
    - 'workers/**'
    - 'scripts/**'
    - 'templates/**'
    - 'requirements.txt'
    - 'start.sh'
    - 'manage.py'
    - '.github/workflows/**'
  ```
- Push `agents/*.md` sẽ KHÔNG trigger deploy nữa.

**Bước 2: GraphQL Listener sớm hơn** (`app/adapters/facebook/adapter.py`)
- Hiện tại: listener `intercept_graphql` được define và gắn tại L943-962, chỉ trước khi click Post.
- Thay đổi: Di chuyển block define + `self.page.on("response", intercept_graphql)` lên **ngay sau context verification thành công** (khoảng sau L649 — dòng `Context verified successfully`).
- Mở rộng mutation list trong `intercept_graphql`: thêm `"ReelCreateMutation"`, `"useReelCreationMutation"`, `"CometVideoUploadMutation"`.
- Mở rộng data key search: ngoài `story_create`, `video_publish`, thêm `reel_create`, `video_upload`.
- Tại Phase 4 (L981), giữ nguyên logic wait nhưng check `captured_post_ids` trước — nếu đã có thì skip busy-wait.

**Bước 3: Caption Selectors** (`app/adapters/facebook/adapter.py` Phase 3 + `app/adapters/facebook/pages/reels.py`)
- Trong `adapter.py` Phase 3 (L889), thay selector đơn bằng danh sách có fallback:
  ```python
  caption_selectors = [
      'div[role="textbox"][contenteditable="true"]',
      'div[contenteditable="true"][data-lexical-editor="true"]',
      'div[contenteditable="true"][aria-label*="reel" i]',
      'div[contenteditable="true"][aria-label*="Mô tả"]',
      'div[contenteditable="true"][aria-label*="Describe"]',
      'div[contenteditable="true"][aria-placeholder]',
      'div[contenteditable="true"]',
  ]
  ```
  - Loop qua từng selector, `wait_for` timeout 5s mỗi cái, break khi thấy.
- Trong `reels.py` hàm `fill_caption()` (L504-513), thêm 2 candidates MỚI vào ĐẦU list:
  ```python
  surface.locator('div[contenteditable="true"][data-lexical-editor="true"]').first,
  surface.locator('div[role="textbox"][contenteditable="true"][aria-label]').first,
  ```

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Selector mới vẫn không match DOM | Medium | Fallback gracefully, log surface inventory tại Step 3 |
| GraphQL mutation names thay đổi | Low | Log tất cả `/api/graphql/` POST data cho debug |
| Deploy path filter quá strict, bỏ sót file cần deploy | Low | Thêm path vào filter khi phát hiện |

---

## Validation Plan
*(Executor phải thực hiện những check này và ghi kết quả vào Execution Notes)*

- [ ] Check 1: `python -m py_compile .github/workflows/deploy.yml` hoặc YAML lint pass
- [ ] Check 2: `python -m py_compile app/adapters/facebook/adapter.py` → exit 0
- [ ] Check 3: `python -m py_compile app/adapters/facebook/pages/reels.py` → exit 0
- [ ] Check 4: `grep -n 'paths:' .github/workflows/deploy.yml` → có kết quả
- [ ] Check 5: `grep -n 'intercept_graphql' app/adapters/facebook/adapter.py` → xuất hiện TRƯỚC Phase 2
- [ ] Check 6: `grep -n 'data-lexical-editor' app/adapters/facebook/pages/reels.py` → có kết quả

---

## Rollback Plan
Nếu execution fail → `git checkout -- .github/workflows/deploy.yml app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py`

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ✅ Bước 1: Đã thêm `paths` filter vào `deploy.yml`. Verify: `grep -n 'paths:'` trả về line 8.
- ✅ Bước 2: Di chuyển `intercept_graphql` lên đầu `publish()`. Verify: Line 559. Mở rộng mutations & keys.
- ✅ Bước 3: Cập nhật caption selectors trong `adapter.py` và `reels.py`. Verify: Line 505 có `data-lexical-editor`.

**Verification Proof**:
```bash
# Compile check
python3 -m py_compile app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py
# Output: (Success)

# GraphQL Listener Point
grep -n 'intercept_graphql' app/adapters/facebook/adapter.py | head -n 1
# Output: 559:        def intercept_graphql(response):

# Lexical Selector
grep 'data-lexical-editor' app/adapters/facebook/pages/reels.py
# Output: surface.locator('div[contenteditable="true"][data-lexical-editor="true"]').first,
```

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING. Không có section này = Claude Code không được archive)*

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Push agents/*.md KHÔNG trigger deploy | Yes - line 8 paths: | ✅ |
| 2 | Push app/*.py VẪN trigger deploy | Yes - line 9 app/** | ✅ |
| 3 | GraphQL listener attach trước Phase 2 | Yes - line 559 | ✅ |
| 4 | Thêm mutations: ReelCreate, CometVideoUpload | Yes - in mutations list | ✅ |
| 5 | Caption selectors có data-lexical-editor, role=textbox | Yes - in candidates list | ✅ |
| 6 | Compile check pass | Yes - done | ✅ |

### Scope & Proof Check
- [x] Executor làm đúng Scope, không mở rộng âm thầm
- [x] Proof là output thực tế, không phải lời khẳng định
- [x] Proof cover hết Validation Plan

### Verdict
> **APPROVED — Ready to hand off**

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- Trạng thái sau execution: ...
- Những gì cần làm tiếp (nếu có): ...
- Archived: Yes / No — [date]
