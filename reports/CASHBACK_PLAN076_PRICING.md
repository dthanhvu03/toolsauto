# PLAN-076 — Cashback Pricing & Policy Consistency V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan076-pricing`, tách từ `main@a9ff267` (code production `6dc2dd1`) |
| Worktree | `/home/vu/toolsauto-cashback-pricing` |
| ADR | ADR-053 (mới) |
| Trạng thái | **Chủ bot duyệt phát hành 2026-10-24**, kèm yêu cầu làm mục 20.2 («Admin còn») và 20.3 (nhập số tự do, huỷ lịch hẹn). Hai mục đã làm (mục 21). Chi tiết triển khai: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN076.md` |

---

## 1. Tóm tắt

- **Không đổi công thức nào.** V1.1 vẫn là 70% hoa hồng. V1.2 vẫn trừ dự phòng phí 0,98% và thuế 10% rồi chia 70%. Mọi link cũ và cả 2 khoản pending thật giữ đúng số cũ (đã diễn tập trên bản sao DB production).
- **Một công thức cho mọi nơi:** báo giá khách, tính lại trên hoa hồng Shopee, màn Chính sách, Hạng, Thuế & phí, Mô phỏng và các bước xem trước đều gọi `pricing.cashback_for`. Màn admin không còn tự nhân tỷ lệ.
- **Mỗi link có snapshot chính sách bất biến** (bảng mới `link_policy_snapshots`, chỉ thêm, không sửa, không xoá). Từ nay, đổi tỷ lệ, phí, thuế, `.env` hay bật V1.2 đều chỉ tác động link tạo sau mốc hiệu lực.
- **Đã sửa 3 lỗi thật về tính nhất quán:**
  1. Sổ ví tính lại khoản pending theo chính sách tra theo giờ và theo `.env` hiện tại, nên có thể đổi tiền của link cũ.
  2. Link tạo sát mốc đổi chính sách có thể được báo theo chính sách cũ nhưng bị tính lại theo chính sách mới.
  3. Mốc hiệu lực đã qua lúc bấm Áp dụng vẫn được ghi, tức là hồi tố tới khoảng 10 phút.
- **🧮 Mô phỏng làm lại:**
  - cùng engine với khách: hoa hồng giả định 100.000đ thì khách nhận 62.314đ, đúng như thẻ link;
  - có cột so sánh V1.1/V1.2, lịch đã hẹn giờ, và hạng thành viên ở dạng bản nháp;
  - chỉ đọc.
- **Khoá tài chính, ví, payout, duyệt hoa hồng, đối soát:** không đổi gì.
- **490 test pass** (412 cũ + 78 mới), gồm cả phần bổ sung ở mục 21.

---

## 2. Baseline production (kiểm tra lại trước khi code)

| Mục | Giá trị |
|---|---|
| Git | `main@a9ff267` (code `6dc2dd1`), sạch |
| Process | PID 604968, khởi động 03:57:20 UTC, cwd `/home/vu/toolsauto` |
| Calculator | `CASHBACK_ESTIMATE_POLICY=v1.2`, `CASHBACK_RATE_PERCENT=70`. Không đặt phí/thuế/dự phòng khác/làm tròn trong `.env`, nên dùng mặc định trong code: 98 bps, 1.000 bps, 0đ, 1đ. Các mặc định này không đổi từ khi thêm (`4c2a9c0`) |
| Chính sách chia | `share_policies` trống: 70% mặc định cấu hình |
| Chính sách dự phòng | `reserve_policies` #1: Cá nhân, phí 0,98%, thuế 10%, hiệu lực 2026-10-23T09:55:51Z |
| Link | 31 link đã tạo: 27 V1.1 (`estimate_policy` NULL, 70%), 21/10 → 23/10 09:17; 4 V1.2 `v1.2-reserve-2026-10-23+r1`, 24/10. 1 link bị từ chối |
| Sổ ví | 2 khoản `pending`, đều thuộc link V1.1: 12.157đ (HH 17.368) và 960đ (HH 1.372) |
| Hoa hồng | 2 đơn bot PENDING / NOT_VERIFIED, 1 đơn ngoài bot FRAUD |
| Khoá | 4 trigger `financial_lock_*`; không có bảng mở khoá; ví tắt; 0 available; 0 payout |
| Test | **412 passed** |

---

## 3. Đường đi công thức: trước và sau

### Trước

```
Product Data → HH ước tính ─┬─ V1.1: money.estimated_cashback(HH, .env rate)
                            └─ V1.2: active_reserve(now) + active_share(now)   ← hai lần đọc riêng
                                     + .env (dự phòng khác, làm tròn)
                                     → estimate_cashback → thẻ link, link_requests

Conversion HH → sổ ví (mỗi lần đồng bộ) → _real_cashback:
     active_reserve(link.created_at), active_share(link.created_at)   ← tra theo giờ ghi link, không theo nhãn r/s
     + .env hiện tại; V1.1 thiếu tỷ lệ thì lấy .env                     ← có thể khác lúc báo giá
     → cập nhật cashback_vnd của khoản pending

