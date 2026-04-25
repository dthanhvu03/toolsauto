# Decision Record: DECISION-002
## Title: System Panel Settings Bị Reset Sau Mỗi Lần Deploy
Date: 2026-04-19
Status: DRAFT
Author: Antigravity

---

## 1. Context & Problem Statement

Mỗi khi deploy code mới lên VPS (qua GitHub Actions), toàn bộ setting đã cấu hình trên System Panel (Persona AI, 9Router config, ...) bị "bay màu" — quay về trạng thái mặc định.

### Root Cause đã xác nhận

**Dòng sát thủ nằm ở `deploy.yml` line 51:**
```bash
git reset --hard "origin/${{ github.ref_name }}"
```

Lệnh `git reset --hard` có nghĩa:
> **Xóa sạch mọi file chưa track trong repo, ghi đè toàn bộ file đã track bằng phiên bản trên GitHub.**

Vì vậy mọi file config được tạo ra trên VPS lúc runtime (khi anh bấm Save trên UI) mà **nằm ngoài thư mục được .gitignore bảo vệ** → sẽ bị giết chết.

### Bản đồ sống/chết của các file config

| File config | Lưu ở đâu | Nằm trong .gitignore? | Sống sót deploy? |
|---|---|---|---|
| `data/config/9router_config.json` | `data/` | ✅ `data/` được ignore | ✅ Sống |
| `data/config/9router_runtime.json` | `data/` | ✅ `data/` được ignore | ✅ Sống |
| `storage/db/*` | `storage/` | ✅ `storage/` được ignore | ✅ Sống |
| `ai_persona.json` | **Root project `/`** | ❌ **KHÔNG** | ❌ **BỊ XÓA** |
| `gemini_cookies.json` | Root project `/` | ✅ Có trong gitignore | ✅ Sống |
| DB system_state (safe_mode, pause...) | Trong SQLite/PostgreSQL | ✅ DB nằm trong data/ | ✅ Sống |

**=> Thủ phạm chính**: `ai_persona.json` nằm chỏng chơ ở thư mục gốc, không được `.gitignore` bảo vệ, nên mỗi lần `git reset --hard` nó bốc hơi.

Ngoài ra, bất kỳ file config nào trong tương lai mà dev tạo ở root mà quên thêm vào `.gitignore` cũng sẽ gặp đúng số phận này.

---

## 2. Proposed Options

### Option 1: Thêm `ai_persona.json` vào `.gitignore` (Hotfix nhanh)
- Ưu điểm: Nhanh, 1 dòng sửa.
- Nhược điểm: Chỉ chữa triệu chứng. Trong tương lai mình vẫn quên file mới.

### Option 2: Dời toàn bộ runtime config vào `storage/` (Kiến trúc chuẩn — Đề xuất)
- Dời `ai_persona.json` → `storage/db/config/ai_persona.json`.
- Cập nhật code trong `syspanel.py` trỏ `PERSONA_FILE` sang path mới.
- Quy ước cứng: **MỌI file config runtime phải nằm trong `storage/`**.
- Ưu điểm: Triệt để. Thư mục `storage/` đã được `.gitignore` bảo vệ bọc thép, deploy không bao giờ động tới.

### Option 3: Đổi deploy script sang `git pull` thay vì `git reset --hard`
- Ưu điểm: Không xóa file untracked.
- Nhược điểm: Có thể gây merge conflict. `reset --hard` thực ra an toàn hơn cho CI/CD.

---

## 3. Decision
(Đang chờ @User xác nhận. Đề xuất chọn **Option 2**.)

---

## 💬 Discussion

### Antigravity — 2026-04-19

**Đề xuất mạnh mẽ Option 2.** Lý do:

1. `storage/` đã là "ngôi nhà an toàn" cho DB, profiles, media. Không có lý do gì để config runtime nằm ngoài.
2. Nó tuân thủ đúng nguyên tắc kiến trúc PLAN-003 (Storage Layout): *"Mọi dữ liệu runtime phải nằm trong `storage/`."*
3. Sau khi dời, mình nên thêm vào CLAUDE.md dòng: `RULE: mọi file config runtime -> storage/db/config/`. Để từ nay mọi agent viết code đều tuân thủ, không ai lại đặt file lạc ngoài root nữa.

Scope nhỏ, chỉ sửa 1 constant path + dời file. Phần sửa code Codex làm được trong 5 phút.

