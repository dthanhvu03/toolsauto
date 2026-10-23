# PLAN-060 — Viết lại UI/UX Telegram của cashback_bot

| | |
|---|---|
| Trạng thái | **APPROVED (user, 2026-10-23)** — P0–P4 xong; P5 còn bấm thử trên chat thật sau restart |
| Người soạn | Claude Code (2026-10-23) |
| Executor | Claude Code toàn bộ P0–P5 (user trực tiếp giao cả P1 ngày 2026-10-23, thay Codex) |
| Phạm vi | `cashback_bot/` + `tests/test_cashback_*.py` |
| Ngoài phạm vi | Công thức tính tiền, policy V1.2, đối soát, chi trả, tracking đơn |

---

## 1. Hiện trạng (đã đọc code ngày 2026-10-23)

### Phía khách
- `/start`, `/help`, `/huongdan`, `/dieukien`, `/cachtinh`, `/hang` đều là khối chữ dài, không có nút. Khách phải gõ lệnh để đi tiếp.
- Mỗi tin đều lặp lại cảnh báo "thử nghiệm / chưa chi trả / chỉ ước tính" (4–5 lần trong một phiên). Cảnh báo quan trọng bị chìm.
- Giọng văn không thống nhất: bản V1.1 dùng emoji + tiêu đề IN HOA; bản V1.2 (`how_to_calc_v12`, `render_success_v12`) không emoji, có chữ "Cashback" tiếng Anh, đoạn cảnh báo dài 3 câu.
- Thẻ kết quả link chỉ có 1 nút Mua. Không có đường tới "Lưu ý trước khi mua", đúng thời điểm khách cần nhất.
- Lỗi (`INVALID_LINK`, `STALE`, `NOT_FOUND`, `GENERIC_FAIL`) không có nút; giọng mỗi tin một kiểu.
- Không có trạng thái chờ khi gọi Product Data. Khách gửi link xong không thấy phản hồi gì cho tới khi có kết quả.
- Không đặt description / short description qua BotFather API → màn "What can this bot do?" trước khi bấm Start trống hoặc lỗi thời.

### Phía admin (`/admin`)
- **Lỗi hiển thị:** `admin_ui.py` gọi `.replace(",", ".")` trên cả đoạn văn (chuỗi nối ngầm). Kết quả thật: `Hạng Đồng. Bạc. Vàng đang là mức định hướng. chưa áp dụng`, `0.98%` thay vì `0,98%`. Lỗi có ở `policy_text`, `rank_text`, `fee_text`, `_rank_preview`.
- **Lỗi hiển thị:** `home_text` in lặp: "Tỷ lệ đang áp dụng" và "Tỷ lệ ước tính hiện tại" cùng một số; "Đối soát &amp; chi trả" in 2 lần.
- Nút "◀️ Quay lại" và "🏠 Tổng quan" cùng trỏ về `c:menu:home`, nên hai nút làm cùng một việc.
- Bấm nút hết hạn / không hợp lệ: `handle_callback` trả `BotReply` chỉ có chữ, không có bàn phím. `editMessageText` thay cả màn hình bằng 1 câu và **xoá hết nút** → ngõ cụt.
- Lúc đang chờ nhập số cho bản nháp, không có nút Hủy. Bản nháp treo tới khi hết hạn 10 phút và vẫn được đếm vào "Bản nháp đang chờ".
- Sau Xác nhận / Hủy, màn hình còn 1 câu thông báo + menu chính, không quay về màn vừa sửa.
- Màn Thuế & phí hardcode `fee_bps = 98`, `tax_bps = 1000`, không đọc settings / bản đã lưu.
- Lịch sử in mã thô `confirm · confirmed · 2026-10-23T03:12:00Z` (UTC, tiếng Anh).

### Thông báo admin (`admin_notify.py`)
- Tiêu đề mã tiếng Anh `NEW_USER`, `LINK_SENT`, `REQUEST_FAILED`; tin nào cũng kêu chuông, kể cả LINK_SENT thường ngày.