Admin:
  🧮 Mô phỏng, 🎖️ Hạng: share_cashback(quỹ, %)       ← công thức riêng, không trừ dự phòng V1.2
  💰 Chính sách V1.1: share_cashback; V1.2 và 🧾 Thuế & phí: estimate_cashback
```

### Sau

```
Product Data → HH ước tính → resolve_policy(now)   (một transaction đọc, ra PolicyResolution)
                           → cashback_for(HH, resolution) → thẻ link
                           → link_requests + link_policy_snapshots   (cùng một transaction)

Conversion HH → sổ ví → _real_cashback → snapshot của link (theo matched_link_id)
                                       → cashback_for(HH, snapshot)
     (link chưa có dòng snapshot: dựng tạm trong bộ nhớ theo đúng quy tắc backfill, không ghi giữa transaction sổ ví)

Admin (Chính sách, Hạng, Thuế & phí, Mô phỏng, các bước xem trước) → resolve_policy → cashback_for
```

### Mỗi thứ lấy từ đâu (sau PLAN-076)

| Nơi | `.env` | DB chính sách | Theo thời gian | Snapshot | Công thức riêng |
|---|---|---|---|---|---|
| Báo giá link mới | mặc định khi chưa có dòng chính sách; dự phòng khác, làm tròn | `reserve_policies`, `share_policies` (V1.2) | có, theo lúc nhận tin | ghi | không |
| Tính lại khoản ví | không | không | không | đọc | không |
| Màn admin, mô phỏng | như báo giá | như báo giá | như báo giá | đọc (độ phủ) | không |
| Link cũ chưa có snapshot | mặc định code khi nhãn không có `r`/`s` | đọc **theo id** trong nhãn | chỉ phần admin chịu của V1.1 (như code cũ) | ghi một lần lúc khởi động | không |

**Bốn loại phép tính** (mục B1 của PLAN):

| Phép tính | Đường đi |
|---|---|
| Báo giá ước tính | `cashback_for(HH ước tính, chính sách lúc báo giá)` |
| Tính trên hoa hồng Conversion Report | `cashback_for(HH Shopee, snapshot)` |
| Tính trên hoa hồng đã duyệt | chưa có: APPROVED vẫn bị chặn (PLAN-074) |
| Quyết toán theo chứng từ | `calculator.final_cashback`, `settle_commission`: không đổi, không nối vào chi trả |

---

## 4. Công thức V1.1 (giữ nguyên)

```
khách = ⌊HH × tỷ lệ⌋                    (tỷ lệ chia theo link; 70%)
phí dự phòng = ⌈HH × 0,98%⌉, thuế dự phòng = ⌈HH × 10%⌉   (admin chịu, không trừ khi chia)
còn lại = HH − khách − phí − thuế
```

- `cashback_for` dùng `bps_floor(HH, tỷ lệ × 100)`. Kết quả bằng `quote_displayed_vnd` (`(HH × %) // 100`) với mọi HH nguyên và mọi tỷ lệ % nguyên (test 01 thử 7 tỷ lệ × 9 mức HH).
- Ví dụ đơn thật: HH 17.368 → khách 12.157, phí 171, thuế 1.737.

## 5. Công thức V1.2 (giữ nguyên)

```
phí = ⌈HH × phí%⌉, thuế = ⌈HH × thuế%⌉, khác = dự phòng khác (0đ)
quỹ chia = max(0, HH − phí − thuế − khác)
khách = làm_tròn_xuống(⌊quỹ × tỷ lệ⌋, đơn vị) (đơn vị 1đ)
còn lại = HH − khách − phí − thuế − khác
```

- HH 100.000 → phí 980, thuế 10.000, quỹ 89.020, **khách 62.314**, còn lại 26.706. Khớp ví dụ trong PLAN, được tính bằng engine chứ không hardcode.
- Dự phòng chỉ là mức ước tính, không phải nghĩa vụ thuế. Không trừ hai lần: V1.1 không trừ khi chia; V1.2 trừ đúng một lần trước khi chia.
- Không dùng float: tiền và bps là số nguyên. `cashback_for(100000.0, …)` bị từ chối (test 10).

---

## 6. Cấu trúc snapshot (`link_policy_snapshots`, ADR-053)

| Cột | Ý nghĩa |
|---|---|
| `link_id` (PK) | link, một dòng mỗi link |
| `schema_version` | 1 |
| `provenance` | `captured` (ghi lúc tạo link), `backfilled` (dựng lại và khớp số đã báo), `unresolved` |
| `policy_label` | nhãn y như trên link: `v1.1:70`, `v1.2-reserve-2026-10-23+r1+s2` |
| `pricing_version`, `formula`, `rounding` | `v1.1`/`v1.2`; `gross_x_share_floor`/`reserve_ceil_then_share_floor`; `reserve_ceil_vnd_share_floor_vnd` |
| `share_bps`, `share_policy_id` | tỷ lệ chia và id `share_policies`. NULL = mặc định cấu hình |
| `reserve_policy_id`, `fee_bps`, `tax_reserve_bps` | dự phòng áp dụng |
| `other_reserve_vnd`, `rounding_unit` | tham số V1.2 khác |
| `resolved_at` | lúc chọn chính sách (lúc báo giá), không phải lúc ghi link |
| `quote_commission_vnd`, `quote_cashback_vnd`, `quote_source` | số đã báo và nguồn (`product_data`) |
| `note`, `created_at` | lý do (backfill/unresolved), giờ ghi |

