# TASK-066 — Pilot P0 bridge repo / P1 native quote

| Thông tin | Nội dung |
|---|---|
| Mã công việc | TASK-066 |
| Trạng thái | **P0 live — quan sát; chờ Owner «làm P1» hoặc rollback** |
| Ưu tiên | Cao |
| Kế hoạch | [PLAN-180](../plans/active/PLAN-180-shopee-native-pilot-p0-p1.md) |
| Cha | PLAN-177 / TASK-063 (đã VERIFY smoke 1 SP; chưa bật khách) |
| Người thực hiện | Cursor khi Owner nói «làm P0» / «làm P1» |
| Phối hợp | Anti review vận hành nếu cần; Owner quyết rollback/giữ |

## Tóm tắt cho anh

**P0:** chỉ đổi cầu nối tạo link sang bản repo (chờ B). Số hoàn vẫn Product Data.
**P1:** (sau P0 ổn) bật lấy số từ Shopee trước, Product Data vẫn dự phòng.

Không nhảy cóc P1. Không tự bật khi chưa có lệnh anh.

## Acceptance

- [ ] Runbook `reports/plan177/PILOT-P0-P1-RUNBOOK.md` có lệnh bật/đo/rollback
- [ ] P0: health `toolsauto` + shortlink OK + PRIMARY vẫn `product_data`
- [ ] P1: có native thật + fallback PD/+ báo cáo 24–48h
- [ ] Mọi lúc rollback được &lt; 2 phút theo runbook
- [ ] Không mở Gate A / không đổi công thức tiền / không commit secrets