### Ràng buộc kỹ thuật (quyết định ai làm phần nào)
- Bảng `outbound_messages` chỉ lưu `button_url`. Khi gửi lại (retry), `_markup(row["button_url"])` dựng lại **chỉ nút Mua**; mọi `inline_keyboard` khác bị mất. Hiện admin menu đã dính lỗi này khi retry. Thêm nút cho khách bắt buộc phải lưu cả `reply_markup`. Phần này là migration + worker → **Codex**.
- `service._handle_callback` đẩy mọi callback sang `admin_panel` → khách bấm nút sẽ nhận "Lệnh này chỉ dành cho quản trị". Cần tách namespace callback (`u:` cho khách, `c:` cho admin) trong `service.py` → **Codex**.
- `answer_callback` chưa nhận `text` / `show_alert` → chưa có toast / popup.

---

## 2. Tham khảo bên ngoài và rút ra gì

| Nguồn | Điều rút ra | Áp vào |
|---|---|---|
| [Telegram Bot Features](https://core.telegram.org/bots/features) (chính thức) | Hỗ trợ `/start`, `/help`; dùng inline keyboard cho điều hướng; **sửa tin thay vì gửi tin mới** khi chuyển trang; description ≤512 ký tự hiện trước khi Start; about ≤120 ký tự; luôn `answerCallbackQuery`; deep link `?start=<param>` | Khách: home có nút, đổi trang bằng edit; đặt description/about |
| [GramIO — UX Patterns](https://gramio.dev/guides/ux-patterns) | Button-first; `/start` là "trang chủ", không phải danh sách lệnh; ≤4 hàng nút; tác vụ >300ms phải có trạng thái chờ; toast cho xác nhận nhẹ, alert cho lỗi cần đọc; xác nhận phá huỷ: nút an toàn trước, nhắc lại hệ quả; Back ở hàng cuối, Home khi sâu >2 cấp; breadcrumb trong text; empty state có lời gợi ý; ≤5 lệnh trong `setMyCommands`, lệnh admin scope riêng | Toàn bộ khung điều hướng admin + khách |
| [Telegram editMessageText rules (tested)](https://charliemorrison.dev/blog/telegram-edit-message-rules-tested/) | Edit không kèm `reply_markup` = **xoá nút**; cùng text + cùng nút = lỗi 400 "not modified"; giới hạn 4096 ký tự, vượt thì bị từ chối, không cắt | Mọi màn phải trả lại keyboard; giữ màn admin dưới ~3500 ký tự |
| [Inline keyboard guide](https://botnamefinder.com/blog/telegram-inline-keyboard-builder-guide) | `callback_data` 1–64 byte; 3–4 nút/hàng trên điện thoại | Mã callback ngắn `u:p:calc` |
| Bot hoàn tiền VN: [hoantiensanpham](https://hoantiensanpham.com/bot-guide), [RyBot](https://rybot.vn/), [Shopple](https://shopple-cashback-production.up.railway.app/) | Mẫu chung: dán link → thẻ "✅ đã nhận" + tên SP + số hoàn + 1 nút mua lớn; phản hồi nhanh ~1s; tách rõ "chờ duyệt" và "đã duyệt" | Thẻ kết quả gọn, số tiền là tiêu điểm; giữ nhãn "dự kiến" xuyên suốt |

Ghi chú: nguồn bot VN là trang tự giới thiệu, chỉ dùng tham khảo bố cục, không coi là bằng chứng hiệu quả.

---

## 3. Nguyên tắc thiết kế mới

1. **Một tin sống cho điều hướng.** Đổi trang = `editMessageText`. Tin mới chỉ cho: kết quả link, lỗi, thông báo.
2. **Số tiền là tiêu điểm.** Thẻ kết quả: số hoàn dự kiến in đậm ở đầu, tên SP + giá phía dưới.
3. **Cảnh báo một dòng, chi tiết một chỗ.** Mỗi tin tối đa 1 dòng `ⓘ`. Toàn bộ giải thích nằm ở trang "Cách tính".
4. **Một bộ từ vựng.** Khách: "hoàn dự kiến" (không dùng "cashback", "hoa hồng" chỉ xuất hiện ở trang Cách tính). Admin: "Đang áp dụng" / "Bản nháp" / "Mô phỏng" (giữ 3 nhãn đã có).
5. **Không ngõ cụt.** Mọi màn có nút đi tiếp. Nút hết hạn → popup alert, giữ nguyên màn hình.
6. **Phản hồi tức thì.** Callback luôn được answer; gửi link → `sendChatAction typing` trước khi gọi Product Data.
7. **Nút an toàn đứng trước.** `[✖️ Hủy] [✅ Xác nhận lưu]`, text nhắc lại hệ quả.

---

## 4. Thiết kế màn hình

### 4.1 Khách — Trang chủ (`/start`, `/help`, lệnh lạ)

```
🎁 <b>Xem món Shopee được hoàn bao nhiêu</b>

Dán link sản phẩm Shopee vào đây.
Bot trả lại link mua và số tiền hoàn dự kiến.

ⓘ Đang thử nghiệm: số hoàn là ước tính, chưa chi trả.

[ 📖 Cách dùng ]      [ 🛡️ Để được ghi nhận ]
[ 💰 Cách tính ]
```
- `/hang` + nút Hạng **ẩn** khi `MEMBERSHIP_CUTOVER = False` (trang "chưa áp dụng" chỉ gây nhiễu). Lệnh `/hang` gõ tay vẫn trả lời.
- Các trang con đổi bằng edit, hàng cuối luôn `[ ◀️ Trang chủ ]`.
- `setMyCommands` còn: `start`, `huongdan`, `dieukien`, `cachtinh`, `help` (≤5). `/admin` đăng ký riêng với `scope=chat` cho từng admin.

### 4.2 Khách — Thẻ kết quả link

```
✅ <b>Đã tạo link hoàn tiền</b>

💰 Hoàn dự kiến: <b>12.345đ</b>

🛍️ Áo thun nam cổ tròn Cotton
Giá tham khảo: 189.000đ

ⓘ Số ước tính, chỉ chắc khi Shopee xác nhận đơn.

[ 🛒 Mua trên Shopee ]                       ← url
[ 🛡️ Lưu ý trước khi mua ]                   ← callback → popup alert ≤200 ký tự
```
- Một template cho cả V1.1 và V1.2; chỉ khác dòng `ⓘ` (V1.2: "đã trừ dự phòng phí và thuế").
- Popup "Lưu ý" (alert, không tạo tin mới, không đè thẻ): 3 ý ngắn: xoá SP cũ khỏi giỏ, mở đúng link này, không bấm sang link khác.

### 4.3 Khách — Lỗi (một khuôn)

```
⚠️ <b>{Tiêu đề ngắn}</b>
{1 câu nguyên nhân}
{1 câu cần làm gì}

[ 📖 Cách lấy link ]   (chỉ với lỗi link sai)
```
Áp cho: link sai, không thấy SP, dữ liệu chưa sẵn, lỗi tạo link, gửi quá nhiều, tài khoản chưa mở.

### 4.4 Admin — Khung

```
⚙️ Quản trị › Hạng thành viên            ← breadcrumb dòng đầu

🟢 Đang áp dụng   …
🟡 Bản nháp       …
🔵 Mô phỏng       …

[ 🥉 Đồng ] [ 🥈 Bạc ] [ 🥇 Vàng ]
[ ◀️ Tổng quan ]                          ← cấp 1: một nút duy nhất
```
- Tổng quan: bỏ dòng lặp, gom thành khối trạng thái 5 dòng.
- Nhập số (cấp 2): hiện giá trị đang lưu, khoảng hợp lệ, ví dụ; nút `[ ✖️ Hủy bản nháp ] [ ◀️ Quay lại ]`.
- Xem trước: `[ ✖️ Hủy ] [ ✅ Xác nhận lưu ]`, nhắc lại "Chưa áp dụng cho khách".
- Sau Xác nhận/Hủy: toast "Đã lưu phiên bản vN" / "Đã hủy" + quay lại **màn vừa sửa** (không phải menu chính).
- Nút hết hạn / sai người: alert popup, giữ nguyên màn.
- Lịch sử: `23/10 10:12 · Hạng Bạc 65% → 66% · Đã lưu` (giờ VN, tiếng Việt).

### 4.5 Thông báo admin

```
🔗 <b>Link mới</b> · @username
Áo thun nam cổ tròn…
189.000đ · hoàn 12.345đ
<code>sub_id</code> · 10:12 23/10
```
- `NEW_USER` / `LINK_SENT`: `disable_notification=true` (im lặng).
- `REQUEST_FAILED`: có chuông, tiêu đề `⚠️ Lỗi: {mô tả tiếng Việt}`.

---

## 5. Kế hoạch thực hiện

| Phase | Việc | Executor | File | Ghi chú |
|---|---|---|---|---|
| **P0** | Sửa lỗi `,`→`.`; bỏ dòng lặp ở Tổng quan; nút hết hạn trả lại keyboard thay vì ngõ cụt | Claude Code | `admin_ui.py`, `admin_policy.py`, test admin | Không đổi hành vi tiền. Làm được ngay khi duyệt |
| **P1** | Hạ tầng: cột `reply_markup_json` cho `outbound_messages` (retry giữ nút); `answer_callback(text, show_alert)`; `send_chat_action`; `set_my_description` / `set_my_short_description`; `setMyCommands` scope admin; `disable_notification` cho admin notify; routing callback `u:` vs `c:` trong `service.py`; `BotReply` thêm `toast` / `alert` | **Codex** | `db.py` + migration `005_*`, `telegram_api.py`, `poller.py`, `service.py`, `messages.py` (dataclass) | Backend, ngoài vai Claude Code. Cần backup DB trước migration |
| **P2** | Viết lại copy khách: trang chủ + 3 trang con + thẻ kết quả + khuôn lỗi + popup lưu ý + description/about | Claude Code | `messages.py`, test copy | Phụ thuộc P1 cho nút và popup; phần chữ làm song song được |
| **P3** | Viết lại màn admin: breadcrumb, nút theo cấp, Hủy ở bước nhập, quay về màn vừa sửa, lịch sử dễ đọc | Claude Code | `admin_ui.py`, `admin_policy.py` (chỉ phần render/keyboard) | Màn Thuế & phí đọc số thật → Codex (logic) |
| **P4** | Restyle thông báo admin | Claude Code | `admin_notify.py` | Phụ thuộc `disable_notification` ở P1 |
| **P5** | Verify: pytest toàn bộ `tests/test_cashback_*.py`; script in ra mọi màn để soát chữ; bấm thử trên chat thật bằng tài khoản allowlist | Claude Code + user | — | Restart bot phải được user đồng ý |

Thứ tự: P0 → (P1 ∥ P2 phần chữ) → P2 gắn nút → P3 → P4 → P5.

### Số file mỗi phase
P0: 2 file code + 1–2 file test. P1 vượt 3 file nhưng là feature hạ tầng, không phải sửa bug; Anti tách thành TASK riêng cho Codex.

---

## 6. Tiêu chí xong (Acceptance)

- [x] Không còn chuỗi `.replace(",", ".")` áp lên cả đoạn văn; `0,98%` hiển thị đúng; test bắt được.
- [x] Tổng quan admin không có dòng lặp.
- [x] Mọi màn admin và khách có ít nhất 1 nút đi tiếp; bấm nút hết hạn không làm mất keyboard.
- [x] Gửi lại (retry) một tin có inline keyboard vẫn còn đủ nút (test poller).
- [x] `/start` có nút; chuyển trang bằng edit, không sinh tin mới (test `edit_message_id`).
- [x] Thẻ kết quả V1.1 và V1.2 dùng chung một template; khách không thấy chữ "cashback"/"hoa hồng" ngoài trang Cách tính (ngoại lệ `/dieukien`, `/hang`, xem P2).
- [x] Mỗi tin khách có ≤1 dòng cảnh báo `ⓘ`.
- [x] Popup "Lưu ý" ≤200 ký tự.
- [x] Mọi màn <3500 ký tự.
- [x] `setMyCommands` khách ≤5 lệnh; `/admin` chỉ hiện với admin.
- [x] pytest `tests/test_cashback_*.py` xanh (137 test).
- [ ] Ảnh chụp chat thật: trang chủ, thẻ kết quả, popup, 1 lỗi, admin Tổng quan, 1 lượt sửa hạng. **Chờ user restart bot rồi bấm thử.**

## 7. Câu hỏi cần user/Anti chốt

User duyệt 2026-10-23, câu 1–3 lấy theo đề xuất:

1. ✅ Xưng hô: giữ "bạn / mình".
2. ✅ Ẩn `/hang` khỏi menu khách cho tới khi bật hạng thành viên.
3. ✅ Không dùng reply keyboard cố định; dùng inline + Menu button.
4. ⏳ **Restart bot** để verify trên chat thật: **chưa có thời điểm**. Không restart cho tới khi user nói.

---

## 8. Proof / Log thực thi

### P0 — Claude Code — 2026-10-23 — DONE (chưa commit, chưa restart bot)

- `admin_ui.py`: bỏ mọi `.replace(",", ".")` áp lên đoạn văn; số tiền định dạng từng số bằng `money.format_vnd`. Bỏ dòng "Tỷ lệ ước tính hiện tại" và dòng "Đối soát và chi trả" lặp ở `home_text`.
- `admin_policy.py`: `_rank_preview` dùng `format_vnd`; `handle_callback` tách ra `_route_callback`. Callback admin trả về không có nút thì gắn `NAV_KEYBOARD` (nút hết hạn, bản đã xử lý, DB chưa mở không còn là ngõ cụt).
- Test mới trong `tests/test_cashback_admin_ui_ux.py`: `test_dau_phay_trong_cau_chu_khong_bi_doi_thanh_dau_cham`, `test_tong_quan_khong_lap_dong`, `test_nut_het_hieu_luc_van_giu_nut_dieu_huong`.
- Proof: trên code cũ 3 test mới **3 failed**; trên code mới `.venv/bin/python -m pytest tests/test_cashback_*.py -q` → **122 passed** (nền 119 + 3).
- Để lại cho P3: `AdminPanel._simulation_text` (không có chỗ gọi) còn `.replace(",", ".")` cũ, xoá khi dọn admin.
- Bot đang chạy vẫn dùng code cũ tới khi restart.

### P2 (phần chữ, chưa gắn nút) — Claude Code — 2026-10-23 — DONE (chưa restart bot)

- `messages.py`: viết lại theo khuôn mục 3–4. `/start`, `/help`, lệnh lạ dùng chung `HOME` (tạm liệt kê 3 lệnh, sẽ thay bằng nút sau P1). Thẻ kết quả V1.1/V1.2 chung `_render_card`, chỉ khác dòng `ⓘ`; hoàn 0đ đổi tiêu đề thành "Đã tạo link mua". Lỗi chung khuôn tiêu đề + nguyên nhân + việc cần làm. `BOT_COMMANDS` bỏ `hang` (còn 5); gõ `/hang` vẫn trả lời.
- `admin_ui.py`: màn "Nội dung lệnh" khớp danh sách lệnh mới.
- Giữ nguyên các câu an toàn test đang ép: "không thu phí sử dụng", "không bảo đảm đơn hàng được ghi nhận", "không bảo đảm Shopee sẽ ghi nhận hoa hồng", "Chưa phải tiền có thể rút.", "Shopee xác nhận đơn hợp lệ", "chưa chính thức áp dụng".
- Ngoại lệ từ vựng: "hoa hồng" vẫn xuất hiện ở `/dieukien` (câu an toàn) và `/hang` (tỷ lệ), không chỉ `/cachtinh`.
- ✅ **Chủ bot đã duyệt chữ hiển thị mới, gồm cả V1.2 (2026-10-23)** (ADR-045: cắt V1.2 chỉ sau khi duyệt câu hiển thị): `how_to_calc_v12` và dòng `ⓘ` thẻ V1.2. Duyệt chữ **không** bật V1.2; vẫn cần backup, migration `001` trên bản sao, `CASHBACK_ESTIMATE_POLICY=v1.2`, restart (xem `POLICY_V12.md`).
- Test: cập nhật assert tiêu đề ở `test_cashback_bot.py`, `test_cashback_v11.py`, `test_cashback_v12.py`; thêm `test_khuon_chu_khach_plan_060` (≤1 dòng ⓘ, không chữ "cashback", thẻ không nhắc "hoa hồng", <3500 ký tự, thẻ 0đ). Proof: `.venv/bin/python -m pytest tests/test_cashback_*.py -q` → **123 passed**.

### P1 + P2 gắn nút + P3 + P4 — Claude Code — 2026-10-23 — DONE (chưa restart bot)

User giao Claude Code làm luôn P1 thay Codex.

- **P1 hạ tầng:** `db.py` thêm cột `outbound_messages.reply_markup_json` (qua `_add_column`, NULL được); `enqueue_outbound` lưu bàn phím đầy đủ; `poller._row_markup` dùng bàn phím đã lưu khi gửi lại, dòng cũ vẫn dựng nút Mua. `telegram_api.py`: `answer_callback(text, show_alert)`, `send_chat_action`, `set_my_description`, `set_my_short_description`, `set_my_commands(commands, scope)`, `send_message(disable_notification)`. `poller._register_profile` đăng ký lệnh khách, mô tả, và `/admin` theo scope chat từng admin. `poller._typing` gửi "đang gõ" khi nhận tin không phải lệnh. Reply có `text` rỗng chỉ trả lời callback, không ghi hàng đợi. `service.py` tách callback `u:` (khách) và `c:` (admin).
- **P2 gắn nút:** trang chủ 3 nút (Hạng chỉ hiện khi `MEMBERSHIP_CUTOVER`); trang con có `◀️ Trang chủ`, đổi trang bằng edit; thẻ kết quả thêm nút `🛡️ Lưu ý trước khi mua` → popup; link sai có nút `📖 Cách lấy link`; khách chưa mở bấm nút → popup.
- **P3 admin:** viết lại `admin_ui.py`: breadcrumb, menu 3×2, màn cấp 1 một nút `◀️ Tổng quan`, bước nhập số hiện giá trị đang lưu + nút `✖️ Hủy bản nháp`, xem trước `✖️ Hủy` / `✅ Xác nhận lưu`. Xác nhận/hủy → toast + quay về màn vừa sửa kèm dòng thông báo. Màn Thuế & phí đọc bản đã lưu hoặc mặc định từ settings (bỏ hardcode 98/1000). Lịch sử giờ VN, tiếng Việt. Xoá `_simulation_text` chết. Nhập số sai vẫn có nút Hủy.
- **P4 thông báo admin:** tiêu đề tiếng Việt; `NEW_USER`/`LINK_SENT` gửi im lặng; **sửa lỗi** `flush_pending` không bắt `TelegramDeliveryError` (trước đây làm văng vòng poll).
- **Lệch so với plan:** nút admin hết hạn / đã xử lý vẫn sửa tin thành câu giải thích + `◀️ Tổng quan` (P0) thay vì popup, vì trạng thái bản nháp đã đổi thật.
- **Migration thử trên bản sao** `data/backups/cashback-20261023T081443Z.sqlite`: thêm cột, chạy 2 lần không lỗi, 65 dòng outbound giữ nguyên, `integrity_check` ok.
- **Test:** cập nhật assert thiết kế ở `test_cashback_admin.py`, `test_cashback_admin_ui_ux.py`, `test_cashback_bot.py`; fake Telegram nhận thêm tham số. Thêm `tests/test_cashback_plan060.py` (14 test). Proof: `.venv/bin/python -m pytest tests/test_cashback_*.py -q` → **137 passed**.