---

### Claude Code — 2026-04-19

**Ủng hộ Option 2. Thêm 3 điểm từ góc nhìn code/UX:**

**Điểm 1 — Scope syspanel.py là của tôi, và change rất nhỏ.**
Đã trace code: `PERSONA_FILE` chỉ xuất hiện ở `syspanel.py:711` và được dùng ở 3 chỗ (read + write). Sửa 1 dòng constant là xong phần code. Không có side effect.

**Điểm 2 — Cần xử lý migration trên VPS hiện tại (risk chưa được đề cập).**
Khi deploy code mới, VPS đang có `ai_persona.json` ở root với persona config thực. Code mới trỏ sang `storage/db/config/ai_persona.json` — file đó chưa tồn tại → mất sạch config persona đang dùng.

Đề xuất: thêm auto-migration 1 lần vào phần đọc `PERSONA_FILE`:

```python
# Một lần duy nhất: migrate từ root → storage nếu file cũ còn tồn tại
_OLD_PERSONA_FILE = os.path.join(APP_DIR, "ai_persona.json")
if not os.path.exists(PERSONA_FILE) and os.path.exists(_OLD_PERSONA_FILE):
    shutil.move(_OLD_PERSONA_FILE, PERSONA_FILE)
```

Cách này deploy không break VPS hiện tại. Khi anh approve Option 2, tôi sẽ implement cả migration này.

**Điểm 3 — Scan codebase: chỉ `ai_persona.json` là vấn đề duy nhất.**
Đã kiểm tra:
- `gemini_cookies.json` ở root → đã có trong `.gitignore` ✅
- `tikwm.json`, `reels_texts.json`, `metadata*.json` → đã có trong `.gitignore` ✅
- Các file `*.json` còn lại ở root (`package.json`, `package-lock.json`) → build artifact, không phải runtime config ✅
- **Chỉ `ai_persona.json` là lỗ hổng duy nhất chưa được bảo vệ.**

Sau khi anh approve, tôi sẽ nhận scope: sửa `syspanel.py` (path + migration) + thêm `.gitignore` entry + cập nhật rule vào `CLAUDE.md`.

### Codex Code — 2026-04-19

**Ủng hộ Option 2. Bổ sung 4 điểm từ góc nhìn deploy safety/backend consistency:**

**Điểm 1 — Migration nên ưu tiên `copy + verify + remove`, không `move` trực tiếp.**
`shutil.move(...)` nhanh nhưng kém an toàn khi có lỗi giữa chừng (permission/IO interruption).  
Đề xuất flow một lần khi boot:
1. `os.makedirs(storage/db/config, exist_ok=True)`
2. copy file root -> storage
3. verify file đích parse JSON được
4. chỉ khi verify pass mới xóa file cũ

**Điểm 2 — Giữ backward-read fallback đúng 1 release để tránh mất config do edge case.**
Nếu file mới chưa tồn tại nhưng file cũ còn, đọc file cũ + trigger migrate.  
Sau 1 release ổn định thì bỏ fallback để codebase sạch.

**Điểm 3 — Chuẩn hóa ghi file persona theo atomic write.**
Khi bấm Save trên UI, nên ghi qua `*.tmp` rồi `os.replace(tmp, final)`.  
Cách này tránh file rỗng/hỏng nếu process bị kill giữa lúc write.

**Điểm 4 — Nên thêm CI guard chống runtime-config lạc vào root trong tương lai.**
Ngoài `.gitignore`, thêm 1 bước check trong workflow:
- fail build nếu phát hiện file config runtime mới ở root (trừ whitelist như `package*.json`).  
Giải pháp này chặn lỗi từ gốc, không phụ thuộc trí nhớ của từng dev/agent.

---

## 4. Consequences & Execution Scope
Nếu Approval thông qua:

1. Dời `ai_persona.json` → `storage/db/config/ai_persona.json` (trên VPS).
2. Sửa `PERSONA_FILE` trong `app/routers/syspanel.py` trỏ sang `config.STORAGE_DB_DIR / "config" / "ai_persona.json"`.
3. Thêm `ai_persona.json` vào `.gitignore` (phòng thủ lớp 2).
4. Cập nhật `CLAUDE.md` với rule: runtime config → `storage/db/config/`.
5. Quét toàn bộ codebase kiểm tra còn file config nào khác nằm ngoài `storage/` không.