**Ràng buộc:**
- trigger `link_policy_snapshots_no_update` và `link_policy_snapshots_no_delete`;
- CHECK: mọi dòng không phải `unresolved` phải đủ tham số chính sách;
- ghi cùng transaction với `link_requests`: snapshot lỗi thì link cũng không được lưu (test riêng).

**Nguồn ưu tiên:**
- Sổ ví chỉ đọc snapshot.
- Cột `estimate_policy` và `cashback_rate_percent` trên link giữ nguyên như dữ liệu lịch sử. Diễn tập xác nhận 31/31 link khớp snapshot.
- `reserve_policies` và `share_policies` cũng thành chỉ thêm (trigger chặn sửa và xoá); trước đây chỉ do code không sửa.

---

## 7. Xử lý link cũ

Lúc khởi động, bot dựng snapshot cho link đã tạo mà chưa có dòng:

| Loại | Cách dựng | Điều kiện để ghi `backfilled` |
|---|---|---|
| V1.1 (`estimate_policy` NULL) | tỷ lệ = `cashback_rate_percent` đã lưu. Phí, thuế admin chịu: mức có hiệu lực lúc tạo link, đúng như code cũ | `⌊HH ước tính × tỷ lệ⌋` = số đã báo |
| V1.2 `…+r{id}+s{id}` | đọc **đúng** dòng `r{id}`, `s{id}` theo id, không tra theo giờ; không có `s` thì tỷ lệ = tỷ lệ đã lưu trên link | dòng chính sách tồn tại và hiệu lực không muộn hơn giờ tạo link; tỷ lệ khớp; `cashback_for` = số đã báo; nhãn dựng lại = nhãn đã lưu |

Không thoả thì ghi **`unresolved`**:
- cột chính sách để trống, kèm lý do (thiếu số, nhãn lạ, không thấy chính sách, tính lại không ra số đã báo);
- **không gán chính sách mới, không sửa `link_requests`**;
- khoản ví của link đó giữ cách tính trước PLAN-076;
- màn 📊 Lịch sử hiện "chưa xác định: N".

Lúc tính ví, nếu link chưa có dòng snapshot (ví dụ backfill khởi động lỗi), bot dựng tạm trong bộ nhớ theo cùng quy tắc, không ghi.

**Trên bản sao DB production:**
- 27 V1.1 + 4 V1.2 = **31 backfilled, 0 unresolved**;
- 27 link V1.1 đều trước mốc r1 nên `reserve_policy_id` NULL (mặc định 0,98% / 10%); 4 link V1.2 trỏ đúng r1;
- **0 lệch** giữa số đã báo và snapshot.

---

## 8. Thời điểm hiệu lực

| Quy tắc | Cách làm |
|---|---|
| Không hồi tố | `effective_from` ghi `max(mốc đã chọn, lúc bấm Áp dụng)`. Ví dụ: chọn 16:05, bấm lúc 16:08 thì ghi 16:08, không phải 16:05. Thông báo đổi thành "hiệu lực ngay bây giờ" |
| Không sửa chính sách cũ | trigger chặn UPDATE và DELETE trên `share_policies` / `reserve_policies` |
| Múi giờ | lưu UTC `YYYY-MM-DDTHH:MM:SSZ`, admin nhập giờ Việt Nam (như trước) |
| Đúng giây hiệu lực | link chọn lúc `≥ mốc` dùng chính sách mới (`effective_at <= now`) |
| Hai chính sách cùng mốc | dòng `id` lớn hơn thắng; snapshot ghi đúng id đó (`+s{id}`) |
| Link sát mốc | quote và snapshot dùng chung một `PolicyResolution` chọn lúc nhận tin. Link báo lúc 16:00:00 theo 70%, chính sách 65% hiệu lực 16:00:01, link ghi sau đó: tiền vẫn theo 70% (test 25) |
| Hẹn giờ, restart | chưa tới mốc thì link vẫn theo chính sách cũ. Restart không đổi gì; link sau mốc dùng chính sách mới (test 27) |
| Huỷ bản nháp | như cũ: bản nháp huỷ không ghi chính sách. Chưa có nút huỷ chính sách đã hẹn giờ (xem mục 18) |

---

## 9. Admin Simulator (🧮 Mô phỏng)

Chỉ đọc. Không ghi bảng nào: test so số dòng 14 bảng trước và sau khi bấm mọi nút.

**Hiển thị:**
- Calculator và báo giá đang chạy, tỷ lệ chia, phí dự phòng, thuế dự phòng.
- Bảng hai cột cùng một hoa hồng giả định: **cột công thức đang báo giá** và **cột so sánh** (V1.2 đang chạy thì so với V1.1, và ngược lại). Các dòng: hoa hồng, dự phòng phí, dự phòng thuế, quỹ chia, khách nhận, còn lại; cuối bảng là chênh lệch khách nhận.
- 🗓️ **Đã hẹn giờ**: tối đa 3 mốc sắp tới, mỗi mốc tính bằng chính sách sẽ có hiệu lực lúc đó.
- 🟡 **Hạng thành viên**: bản nháp, chưa bật. Dùng cùng engine, chỉ thay tỷ lệ.
- **Nút chọn hoa hồng giả định:** 10k, 50k, 100k, 500k (`c:sim:<số>`, chỉ nhận đúng 4 giá trị).

