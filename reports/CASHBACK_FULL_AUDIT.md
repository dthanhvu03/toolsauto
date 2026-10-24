# Cashback Bot — Báo cáo kiểm toán toàn hệ thống

| | |
|---|---|
| Ngày kiểm | 2026-10-24, khoảng 02:15–02:45 UTC (09:15–09:45 giờ VN) |
| Người kiểm | Claude Code (chỉ đọc). Hai agent đọc code hỗ trợ phần /admin và độ tin cậy; mọi kết luận quan trọng đã được đối chiếu lại với code |
| Phạm vi | `cashback_bot/`, `tests/test_cashback_*.py`, `data/cashback.sqlite` (mở `mode=ro`), `logs/cashback_bot.log`, metadata process |
| Không làm | Không sửa code, không restart, không ghi DB, không chạy migration, không gửi Telegram, không gọi Shopee/AddLiveTag |
| Vị trí file | Worktree `/home/vu/toolsauto-cashback-arch` **không còn tồn tại**, nên báo cáo đặt ở `reports/` của repo chính (xem A3) |

Cách đọc trạng thái:

- **LIVE VERIFIED**: đang chạy production và có bằng chứng dữ liệu thật.
- **LIVE UNVERIFIED**: đang chạy production nhưng chưa có bằng chứng.
- **CODED & TESTED**: đã có code và test, chưa chạy production.
- **PROTOTYPE**: bản thử nghiệm.
- **DESIGN ONLY**: mới có tài liệu.
- **NOT IMPLEMENTED**: chưa làm.
- **BLOCKED**: chưa làm được vì thiếu điều kiện bên ngoài.

---

## 1. Tóm tắt cho chủ bot

**Bot đang làm được:**
- Khách dán link Shopee, bot trả link mua có gắn mã theo dõi (Sub ID) kèm số tiền hoàn dự kiến.
- Từ 21/10 đến 24/10 có 5 người dùng, tạo 28 link, gửi thành công cả 28.
- Admin đồng bộ được click và đơn từ Shopee bằng cookie, khi bấm 🔄.
- Đã thấy **2 đơn thật mua qua link bot và khớp đúng người tạo link**: đơn kem nền DOPI và đơn bộ cọ trang điểm. Cả hai đang chờ Shopee duyệt.

**Khách dùng được đến đâu:** tạo link → mua → bot biết đơn đó của ai. Phần hoàn tiền dừng ở đó: ví đang **tắt**, chưa có khoản nào được duyệt, chưa chi đồng nào.

**Admin quản lý được:**
- Xem thống kê.
- Đồng bộ Shopee, xuất CSV.
- Đổi tỷ lệ chia cho khách, có bước xem trước và hẹn giờ.
- Đổi mức dự phòng phí và thuế.
- Bật hoặc tắt ví, đặt số ngày giữ tiền và mức rút tối thiểu.
- Duyệt yêu cầu rút, có ảnh VietQR.
- Xem lịch sử thay đổi.

**Chưa làm được:**
- Hạng thành viên mới hiển thị. Không khách nào được tính theo hạng.
- Chưa đối chiếu với **tiền Shopee thật sự trả**.
- Chưa biết đơn nào Shopee **duyệt** hay **đánh dấu gian lận**.
- Chưa có quy trình thuế cho người nhận tiền.

**Ba rủi ro lớn nhất:**
1. **Ví coi đơn "hoàn thành" là chắc chắn có tiền.** Ví cho rút sau "hoàn thành + 15 ngày", trong khi Shopee chỉ trả sau khi duyệt theo kỳ tháng. Shopee có thể đánh dấu gian lận ngay cả với đơn đã hoàn thành: đơn 23/09 trong DB là một ví dụ thật. Nếu bật rút tiền bây giờ, admin có thể chi trước khoản Shopee không bao giờ trả.
2. **Đơn đã vào ví thì bot không cập nhật hoa hồng nữa**, trừ khi Shopee huỷ đơn. Shopee giảm hoa hồng hoặc gắn cờ gian lận sau đó, bot vẫn giữ số cũ.
3. **Số báo khách cao hơn thực tế.** Hai đơn thật: hoa hồng ước tính 30.510đ thực tế 17.368đ (−43%); 1.663đ thực tế 1.372đ (−17,5%). Câu chữ đã được sửa (commit `6de6f82`), nhưng con số vẫn tính theo giá niêm yết.

**Rủi ro kỹ thuật cần sửa sớm (nhỏ, rẻ):**
- Một tin nhắn lỗi lặp lại có thể làm cả bot im lặng (P0-4).
- Token bot có thể bị ghi vào log khi mạng lỗi (P1-8).
- Backup đang chạy tay (P1-9).

**Có nên mở cho khách chưa?** Thực tế bot **đang mở công khai** (`CUSTOMER_ACCESS_ENABLED=true`). Ở mức "tạo link và ước tính" thì chấp nhận được, với điều kiện chủ bot chủ động quyết định để công khai và có trang điều khoản ngắn.

**Có nên mở rút tiền chưa?** **Chưa (NO-GO)** cho tới khi xong mục "BEFORE PAYMENT" ở phần 10.

---

## 2. Phase A — Môi trường

### A1. Process production

| Mục | Giá trị | Bằng chứng |
|---|---|---|
| PID | 590993 | `ps` |
| Bắt đầu | 2026-10-24 02:14:25 UTC | `ps -o lstart` |
| Lệnh | `.venv/bin/python -m cashback_bot` | `/proc/590993/cmdline` |
| Thư mục | `/home/vu/toolsauto` | `/proc/590993/cwd` |
| DB | `/home/vu/toolsauto/data/cashback.sqlite` | `/proc/590993/fd` |
| Lock | `/tmp/cashback_bot.lock` | `/proc/590993/fd/3` |
| Log | `logs/cashback_bot.log` | fd 1, 2 |
| Code đã nạp | **Gần chắc là HEAD `6de6f82`**. Commit lúc 02:13:00, file `.py` sửa muộn nhất lúc 02:12:33, process khởi động 02:14:25. Không có file nào sửa sau giờ khởi động. Không đo được trực tiếp code trong bộ nhớ | `find -newermt` |
| Số lần khởi động | 33 lần trong log từ 22/10 (do restart thủ công khi phát triển) | `grep "INFO start"` |
| Lỗi gần đây | 3 lần Telegram poll lỗi tạm (ReadTimeout, HTTPError), 1 lần `sendMessage http=502`, 4 lần Shopee từ chối một phần lúc thử tham số (23/10). Không có lỗi logic | log |

### A2. Source production

- Nhánh `main`, HEAD `6de6f82`, `git status` sạch.
- Không có thay đổi chưa commit, nên restart không vô tình kích hoạt code chưa duyệt.
- Restart sẽ đọc lại `.env`, và `.env` đang có `CASHBACK_ESTIMATE_POLICY=v1.2` và `CUSTOMER_ACCESS_ENABLED=true`.

### A3. Worktree phát triển

