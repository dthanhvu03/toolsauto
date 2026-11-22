# PLAN-180 — Kết quả P0 (19/11/2026 ~00:04 VN ngày 20)

## Verdict

**P0 ĐẠT.** Bridge repo phục vụ WSL: health `implementation=toolsauto`, shortlink OK. `PRODUCT_QUOTE_PRIMARY` vẫn `product_data`. Không restart Cashbot/Zalo.

## Bằng chứng

| Kiểm tra | Kết quả |
|---|---|
| Baseline (trước flip) | health legacy ok; shortlink success; PRIMARY=product_data → `pilot-p0-baseline-20261119.json` |
| Health sau P0 (WSL → 192.168.112.1:9224) | `implementation=toolsauto`, `quote_schema=1` |
| Shortlink P0 | HTTP 200, success=true, host `s.shopee.vn`, **0,285s** (warm) |
| PRIMARY | `product_data` (không đổi) |
| Snapshot `quote_source` | all_time vẫn chỉ `product_data` (184) |

## Việc phải sửa khi bật (trong phạm vi P0)

1. Repo mặc định listen `127.0.0.1` → WSL không gọi được. Đã set `SHOPEE_BRIDGE_LISTEN_HOST=192.168.112.1` + `SHOPEE_BRIDGE_ALLOWED_PEERS=192.168.112.133` trong `ecosystem.config.js`.
2. Win32 `node.exe` **không** nhận env PM2/WSL tùy ý → thêm `WSLENV` trong `run_shopee_mcp.sh` để forward listen/peers/profile.

## Quan sát tiếp (2–4 giờ / ~20 shortlink)

- Health vẫn `toolsauto`.
- Shortlink khách / thử tay không cụm fail.
- PRIMARY vẫn `product_data`.
- Nếu WSL IP đổi (khác `.133`) → cập nhật `SHOPEE_BRIDGE_ALLOWED_PEERS` + restart bridge.

## Rollback P0

1. ecosystem: `SHOPEE_BRIDGE_IMPLEMENTATION=legacy`; có thể bỏ listen/peers.
2. `pm2 startOrReload ecosystem.config.js --only shopee-mcp --update-env`
3. Health không còn `toolsauto`; shortlink smoke 1 lần.

## Next

Cửa sổ P0 đang mở. Owner bảo **«làm P1»** chỉ sau khi P0 quan sát ổn.
