# Runbook pilot P0/P1 — PLAN-180 / TASK-066

Owner đã duyệt plan. **Chỉ bật khi anh nói «làm P0» / «làm P1».**

Bridge: `http://192.168.112.1:9224`
DB cashback (mặc định): `data/cashback.sqlite` — mọi truy vấn **chỉ đọc**.

---

## Trạng thái trước pilot (kiểm tra nhanh)

```bash
curl -sS --max-time 8 "http://192.168.112.1:9224/health"
cd /home/vu/toolsauto && .venv/bin/python -c "from cashback_bot.config import load_settings; s=load_settings(); print(s.product_quote_primary)"
```

- Legacy health: `status=ok`, **không** có `implementation=toolsauto` (hoặc không phải bản repo).
- PRIMARY kỳ vọng trước P1: `product_data`.

Đếm snapshot (đọc-only):

```bash
cd /home/vu/toolsauto && .venv/bin/python reports/plan177/pilot_quote_source_counts.py
```

---

## P0 — Bật bridge repo (quote vẫn PD)

### Bật

1. Trong `ecosystem.config.js` → app `shopee-mcp` →
   `SHOPEE_BRIDGE_IMPLEMENTATION=repo`
   + `SHOPEE_BRIDGE_LISTEN_HOST=192.168.112.1`
   + `SHOPEE_BRIDGE_ALLOWED_PEERS=<IP WSL exact>` (vd `192.168.112.133`; kiểm `ip -4 route get 192.168.112.1`).
2. `run_shopee_mcp.sh` phải forward env sang Win32 qua `WSLENV` (đã có từ P0 19/11).
3. Kill orphan listen `:9224` nếu cần, rồi `pm2 startOrReload ecosystem.config.js --only shopee-mcp --update-env`.
4. Chờ prepare (~15–55s) rồi:

```bash
curl -sS --max-time 8 "http://192.168.112.1:9224/health"
# Kỳ vọng: implementation=toolsauto , quote_schema=1
curl -sS --max-time 60 \
  "http://192.168.112.1:9224/api/generate_shortlink?url=https%3A%2F%2Fshopee.vn%2Fproduct%2F1175585681%2F54321049804&sub_id=PILOTP0"
```

5. **Không** đổi `PRODUCT_QUOTE_PRIMARY`. **Không** restart Cashbot trừ Owner bảo.
6. Quan sát 2–4 giờ / ~20 shortlink; ghi `reports/plan177/PILOT-P0-RESULT-YYYYMMDD.md`.

### Rollback P0

1. `SHOPEE_BRIDGE_IMPLEMENTATION = "legacy"` trong ecosystem (hoặc xóa key).
2. `pm2 restart shopee-mcp --update-env`
3. Health không còn `implementation=toolsauto`; shortlink smoke 1 lần OK.

---

## P1 — Native quote (chỉ sau P0 đạt)

### Điều kiện

Health đang `toolsauto` + Owner nói «làm P1».

### Bật

1. `.env`: `PRODUCT_QUOTE_PRIMARY=native` (giữ degraded bật / mặc định on).
2. `systemctl restart cashback-bot cashback-zalo`
3. Owner gửi 1 link test → kiểm log/snapshot `quote_source` (`native_shopee` hoặc fallback `product_data` / `degraded_unquoted`).
4. Quan sát 24–48h (có qua đêm); mỗi ngày chạy `pilot_quote_source_counts.py`.

### Rollback P1

```bash
# .env → PRODUCT_QUOTE_PRIMARY=product_data
systemctl restart cashback-bot cashback-zalo
```

Full về pre-pilot: rollback P1 rồi rollback P0.

---

## Dấu hiệu rollback ngay

- Cụm shortlink fail / bridge restart loop (P0).
- Cụm 403/`90309999` hoặc timeout làm khách không nhận được trả lời (P1).
- `degraded_unquoted` tăng bất thường so với baseline trước P1.

---

## Lệnh Owner → Agent

| Anh nói | Agent làm |
|---|---|
| `làm P0` | Execute mục P0 + báo cáo |
| `làm P1` | Execute mục P1 (chỉ nếu P0 OK) |
| `rollback P0` / `rollback P1` / `rollback hết` | Theo mục rollback |