- `/home/vu/toolsauto-cashback-arch` **không tồn tại** (`git worktree list` chỉ có repo chính).
- Nhánh `cursor/cashback-v12-architecture` và 5 nhánh cashback khác đều có **0 commit chưa vào main**.
- Kết luận: không có code V1.2, Admin, Pricing, Tax Profile hay Membership nào nằm ngoài production. Production chính là bản đầy đủ nhất.

### A4. Dữ liệu production (đọc ở chế độ chỉ đọc)

| Bảng | Số dòng | Ghi chú |
|---|---|---|
| telegram_users | 5 | 21/10 → 24/10 |
| link_requests | 28 | 28/28 `created` + `sent`. 27 link V1.1, 1 link V1.2. Sub ID 8 ký tự, 28/28 khác nhau |
| shopee_clicks | 10 | 7 click mang Sub ID của bot, 3 click không có Sub ID |
| shopee_conversions | 3 | 2 đơn qua bot (UNPAID, PAID). 1 đơn ngoài bot ngày 23/09, COMPLETED nhưng `is_fraud=1`, hoa hồng 0 |
| cashback_entries | 2 | 12.157đ và 960đ, cả hai `pending` |
| cashback_payouts | 0 | chưa chi lần nào |
| bank_accounts | 1 | 1 tài khoản khai thử |
| reserve_policies | 1 | PERSONAL, phí 0,98%, thuế dự phòng 10%, hiệu lực 23/10 09:55 UTC |
| share_policies | 0 | tỷ lệ chia lấy từ `.env` (70%) |
| policy_versions | 0 | chưa có phiên bản hạng nào được xác nhận |
| admin_change_audit | 17 | draft 5, cancel 3, reserve_apply 1, wallet_enabled 6, wallet_hold_days 2 |
| outbound_messages | 292 | 292 `sent`, mỗi tin 1 lần thử |
| admin_notifications | 33 | 33 `sent` |
| shopee_sync_runs | 7 | 6 tay, 1 tự động. Cả 7 `success` |
| bot_state | — | `wallet_enabled=0`, `wallet_hold_days=15`, công tắc tự đồng bộ không bật |

Schema: không có bảng phiên bản migration. Migration 001 đã có (cột `estimate_policy`). 004–006 được tạo **mỗi lần mở kết nối admin** (`admin_policy.py:1142-1144`). 003 (snapshot hạng) chưa áp dụng. `PRAGMA foreign_keys` mặc định tắt, chỉ bật trong kết nối của admin.

---

## 3. Phase B — Bảng tính năng

### B1. Telegram Bot

| Tính năng | Bằng chứng code | Test | Production | Trạng thái | Thiếu |
|---|---|---|---|---|---|
| /start, trang chủ, nút | `messages.py:home_reply`, `service.py:169` | `test_cashback_bot.py`, `test_cashback_plan060.py` | 5 người dùng, 292 tin gửi | LIVE VERIFIED | — |
| /help /huongdan /dieukien /cachtinh | `messages.py:HUONGDAN, DIEUKIEN, how_to_calc` | `test_lenh_cach_tinh` | đăng ký menu lệnh (`setMyCommands ok`) | LIVE VERIFIED (tin tĩnh) | — |
| /hang | `messages.py:hang_message` (chữ "đang phát triển") | có | chạy | LIVE, **chỉ thông báo** | không có hạng thật |
| /vi, ví khách | `service.py`, `wallet.py` | `test_cashback_wallet.py` | ví tắt, khách thấy "chưa mở" | CODED & TESTED | xem B8 |
| /admin | `admin_policy.py` | `test_cashback_admin*.py` | 17 dòng audit thật | LIVE VERIFIED | xem phần 5 |
| Gửi link → thẻ hoàn dự kiến | `service.py:handle_text`, `messages.py:_render_card` | `test_ac01_link_hop_le_va_cashback_70` | 28 link | LIVE VERIFIED | ước tính cao hơn thực tế |
| Inline keyboard và callback | `service.py:handle_update`; `u:*` cho khách, `c:*` cho admin | có | có | LIVE VERIFIED | — |
| Phiên nhập cấu hình | `admin_drafts`, `reserve_drafts`, `share_drafts`, TTL 10 phút, nonce | `test_cashback_reserve.py`, `test_cashback_share.py` | 5 draft, 1 lần apply | LIVE VERIFIED | — |
| Rate limit | `telegram_users.rate_*`, `messages.rate_limited_reply` | có | không có bằng chứng bị kích hoạt | LIVE UNVERIFIED | — |
| Allowlist / công khai | `service.py:allowed` (dòng 93-96) | có | `CUSTOMER_ACCESS_ENABLED=true`, log in `public=True` | **LIVE: bot đang công khai** | cần chủ bot xác nhận có chủ ý |
| Quyền admin | `admin_policy.py:is_admin` (178); callback chỉ chạy trong chat riêng (221) | có | có | LIVE VERIFIED | — |
| Thông báo admin | `admin_notify.py`, outbox `admin_notifications` | có | 33 tin gửi | LIVE VERIFIED | — |

### B2. Link Shopee

| Tính năng | Bằng chứng | Trạng thái |
|---|---|---|
| Nhận dạng và chuẩn hoá URL, link rút gọn `s.shopee.vn`, `vn.shp.ee` | `shopee_url.py`; DB có `original_url` dạng rút gọn, `item_id` và `shop_id` đúng | LIVE VERIFIED |
| Dữ liệu sản phẩm AddLiveTag (giá, hoa hồng) | `product_data.py:quote_from_payload` (120-125); 12 link `api`, 16 link `db` (bộ đệm) | LIVE VERIFIED |
| Link affiliate `an_redir` có `affiliate_id`, `sub_id` | `affiliate.py:build_an_redir` | LIVE VERIFIED |
| Sub ID: 8 ký tự, duy nhất, giữ hoa thường | `affiliate.py:new_sub_id`; 28/28 khác nhau; Shopee trả về `utm_content` như `u3e52GNL----` và bot khớp đúng | LIVE VERIFIED |
| Chống tạo trùng khi Telegram gửi lại | `link_requests.telegram_update_id UNIQUE` (`db.py:20`), tra lại theo update (`db.py:298`) | CODED & TESTED |
| Shopee ghi nhận click theo Sub ID | 7/10 click mang Sub ID của bot | LIVE VERIFIED |
| Shopee ghi nhận **đơn** theo Sub ID | 2 đơn khớp `matched_link_id` 24, 25 và đúng `telegram_user_id` | LIVE VERIFIED (mẫu 2 đơn) |

### B3. Công thức tiền