**Chế độ:**
- Hỗ trợ: chính sách hiện hành, chính sách đã hẹn giờ, so sánh V1.1/V1.2.
- Chưa có trong V1: mô phỏng chính sách lịch sử, nhập số tự do.

---

## 10. Nội dung cho khách

| Trang | Thay đổi |
|---|---|
| `/cachtinh` (V1.2) | "Số dự kiến đã trừ phí và thuế liên quan" → "Số dự kiến **đã trừ trước dự phòng phí và thuế**. Đây là mức bot tự đặt để ước tính, **không phải số thuế bạn phải nộp**" |
| `/cachtinh` (cả hai) | thêm "• Mỗi link giữ cách tính lúc bot tạo link. Bot đổi cách tính thì chỉ áp dụng cho link tạo sau đó." Dòng ⓘ: "Bot chưa theo dõi đơn và chưa chi trả" → "**Ví hoàn tiền chưa mở, bot chưa chi trả.**" (bot đã theo dõi đơn từ PLAN-066) |
| Trang chủ `/start`, `/help` | "…chưa theo dõi đơn và chưa chi trả" → "Số hoàn là ước tính. Ví hoàn tiền chưa mở, bot chưa chi trả." |
| Mô tả bot (màn trước khi bấm Start) | cùng ý trên. Bot gửi lại mô tả lúc khởi động như mọi lần |
| Thẻ link, `/huongdan`, `/dieukien`, `/hang` | không đổi. Thẻ link vẫn hiện "khoảng … dự kiến", số lấy từ đúng phép tính ghi vào snapshot |

- Vẫn **không hiện %**, phí hay thuế cho khách (quyết định ngày 23/10).
- Link cũ gửi lại cùng update vẫn hiện số đã báo, không tính lại.

---

## 11. UI: trước và sau

**🧮 Mô phỏng (V1.2 đang chạy):**

```
TRƯỚC                                       SAU
🔵 MÔ PHỎNG THEO HẠNG                       🔵 MÔ PHỎNG · hoa hồng giả định 100.000đ
Quỹ 100.000đ                                                 V1.2    V1.1
• Đồng 60%: hoàn 60.000đ · còn 40.000đ      Hoa hồng      100.000 100.000
• Bạc 65%: hoàn 65.000đ · còn 35.000đ       Dự phòng phí     -980    -980
• Vàng 70%: hoàn 70.000đ · còn 30.000đ      Dự phòng thuế -10.000 -10.000
                                             Quỹ chia       89.020       —
(khách thật nhận 62.314đ, admin thấy         Khách nhận     62.314  70.000
 70.000đ)                                    Còn lại        26.706  19.020
                                             • Khách nhận V1.2 so với V1.1: -7.686đ
                                             🟡 HẠNG THÀNH VIÊN · bản nháp, chưa bật
                                             • Đồng 60%: hoàn 53.412đ · còn 35.608đ
                                             …
                                             [10k] [50k] [• 100k] [500k]
```

**Các màn khác:**
- **🎖️ Hạng thành viên**: mô phỏng chuyển sang công thức đang báo giá. Đang chạy V1.2: "Đồng 60%: hoàn 53.412đ · còn 35.608đ"; trước đây là 60.000 / 40.000.
- **Xem trước khi đổi hạng**: cũng tính theo công thức đang báo giá.
- **💰 Chính sách (V1.1)**: thêm dòng dự phòng phí và thuế "admin chịu". "Phần còn lại" thành phần dư sau dự phòng (19.020đ thay vì 30.000đ), cùng nghĩa với "Admin còn" ở 📈 Thống kê.
- **📊 Lịch sử**: thêm khối 🧾 **Phiên bản chính sách**, gồm:
  - từng phiên bản tỷ lệ chia và dự phòng, kèm mốc và trạng thái 🟢 ĐANG ÁP DỤNG / 🗓️ ĐÃ HẸN GIỜ / ⚪ ĐÃ THAY; chưa có dòng nào thì hiện "Mặc định cấu hình";
  - dòng "Link đã chốt chính sách: N · chưa xác định: M".
- **Thuế & phí**: số giữ nguyên. Ở V1.1 không còn dòng "Quỹ phân chia", thay bằng "V1.1 chia trên hoa hồng gốc, admin chịu dự phòng".
- **Không đổi:** 📝 Nội dung lệnh (vẫn là chữ cố định, không phải CMS). Hạng thành viên vẫn ghi "Chưa bật". Không thêm nút ghi nào.

---

## 12. Files changed

