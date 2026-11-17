# PLAN-174 — AffiPad FB voucher (bridge short + trackingOnly)

| Field | Value |
|---|---|
| ID | PLAN-174 |
| Status | executed — rotate FB/IG + chặn farm cùng món liên tiếp; mn test tử |
| Executor | Cursor |
| Owner request | 17/11: giống bot họ → short opaque + Meta, hoa hồng mình |

## Mục tiêu

Khi khách tạo link Cashbot:

1. `build_an_redir` (giữ affiliate_id + sub_id)
2. Bridge rút gọn `product_url` + `sub_id` → `s.shopee.vn/XXXX`
3. AffiPad `trackingOnly` + `fb_reels` trên short → `s.shopee.vn/XXXX?Meta…`
4. Bridge tắt → ký thẳng `an_redir`; AffiPad lỗi → giữ `an_redir` thường (không chặn mua)

## Scope

- `cashback_bot/affipad.py`
- `cashback_bot/config.py` + `.env`: `AFFIPAD_*`
- `cashback_bot/service.py`: bridge short rồi ký
- `cashback_bot/shopee_shortener.py`: **không** rút gọn URL đã có Meta
- Tests mock HTTP; không đổi schema/ví/tiền

## Không làm

- `convert` thường (s.afp.ad / lệch affiliate)
- Mua đơn / claim voucher tự động
- Đổi Sub ID `VOUCHERS`

## Validation

- Unit: short→ký / bridge tắt→ký an_redir / AffiPad fail→an_redir / tắt flag
- Shortener: URL có `sm_sig_id` giữ nguyên
- Live: owner mở POC short → voucher hiện (17/11 ~13:40 VN)

## Proof

- POC like-competitor: `reports/AFFIPAD_LIKE_COMPETITOR_POC_20261117T063605Z.json` — `trackingOnly_on_bridge_short` + utm `an_17315920094`
- Owner confirm: mở app hiện voucher
- Wire: service dùng `shorten_shopee_url` rồi `sign_tracking_only`
- Flag: `AFFIPAD_FB_VOUCHER_ENABLED=1` — tắt nhanh `=0` nếu cần
- UX 17/11 ~14:02: thẻ Meta hiện lead + lưu ý hết lượt / 0h·9h·15h·20h / trễ 30–40s; trang 🛡️ có `FB_VOUCHER_RULE` (cờ `f`)
- 17/11 ~14:16: `AFFIPAD_TRACKING_PRESET=rotate` xen kẽ `fb_reels`/`ig_reels`; gửi lại đúng món liên tiếp → `same_item_voucher` + nút Mua link cũ (không ký AffiPad lần 2)