| Công thức | Ở đâu | Đang phục vụ khách? | Trạng thái |
|---|---|---|---|
| V1.1: hoàn = 70% × HH ước tính | `money.estimated_cashback`, `pricing.quote_displayed_vnd` | 27 link cũ. Ví dùng công thức này cho đơn của link V1.1 | LIVE (link cũ) |
| V1.2: HH − phí 0,98% − thuế dự phòng 10%, rồi × 70% | `calculator.estimate_cashback` (112-123), `service._quote_cashback` | **Link mới từ 23/10** (1 link). Ví dùng cho đơn của link V1.2 | LIVE VERIFIED (1 link) |
| Số ví theo hoa hồng thật | `service._real_cashback`, `wallet.refresh` | Ví tắt, 2 dòng sổ chờ | LIVE UNVERIFIED |
| Final settlement (thuế đã khấu trừ, VAT, điều chỉnh, bằng chứng thanh toán) | `calculator.final_cashback`, `pricing.net_of_charges`, `tax_profile.py` | Không. `payable_vnd` luôn None | CODED & TESTED, chưa nối |
| Làm tròn | `bps_floor` (phần khách, xuống), `bps_ceil` (dự phòng, lên) | có | thiên về an toàn cho chủ bot |
| Đơn vị tiền | VND nguyên; tiền Shopee chia 100.000 (`shopee_sync.parse_shopee_money_vnd`) | có | đối chiếu bằng response thật |
| Snapshot chính sách trên link | V1.1 lưu `cashback_rate_percent`. V1.2 lưu nhãn `estimate_policy` có `+r{id}+s{id}`, **nhưng ví không đọc nhãn này**: tính lại theo mức có hiệu lực lúc `link_created_at` | một phần | xem rủi ro P1-4 |
| Trùng công thức | `pricing.py` là cửa chung. `admin_ui` màn 🧮 mô phỏng dùng `share_cashback` trên số thô, **không trừ phí và thuế dù V1.2 đang bật** | — | màn mô phỏng lệch với số khách thấy |

**Bù lỗ:** khách chỉ được ghi số theo **hoa hồng thật**, không theo số ước tính, nên ước tính cao không làm chủ bot lỗ trực tiếp. Chủ bot chỉ có thể lỗ khi **chi trước** khoản Shopee chưa duyệt, hoặc khi Shopee giảm hay thu hồi hoa hồng sau khi đã chi (B7, B8).

### B4. Hạng thành viên (Đồng 60%, Bạc 65%, Vàng 70%)

| Mục | Bằng chứng | Trạng thái |
|---|---|---|
| Tỷ lệ, bản nháp, xem trước, xác nhận | `admin_policy._begin/_preview_number/_confirm`, `admin_drafts`, `policy_versions` | CODED & TESTED (0 phiên bản được xác nhận trên production) |
| Ảnh hưởng tới số khách | `policy_versions.customer_effect` có ràng buộc CHECK chỉ cho phép `'none'` (`004_admin_policy.sql:11`) | **Không có ảnh hưởng** |
| Gán hạng, lên hạng, lịch sử, xuống hạng | `ranks.py`: `share_for_new_link`, `consider_promotion` (luôn None), `RankHistory`, `ProgressBook` không được service hay poller gọi | CODED & TESTED một phần, **không chạy** |
| Snapshot hạng trên link | migration 003 chưa áp dụng | DESIGN ONLY |
| Chống gian lận khi lên hạng | không có | NOT IMPLEMENTED |
| Công tắc | `ranks.MEMBERSHIP_CUTOVER = False` (`ranks.py:15`), chỉ dùng để ẩn nút | — |

### B5. Thuế và phí

| Mục | Bằng chứng | Trạng thái |
|---|---|---|
| Dự phòng phí 0,98% và thuế 10% trong báo giá V1.2 | `reserve_policies` (1 dòng PERSONAL), `service._quote_cashback` | LIVE VERIFIED, **là dự phòng, không phải chứng từ** |
| PERSONAL / INDIVIDUAL_BUSINESS / HOUSEHOLD_BUSINESS | `tax_profile.py` chỉ được test import. Loại hình trong `reserve_policies` chỉ là nhãn | CODED & TESTED, không dùng |
| Phí đã gồm VAT, thuế đã khấu trừ, chống trừ hai lần | `pricing.net_of_charges` (70-109), `calculator.settle_commission` | CODED & TESTED, không nối |
| Thời điểm hiệu lực, phiên bản | `reserve_policies.effective_at`, `share_policies.effective_at` | LIVE VERIFIED |
| Phí và thuế admin chịu trên từng đơn | `cashback_entries.fee_vnd`, `tax_vnd` (commit `5e17df9`) | LIVE (2 dòng) |
| Thuế khi trả tiền cho người nhận | không có | NOT IMPLEMENTED |
| Nghĩa vụ pháp lý | không có chứng từ trong repo | NOT VERIFIED |

### B6. Admin: xem phần 5.

### B7. Đối soát đơn

| Mục | Bằng chứng | Trạng thái |
|---|---|---|
| Đồng bộ bằng cookie qua API nội bộ Shopee (`/api/v1/click_report/list`, `/api/v3/report/list`) | `shopee_client.py`, `shopee_sync.py`; 7 lần chạy `success` | LIVE VERIFIED |
| Click report | 10 click | LIVE VERIFIED |
| Conversion report và gắn Sub ID | 2 đơn khớp đúng người | LIVE VERIFIED (mẫu nhỏ) |
| Định danh đơn | `conversion_id` = `order_id` (PK, upsert). Checkout nhiều đơn được tách theo đơn | CODED & TESTED |
| Hoa hồng ước tính của Shopee (`estimated_total_commission`, `affiliate_net_commission`) | lưu `gross_commission_vnd`, `net_commission_vnd` | LIVE VERIFIED |
| **Hoa hồng đã duyệt** (validation, `fraud_status`, `affiliate_item_status`) | `shopee_sync` chỉ lưu `validation_month`; **không đọc `is_fraud`, `fraud_status`, `checkout_status`**. Ví chỉ dựa vào `order_status` (`wallet.order_state`, 167-173) | **NOT IMPLEMENTED** |
| Bằng chứng Shopee đã trả tiền | không có | NOT IMPLEMENTED |
| Shopee Open API | không có quyền truy cập (memory: không có Open API) | BLOCKED |
| Nhập tay | chỉ xuất CSV, không nhập vào được | NOT IMPLEMENTED |
| Đơn huỷ | `order_state` → `cancelled`; đơn đã vào ví mà bị huỷ thì báo admin để trừ lại | CODED & TESTED |
| **Hoa hồng giảm sau khi vào ví** | `wallet.refresh` (280-281): dòng đã `available` và đơn chưa huỷ thì `continue`, không cập nhật | **Không xử lý** |
| Đối soát với kỳ thanh toán Shopee | không có | NOT IMPLEMENTED |

Trả lời các câu trong đề:
- Đã test click: **có**.
- Đã có đơn thật qua bot: **có, 2 đơn**.
- Đã khớp đơn với người dùng Telegram: **có, 2/2**.
- Đã khớp hoa hồng được duyệt: **chưa**. Cả hai đơn đang chờ, và bot chưa đọc trạng thái duyệt.
- Đã khớp tiền Shopee thực trả: **chưa**.

### B8. Ví và chi trả

