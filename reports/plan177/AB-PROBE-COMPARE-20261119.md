# PLAN-177 — A/B probe hoa hồng (19/11/2026 ~23:21 VN)

## Kết luận

Cùng profile, cùng item `54321049804`, cùng kiểu `fetch` in-page + CSRF:

| Nhánh | Script | Chờ trước fetch | Kết quả |
|---|---|---|---|
| **A (GPT)** | `runtime-lifecycle-probe.mjs` | `waitUntil: commit` + ~0,8–1,3s | **HTTP 403**, nhãn `verification_required` (`90309999`) |
| **B (Cursor)** | `portal-session-probe.mjs` | `domcontentloaded` + `networkidle` + ~2,5–4s | **HTTP 200**, `code=0`, `ids_exact` shop `1175585681` |

→ Chặn **không** phải “GPT không gọi được / firewall”. Khác **lifecycle chờ trang sẵn** trước khi gọi REST detail. Owner mở UI trước đó **không đủ** để làm A cũng xanh (A vẫn 403 trong lượt này).

Thứ tự chạy: **A rồi B** (có khoảng kill browser + xóa lock giữa hai nhánh). Chưa chạy ngược B→A trong cùng phiên.

## Cách em chạy (để anh / GPT làm lại)

1. `pm2 stop shopee-mcp`
2. Kill process Cloak giữ `\.shopee-mcp\chrome-profile` + xóa `Singleton*` / `lockfile`
3. Windows Node, `SHOPEE_PROFILE_DIR=C:\Users\Admin\.shopee-mcp\chrome-profile`, `SHOPEE_DOMAIN=shopee.vn`
4. **A:** `node reports/plan177/runtime-lifecycle-probe.mjs`
5. Kill/xóa lock lại
6. **B:** stdin `{"kind":"detail","params":{"item_id":"54321049804"}}` → `node reports/plan177/portal-session-probe.mjs`
7. `pm2 start shopee-mcp` → health `:9224` + shortlink smoke

## Artifact

- `ab-gpt-runtime-20261119.json` / `ab-gpt-runtime-full-20261119.json`
- `ab-cursor-portal-20261119.jsonl`
- Diagnostic GPT gốc 22:45 giữ tại `runtime-lifecycle-20261119.json` (đã restore từ bak)

## Hệ quả cho bridge native

Cầu nối repo / client native cần **chờ kiểu B** (trang offer ổn + delay ngắn kiểu người) trước `GET /api/v3/offer/product`, không fetch ngay sau `commit`. Không tăng timeout vô hạn; không vượt CAPTCHA.

Legacy đã phục hồi: health 200, shortlink OK sau A/B. Native vẫn tắt cho khách.