| File | Thay đổi |
|---|---|
| `cashback_bot/pricing.py` | `PolicyResolution`, `CashbackQuote`, `cashback_for`, mã công thức và làm tròn |
| `cashback_bot/policy_snapshot.py` (mới) | ghi, đọc, dựng lại snapshot; backfill; độ phủ |
| `cashback_bot/admin_reserve.py` | `resolve_policy` (một transaction đọc), `effective_from` |
| `cashback_bot/service.py` | báo giá và snapshot dùng chung một lần chọn; `_real_cashback` theo snapshot; cách cũ còn lại trong `_legacy_cashback` cho link `unresolved`; backfill lúc khởi động |
| `cashback_bot/db.py` | bảng `link_policy_snapshots` và 2 trigger; `insert_created(..., snapshot)` ghi cùng transaction |
| `cashback_bot/admin_policy.py` | mọi màn tiền dùng `resolve_policy` + `cashback_for`; màn Mô phỏng mới; `c:sim:*`; phiên bản chính sách; chặn hồi tố khi Áp dụng |
| `cashback_bot/admin_ui.py` | bảng mô phỏng, nút chọn hoa hồng, khối phiên bản chính sách, chữ V1.1 ở Chính sách |
| `cashback_bot/messages.py` | `/cachtinh`, trang chủ, mô tả bot |
| `migrations/005_reserve_policies.sql`, `006_share_policies.sql` | trigger chỉ thêm |
| `tests/test_cashback_pricing_policy.py` (mới) | 44 test |
| `tests/test_cashback_admin.py`, `_admin_ui_ux.py`, `_plan060.py` | cập nhật theo API và chữ mới. Mỗi chỗ đổi đều đúng chủ đích: «còn» sau dự phòng, nút mô phỏng, câu dự phòng |
| `agents/decisions/ADR-053-link-policy-snapshot.md`, `agents/plans/active/PLAN-076-…md` | tài liệu |

---

## 13. Migration evidence

**Cơ chế:**
- Bảng và trigger snapshot tạo trong `repo.migrate()` bằng `IF NOT EXISTS`.
- Trigger của hai bảng chính sách tạo cùng lúc với bảng, mỗi lần mở kết nối admin.
- Backfill chạy khi `CashbackService` khởi động. Chỉ ghi vào bảng mới và bỏ qua link đã có dòng.

**Diễn tập trên bản sao DB production** (Backup API, 0600, đã xoá). Chạy `migrate()` 2 lần, khởi động service 2 lần, một lần làm mới ví:

| Kiểm tra | Kết quả |
|---|---|
| Bảng thêm | chỉ `link_policy_snapshots` |
| Bảng cũ (26) | đối chiếu bằng hash nội dung. Chỉ `cashback_entries` đổi, và chỉ ở cột `updated_at` do làm mới ví (code cũ cũng ghi cột này) |
| Snapshot | 27 `backfilled` v1.1 + 4 `backfilled` v1.2; 0 `unresolved`; chạy lại không ghi thêm |
| Quote ↔ snapshot | 0 lệch (số và nhãn) trên 31 link |
| Khoản pending | `246425365260309`: 12.157 / 171 / 1.737, `v1.1:70`; `246419317220025`: 960 / 14 / 138, `v1.1:70`. Giống hệt trước |
| Conversion, đối soát, chính sách | không đổi (hash) |
| Trigger | 4 `financial_lock_*` + 3 settlement + 2 snapshot |
| Ví | tắt, 2 lý do khoá; 0 available; 0 payout |
| `integrity_check` | ok |

---

## 14. Regression

- `tests/test_cashback_*.py`: **456 passed** (412 + 44), khoảng 80 giây. Ruff sạch trên mọi file thay đổi.
  - Hai cảnh báo ruff cũ ở `tests/test_cashback_admin.py` và `test_cashback_admin_ui_ux.py` có sẵn trên `main`, không do PLAN này.
- Không test nào gọi Shopee hay Telegram thật: dùng `FakeClient`, không mở mạng.
- Các bộ test của PLAN-073/074/075 vẫn pass nguyên vẹn: cô lập update, log an toàn, backup, duyệt hoa hồng, đối soát, Sub ID, đồng bộ Shopee, menu admin.

| Nhóm PLAN | Test mới (`test_cashback_pricing_policy.py`) |
|---|---|
| A. Pricing (1–10) | V1.1 bằng công thức cũ ở mọi tỷ lệ; V1.2 ra 62.314; mô phỏng bằng quote thật ở 4 mức; dự phòng 0, phí 0; HH 0 và rất nhỏ; giá trị lớn; làm tròn; chặn float; nhãn |
| B. Snapshot (11–20) | link mới ghi đủ trường; đổi tỷ lệ hoặc phí/thuế sau link không đổi tiền; V1.1 không thành V1.2; đọc `r{id}` theo id; link thiếu dữ liệu `unresolved`; mẫu production; restart; gửi lại cùng update; đơn về sau 40 ngày; bảng chỉ thêm; ghi lỗi thì không lưu link |
| C. Effective time (21–27) | chưa tới giờ / đúng giây; hai chính sách cùng mốc; chặn hồi tố (chia và dự phòng); link sát mốc; quote = snapshot ở mọi link; restart có lịch hẹn; một transaction đọc |
| D. Admin (28–34) | không có công thức riêng trong `admin_policy` và `_real_cashback`; mô phỏng chỉ đọc; so sánh V1.1/V1.2; lịch hẹn; bản nháp hạng không thành đang áp dụng, Membership tắt; lịch sử phiên bản thật; callback sai quyền hoặc sai số bị từ chối; màn hạng dùng engine |
| E. Khách (35–40) | `/cachtinh` theo calculator; thẻ link = snapshot; không hứa, không gọi dự phòng là thuế, không gọi quote là số dư |
| F. Tài chính (41–47) | ví tắt, bật ví bị chặn, 0 available, 0 payout, trigger còn, conversion và đối soát không đổi; 2 khoản pending thật giữ số |