| Mục | Bằng chứng | Trạng thái |
|---|---|---|
| Sổ pending → holding → available / cancelled | `wallet.refresh` | CODED & TESTED. Production: ví **tắt**, 2 dòng `pending` |
| Số dư = available − đang yêu cầu − đã trả | `wallet._balance` (473-491) | CODED & TESTED |
| Mốc "có thể rút" | `COMPLETED` + `wallet_hold_days` (production: 15) | CODED & TESTED, **sai mốc** (xem P0-1) |
| Yêu cầu rút: BEGIN IMMEDIATE, mỗi người một yêu cầu, mức tối thiểu | `wallet.request_payout` (~405-412) | CODED & TESTED |
| Admin duyệt đã chuyển / từ chối, chống bấm hai lần | `admin_wallet._payout` (115-135), kiểm tra `status != 'requested'` | CODED & TESTED |
| VietQR tự tạo (EMVCo, CRC) | `vietqr.py`, 59 ca test | CODED & TESTED. **Chưa quét bằng app ngân hàng thật** |
| Audit chi trả | chỉ có `decided_by`, `decided_at` trên `cashback_payouts`. **Không ghi vào `admin_change_audit`** | thiếu |
| Trần quỹ (không chi vượt tiền Shopee đã trả) | không có | NOT IMPLEMENTED |
| Khấu trừ thuế người nhận | không có | NOT IMPLEMENTED |
| Đối soát chuyển khoản (sao kê) | không có. Admin tự bấm "Đã chuyển" | NOT IMPLEMENTED |

### B9. Độ tin cậy và bảo mật: xem phần 7.

---

## 4. Phase C — Luồng người dùng

| Journey | Đã chạy | Chưa chạy hoặc thiếu | Điều kiện để xong |
|---|---|---|---|
| **1. Người mới** /start → /huongdan → dán link → nhận link | ✅ toàn bộ (28 link, 5 người) | — | Đã xong |
| **2. Mua hàng** link → Shopee → click → đơn → hoa hồng | ✅ click có Sub ID; ✅ 2 đơn khớp; ✅ hoa hồng ước tính của Shopee | ❌ hoa hồng **được duyệt**. Bot chưa đọc cờ duyệt hay gian lận | Đọc trạng thái duyệt hoặc gian lận của Shopee |
| **3. Nhận tiền** đơn → đối soát → xác nhận tiền → tính hoàn → chi | ✅ tính hoàn theo hoa hồng thật (2 dòng sổ) | ❌ ví tắt; ❌ không có bước "Shopee đã duyệt"; ❌ không đối chiếu tiền Shopee trả; ❌ chưa quét QR thật; ❌ chưa có quy định thuế | Làm hết mục BEFORE PAYMENT |
| **4. Hạng thành viên** Đồng → Bạc → Vàng | ❌ chỉ hiển thị | ❌ gán hạng, đếm đơn hợp lệ, lên/xuống hạng, snapshot | Quyết định kinh doanh rồi mới làm (LATER) |
| **5. Admin** đổi tỷ lệ → nháp → mô phỏng → xác nhận → kích hoạt | ✅ với **tỷ lệ chia** và **dự phòng phí/thuế**: nháp → chọn giờ → xem trước → áp dụng, có audit khi áp dụng | ⚠️ hạng chỉ lưu, không có tác dụng; ⚠️ màn 🧮 mô phỏng không trừ phí/thuế; ⚠️ bước nháp/huỷ của tỷ lệ và dự phòng không ghi audit | Sửa chữ gây hiểu nhầm (P1-3) |

Điểm đứt của chuỗi tạo link → nhận tiền: **giữa "Shopee báo có đơn" và "Shopee xác nhận trả tiền"**. Bot chưa có dữ liệu nào cho bước thứ hai.

---

## 5. Phase B6 — Kiểm tra từng nút /admin

| Nút | Backend thật? | Dữ liệu | Sửa được | Nháp → xem trước → xác nhận | Audit | Hẹn giờ | Link cũ |
|---|---|---|---|---|---|---|---|
| 📈 Thống kê (`c:st:*`, `:more`) | có | DB thật | không | — | — | — | — |
| 🔗 Shopee Affiliate: dán cookie | có, kiểm tra trực tiếp với Shopee (`admin_policy.py:484`) | thật | cookie | không | có (494) | — | — |
| ↳ 🔄 Đồng bộ | có (đặt cờ, poller chạy) | — | — | — | **không** | — | — |
| ↳ Tự đồng bộ 4 giờ | có | thật | bật/tắt | không | có (407) | — | — |
| ↳ CSV | có | thật | — | — | không | — | — |
| 👛 Ví khách | có (`admin_wallet.py:50`) | thật | bật/tắt (có xác nhận), giữ ngày, tối thiểu, duyệt chi | chỉ bật ví và duyệt chi có xác nhận | cài đặt: có. **Chi trả: không** | — | — |
| 💰 Chính sách (tỷ lệ chia) | có, `share_drafts` → `share_policies` | thật | % chia (0–70) | có: nháp → giờ → xem trước → áp dụng | chỉ khi áp dụng (733) | có | V1.1: giữ số. V1.2: tính lại theo mức lúc tạo link |
| 🎖️ Hạng | có, nhưng `customer_effect='none'` | tỷ lệ từ DB; dòng "ĐANG ÁP DỤNG: Chưa bật" **viết cứng** (`admin_ui.py:187`) | lưu phiên bản | đủ bước, có kiểm tra phiên bản | đủ (536, 578, 595, 647) | không | **không tác dụng** |
| 🧾 Thuế & phí dự phòng | có, `reserve_drafts` → `reserve_policies` | thật | loại hình (nhãn), phí, thuế (≤50%) | có: loại → phí → thuế → giờ → xem trước → áp dụng | chỉ khi áp dụng (957) | có | như tỷ lệ chia |
| 🧮 Mô phỏng | có | tỷ lệ hạng từ DB | không | — | — | — | **không trừ phí/thuế khi V1.2 đang bật** |
| 📊 Lịch sử | có | 8 dòng `admin_change_audit` gần nhất | — | — | — | — | — |
| 📝 Nội dung lệnh | **chữ tĩnh** (`admin_ui.py:274-287`) | — | không | — | — | — | — |

Cần restart khi: đổi V1.1↔V1.2 (`.env`), đổi mặc định phí/thuế trong `.env`, cập nhật menu lệnh /vi. Đổi tỷ lệ chia hay dự phòng **không cần restart** (`service._quote_cashback` đọc DB mỗi lần báo giá).

Người dùng thường bấm được nút admin không? **Không.** Callback `c:` bắt buộc là admin và trong chat riêng (`admin_policy.py:221`). Các bước nháp còn kiểm tra admin sở hữu và nonce.

Chữ gây hiểu nhầm trên màn /admin home (`admin_ui.py:105-110`):
- "Đối soát & chi trả: Chưa mở", trong khi đồng bộ và ví đã có.
- "Sửa cấu hình không đổi báo giá khách cho tới khi kích hoạt", trong khi áp dụng tỷ lệ chia hay dự phòng **có** đổi báo giá link mới ngay từ giờ hiệu lực.
- "Bản nháp đang chờ" chỉ đếm `admin_drafts`, bỏ sót nháp dự phòng và tỷ lệ chia.

---

## 6. Phase E — An toàn tài chính

### Mức an toàn từng công thức

