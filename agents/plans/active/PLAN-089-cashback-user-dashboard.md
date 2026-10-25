# PLAN-089 — Dashboard khách hàng và dòng tiền cashback (Telegram + web)

| | |
|---|---|
| Executor | Claude Code (chủ bot giao 2026-10-25: "cả 2", "cần hết theo góc nhìn CEO, COO") |
| Trạng thái | Chủ bot duyệt 2026-10-25 ("triển khai tất cả theo plan"). ✅ Đã chạy 2026-10-25 14:15Z (`a193faa`), chờ chủ bot xem thử |
| Không đổi | Chỉ đọc DB (`mode=ro`); không sửa sổ ví, chính sách hay trạng thái đơn; không gọi Shopee |
| Nguồn dữ liệu | `data/cashback.sqlite`: `telegram_users`, `channel_identities`, `link_requests`, `shopee_clicks`, `shopee_conversions`, `cashback_entries`, `cashback_payouts`, `settlement_batches/items`, `support_tickets`, `admin_notifications`, `outbound_messages`, `bot_state` |

## 1. Kiến trúc

```
cashback_bot/insights.py  ← MỘT nơi tính mọi con số (sqlite thuần, mở mode=ro, không import requests)
   ├── /admin Telegram: 💹 Dòng tiền · 🛠 Vận hành · 👥 Khách hàng      (cashback_bot/admin_insights.py)
   └── Web Dashboard :8000  /cashback, /cashback/users, /cashback/users/{id}  (app/features/cashback_insights/)
```

- Hai giao diện dùng chung một module tính số, nên Telegram và web luôn ra cùng một con số.
- Web: cùng FastAPI, có đăng nhập, dùng Tailwind + htmx như các trang khác. Không thêm thư viện ngoài. Biểu đồ vẽ bằng SVG trong template.
- Tiền có hai lớp và luôn ghi rõ: **tạm tính** (Shopee chưa duyệt / chưa trả) và **thực** (Shopee đã trả, đã đối soát).

## 2. Chỉ số

### 2.1 Dòng tiền: từ khách mua tới tiền về túi (CEO)

Theo kỳ: 7 ngày / 30 ngày / tháng này / từ đầu. Mỗi dòng tách theo trạng thái (chờ duyệt / đã duyệt / đã Shopee trả / huỷ).

| # | Chỉ số | Công thức |
|---|---|---|
| M1 | GMV qua bot | Σ `gmv_vnd` đơn khớp link bot |
| M2 | Hoa hồng gộp | Σ `gross_commission_vnd` |
| M3 | Phí MCN | Σ `mcn_fee_vnd` |
| M4 | Hoa hồng ròng | Σ `net_commission_vnd` (= M2 − M3) |
| M5 | Phần của khách | Σ `cashback_entries.cashback_vnd` (trừ huỷ) |
| M6 | Dự phòng thuế + phí | Σ `tax_vnd` + `fee_vnd` (theo snapshot chính sách từng link) |
| M7 | **Biên của chủ bot** | M4 − M5 − M6, và % trên M4 |
| M8 | Tiền mất do huỷ / trả hàng / gian lận | hoa hồng ròng của đơn huỷ, tính bằng tiền và % |
| M9 | Tiền Shopee đã trả thật | `settlement_batches` MATCHED: `bank_received_vnd` |
| M10 | Tiền sắp về | hoa hồng ròng đã APPROVED, chưa SETTLED |

**Nghĩa vụ với khách (công nợ)**, xem theo một thời điểm:

| # | Chỉ số |
|---|---|
| L1 | Đang chờ Shopee (pending) |
| L2 | Đang giữ (holding) |
| L3 | Trong ví chưa rút |
| L4 | Đang chờ chuyển (yêu cầu rút mở) |
| L5 | Đã trả |
| L6 | Đang trừ lại (số dư âm do thu hồi) |
| L7 | Quỹ có chứng từ còn = M9 − phần đã chi và đang giữ |

**Thời gian ra tiền** (trung vị, theo ngày):

| # | Chặng |
|---|---|
| T1 | Mua → hoàn thành |
| T2 | Hoàn thành → Shopee trả |
| T3 | Yêu cầu rút → đã trả |

T3 đo SLA 3–7 ngày làm việc trong ADR-059.

### 2.2 Tăng trưởng và giá trị khách (CEO)

