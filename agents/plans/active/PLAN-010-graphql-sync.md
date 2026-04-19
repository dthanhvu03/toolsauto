# PLAN-010: GraphQL Sync + Caption Fix + Deploy Path Filter

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-010 |
| **Status** | Active |
| **Executor** | Antigravity (trực tiếp) |
| **Related Task** | TASK-010 |
| **Related ADR** | DECISION-003 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Goal
Sửa 3 vấn đề gây tê liệt hệ thống Publisher:
1. Ngăn deploy bị trigger khi push docs/agent files
2. Fix selector caption Reels Step 3 bị Facebook thay đổi DOM
3. Đồng bộ GraphQL intercept xuyên suốt flow publish

---

## Context

### Hiện trạng flow publish (adapter.py L560-1176):
```
Phase 1: Navigate → Switch context → Verify /me
Phase 2: Pre-scan reels → Feed browse → Neutralize overlays → Open reels entry
Phase 3: Upload video → Click Next x2 → Fill caption (❌ BROKEN)
Phase 4: Click Post → GraphQL intercept (✅ working nhưng muộn) → Wait submission
Phase 5: Verify post URL (toast → redirect → reels_tab scan → salt match)
```

### Vấn đề cụ thể:
1. **Deploy**: `git push` bất kỳ file nào trên `develop` → trigger deploy → kill Publisher
2. **Caption**: `div[contenteditable="true"]` + Step 3 selectors không match DOM mới → post không có caption
3. **GraphQL**: Listener chỉ attach ở L962 (Phase 4), bỏ lỡ early signals

### GraphQL hiện tại (adapter.py L946-962):
```python
def intercept_graphql(response):
    if "/api/graphql/" in response.url:
        req_post = response.request.post_data or ""
        if "ComposerStoryCreateMutation" in req_post or \
           "VideoPublishMutation" in req_post or \
           "doc_id=35222657370682144" in req_post:
            body = response.json()
            data = body.get("data", {})
            story_create = data.get("story_create", {}) or data.get("video_publish", {})
            if story_create:
                p_id = story_create.get("post_id") or story_create.get("video_id")
                if p_id:
                    captured_post_ids.append(str(p_id))
```

---

## Proposed Approach

### Phase A: Deploy Path Filter (.github/workflows/deploy.yml)

**File**: `.github/workflows/deploy.yml`

**Thay đổi**: Thêm `paths` filter vào trigger `on.push`:

```yaml
on:
  push:
    branches: [develop, main]
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

Kết quả: Push `agents/`, `CLAUDE.md`, `README.md` → **KHÔNG deploy** → Publisher sống yên.

---

### Phase B: Fix Caption Selectors

**Files**: `app/adapters/facebook/adapter.py` (L886-898), `app/adapters/facebook/pages/reels.py` (L500-546)

**Bước 1**: Lấy screenshot DOM thực tế từ VPS tại Reels Step 3 để xem Facebook đã đổi cấu trúc gì.

**Bước 2**: Cập nhật selectors trong 2 nơi:

**a) adapter.py Phase 3 (L886-898)** — Hard-coded wait cho caption area:
```python
# Hiện tại (broken):
caption_loc = self.page.locator('div[contenteditable="true"]').first
caption_loc.wait_for(state="visible", timeout=15000)

# Đề xuất: Thêm nhiều selector layers
caption_selectors = [
    'div[role="textbox"][contenteditable="true"]',
    'div[contenteditable="true"][data-lexical-editor="true"]',      # Lexical editor mới
    'div[contenteditable="true"][aria-label*="reel"]',
    'div[contenteditable="true"][aria-label*="Mô tả"]',
    'div[contenteditable="true"][aria-label*="Describe"]',
    'div[contenteditable="true"][aria-placeholder]',
    'div[contenteditable="true"]',
]
```

**b) reels.py fill_caption() (L500-546)** — Thêm selectors mới:
```python
# Thêm vào đầu danh sách candidates:
surface.locator('div[contenteditable="true"][data-lexical-editor="true"]').first,
surface.locator('div[role="textbox"][contenteditable="true"][aria-label]').first,
```

**Bước 3**: Thêm debug logging chi tiết khi caption area không tìm thấy — dump DOM structure của surface tại Step 3.

---

### Phase C: GraphQL Sync Enhancement

**File**: `app/adapters/facebook/adapter.py`

**Thay đổi 1**: Di chuyển GraphQL listener **sớm hơn** — attach ngay sau khi open session, trước Phase 1. Hiện tại listener chỉ gắn ở L962 (Phase 4), quá muộn.

```python
# Gắn ngay sau khi verify context thành công (trước Phase 2):
captured_graphql_events = []
captured_post_ids = []