- **70% của V1.1:** khách nhận 70% hoa hồng gốc, phí 0,98% và thuế dự phòng 10% admin chịu hết. Admin còn khoảng 19%. Không lỗ nếu thuế và phí thật không vượt 30% hoa hồng. Bằng chứng 2 đơn: admin còn 3.303đ và 260đ.
- **V1.2 (đang chạy cho link mới):** trừ 10,98% trước, khách nhận 70% phần còn lại, tức khoảng 62,3% hoa hồng. Admin còn khoảng 26,7%, kèm khoản dự phòng.
- **Hạng 60/65/70:** không chạy nên không có rủi ro hiện tại. Nếu bật, Vàng 70% trên V1.2 vẫn còn biên.
- **Payout:** đây là chỗ lỗ được, vì tiền "có thể rút" dựa trên `COMPLETED + 15 ngày`, không dựa trên Shopee duyệt hay Shopee trả.

### 18 tình huống

| # | Tình huống | Có xử lý? | Test | Chặn được rủi ro? | Thiếu |
|---|---|---|---|---|---|
| 1 | HH ước tính > thực tế | Có: ví ghi theo hoa hồng thật. Chữ đã nói rõ (`messages._PAID_BASIS`) | `TestPaidBasisWording` | Có về tiền. Lòng tin khách vẫn bị ảnh hưởng | ước tính vẫn theo giá niêm yết |
| 2 | Thuế Shopee đã khấu trừ | Chỉ dự phòng 10% trên mọi đơn. Chưa nối khoản khấu trừ thật | `test_cashback_tax_profiles.py` (không nối) | Một phần | số khấu trừ thật theo kỳ |
| 3 | Phí Shopee đã khấu trừ | Dự phòng 0,98% | có | Một phần | phí thật theo kỳ |
| 4 | Thuế và phí bị trừ hai lần | Có trong `net_of_charges` và `settle_commission`, nhưng chưa nối | có | Chưa áp dụng | — |
| 5 | Đơn huỷ | Có: `cancelled`. Đã vào ví thì báo admin trừ lại | có | Có | — |
| 6 | Không có conversion | Không có gì để ghi, nên không chi | — | Có | — |
| 7 | Commission = 0 | Hoàn 0, không báo khách (`service.refresh_wallet`) | có | Có | — |
| 8 | Không khớp Sub ID | Đơn vẫn lưu, không gán người (`matched_link_id` NULL) | có | Có | — |
| 9 | Link bị chuyển tiếp cho người khác | Tiền về người tạo link (chủ Sub ID) | — | Theo thiết kế | cần ghi vào điều khoản |
| 10 | Khách lên hạng sau khi tạo link | Không áp dụng vì hạng chưa chạy | — | — | — |
| 11 | Link cũ theo chính sách cũ | V1.1: giữ tỷ lệ đã lưu. V1.2: tính lại theo mức có hiệu lực lúc tạo link | có | Gần đủ | có khe hở hồi tố tối đa 10 phút (P1-4) |
| 12 | Thiếu settlement | Không có settlement | — | **Không** | P0-2 |
| 13 | Nhiều đơn trong một kỳ | Ghi từng đơn; checkout nhiều đơn tách HH theo món (commit `00b0892`) | `test_multi_order_checkout_counts_shop_commission` | Có | phí MCN của checkout nhiều đơn để 0 |
| 14 | Phí chuyển khoản > lợi nhuận | Rút tối thiểu 10.000đ. Phí chuyển khoản không tính | — | Một phần | — |
| 15 | Chi trùng | Một yêu cầu mỗi người, BEGIN IMMEDIATE, chặn bấm hai lần | có | Có trong bot. Không chặn được chuyển tay hai lần ngoài bot | đối soát sao kê |
| 16 | Hoa hồng bị thu hồi sau đối soát | Chỉ khi Shopee **huỷ đơn**. Giảm HH hoặc gian lận trên đơn `COMPLETED` bị bỏ qua | không | **Không** | P0-1 |
| 17 | Đổi loại hình thuế | Đổi được ở 🧾, có hẹn giờ; link cũ theo mức cũ | có | Có cho dự phòng | — |
| 18 | Thuế của người nhận | không có | — | **Không** | cần kế toán xác nhận |

**Không thể kết luận hệ thống chắc chắn không lỗ.** Chưa có dữ liệu Shopee duyệt hoặc trả tiền cho đơn nào qua bot.

---

## 7. Độ tin cậy và bảo mật

| Mục | Bằng chứng code | Test | Trạng thái và lỗ hổng |
|---|---|---|---|
| Khoá một process | `poller._acquire_single_process_lock` (200-209), `flock` trên `/tmp/cashback_bot.lock` | `test_single_process_lock` | LIVE VERIFIED (fd 3 của PID 590993). Chỉ chặn trong cùng máy |
| Lưu offset Telegram | `db.set_offset` (631), gọi sau mỗi update | `test_restart_van_gui_lai_dung_link` | LIVE. **Không bọc try/except cho từng update** (`poller.py:228-296`): một update luôn gây lỗi sẽ bị thử lại mãi, cả bot im lặng (P0-4) |
| Chống tạo link trùng khi gửi lại | `telegram_update_id UNIQUE` (`db.py:20, 49`); `service.py:318-321` hiện lại link cũ | `test_retry_khong_tao_sub_id_moi`, `test_cung_update_khong_tao_them_sub_id` | CODED & TESTED. Khi hiện lại link cũ, bot không so người gửi với chủ link (rủi ro thấp, P2-6) |
| Hàng đợi tin gửi | `outbound_messages`; backoff `30s × lần`, tối đa 5 lần, 429 đọc `Retry-After`; dòng kẹt `sending` gửi lại (`poller.py:107-117, 187-194`) | `test_qua_so_lan_thi_needs_review`, `test_telegram_429_khong_chan_user_sau` | LIVE VERIFIED (292/292 sent). Có thể gửi trùng khi Telegram timeout (gửi ít nhất một lần); mỗi vòng chỉ xả 3 tin |
| Outbox thông báo admin | `event_key UNIQUE` (`db.py:64`), tối đa 5 lần | `test_link_sent_notify_khong_trung_khi_retry_cung_update` | LIVE VERIFIED (33/33). Khoá `request_failed:telegram_poll_failed:0:0` chỉ báo **một lần trong đời DB**. Tin ví của khách đi chung outbox, nên tắt thông báo admin thì khách cũng mất tin (`admin_notify.py:320`) |
| Rate limit | `db.consume_link_attempt` (400-462): 8 link / 10 phút, nghỉ 5 phút | `test_user_vuot_limit_khong_anh_huong_user_khac` | LIVE UNVERIFIED. Lệnh và nút bấm không bị giới hạn |
| Transaction | `BEGIN IMMEDIATE` chỉ ở `wallet.request_payout` (405); `decide_payout ... WHERE status='requested'` | `test_full_withdraw_flow` | CODED & TESTED |
| Ràng buộc duy nhất | `link_requests.sub_id`, `telegram_update_id`; `shopee_conversions.conversion_id`; `cashback_entries.conversion_id` | có | LIVE |
| Foreign keys | `PRAGMA foreign_keys=ON` ở `db.py:240`, `admin_policy.py:1141` | — | có |
| Migration | `repo.migrate()` lúc khởi động (`CREATE IF NOT EXISTS`, `_add_column`); 004–006 chạy mỗi lần mở kết nối admin; 001/003 chạy tay; không có bảng phiên bản; không WAL, không `busy_timeout` | `apply_snapshot_columns` idempotent | Chạy được nhưng thiếu kiểm soát phiên bản (P2-2) |
| Backup / restore | `python -m cashback_bot.backup`: SQLite Backup API, `integrity_check`, giữ 14 bản; restore chỉ ra file mới | `test_backup_bo_qua_giao_dich_chua_commit`, `test_restore_ra_file_moi_va_tu_choi_de_len_db_that` | CODED & TESTED. **Chạy tay, không có lịch**; nằm cùng ổ đĩa, không mã hoá; chứa đủ số tài khoản ngân hàng (P1-9) |
| Cookie Shopee | lưu 0600 qua file tạm; tin chứa cookie bị xoá khỏi chat; không log cookie | `test_save_and_load_cookies_with_chmod_0600` | LIVE VERIFIED. Đợt trước từng có test ghi đè cookie thật; đã chặn bằng `tests/conftest.py` |
| Token bot trong log | `telegram_api.py:165, 214` log nguyên chuỗi lỗi của `requests`. Lỗi kết nối thường chứa URL `/bot<TOKEN>/…` | — | **Rủi ro chưa xảy ra**: log hiện có 0 dòng chứa `api.telegram.org/bot`. File log quyền 0644 (P1-8) |
| Dữ liệu cá nhân | STK và tên chủ tài khoản lưu dạng rõ trong SQLite; tin admin chỉ hiện 4 số cuối STK; khi ví tắt, mọi chữ khách gõ (kể cả STK) lưu vào `link_requests.original_url` như link sai (`service.py:347-354`) | — | Cần trang quyền riêng tư; cân nhắc không lưu chữ thô |
| Khôi phục sau lỗi | `_loop` bắt lỗi, báo admin, nghỉ 5s; AddLiveTag lỗi thì khách nhận tin "chưa sẵn"; lỗi Shopee được cô lập | `test_ac03_api_loi_va_timeout` | LIVE (đã gặp ReadTimeout, 502, đều tự hồi phục). Đồng bộ Shopee chạy trong vòng poll (tối đa 20 trang × 2 báo cáo, mỗi trang timeout 20s), có thể làm bot đứng vài phút khi đang đồng bộ |
| Product data | timeout 20s, cách nhau ≥0,35s, từ chối dữ liệu quá `PRODUCT_MAX_AGE_HOURS` (3 giờ) | `test_client_http_va_timeout` | LIVE VERIFIED. Không cache, không thử lại |
| Supervisor | không có unit systemd hay cron trong repo; user restart tay | — | 33 lần khởi động trong 3 ngày |