---

## 15. Financial Lock verification

- Không sửa `payout_gate.py`, `wallet.py`, `commission_validation.py`, `settlement.py` hay 4 trigger `financial_lock_*`.
- Snapshot, backfill, mô phỏng: không đụng `validation_status`, `settlement_status`, `settlement_*`, `shopee_conversion_changes`, trạng thái sổ ví hay payout.
- Đã kiểm tra trong test và trên bản sao DB: không có APPROVED, SETTLED hay `available` mới, không có payout; nút bật ví vẫn trả `PayoutBlocked`.
- Mô phỏng không lưu số nào thành khoản nợ hay số dư.

---

## 16. Kế hoạch triển khai (chỉ làm khi chủ bot duyệt)

1. Backup bằng Backup API: `.venv/bin/python -m cashback_bot.backup`, rồi `verify_backup`.
2. Trên `main`: `git merge --ff-only cursor/cashback-plan076-pricing`, chạy toàn bộ test, push.
3. Chủ bot restart:
   ```
   kill -TERM <PID>; cd /home/vu/toolsauto && umask 077 && setsid nohup .venv/bin/python -m cashback_bot >> logs/cashback_bot.log 2>&1 &
   ```
4. Kiểm tra sau triển khai, DB ở chế độ chỉ đọc:
   - process và log: 0 ERROR, có dòng `snapshot chính sách link cũ backfilled=31 unresolved=0`;
   - `link_policy_snapshots` có 31 dòng, 0 lệch với link;
   - 2 khoản pending giữ 12.157 / 960;
   - khoá tài chính còn nguyên, 0 available, 0 payout;
   - dựng thử màn Mô phỏng, Lịch sử, `/cachtinh` trên bản sao.
5. Chủ bot tự xem: /admin → 🧮 Mô phỏng, 📊 Lịch sử; gửi một link thử, kiểm tra số trên thẻ.

**Thay đổi khách thấy được:**
- câu chữ `/cachtinh`, trang chủ, mô tả bot;
- **không đổi số tiền** nào trên link mới hay link cũ.

---

## 17. Rollback

- **Code:** `git revert` commit PLAN-076 rồi restart.
  - Bảng `link_policy_snapshots` để lại vô hại: code cũ không đọc.
  - Trigger chỉ-thêm của hai bảng chính sách cũng vô hại: code cũ không sửa hay xoá dòng chính sách.
  - Sau rollback, sổ ví quay về cách tra theo giờ như trước, và lỗi hồi tố quay lại.
- **Không restore DB** để rollback code: sẽ mất link, conversion và lịch sử phát sinh sau triển khai. Chỉ restore khi DB hỏng, theo `cashback_bot/BACKUP.md`.

---

## 18. Rủi ro còn lại

- **Link `unresolved`**: hiện 0. Nếu sau này có, khoản ví của link đó giữ cách tính cũ (tra theo giờ). Màn Lịch sử báo số đếm để admin xem tay.
- **Backfill V1.2 dùng mặc định `.env` hiện tại** cho dự phòng khác (0đ) và đơn vị làm tròn (1đ). Đúng vì các giá trị này chưa từng đổi, và được kiểm chứng bằng việc tính ra đúng số đã báo. Nếu chủ bot đổi chúng trước khi triển khai, link V1.2 cũ sẽ thành `unresolved` thay vì bị gán sai.
- **Phần admin chịu (phí, thuế) của link V1.1 dựng lại theo mức có hiệu lực lúc tạo link**, như code cũ. Không ảnh hưởng tiền khách.
- **Đổi `CASHBACK_RATE_PERCENT` trong `.env`** vẫn đổi tỷ lệ của link mới (V1.1, và V1.2 khi chưa có `share_policies`). Đây là chủ đích; link cũ không bị ảnh hưởng nữa.
- **Chưa có nút huỷ chính sách đã hẹn giờ.** Muốn bỏ một lịch hẹn thì phải áp dụng một chính sách mới có mốc sau đó.
- **Mô phỏng chỉ có 4 mức hoa hồng**, chưa nhập số tự do, chưa mô phỏng chính sách lịch sử.
- **«Còn lại» đổi nghĩa** ở màn Hạng và màn Chính sách (V1.1): nay là phần dư sau dự phòng, cùng nghĩa "Admin còn" ở Thống kê. Admin quen số cũ có thể thấy lạ.
- **📝 Nội dung lệnh** vẫn là chữ cố định trong mã nguồn, không phải CMS.

---

## 19. Release gates

