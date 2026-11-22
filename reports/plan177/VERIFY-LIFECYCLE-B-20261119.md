# PLAN-177 — Verify lifecycle-B (Cursor thay Claude, 19/11/2026 ~23:45 VN)

## Verdict

**VERIFY APPROVED** cho phạm vi: sửa chờ portal kiểu B + smoke **một** sản phẩm + phục hồi legacy.
**Không** phê duyệt bật native cho khách / đổi PRIMARY / restart Cashbot.

## Anti-style checklist

| # | Criterion | Proof | Pass? |
|---|---|---|---|
| 1 | `networkidle` ≤ 8s; settle 2,5–4s; không rút ngắn settle khi thiếu budget | `scripts/shopee_bridge/browser.mjs` L137–145; test `navigation invalidates… never shortens lifecycle B` | ✅ |
| 2 | Navigate giữa settle → invalidate / lỗi, không fetch mù | `portalNavigation` + check L155; browser tests lifecycle B | ✅ |
| 3 | Smoke: ids_exact `1175585681/54321049804`, source native | `lifecycle-b-native-smoke-20261119.json` quote elapsed 1.347s | ✅ |
| 4 | Shortlink repo OK | cùng JSON: success, host `s.shopee.vn`, 0.193s | ✅ |
| 5 | Node bridge tests 38/38 | GPT TAP + Cursor rerun 2026-11-19: `# pass 38 # fail 0` (~2,9s) | ✅ |
| 6 | Legacy restore health+shortlink | `lifecycle-b-legacy-restore-20261119.json`; health live Cursor lúc verify: 200 / shopee-mcp | ✅ |
| 7 | PRIMARY mặc định vẫn `product_data` | `.env` unset; `load_settings().product_quote_primary == product_data` | ✅ |
| 8 | Artifact không lộ cookie/token value | Scan 12 file lifecycle-B/AB vs cookie file: 0 leak | ✅ |
| 9 | Scope không mở rộng âm thầm (không bật khách) | Báo cáo GPT + env flags unset; không restart Cashbot trong verify | ✅ |

## Không nằm trong verify lần này

- Ổn định nhiều SKU / nhiều giờ / freshness độc lập vs PD
- Bật `SHOPEE_BRIDGE_IMPLEMENTATION=repo` hoặc `PRODUCT_QUOTE_PRIMARY=native` trên bot khách
- Gate A ALT, giai đoạn 3 đo KPI

## Đề xuất bước Owner/Anti

1. Anti ký sign-off vận hành nếu đồng ý verdict trên.
2. Owner chọn: **giữ PD** (an toàn) hoặc **pilot native** có cửa sổ đo + cờ rollback rõ.
3. Nếu pilot: chỉ opt-in có chủ đích; quan sát lỗi 403/`90309999`, p95, lệch hoa hồng — một mẫu smoke không thay KPI.