---

## 8. Phase D — So với Caffi (caffiliate.vn/policies.html, đọc ngày 24/10/2026)

| Nhóm | Caffi | Cashback Bot | Cần trước khi có khách? | Cần trước khi chi? | Có nên làm theo? |
|---|---|---|---|---|---|
| Tạo link | có | có | — | — | — |
| Điều kiện ghi nhận đơn | trang chính sách | /dieukien | đã có | — | — |
| Tiền dự kiến | "điểm tạm tính" | "hoàn dự kiến khoảng…", "hoàn tạm tính" | đã có | — | — |
| Tiền đã duyệt | thưởng tính trên **hoa hồng đối tác xác nhận** | ví ghi theo hoa hồng Shopee **ước tính**, mốc "hoàn thành + N ngày" | — | **Bắt buộc**: theo hoa hồng đã duyệt | Có |
| Hạng | Đồng 60%, Vàng 70%, Kim Cương 80%, ngày khuyến mãi +10%, rớt hạng sau 90 ngày không mua | chỉ hiển thị | Không | Không | Để sau. Tỷ lệ 80–90% của Caffi dựa vào quy mô và quỹ riêng, không nên chép |
| Lịch sử giao dịch | có | /vi hiện 5 dòng sổ gần nhất | — | đã có | — |
| Đối soát | theo sàn | đồng bộ bằng cookie, bấm tay | — | cần đối chiếu kỳ trả | Có |
| Quỹ hoàn nhanh | 50 triệu/tuần, Caffi tự chi, 48–72 giờ | không | Không | Không | **Không nên làm sớm**: đây là chi trước bằng vốn |
| Rút tiền | về tài khoản chính chủ, tối đa 20 triệu/tháng | tối thiểu 10.000đ, VietQR, admin chuyển tay; **không có trần tháng**; không kiểm tra tên chính chủ | — | thêm trần tháng; nhắc đối chiếu tên (màn duyệt đã nhắc) | Có (trần) |
| Tranh chấp | email, phản hồi 7 ngày làm việc, tạm giữ tối đa 30 ngày khi nghi gian lận | không có kênh | Nên có một dòng liên hệ | **Bắt buộc** | Bản tối giản |
| Thuế và phí | chủ chương trình tự lo thuế; trừ thuế người nhận nếu luật yêu cầu | dự phòng nội bộ; không có gì cho người nhận | — | **Bắt buộc** có quyết định | Có, sau khi hỏi kế toán |
| Thay đổi chính sách | báo trước 15 ngày nếu bất lợi; quyền lợi đã xác nhận được giữ | hẹn giờ hiệu lực; link cũ giữ số | Nên ghi vào điều khoản | Có | Có |
| Dữ liệu cá nhân | thời hạn xử lý yêu cầu, không mua bán dữ liệu | lưu Telegram ID, username, STK, tên chủ TK; không có trang quyền riêng tư; không có lệnh xoá dữ liệu | Nên có | **Bắt buộc** trước khi thu STK | Bản tối giản |
| Quyền theo Sub ID / link chia sẻ | không nói rõ | tiền về người tạo link | Nên ghi rõ | Có | Có |

---

## 9. Rủi ro P0 / P1 / P2

**P0: phải xong trước khi bật rút tiền**

| ID | Vấn đề | Ảnh hưởng | Ví dụ | Bằng chứng | Đề xuất | Độ khó |
|---|---|---|---|---|---|---|
| P0-1 | Mốc "có thể rút" là `COMPLETED` + 15 ngày. Bot không đọc cờ gian lận hay trạng thái duyệt. Đơn đã `available` thì bỏ qua mọi thay đổi trừ huỷ | Chi tiền Shopee không trả; không thu hồi được | Đơn 23/09: `COMPLETED`, `is_fraud=1`, HH 0. Nếu cờ gian lận đến **sau** khi tiền vào ví, khách vẫn rút được | `wallet.order_state` 167-173; `wallet.refresh` 280-281; `shopee_sync` không đọc `fraud_status` | (a) Chỉ cho `available` khi item không gian lận **và** đã qua kỳ duyệt (`validation_month`), hoặc admin xác nhận theo kỳ. (b) Đơn đã vào ví mà HH giảm hoặc bị gắn gian lận thì ghi dòng điều chỉnh âm và báo admin | Trung bình |
| P0-2 | Không đối chiếu với tiền Shopee thực trả, không có trần quỹ | Chi vượt số tiền đã nhận | 15 ngày giữ tiền < chu kỳ trả của Shopee (đối soát theo tháng), nên luôn chi trước | không có code | Thêm bước "kỳ Shopee đã trả X" do admin nhập. Tổng có thể rút ≤ X − dự phòng | Trung bình |
| P0-3 | Thuế của người nhận và thuế của chủ bot chưa có quyết định | Rủi ro pháp lý | — | `tax_profile.payable_vnd` luôn None | Hỏi kế toán, ghi ADR, rồi mới chi | Quyết định |
| P0-4 | Một update Telegram luôn gây lỗi sẽ chặn offset; bot thử lại mãi và **im lặng với mọi người** | Toàn bộ bot ngừng trả lời | Một tin có dữ liệu lạ làm `handle_update` ném lỗi | `poller.py:228-296` không có try/except từng update; `_loop` (395) nghỉ 5s rồi thử lại cùng offset | Bọc từng update; lỗi lần 2 thì ghi `needs_review`, báo admin, bỏ qua offset đó | Nhỏ. **Nên làm ngay**, là điều kiện trước khi mở rộng |