| # | Chỉ số | Định nghĩa |
|---|---|---|
| G1 | Khách mới | theo kỳ, tách Telegram / Zalo |
| G2 | Khách hoạt động | tạo link hoặc có đơn trong 7 / 30 ngày |
| G3 | Phễu | khách → tạo link → có click → có đơn → đơn hoàn thành → Shopee trả, kèm tỉ lệ từng bước |
| G4 | Doanh thu mỗi khách | M4 / khách hoạt động; biên mỗi khách = M7 / khách hoạt động |
| G5 | Giá trị tích luỹ (LTV) | biên của chủ bot từ trước tới nay, tính cho từng khách |
| G6 | Mức tập trung | % biên đến từ top 1 khách và top 10% khách (rủi ro phụ thuộc vài người) |
| G7 | Giữ chân | trong số khách mới tuần N, bao nhiêu % tạo link lại ở tuần N+1 / N+4 |
| G8 | Đơn trung bình | GMV / đơn; hoa hồng / đơn; số đơn / khách |
| G9 | Ngành hàng / shop | top `cat_name`, `shop_name` theo GMV và hoa hồng |
| G10 | Kênh | Telegram và Zalo: khách, đơn, biên |

### 2.3 Vận hành (COO)

| # | Chỉ số | Ngưỡng cảnh báo (đề xuất) |
|---|---|---|
| O1 | Hai bot sống, cùng commit (`code_version`, nhịp sống) | im > 10 phút / khác commit |
| O2 | Đồng bộ Shopee: lần thành công gần nhất, số lần lỗi liền | quá 2 chu kỳ |
| O3 | Tin gửi khách 24 giờ: đã gửi / `unknown` / lỗi / bị chặn | `unknown` + lỗi > 0 |
| O4 | Link tạo lỗi, link chưa giao tới khách (`delivery_status`) | > 0 |
| O5 | Ticket: đang mở, tuổi ticket lâu nhất | > 24 giờ |
| O6 | Yêu cầu rút: đang mở, tuổi lâu nhất | > 5 ngày làm việc |
| O7 | Đơn chờ đối soát lâu (completed, chưa SETTLED) | > 45 ngày |
| O8 | Sức chứa Zalo BASIC | ≥ 40/50 |
| O9 | Backup gần nhất, ví còn khoá vì lý do gì | > 26 giờ |
| O10 | Cảnh báo sổ (`payouts.invariants`) | > 0 |

### 2.4 Từng khách

**Danh sách**:
- Cột: tên, kênh, ngày vào, lần cuối dùng, link, click, đơn (hoàn thành / huỷ).
- Cột tiền: GMV, hoa hồng ròng, phần của khách, biên của chủ bot, số dư ví, đang chờ chuyển.
- Cột khác: hạng, ticket, nhóm, cờ cảnh báo.

**Nhóm** (đề xuất, chủ bot chỉnh được):

| Nhóm | Điều kiện |
|---|---|
| 🆕 Mới | ≤ 7 ngày |
| 🟢 Đang hoạt động | có link trong 14 ngày |
| 💎 Giá trị cao | top 10% theo biên |
| 🟠 Sắp rời | từng có đơn, 14–30 ngày không dùng |
| ⚪ Ngủ | > 30 ngày không dùng |
| 🔴 Cần xử lý | chặn bot, số dư âm, ticket mở, vừa đổi tài khoản |

**Chi tiết một khách**:
- Thẻ tiền (như mục 2.1 nhưng cho một khách).
- Dòng thời gian: link → click → đơn → đổi trạng thái → vào ví → rút; ticket; tin bot đã gửi và kết quả gửi.
- Ngân hàng: chỉ 4 số cuối và trạng thái xác minh.
- Điều khoản đã đồng ý, tuỳ chọn thông báo.

## 3. Phác giao diện

### Telegram `/admin` (số chỉ để minh hoạ)

```
⚙️ Quản trị
[🔗 Shopee] [👛 Ví khách]
[💹 Dòng tiền] [🛠 Vận hành] [👥 Khách hàng]   ← mới
...

💹 Dòng tiền · 30 ngày  (tạm tính · thực)
GMV 12.400.000đ · 38 đơn · 9 khách
Hoa hồng ròng 610.000đ (MCN −32.000đ)
 ├ Khách  427.000đ (70%)
 ├ Dự phòng thuế/phí 61.000đ
 └ Biên của anh 122.000đ (20%)
Mất do huỷ 45.000đ (7%)
Shopee đã trả thật 0đ · Sắp về 210.000đ
Công nợ khách: chờ 300k · giữ 90k · ví 0 · chờ chuyển 0
Ra tiền (trung vị): mua→xong 9 ngày · xong→Shopee trả –
[7 ngày] [30 ngày] [Tháng này] [Từ đầu]

👥 Khách hàng · xếp theo biên ▾
1. 💎 Tuan (Zalo) · 6 đơn · biên 41.000đ · ví 0
2. 🟢 @minh · 3 đơn · biên 18.000đ
...
[Biên] [Đơn] [Mới] [Sắp rời] [Cần xử lý]
```

### Web `/cashback`

