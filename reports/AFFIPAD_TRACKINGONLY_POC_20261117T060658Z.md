# AffiPad trackingOnly POC — 17/11/2026 13:06 VN

Mục tiêu: ra link kiểu mẫu Bot San Sale (`s.shopee.vn/…?fb_content_id=…&sm_sig_id=…`).

## Cách làm

1. Tạo `an_redir` bằng Affiliate ID + Sub ID của mình (`cashback_bot.affiliate.build_an_redir`).
2. AffiPad `POST /v1/convert` với `trackingOnly=true`, `tracking.preset=fb_reels` (tool `fb-voucher`).
3. Không ghi chữ ký/payload đầy đủ vào repo; link thô ở Windows Downloads.

## Kết quả

| Kiểm tra | Kết quả |
|---|---|
| Host `s.shopee.vn` + field Meta trên URL trả về | **CÓ** (`/an_redir?…&fb_content_id&encrypted_payload&sm_sig_id…`) |
| Giữ `affiliate_id` / `sub_id` của mình trên URL | **CÓ** |
| Destination `utm_source=an_<Affiliate ID mình>` | **CÓ** (`an_17315920094`) |
| Sub ID còn trên destination | **CÓ** |
| Giống hệt short opaque `s.shopee.vn/5LDX…?…` | **KHÔNG** — mình ra `/an_redir?…` (dài hơn, nhưng đúng attribution) |

So với `convert` thường (trả `s.afp.ad`, `utm_source` lệch): **trackingOnly trên an_redir của mình** là hướng đúng cho Cashbot.

## Chưa làm

- Mở app Shopee / checkout để xác nhận voucher FB có hiện và áp được.
- Đối soát đơn thật + hoa hồng theo Sub ID.
- Gắn vào bot khách.

Evidence JSON: `AFFIPAD_TRACKINGONLY_POC_20261117T060658Z.json`.  
Link thử (private): `C:\Users\Admin\Downloads\affipad-trackingonly-20261117T060658Z.txt`.