**P1: nên làm trước khi mở rộng người dùng**

| ID | Vấn đề | Ảnh hưởng | Bằng chứng | Đề xuất | Độ khó |
|---|---|---|---|---|---|
| P1-1 | Bot đang công khai, allowlist không còn tác dụng | Ai cũng dùng được; tốn quota AddLiveTag (phi thương mại, là nguồn duy nhất) | `.env CUSTOMER_ACCESS_ENABLED=true`; log `public=True` | Chủ bot xác nhận có chủ ý. Nếu không thì tắt cờ | Cấu hình |
| P1-2 | Ước tính theo giá niêm yết, lệch −17% đến −43% | Khách mất lòng tin | 2 đơn thật (A4) | Đã sửa chữ. Cân nhắc hệ số an toàn hoặc chỉ hiện khoảng | Nhỏ |
| P1-3 | Chữ /admin gây hiểu nhầm; màn 🧮 không trừ phí/thuế | Admin quyết định sai | `admin_ui.py:105-110, 187`; màn sim | Sửa chữ, cho sim dùng `live_policy` | Nhỏ |
| P1-4 | V1.2 tính lại theo mức có hiệu lực lúc tạo link, không đọc snapshot `+r+s`. Áp dụng với `effective_at` cũ tới 10 phút | Link tạo trong khe đó bị đổi số | `service._real_cashback` 282-290; `admin_reserve.py:134`; `admin_policy.py:939, 722` | Đọc id chính sách từ nhãn đã lưu; chặn `effective_at` < lúc bấm áp dụng | Nhỏ |
| P1-5 | Chi trả không ghi `admin_change_audit`; bước nháp/huỷ tỷ lệ và dự phòng không ghi; 🔄 không ghi | Thiếu vết kiểm toán | báo cáo /admin | Ghi audit cho chi trả trước | Nhỏ |
| P1-6 | Đồng bộ dựa vào cookie và API nội bộ Shopee | Shopee đổi API hoặc khoá phiên thì mất đối soát | `shopee_client.py`; ngày 23/10 Shopee trả HTTP 400 khi đổi tham số | Giữ đồng bộ tay; theo dõi lỗi; tìm nguồn dự phòng | — |
| P1-7 | Chưa quét VietQR bằng app ngân hàng thật; BIN của 10 ngân hàng thêm sau chưa đối chiếu danh sách NAPAS | Chuyển nhầm hoặc QR lỗi | PLAN-066 proof | Thử 1 giao dịch nhỏ với tài khoản của chủ bot | Nhỏ |
| P1-8 | Lỗi mạng của `editMessageText` và `deleteMessage` được log nguyên văn, có thể chứa token bot | Lộ token, ai có token điều khiển được bot | Chưa xảy ra (0 dòng); log 0644 | `telegram_api.py:165, 214` | Chỉ log `type(exc).__name__` như các chỗ khác; `chmod 600` file log | Rất nhỏ |
| P1-9 | Backup chạy tay, cùng ổ đĩa, không mã hoá, chứa STK | Mất dữ liệu khi hỏng ổ; lộ STK nếu file bị chép | BACKUP.md: "Chưa có lịch tự chạy" | `backup.py` | Cron backup hằng ngày, chmod 600, chép ra ngoài máy | Nhỏ |

**P2: để sau**

| ID | Vấn đề | Đề xuất |
|---|---|---|
| P2-1 | Hạng thành viên mới là giao diện | Chỉ làm khi có quyết định kinh doanh và đủ dữ liệu đơn duyệt |
| P2-2 | Migration 004–006 chạy lại mỗi lần mở kết nối admin; không có bảng phiên bản; 003 treo | Gom vào `repo.migrate()` có version |
| P2-3 | Phí MCN của checkout nhiều đơn để 0 | Chia theo tỷ lệ HH khi có MCN |
| P2-4 | Code chết trong `admin_policy` (`_config_for` nhánh không phải hạng, `RESERVE_NAMES`) | Dọn khi có PLAN |
| P2-5 | 33 lần khởi động trong 3 ngày (restart tay) | Dùng service manager khi ổn định |
| P2-6 | Hiện lại link cũ theo `update_id` không so người gửi (`service.py:319-321`) | Thêm điều kiện cùng `telegram_user_id` |
| P2-7 | Cảnh báo `telegram_poll_failed` chỉ gửi một lần trong đời DB (`admin_notify.py:192`) | Thêm mốc thời gian vào `event_key` |
| P2-8 | Tin ví của khách đi chung outbox admin; tắt thông báo admin thì khách mất tin (`admin_notify.py:320`) | Tách điều kiện gửi |
| P2-9 | Gửi trùng tin khi Telegram timeout (gửi ít nhất một lần) | Chấp nhận được; ghi chú vận hành |
| P2-10 | Khi ví tắt, chữ khách gõ (kể cả STK) lưu vào `link_requests.original_url` | Không lưu chữ không phải link |
| P2-11 | Đồng bộ Shopee chạy trong vòng poll, có thể làm bot đứng vài phút | Tách luồng khi bật tự đồng bộ |

---

## 10. Lộ trình

**NOW, trước khi mở rộng người dùng:**
0. Sửa nhanh, mỗi việc vài dòng code: bọc lỗi từng update (P0-4); không log nguyên văn lỗi mạng có thể chứa token, chmod log (P1-8); cron backup hằng ngày (P1-9).
1. Chủ bot quyết định công khai hay chỉ allowlist (P1-1).
2. Giữ ví **tắt**. Đồng bộ tay để theo dõi đơn, không hứa chi.
3. Sửa chữ /admin và màn mô phỏng (P1-3), ghi audit cho chi trả (P1-5). Việc nhỏ.
4. Trang "Điều khoản ngắn" cho khách: điều kiện ghi nhận, số dự kiến và số duyệt, link chia sẻ thì tiền về người tạo link, thay đổi chính sách, liên hệ.

