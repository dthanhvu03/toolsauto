# PLAN-180 — Pilot P0/P1: bridge repo rồi native quote (Cashbot)

| Thông tin | Nội dung |
|---|---|
| Mã kế hoạch | PLAN-180 |
| Trạng thái | **P0 bật lại 08:09 VN 20/11 (sau drift legacy qua đêm). toolsauto + shortlink OK; pm2 save. PRIMARY=product_data. Chờ «làm P1».** |
| Cha | [PLAN-177](PLAN-177-shopee-native-product-quote.md) / [TASK-063](../tasks/TASK-063-shopee-native-product-quote.md) |
| Task | [TASK-066](../tasks/TASK-066-shopee-native-pilot-p0-p1.md) |
| Người làm | Cursor execute khi Owner bảo; Anti review vận hành nếu cần |
| Không làm trong plan này | Gate A ALT; giai đoạn 3 KPI dài; đổi công thức tiền; mở bridge ra Internet |

## 1. Mục tiêu (1 câu)

Cho khách dùng dần đường Shopee mới **có lưới Product Data**, tách lỗi link và lỗi số hoàn bằng hai tầng P0 → P1, luôn rollback &lt; 2 phút.

## 2. Bối cảnh đã có (không làm lại)

- Lifecycle B trong `scripts/shopee_bridge/browser.mjs` + smoke 1 SP + VERIFY APPROVED (`reports/plan177/VERIFY-LIFECYCLE-B-20261119.md`).
- Ladder sẵn: `native` → PD hợp lệ → `degraded_unquoted` (`cashback_bot/service.py`).
- Launcher opt-in: `SHOPEE_BRIDGE_IMPLEMENTATION=repo` trong `run_shopee_mcp.sh`.
- Health repo trả `implementation: toolsauto`; legacy không có field đó / `server=shopee-mcp` version npm.
- Mặc định hiện tại: PRIMARY unset → `product_data`; PM2 `shopee-mcp` **chưa** set `SHOPEE_BRIDGE_IMPLEMENTATION` → legacy.

## 3. Hai tầng pilot — anh hình dung thế này

```
Khách gửi link Shopee
        │
        ├─[P0] Tạo shortlink ──► Bridge REPO (chờ B)     │ số hoàn vẫn Product Data
        │
        └─[P1] Lấy số hoàn ──► Native Shopee ──fail──► Product Data ──fail──► link chưa số
```

- **P0 hỏng** → khách khó có link rút gọn / chậm tạo link; số hoàn vẫn như cũ.
- **P1 hỏng** → vẫn có số từ PD (nếu PD sống) hoặc link chưa số; shortlink vẫn đi bridge repo.

## 4. Phạm vi build / không build

### Có thể phải đụng code/config (tối thiểu)

| ID | Việc | File | Bắt buộc? |
|---|---|---|---|
| B1 | Ghi rõ env pilot trong `ecosystem.config.js` (mặc định vẫn `legacy`; comment/`repo` chỉ khi Owner bật) | `ecosystem.config.js` | Nên có — tránh quên cờ khi restart PM2 |
| B2 | Cheat-sheet lệnh đo + rollback trong report | `reports/plan177/PILOT-P0-P1-RUNBOOK.md` | Có |
| B3 | Script đọc-only đếm `quote_source` từ SQLite snapshot (không DELETE) | `reports/plan177/pilot_quote_source_counts.py` hoặc lệnh SQL trong runbook | Nên có — đo P1 |

### Không build

- Không đổi `sure_commission` / ví / settlement.
- Không sửa npm global.
- Không UI dashboard mới.
- Không tự ghi `.env` production trong plan draft — chỉ làm khi Owner bảo execute P1.

## 5. P0 — Bridge repo, quote vẫn PD

### Mục tiêu P0

Traffic thật dùng **cầu nối repo** cho shortlink (và voucher nếu bot gọi), quote vẫn AddLiveTag.

### Bước execute (khi Owner: «làm P0»)

1. Backup nhanh: ghi health hiện tại + 1 shortlink smoke → `reports/plan177/pilot-p0-baseline-YYYYMMDD.json`.
2. Set `SHOPEE_BRIDGE_IMPLEMENTATION=repo` cho process `shopee-mcp` (ecosystem + `pm2 restart shopee-mcp --update-env` **hoặc** tương đương an toàn đã thống nhất).
3. Xác minh: `GET http://192.168.112.1:9224/health` có `implementation=toolsauto`, `quote_schema=1`.
4. Smoke: 1 shortlink SP quen (`1175585681/54321049804` hoặc SP anh chọn) → `success=true`.
5. **Không** đổi `PRODUCT_QUOTE_PRIMARY`; **không** restart Cashbot trừ khi anh yêu cầu.
6. Cửa sổ quan sát P0: **2–4 giờ** ban ngày (hoặc ≥20 shortlink thật nếu ít traffic).
7. Ghi `reports/plan177/PILOT-P0-RESULT-YYYYMMDD.md`.

### DoD P0

- [ ] Health = toolsauto
- [ ] Shortlink smoke OK sau restart
- [ ] Cashbot vẫn trả số hoàn bình thường (PD) trên ≥1 tin khách/test
- [ ] Không cụm shortlink fail / bridge restart loop
- [ ] Rollback P0 đã viết sẵn và (khuyến nghị) thử 1 lần trên cửa sổ thấp điểm nếu anh muốn