def intercept_graphql(response):
    if "/api/graphql/" not in response.url:
        return
    try:
        req_post = response.request.post_data or ""
        # Mở rộng mutation types
        mutations = [
            "ComposerStoryCreateMutation",
            "VideoPublishMutation", 
            "ReelCreateMutation",
            "useReelCreationMutation",
            "CometVideoUploadMutation",
        ]
        if any(m in req_post for m in mutations):
            body = response.json()
            # Log event cho debug
            captured_graphql_events.append({
                "ts": time.time(),
                "status": response.status,
                "mutation": next((m for m in mutations if m in req_post), "unknown"),
            })
            
            data = body.get("data", {})
            # Tìm post_id/video_id trong mọi key có thể
            for key in ("story_create", "video_publish", "reel_create", "video_upload"):
                result = data.get(key, {})
                if result:
                    p_id = result.get("post_id") or result.get("video_id") or result.get("id")
                    if p_id:
                        captured_post_ids.append(str(p_id))
                        self.logger.info("[GRAPHQL] Captured post_id=%s from mutation=%s", p_id, key)
                        
            # Detect GraphQL error payload
            errors = body.get("errors", [])
            if errors:
                self.logger.warning("[GRAPHQL] Server returned errors: %s", errors[:2])
    except Exception:
        pass

self.page.on("response", intercept_graphql)
```

**Thay đổi 2**: Ở Phase 4, thay vì busy-wait 120s, sử dụng GraphQL signal nếu đã bắt được:
```python
# Nếu GraphQL đã bắt post_id trước khi click Post → skip DOM wait entirely
if captured_post_ids:
    post_id_from_graphql = captured_post_ids[0]
    self.logger.info("[GRAPHQL] Fast-track: post_id captured before DOM wait")
else:
    # Fallback to existing 120s busy-wait
    ...
```

**Thay đổi 3**: Ở Phase 5, log GraphQL events timeline cho debug:
```python
self.logger.info("[GRAPHQL] Events captured during session: %d", len(captured_graphql_events))
for evt in captured_graphql_events:
    self.logger.debug("[GRAPHQL]  - %s: mutation=%s status=%s", evt["ts"], evt["mutation"], evt["status"])
```

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Selector mới vẫn không match DOM | Medium | Cần screenshot thực tế. Nếu fail → fallback gracefully |
| GraphQL mutation names thay đổi | Low | Log tất cả `/api/graphql/` requests để phát hiện mutation mới |
| Deploy path filter quá strict | Low | Có thể thêm `workflow_dispatch` để manual trigger |

---

## Validation Plan

### Phase A
- [ ] Check: Push file `agents/test.md` → verify GitHub Actions KHÔNG chạy
- [ ] Check: Push file `app/config.py` → verify GitHub Actions CÓ chạy

### Phase B
- [ ] Check: Job publish thành công với caption được điền đầy đủ
- [ ] Check: Không còn WARNING "Caption area not found" trong logs

### Phase C
- [ ] Check: Log có `[GRAPHQL] Captured post_id=` xuất hiện sớm hơn trong flow
- [ ] Check: `python -m py_compile app/adapters/facebook/adapter.py` → PASS

---

## Execution Order
1. **Phase A trước** — Chặn deploy liên tục giết Publisher (5 phút)
2. **Phase C tiếp** — GraphQL sync để hiểu rõ hơn Facebook responses (30 phút)
3. **Phase B cuối** — Caption fix, cần screenshot DOM thực tế (1 giờ)

---

## Rollback Plan
```bash
git checkout -- .github/workflows/deploy.yml app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py
```