```
┌ Dòng tiền ─────────────────────────────── [7N|30N|Tháng|Tất cả] ┐
│ GMV  Hoa hồng ròng  Phần khách  Biên chủ bot  Mất do huỷ  Sắp về  │  ← 6 thẻ, tạm tính / thực
│ [thác nước: GMV → HH gộp → −MCN → −khách → −dự phòng → biên]       │
│ [cột theo ngày: hoa hồng ròng · biên]                              │
├ Công nợ khách ─────────┬ Phễu ────────────────┬ Vận hành ─────────┤
│ chờ | giữ | ví | chuyển │ khách→link→click→đơn  │ O1–O10, đèn màu   │
├ Khách hàng ────────────────────────────────────────────────────────┤
│ tìm… [kênh▾][nhóm▾]  bảng sắp xếp theo từng cột (mục 2.4)          │
└─────────────────────────────────────────────────────────────────────┘
/cashback/users/{id}: thẻ tiền + dòng thời gian + đơn + ví + ticket
```

## 4. Các bước

| Bước | Việc | Proof |
|---|---|---|
| 1 | `insights.py` + test: mỗi chỉ số một test trên DB dựng sẵn; đối chiếu với `admin_stats` và `wallet.totals()` | pytest |
| 2 | Telegram: 3 màn mới, chia trang, nhóm, sắp xếp | pytest + chủ bot bấm thử |
| 3 | Web: route có đăng nhập, 3 trang, htmx đổi kỳ / lọc | pytest (TestClient) + kiểm tra trên trình duyệt |
| 4 | Đối chiếu số trên DB production (chỉ đọc) với ảnh báo cáo Shopee anh gửi | bảng so khớp trong PLAN |

Restart:
- Bước 2: `systemctl restart cashback-bot cashback-zalo`.
- Bước 3: restart `Web_Dashboard` (pm2), không ảnh hưởng hai bot.

## 5. Cần chủ bot duyệt

1. Danh sách chỉ số ở mục 2: thêm hay bỏ gì.
2. "Biên của chủ bot" = hoa hồng ròng − phần khách − dự phòng thuế/phí (theo snapshot từng link). Dự phòng 10% có tính là chi phí không, hay anh muốn xem cả hai số (trước và sau dự phòng)?
3. Ngưỡng nhóm khách và ngưỡng cảnh báo vận hành (mục 2.3, 2.4).
4. Web: trang `:8000` đang mở `0.0.0.0` (máy khác trong mạng vào được, có đăng nhập). Giữ như vậy, hay chỉ cho xem trên máy này (`127.0.0.1`)?

## Trả lời của chủ bot (2026-10-25)

- Làm cả Telegram và web, đủ chỉ số theo góc nhìn CEO / COO.
- Hiện mới tính một phần dự phòng, chưa tính chi phí vận hành và hạ tầng. Vì vậy dashboard hiện biên ba mức:
  - trước dự phòng;
  - sau dự phòng;
  - lãi sau chi phí vận hành / hạ tầng: admin nhập mỗi tháng ở /admin → 💹 Dòng tiền → ✍️, bot chia theo số ngày của kỳ, lưu `bot_state.ops_cost_monthly_vnd` và ghi vào 📊 Lịch sử. Chưa nhập thì ghi "chưa nhập", không tự đoán.
- Ngưỡng nhóm khách và ngưỡng cảnh báo: dùng mức đề xuất (hằng số đầu `insights.py`).
- Web: giữ nguyên cách mở `0.0.0.0:8000` có đăng nhập (chủ bot chưa đổi).

## Đã làm

| Phần | File |
|---|---|
| Tính số (chỉ đọc, `mode=ro`) | `cashback_bot/insights.py` |
| Telegram: 💹 Dòng tiền · 📈 Tăng trưởng · 🛠 Vận hành · 👥 Khách hàng (lọc theo nhóm, sắp xếp, chi tiết) · ✍️ chi phí | `cashback_bot/admin_insights.py`, `admin_policy.py`, `admin_ui.py` (menu) |
| Web: `/cashback`, `/cashback/users`, `/cashback/users/{id}`, mục "Cashback" ở menu trái | `app/features/cashback_insights/`, `app/templates/pages/cashback_*.html`, `fragments/cashback_style.html`, `app/main.py`, `layouts/app.html` |

Hai chỉ số chưa có trong lần này:
- **Hạng thành viên** của từng khách: tính năng hạng chưa bật.
- **Thời gian Shopee trả**: chưa có kỳ đối soát nào, nên chưa có số.

## Proof

- `pytest tests/test_cashback_*.py tests/test_admin_api_lists.py`: 800 passed. `tests/test_cashback_insights.py` có 13 test mới.
- Các test giao diện web khác dùng chung layout: 81 passed.
- `ruff`: sạch.
- Chạy thử trên DB production (chỉ đọc): ròng 18.740đ − khách 13.117đ − dự phòng 2.060đ = biên 3.563đ (19%).
  - Phễu: 11 khách → 5 có click → 2 có đơn.
  - Vận hành: 🔴 "Link 24 giờ: chưa giao tới khách 1" (link `priYghQy` còn `pending`).
- Web chạy thử bằng TestClient: 3 trang trả 200; khách không tồn tại trả 404; chưa đăng nhập thì chuyển `/login`; DB không bị ghi.
