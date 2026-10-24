# ADR-053 — Snapshot chính sách bất biến cho từng link, một công thức tiền

| | |
|---|---|
| Trạng thái | Accepted (PLAN-076), chưa triển khai production |
| Ngày | 2026-10-24 |
| Liên quan | ADR-045 (kiến trúc cashback), ADR-047 (dự phòng), ADR-048 (tỷ lệ chia), ADR-049 (sổ ví), ADR-050 (khoá tài chính) |

## Bối cảnh
- Báo giá link chốt tiền lúc tạo. Nhưng sổ ví tính lại khoản pending ở mỗi lần đồng bộ. Lần tính lại đó tra chính sách theo giờ tạo link, cộng `.env` hiện tại (tỷ lệ mặc định, dự phòng khác, đơn vị làm tròn), chứ không đọc chính sách đã dùng để báo giá.
- Báo giá lấy `now` lúc nhận tin, còn link ghi `created_at` lúc lưu. Link tạo sát mốc đổi chính sách có thể được báo theo chính sách cũ nhưng bị tính lại theo chính sách mới.
- Nhãn V1.2 (`…+r{id}+s{id}`) có sẵn định danh chính sách, nhưng không dùng.
- Mốc hiệu lực đã qua lúc bấm Áp dụng (tối đa khoảng 10 phút) vẫn được ghi, tức là hồi tố.
- Màn 🧮 Mô phỏng và màn Hạng tính `tỷ lệ × quỹ` bằng `share_cashback`, khác công thức V1.2 khách đang nhận.

## Quyết định
1. **Một lần chọn chính sách:** `admin_reserve.resolve_policy(now)` đọc `reserve_policies` và `share_policies` trong một transaction đọc, trả `pricing.PolicyResolution`. Báo giá và snapshot dùng chung kết quả này.
2. **Một công thức:** `pricing.cashback_for(commission, PolicyResolution)` là đường tính duy nhất cho báo giá, tính lại trên hoa hồng Shopee, màn Chính sách, Hạng, Thuế & phí, Mô phỏng và các bước xem trước.
   - V1.1 = `bps_floor(HH, tỷ lệ)`, cùng số với `quote_displayed_vnd`.
   - V1.2 = `estimate_cashback`: phí, thuế làm tròn lên; phần khách làm tròn xuống.
   - Không đổi số nào.
3. **Bảng `link_policy_snapshots`:**
   - Một link một dòng, chỉ thêm: trigger chặn UPDATE và DELETE.
   - Mỗi dòng ghi: phiên bản, công thức, quy tắc làm tròn, tỷ lệ, id chính sách chia và dự phòng, phí, thuế, dự phòng khác, đơn vị làm tròn, thời điểm chọn, hoa hồng và tiền hoàn đã báo, nguồn báo giá.
   - Ghi cùng transaction với `link_requests`: lỗi một bên thì không bên nào được lưu.
4. **Nguồn ưu tiên:** sổ ví tính lại theo snapshot.
   - Cột `estimate_policy` và `cashback_rate_percent` trên link giữ nguyên làm dữ liệu lịch sử. Test đối chiếu chúng phải khớp snapshot.
   - Không tra chính sách theo giờ, không đọc `.env` lúc tính lại.
5. **Link cũ:**
   - Dựng lại lúc khởi động: V1.1 theo tỷ lệ đã lưu; V1.2 theo `r{id}`/`s{id}` trong nhãn, không tra theo giờ.
   - Chỉ ghi `backfilled` khi tính lại ra **đúng** số đã báo cho khách.
   - Không khớp, thiếu số hoặc nhãn lạ thì ghi `unresolved`: cột chính sách để trống, giữ cách tính trước PLAN-076, hiện số đếm ở 📊 Lịch sử. Không gán chính sách mới.
   - Lúc tính ví chỉ đọc, không ghi, vì đang ở giữa transaction sổ ví.
6. **Không hồi tố:**
   - `effective_from` ghi mốc hiệu lực là `max(mốc chọn, lúc bấm Áp dụng)`.
   - `reserve_policies` và `share_policies` có trigger chặn sửa và xoá.
   - Hai chính sách cùng mốc: dòng `id` lớn hơn thắng, và id đó được ghi vào snapshot.

7. **Huỷ lịch hẹn (bổ sung):**
   - chỉ trước mốc hiệu lực;
   - không xoá dòng chính sách, mà ghi `policy_cancellations` (chỉ thêm, `UNIQUE`, CHECK `cancelled_at < effective_at`);
   - các truy vấn chọn chính sách bỏ qua dòng đã huỷ.
8. **«Admin còn»** = HH − khách − dự phòng phí − dự phòng thuế − dự phòng khác: một định nghĩa (`CashbackQuote.remainder_vnd`) cho mọi màn, cùng nghĩa với Thống kê.

## Hệ quả
- Đổi tỷ lệ, phí, thuế, `.env` hay bật V1.2 đều chỉ tác động link tạo sau mốc. Link cũ và khoản pending giữ chính sách gốc.
- Màn Mô phỏng ra cùng số với báo giá khách. Mô phỏng chỉ đọc.
- Snapshot không phải khoản phải trả. Tiền thật vẫn theo hoa hồng Shopee và khoá tài chính (ADR-050), không đổi.
- Đổi công thức trong tương lai phải thêm mã `formula` mới, không sửa mã cũ.