| Gate | Kết luận | Lý do |
|---|---|---|
| Pricing Engine Consistency | **GO** | một `cashback_for`. Test chặn công thức riêng trong `admin_policy` và `_real_cashback` |
| V1.1 Compatibility | **GO** | cùng số với `quote_displayed_vnd`; 27 link và 2 khoản pending thật giữ số |
| V1.2 Compatibility | **GO** | `estimate_cashback` không đổi; 4 link thật khớp; ví dụ 62.314 |
| Historical Snapshot | **GO** | 31/31 backfilled có kiểm chứng; bảng chỉ thêm; `unresolved` không gán chính sách mới |
| Policy Effective Time | **GO** | một lần chọn cho quote và snapshot; chặn hồi tố; cùng mốc thì id lớn thắng |
| Admin Simulator | **GO** | cùng engine, chỉ đọc, so sánh V1.1/V1.2, có lịch hẹn. V1 chưa có nhập số tự do |
| Customer Messaging | **GO** | `/cachtinh` theo calculator, không gọi dự phòng là thuế, không hứa, không lộ % |
| Migration | **GO** | idempotent, chỉ thêm; diễn tập trên bản sao thật, hash bảng cũ không đổi |
| Regression | **GO** | 456/456 |
| Financial Lock | **GO** | không đổi; đã kiểm tra trong test và trên bản sao |
| Production Deployment | **NOT AUTHORIZED** | chờ chủ bot duyệt phát hành riêng |
| Wallet Activation | **NOT AUTHORIZED** | |
| Payout | **NOT AUTHORIZED** | |

---

## 20. Quyết định của chủ bot

1. **Phát hành PLAN-076**: đã duyệt ngày 2026-10-24.
2. **«Còn lại»**: duyệt làm cho đúng nghiệp vụ. Đã làm thành «Admin còn», xem mục 21.1.
3. **Nhập số tự do ở Mô phỏng và huỷ chính sách đã hẹn giờ**: duyệt làm. Xem mục 21.2 và 21.3.
4. Việc từ trước, vẫn chờ:
   - mẫu chứng từ thật (báo cáo Thanh toán, sao kê, báo cáo Xác thực) cho parser và APPROVED có chứng từ;
   - thuế người nhận;
   - chính sách thu hồi;
   - nơi lưu backup ngoài máy.

---

## 21. Bổ sung sau khi chủ bot duyệt (mục 20.2, 20.3)

### 21.1 «Admin còn»: một định nghĩa
- Trên mọi màn tiền (Chính sách, Hạng, xem trước đổi hạng, xem trước đổi tỷ lệ, Mô phỏng), «còn lại», «còn», «phần giữ lại» đổi thành **«Admin còn»** (ở màn Chính sách và bước xem trước đổi tỷ lệ là «Admin còn (sau dự phòng)»).
- Định nghĩa: **hoa hồng − khách nhận − dự phòng phí − dự phòng thuế** (− dự phòng khác nếu có). Cùng nghĩa với «Admin còn» ở 📈 Thống kê.
- Mỗi màn ghi cùng một câu: «Là số ước tính, chưa trừ phí và thuế thực tế theo chứng từ.»
- Công thức không đổi. «70% phần còn lại sau dự phòng» trong mô tả V1.2 giữ nguyên: đó là cơ sở chia (quỹ chia), không phải phần của admin.

### 21.2 Mô phỏng: nhập hoa hồng tự do
- Nút **✏️ Nhập số khác** (`c:sim:input`). Admin gõ `150000`, `150.000`, `150k`, `1,5tr`, `1.25 triệu`…
  - Số nguyên VND, đọc không qua float; dấu `.` / `,` theo nhóm 3 là ngăn nghìn.
  - Chỉ nhận từ 1đ tới 100.000.000đ (một đơn).
- **Trạng thái chờ nhập nằm trong RAM**, hết hạn sau 10 phút, **không ghi DB**: test so số dòng 14 bảng trước và sau.
- Thôi chờ khi: bấm nút khác, gõ lệnh `/…`, dán link Shopee (link được tạo như thường), hoặc đã tính xong. Số sai thì hỏi lại, kèm ví dụ.
- Kết quả dùng đúng `_simulation`: cùng bảng V1.1/V1.2, lịch hẹn, hạng.

### 21.3 Huỷ chính sách đã hẹn giờ
- **Nghiệp vụ:** chỉ huỷ được khi **chưa tới mốc hiệu lực**, tức là chính sách chưa từng áp cho link nào. Đã tới mốc thì không huỷ; muốn đổi thì áp dụng mức mới (không hồi tố).
- **Dữ liệu:**
  - không xoá dòng `share_policies` / `reserve_policies` (vẫn chỉ thêm);
  - ghi một dòng vào bảng mới `policy_cancellations` (`migrations/008_policy_cancellations.sql`), cũng chỉ thêm;
  - `UNIQUE(policy_kind, policy_id)`;
  - **CHECK `cancelled_at < effective_at`**: DB tự chặn huỷ hồi tố;
  - ghi trong `BEGIN IMMEDIATE`, kèm audit `share_cancel` / `reserve_cancel`.
- **Tác động:**
  - `active_share`, `active_reserve`, `upcoming_*` bỏ qua chính sách đã huỷ, nên báo giá, mô phỏng và Lịch sử đều thấy;
  - backfill không nhận nhãn trỏ tới chính sách đã huỷ (thành `unresolved`);
  - snapshot và khoản ví đã có không đổi.
