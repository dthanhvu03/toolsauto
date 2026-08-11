# PLAN-051 — Dọn nợ kỹ thuật: secret rò rỉ + code chết

## Status: In progress (Executor: Claude Code)

## Bối cảnh

Owner yêu cầu audit tính năng (2026-08-11) rồi chọn xử lý nợ kỹ thuật trước.
Trong lúc quét code chết, phát hiện **file cookie phiên thật đang được git track
trong repo public** — việc này nhảy lên trước mọi hạng mục nợ kỹ thuật khác.

Ràng buộc của phiên: **máy không còn Python** (`pythoncore-3.14-64` biến mất, venv
là stub trỏ vào đó) → không chạy được `pytest`. Vì vậy scope chỉ nhận những việc
**chứng minh được bằng grep/route/git**, không nhận refactor cần test.

## Scope

### A. Secret rò rỉ (ưu tiên tuyệt đối)

| Việc | Trạng thái |
|---|---|
| Gỡ `scratch/threads_cookies.json` khỏi index + xoá file | Claude Code làm |
| Gỡ `scratch/smoke_test_models.py` khỏi index (đã nằm trong `.gitignore`) | Claude Code làm |
| Thêm luật `*cookies*.json` vào `.gitignore` | Claude Code làm |
| Đổi mật khẩu / đăng xuất toàn bộ phiên FB · IG · TikTok | **Owner** |
| Purge lịch sử git + force-push (hoặc chuyển repo sang private) | **Owner quyết** |

### B. Code chết — xoá (đã chứng minh 0 tham chiếu)

| File | Dòng | Bằng chứng |
|---|---|---|
| `app/templates/pages/tiktok_links.html` | 339 | Route `/tiktok-links` đã 302 sang `/app/tiktok-links` (dùng `app_tiktok_links.html`) |
| `app/templates/fragments/viral_table.html` | 80 | Chỉ `fragments/app_viral_table.html` được render |
| `app/templates/fragments/syspanel/persona_tuner.html` | 8 | Tự ghi "retired"; không route nào serve → không chống được 404 như comment nói |
| `app/core/ai/gemini_api.py` | 296 | Tự khai DEPRECATED (ADR-006); 0 importer trong `app/`, `tests/`, `scripts/` |
| `app/features/affiliates/ai.py` | 4 | Shim re-export, 0 importer |
| `app/features/viral_intake/video_protector.py` | 4 | Shim re-export, 0 importer (nơi khác import thẳng `app.core.media.video_protector`) |

### C. Ngoài scope phiên này (ghi lại, không làm)

- Refactor god object (`facebook/adapter.py` 2676 dòng, `reup_processor.py` 1160,
  `insights/service.py` 1015) — đổi cấu trúc mà không chạy được test là đánh bạc
- Viết test cho `viral_intake` / `system_panel` / `insights` / `affiliates` — cần pytest
- Sửa `tests/test_threads_world_news.py` — thuộc nhóm P0 mở lại CI, task riêng
- Số phận `WorkflowRegistry` → tách sang ADR-009
- Số phận adapter Threads/TikTok/Instagram đang ngủ → cần Owner quyết
- 3 component `ui/empty_state|input|pagination.html` (47 dòng) 0 nơi dùng — **giữ**,
  đây là design system nên được *áp dụng* chứ không phải xoá

## Verify

Cách chứng minh không cần pytest:

```bash
# 1. Không còn tham chiếu tới file đã xoá
grep -rE "['\"/](tiktok_links|viral_table|persona_tuner)\.html" app
grep -rn "gemini_api|features.affiliates.ai|viral_intake.video_protector" app tests scripts

# 2. Không còn secret trong file đang track
git ls-files -z | xargs -0 grep -lIE '"(xs|c_user|sessionid|ds_user_id)"'
```

Kết quả ghi ở mục Proof bên dưới.

## Proof (2026-08-11)

### A. Secret

| Việc | Kết quả |
|---|---|
| `git rm --cached scratch/threads_cookies.json` + xoá khỏi đĩa | Xong |
| `git rm --cached scratch/smoke_test_models.py` | Xong (file vẫn còn trên đĩa) |
| `.gitignore` thêm `*cookies*.json`, `*_session.json` | Xong — `git ls-files` xác nhận không nuốt nhầm file hợp lệ nào |
| Quét lại toàn bộ file đang track | `git ls-files -z \| xargs -0 grep -lIE '"(xs\|c_user\|sessionid\|ds_user_id)":'` → **rỗng** |

Nội dung đã rò rỉ: cookie phiên thật của **Facebook (`xs`, `c_user`, `datr`, `sb`,
`fr`), Instagram (`sessionid`, `ds_user_id`, `ig_did`), TikTok (`msToken`, `ttwid`)**
— commit `a723c0f` ngày 2026-04-25, repo `github.com/dthanhvu03/toolsauto` là
**PUBLIC** → phơi công khai ~3,5 tháng.

Ngoài ra `gemini_cookies.json` từng bị commit ở `427ea22` (repo init), gỡ khỏi HEAD
tại `8935419` nhưng **vẫn còn trong lịch sử**.

Xoá khỏi HEAD **không** xoá khỏi lịch sử — phần còn lại thuộc Owner (xem Next).

### B. Code chết — đã xoá 731 dòng

```
grep -rE "['\"/](tiktok_links|viral_table|persona_tuner)\.html" app   → rỗng
grep -rnE "gemini_api|features\.affiliates\.ai|viral_intake\.video_protector" app tests scripts
                                                                      → chỉ còn 1 comment (đã sửa)
```

Phát sinh trong lúc làm: docstring `native_fallback.py` nói *"Vision/async vẫn nằm ở
gemini_api.py"* — sai từ TASK-025 (vision đã chuyển sang
`call_native_gemini_vision`). Đã sửa docstring + comment model tier.
Việc xoá `gemini_api.py` chính là bước cuối ADR-006 đã hoạch định → ghi closure vào
ADR-006 §7.

### C. Ghi lại, chưa thực thi

`ADR-009` — số phận WorkflowRegistry / GenericAdapter. Phát hiện chính:
`dispatcher.get_adapter()` **luôn** ghi đè Registry bằng dedicated adapter cho cả 4
platform trong enum → `GenericAdapter` (1015 dòng) là code không thể chạm tới, kể
cả khi seed dữ liệu. Cần Owner chốt trước khi xoá.

## Next

1. **Owner — gấp:** đổi mật khẩu + "đăng xuất mọi phiên" trên Facebook, Instagram,
   TikTok. Đây là thao tác duy nhất vô hiệu hoá được `xs` / `sessionid` đã rò.
2. **Owner quyết:** chuyển repo sang private (chặn phơi nhiễm ngay) và/hoặc purge
   lịch sử bằng `git filter-repo` + force-push — thao tác phá huỷ, cần lệnh trực tiếp.
3. Commit diff hiện tại (9 file) sau khi Owner review.
4. Khôi phục Python → mở lại pytest → mới làm được nhóm C và refactor god object.
