# Báo cáo tiền Cashbot (cập nhật sau fix settlement)

Thời điểm: **20/11/2026 ~10:08 VN** · Nguồn: `data/cashback.sqlite`
Fix chi tiết: `SETTLEMENT-FIX-BATCH3-4-20261120.md` · Bản đọc sớm hơn (~09:01) giữ trong git history / file cũ nếu cần.

## Mốc thời gian

| Hạng mục | Từ | Đến | Số lượng |
|---|---|---|---|
| Link khách tạo | 21/10/2026 | 19/11/2026 | 246 |
| Đơn Shopee trong DB | 22/08/2026* | 18/11/2026 | 25 |
| Dòng hoàn khách (`cashback_entries`) | 24/10/2026 | 19/11/2026 | **21** |
| Kỳ thanh toán Shopee | 10–11/2026 | | **4** kỳ — **cả 4 MATCHED** |

\*Một số conversion sync sớm hơn / ngoài bot (fraud/null user).

## 1) Tiền Shopee đã chuyển về tài khoản shop (thật)

Tổng các kỳ `settlement_batches`:

| | VND |
|---|---:|
| Hoa hồng báo cáo | 97.854 |
| Phí | 958 |
| Thuế khấu trừ | 9.788 |
| **Shopee payout / NH nhận** | **87.108** |

Theo kỳ:

| Kỳ | Trạng thái | Báo cáo HH | NH nhận |
|---|---|---:|---:|
| 2026-10 | MATCHED | 25.371 | 22.585 |
| 2026-11 | MATCHED | 18.415 | 16.392 |
| 2026-11 | MATCHED | 43.413 | 38.646 |
| 2026-11 | MATCHED | 10.655 | 9.485 |

→ **Đã vào ngân hàng shop (đã khớp kỳ): 87.108 đ.**

## 2) Tiền hoàn ghi cho khách (sổ bot)

Trên 21 dòng `cashback_entries`:

| | VND |
|---|---:|
| **Tổng hoàn khách** | **120.903** |

Theo trạng thái ví (sau refresh):

| Status | Đơn | Hoàn khách |
|---|---:|---:|
| **holding** | 7 | 59.141 |
| **available** | 11 | **51.678** |
| **pending** | 3 | 10.084 |

| Ví khách | VND |
|---|---:|
| Có thể coi đã vào ví (`available`) | **51.678** |
| Yêu cầu rút đã tạo | **0** |
| Đã chi trả khách | **0** |

## 3) Theo tháng mua (purchase)

| Tháng | Đơn | Hoàn |
|---|---:|---:|
| 2026-10 | 6 | 25.931 |
| 2026-11 | 15 | 94.972 |

## Đọc nhanh cho anh

1. **Shop đã nhận từ Shopee (4 kỳ MATCHED):** **87.108 đ**.
2. **Cam kết hoàn khách trên sổ:** **120.903 đ**.
3. **Khách rút được ngay (available, chưa ai rút):** **51.678 đ** (↑ từ 25.910 sau khi mở khóa kỳ #3).
4. Kỳ #4 đã MATCHED; 2 đơn còn `holding` vì chưa đủ 7 ngày giữ (mở ~23–24/11).
5. Chưa có payout khách nào trong DB.