- **Giao diện:**
  - màn 💰 Chính sách và 🧾 Thuế & phí có nút **🗑 Huỷ lịch #id** cho từng lịch sắp tới;
  - bấm nút → màn hỏi lại → **✅ Huỷ lịch này** / **◀️ Giữ lịch**;
  - xong thì báo: từ mốc đó link mới vẫn theo chính sách nào;
  - 📊 Lịch sử ghi «✖️ ĐÃ HUỶ TRƯỚC MỐC» và dòng audit.
- **An toàn:**
  - chỉ admin trong chat riêng;
  - callback sai định dạng bị từ chối; id không có → "Không thấy lịch hẹn";
  - huỷ lại → "Đã huỷ trước đó";
  - quá mốc → "Đã có hiệu lực, không huỷ được".

### 21.4 Bằng chứng
- Test: **490 passed** (456 + 34 test bổ sung), ruff sạch.
- Diễn tập lại trên bản sao DB production (0600, đã xoá):
  - chỉ thêm `link_policy_snapshots` và `policy_cancellations`;
  - bảng cũ không đổi, trừ `updated_at` của sổ ví;
  - 31/31 backfilled, 0 lệch;
  - 2 khoản pending giữ 12.157đ / 960đ;
  - đủ trigger chỉ-thêm; khoá tài chính còn nguyên; integrity ok.
- Mô phỏng nhập `17.368` ra cột V1.1 khách 12.157đ, phí 171, thuế 1.737, đúng đơn thật.

---

## Câu hỏi nghiệm thu

**Q1. Cùng hoa hồng giả định, cùng chính sách, Admin và khách có ra cùng số không?**
**Có.**
- Cả hai gọi `cashback_for` với cùng `PolicyResolution`.
- Test 03 tạo link thật (HH 20.000 → 12.462đ) và kiểm tra 4 mức của màn Mô phỏng ra đúng số `cashback_for`.
- Hoa hồng 100.000đ cho 62.314đ ở cả hai phía.

**Q2. Link V1.1 cũ có thể bị tính lại thành V1.2 khi Admin thay chính sách không?**
**Không.**
- Snapshot ghi `pricing_version = v1.1` và chỉ thêm.
- Test 13 bật V1.2 rồi restart: đơn trên link V1.1 vẫn ra 12.157đ, nhãn `v1.1:70`.

**Q3. Admin đổi 70% thành 65%, link cũ có giữ tỷ lệ cũ không?**
**Có.**
- Snapshot giữ `share_bps = 7000`.
- Test 12 và test 20 (đơn về sau 40 ngày) cho khoản ví theo 70%.
- Link mới mới dùng 65%.

**Q4. Admin đổi dự phòng thuế hoặc phí, khoản cashback của link đã tạo có đổi không?**
**Không.** Test 16 đổi thuế 10% thành 1,5%: khoản của link cũ giữ nguyên; link mới ra 13.652đ.

**Q5. Link lịch sử thiếu snapshot xử lý thế nào? Có tự gán chính sách mới không?**
**Không gán chính sách mới.**
- Bot dựng lại snapshot và chỉ ghi `backfilled` khi tính ra đúng số đã báo. Với `r{id}`/`s{id}`, bot đọc theo id.
- Không được thì ghi `unresolved`, để trống chính sách, không sửa link, và giữ cách tính cũ. Màn Lịch sử hiện số đếm.
- Production: 31/31 backfilled, 0 unresolved.

**Q6. `/cachtinh` có giải thích đúng calculator đang phục vụ link mới không?**
**Có.**
- V1.2: "đã trừ trước dự phòng phí và thuế … không phải số thuế bạn phải nộp".
- V1.1: "chưa trừ thuế và phí", không nhắc dự phòng.
- Cả hai: "Mỗi link giữ cách tính lúc bot tạo link". Không hiện %.

**Q7. Có đường nào từ Admin Simulator tạo số dư, khoản phải trả hay payout không?**
**Không.**
- Màn Mô phỏng chỉ đọc. Callback chỉ nhận 4 mức hoa hồng. Không có nút ghi.
- Test 29 so số dòng 14 bảng trước và sau: không đổi.
- Khoá tài chính không đổi.

**Q8. Có thay đổi nào ảnh hưởng 2 đơn thật đang chờ Shopee duyệt không?**
**Không.**
- Hai đơn thuộc link V1.1 70%.
- Trên bản sao DB, sau migrate, backfill và làm mới ví, hai khoản vẫn là 12.157đ (phí 171, thuế 1.737) và 960đ (14, 138), `pending`.
- `validation_status` và `settlement_status` không đổi.

**Q9. Sau PLAN-076, còn thiếu gì trước khi tiếp tục PLAN-077?**
1. Chủ bot duyệt và triển khai PLAN-076 (mục 16).
2. Với hướng parser và APPROVED có chứng từ: **mẫu chứng từ thật** của một kỳ có tiền (báo cáo Thanh toán Shopee Affiliate, sao kê hoặc chứng từ ngân hàng, báo cáo Xác thực). Chưa có thì APPROVED vẫn bị chặn.
3. Quyết định thuế người nhận và chính sách thu hồi. Hai việc này cần cho bước nối đối soát vào khoá và mở ví về sau.