**BEFORE PAYMENT, bắt buộc trước khi có tiền hoàn thật:**
1. P0-1: "có thể rút" chỉ khi Shopee duyệt (không gian lận, qua kỳ duyệt), và có dòng điều chỉnh khi hoa hồng giảm sau khi vào ví.
2. P0-2: admin nhập số Shopee đã trả theo kỳ; tổng có thể rút ≤ số đó trừ dự phòng.
3. P0-3: quyết định thuế (kế toán), ghi ADR.
4. P1-7: quét thử QR thật; thêm trần rút mỗi tháng.
5. P1-4: snapshot chính sách trên link.
6. Kênh khiếu nại tối giản và quy định tạm giữ khi nghi gian lận.

**LATER, tăng giữ chân khách:**
- Hạng thành viên (dữ liệu từ đơn đã duyệt).
- Bật tự đồng bộ khi API ổn định.
- Ngày khuyến mãi.
- Hoàn nhanh có ngân sách (chỉ khi có lãi ổn định).
- Lệnh xem hoặc xoá dữ liệu cá nhân.

---

## 11. Sẵn sàng phát hành

| Mảng | Kết luận | Lý do |
|---|---|---|
| Telegram Bot | **GO** | 292 tin gửi, lỗi chỉ là lỗi mạng tạm và được thử lại |
| Tạo link affiliate | **GO** | 28/28 link, Sub ID duy nhất |
| Theo dõi Sub ID | **CONDITIONAL** | 7 click, 2 đơn khớp. Mẫu nhỏ, phụ thuộc cookie và API nội bộ |
| Ước tính hoàn | **CONDITIONAL** | Lệch 17–43% so với thực tế. Chữ đã nói rõ |
| Cấu hình admin | **CONDITIONAL** | Chạy thật, nhưng chữ gây hiểu nhầm và có khe hở hồi tố 10 phút |
| Hạng thành viên | **NO-GO** | Chỉ giao diện |
| Theo dõi đơn | **CONDITIONAL** | Chạy khi admin bấm. Chưa có trạng thái duyệt |
| Đối soát hoa hồng | **NO-GO** | Chưa đọc duyệt hay gian lận, chưa đối chiếu kỳ trả |
| Thuế & phí | **CONDITIONAL** cho ước tính, **NO-GO** cho quyết toán | Chỉ là dự phòng |
| Ví | **NO-GO** (giữ tắt) | Sai mốc "có thể rút" (P0-1) |
| Chi trả | **NO-GO** | P0-1, P0-2, P0-3, QR chưa thử thật |
| An toàn tài chính | **NO-GO** cho chi trả, **GO** cho giai đoạn chỉ ước tính | Khách chỉ được ghi theo HH thật, chưa chi đồng nào |
| Bảo mật & độ tin cậy | **CONDITIONAL** | Khoá một process, chống trùng update, hàng đợi có retry, cookie 0600 đều chạy. Cần sửa P0-4 (update hỏng làm bot im lặng), P1-8 (token có thể vào log), P1-9 (backup tay) trước khi mở rộng |

GO của một mảng không có nghĩa là toàn hệ thống đã sẵn sàng.

---

## 12. Quyết định đang chờ chủ bot

1. Bot **công khai** hay chỉ cho danh sách người được mời?
2. Mốc "có thể rút": theo kỳ duyệt của Shopee, hay admin tự xác nhận từng kỳ?
3. Thuế: chủ bot đăng ký loại hình nào, và có khấu trừ thuế người nhận không (cần kế toán)?
4. Có hạn mức rút mỗi tháng không, bao nhiêu?
5. Link chia sẻ cho người khác thì tiền về ai? Ghi vào điều khoản.
6. Có giữ ước tính theo giá niêm yết, hay giảm theo hệ số an toàn?
7. Hạng thành viên: bao giờ bật, điều kiện gì? Đề xuất để sau khi có ít nhất vài chục đơn đã duyệt.

---

## Năm câu trả lời

**Q1. Hiện Cashback Bot làm được gì cho người dùng thật?**
Dán link Shopee thì nhận ngay link mua có mã theo dõi và số hoàn dự kiến. Mua qua link thì bot nhận ra đơn và biết đơn của ai, khi admin bấm đồng bộ. Đã chứng minh với 2 đơn thật. Khách **chưa nhận được tiền**: ví đang tắt và chưa có quy trình duyệt hay chi.

**Q2. Chức năng nào nhìn như có nhưng thực tế chưa hoạt động?**
- Hạng thành viên: có nút, có bản nháp, có xác nhận, nhưng DB khoá `customer_effect='none'`.
- Hồ sơ thuế PERSONAL, CNKD, HKD và công thức quyết toán: có code và test, không nối vào báo giá hay ví.
- Ví và rút tiền: có đủ, đang tắt.
- Màn 🧮 Mô phỏng: không phản ánh V1.2.
- "Nội dung lệnh": chữ tĩnh.
- Allowlist: bị cờ công khai vô hiệu.

**Q3. Mở rộng thêm người dùng ngay thì gặp lỗi gì?**
- Tạo link chạy ổn, nhưng có một điểm hỏng đơn lẻ: một tin nhắn khiến code ném lỗi lặp lại sẽ làm **cả bot ngừng trả lời mọi người** (P0-4). Người dùng càng nhiều, khả năng gặp tin lạ càng cao.
- Lỗi mạng Telegram có thể ghi token bot vào log (P1-8, chưa xảy ra).
- Các vấn đề khác: khách thấy số hoàn cao hơn thực tế (17–43%); quota AddLiveTag bị dùng nhiều hơn; đối soát vẫn phải bấm tay bằng cookie, có thể hỏng nếu Shopee đổi API.
- Nếu đồng thời bật ví thì có rủi ro chi tiền Shopee không trả (P0-1, P0-2).

**Q4. Còn thiếu chính xác những gì để bắt đầu đối soát và hoàn tiền thật?**
1. Đọc trạng thái **duyệt hoặc gian lận** của Shopee và chỉ cho rút khi đã duyệt.
2. Ghi điều chỉnh khi hoa hồng giảm sau khi vào ví.
3. Đối chiếu với **số tiền Shopee đã trả** theo kỳ, kèm trần quỹ.
4. Quyết định thuế.
5. Thử một lần chi thật bằng QR với số nhỏ.
6. Điều khoản và kênh khiếu nại tối giản.

**Q5. Chỉ được làm ba việc tiếp theo thì làm gì, vì sao?**
1. **Sửa mốc "có thể rút" theo Shopee duyệt, kèm điều chỉnh khi hoa hồng đổi (P0-1).** Đây là chỗ duy nhất có thể làm chủ bot mất tiền thật. Code nằm gọn trong `wallet.refresh` và `shopee_sync`, không phải xây lại.
2. **Bước đối chiếu kỳ Shopee đã trả và trần quỹ (P0-2).** Đảm bảo chỉ chi từ tiền đã về tay. Việc này đơn giản: admin nhập số kỳ, bot so sánh.
3. **Chốt chính sách cho khách**: quyết định công khai, viết điều khoản ngắn, quyết định thuế. Không tốn nhiều code, nhưng là điều kiện để mở rộng an toàn và để chi tiền đúng luật.

Ngoài ba việc trên, ba sửa nhanh P0-4, P1-8, P1-9 mỗi việc chỉ vài dòng. Nên gộp làm ngay trong một PLAN kỹ thuật nhỏ, trước khi có thêm người dùng.