### Rollback P0

1. `SHOPEE_BRIDGE_IMPLEMENTATION=legacy` (hoặc bỏ env) + `pm2 restart shopee-mcp --update-env`
2. Health không còn `implementation=toolsauto` / behavior legacy
3. Shortlink smoke OK

## 6. P1 — Native quote + fallback PD

### Điều kiện vào P1

P0 DoD đạt **và** Owner nói rõ «làm P1». Không nhảy cóc.

### Mục tiêu P1

Quote thử native trước; PD và degraded giữ lưới. Bridge vẫn repo.

### Bước execute (khi Owner: «làm P1»)

1. Xác nhận P0 đang toolsauto.
2. Ghi baseline: vài `quote_source` gần nhất (SQL đọc-only).
3. `.env`: `PRODUCT_QUOTE_PRIMARY=native` (giữ `PRODUCT_QUOTE_ALLOW_DEGRADED` bật/mặc định on).
4. `systemctl restart cashback-bot cashback-zalo` (đúng deploy README).
5. Anh gửi **1 link test** → log/snapshot: ưu tiên `native_shopee`; nếu fail phải thấy fallback PD hoặc degraded, không “câm”.
6. Cửa sổ: **24–48 giờ**, gồm ít nhất 1 chu kỳ qua đêm.
7. Mỗi cuối ngày: đếm `native_shopee` / `product_data` / `degraded_unquoted`; ghi note 403/timeout nếu có.
8. Báo cáo `reports/plan177/PILOT-P1-RESULT-YYYYMMDD.md`.

### DoD P1 (để giữ pilot / kéo dài)

- [ ] ≥1 native thành công trên traffic/test thật sau restart
- [ ] Fallback PD vẫn hoạt động khi cố ý hoặc khi native lỗi tự nhiên
- [ ] Không cụm `degraded_unquoted` bất thường
- [ ] Không cụm 403/`90309999` liên tiếp
- [ ] Rollback P1 thử hoặc diễn tập lệnh đã xác nhận

### Rollback P1 (giữ bridge repo hoặc về full cũ)

**Chỉ tắt native:**
`PRODUCT_QUOTE_PRIMARY=product_data` + restart cashback-bot/zalo.

**Về full pre-pilot:**
tắt native như trên + rollback P0 (legacy bridge).

## 7. Đo lường (không bịa %)

| Chỉ số | Cách lấy | Ghi chú |
|---|---|---|
| Bridge đang bản nào | `curl …/health` → `implementation` | P0/P1 |
| Shortlink OK/fail | log bridge / thử tay | P0 trọng tâm |
| `quote_source` | bảng snapshot / policy (SELECT only) | P1 trọng tâm |
| Lỗi native | log `[Cashback]` + bridge stages nếu bật diagnostics | 403/timeout |
| Thời gian cảm nhận | anh thử 3–5 link | prepare lần đầu sau restart có thể ~10–15s |

Ngưỡng “đạt tạm / rollback” lấy theo đề xuất vận hành đã thống nhất với Owner (không coi là KPI đã ký giai đoạn 3).

## 8. Phân công

| Ai | Việc |
|---|---|
| Owner | Duyệt plan; nói «làm P0» / «làm P1» / «rollback»; gửi link thử; quyết giữ/tắt sau 48h |
| Cursor | Runbook + (optional) script đếm; execute P0/P1 khi được lệnh; ghi báo cáo; không tự bật |
| Anti | Sign-off vận hành nếu quy trình yêu cầu trước P1 hoặc trước giữ lâu dài |
| GPT/Codex | Không bắt buộc trừ khi P0/P1 phát sinh bug bridge cần sửa code |

## 9. Rủi ro

| Rủi ro | Phòng | Phát hiện | Khắc phục |
|---|---|---|---|
| Antibot 403 khi quote | Lifecycle B đã có; không spam | Log/mã lỗi | Fallback PD; rollback P1 |
| Prepare lâu ăn deadline 20s | Quan sát P0/P1; warm sau restart | Timeout log | Rollback hoặc chỉ giữ P0 |
| Quên env khi `pm2 restart` | B1 ecosystem | Health không toolsauto | Set lại env |
| Đổi nhầm PRIMARY trước P0 | Cấm trong DoD P0 | `load_settings().product_quote_primary` | Đổi lại product_data |

## 10. Thứ tự triển khai sau khi Owner duyệt

1. Viết runbook (+ script đếm nếu thiếu) — **chưa bật**.
2. Owner «làm P0» → execute mục 5 → báo cáo P0.
3. Owner «làm P1» → execute mục 6 → báo cáo P1 hàng ngày.
4. Owner chốt: giữ P1 / chỉ P0 / full rollback.
5. Chỉ khi giữ lâu dài mới cập nhật PLAN-177 mục bật chính thức + Claude/Anti theo quy trình cũ.

## Review

- Owner: **đã duyệt** 19/11/2026 (~23:54 VN).
- Chuẩn bị sau duyệt: runbook `reports/plan177/PILOT-P0-P1-RUNBOOK.md`, script đếm `pilot_quote_source_counts.py`, `ecosystem.config.js` ghi rõ `SHOPEE_BRIDGE_IMPLEMENTATION=legacy` (chưa repo).
- Anti: (optional) review vận hành trước P1.
- **Chưa execute P0/P1** — chờ Owner «làm P0».
