# Điều khoản V3 — bản nháp để chủ bot duyệt (2026-10-25)

Nguồn: V2 đang hiệu lực (`cashback_bot/terms_content.py`) + quyết định ADR-059.
**Chưa đưa vào bot.** Chỉ đưa vào code và công bố khi ví sắp mở, sau khi xong 3 PLAN backend (chờ 7 ngày khi đổi tài khoản, trừ khi Shopee thu hồi, đọc báo cáo thanh toán). Nếu công bố trước, điều khoản hứa những việc bot chưa làm.

Chủ bot đã trả lời các câu hỏi (2026-10-25): hạn mức ngày / tháng tính theo từng khách và khách được rút số lớn một lần; không thêm câu "tự chịu nghĩa vụ thuế"; đổi mức không cần báo trước.

## Tóm tắt thay đổi so với V2

| Mục | V2 | V3 |
|---|---|---|
| 📋 Điều khoản chung, phần 2 | "Ví hoàn tiền và chi trả chưa mở" | Có ví; ví chỉ chạy khi người vận hành bật |
| 💰 Ghi nhận và cách tính | "Bot chưa mở bước 5" | Khi nào khoản vào ví (3 điều kiện); không khấu trừ thuế khi chuyển |
| 🚫 Đơn không được hoàn | "Cách xử lý khoản đã chi sẽ quy định sau" | Shopee thu hồi: trừ vào khoản sau, tạm khoá rút, không đòi chuyển trả |
| 👛 Ví và rút tiền | (chưa có) | **Mục mới:** điều kiện rút, tài khoản nhận, chuyển tiền, đổi mức |
| 🛡 Dữ liệu cá nhân | | Thêm dữ liệu ngân hàng và chứng từ chi trả |
| 📩 Hỗ trợ và khiếu nại | | Giữ nguyên |

---

## 📋 Điều khoản chung

Phần 1 và 3 giữ nguyên V2. Phần 2 thay bằng:

**2. Ví hoàn tiền**
- Khoản hoàn đủ điều kiện được ghi vào ví của bạn trong bot. Bạn rút về tài khoản ngân hàng theo mục 👛 Ví và rút tiền.
- Ví chỉ hoạt động khi người vận hành bật. Khi ví tạm tắt, khoản đã ghi nhận vẫn được giữ và yêu cầu rút đang chờ vẫn được xử lý.

## 💰 Ghi nhận và cách tính

Phần 1 và 3 giữ nguyên V2. Phần 2 đổi câu cuối, phần 4 viết lại:

**2. Số hoàn dự kiến** (chỉ đổi câu cuối)
- … Cách tính hiện hành trừ trước các khoản dự phòng phí và thuế của người vận hành, rồi chia một phần cho bạn. Khoản dự phòng **không phải** số thuế bạn phải nộp. Khi chuyển tiền cho bạn, bot không trừ thêm thuế hay phí.

**4. Các bước của một đơn**
1) Shopee ghi nhận đơn → 2) hoa hồng chờ Shopee xác minh → 3) Shopee duyệt hoa hồng → 4) Shopee thanh toán cho người vận hành, và người vận hành đối soát khớp với tiền thực nhận → 5) khoản vào ví.

Khoản vào ví khi đủ **cả ba**:
- Shopee đã duyệt hoa hồng của đơn.
- Shopee đã thanh toán và đối soát khớp.
- Đã qua số ngày giữ tiền tính từ khi đơn hoàn thành (hiện **15 ngày**, xem trong 👛 Ví).

Thường mất vài tuần đến vài tháng sau khi đặt hàng, tuỳ lịch duyệt và thanh toán của Shopee.

## 🚫 Đơn không được hoàn

Giữ nguyên V2. Câu cuối thay bằng:
- Nếu Shopee giảm hoặc thu hồi hoa hồng của một đơn: khoản chưa vào ví giảm theo. Khoản đã chi được **trừ vào các khoản hoàn sau** của bạn.
- Khi còn khoản phải trừ, bạn tạm chưa rút được cho tới khi trừ đủ. Bot không yêu cầu bạn chuyển trả tiền.
- Đơn Shopee gắn cờ gian lận không được vào ví.

## 👛 Ví và rút tiền (mục mới)

**1. Điều kiện rút**
- Bạn đã đồng ý phiên bản điều khoản này trong bot.
- Số dư rút được từ mức tối thiểu trở lên (hiện **10.000đ**).
- Mỗi lần một yêu cầu: yêu cầu trước xong mới tạo được yêu cầu mới.
- Mỗi yêu cầu, và tổng rút của bạn mỗi ngày, mỗi tháng, không vượt hạn mức đang hiện trong 👛 Ví. Chạm hạn mức ngày hoặc tháng thì bạn rút tiếp vào ngày hoặc tháng sau.

**2. Tài khoản nhận tiền**
- Tài khoản ngân hàng phải đứng tên bạn, và tên chủ tài khoản phải trùng tên bạn khai.
- Người vận hành kiểm tra tên người nhận trước khi chuyển. Tên không khớp thì yêu cầu bị từ chối và tiền trở lại ví.
- **Đổi tài khoản:** sau khi đổi, bạn chờ 7 ngày mới rút về tài khoản mới. Người vận hành có thể xác minh và cho rút sớm hơn. Yêu cầu đang chờ mang tài khoản cũ sẽ được kiểm tra lại.

**3. Chuyển tiền**
- Người vận hành chuyển khoản thủ công trong **3–7 ngày làm việc** kể từ khi bạn gửi yêu cầu.
- Nội dung chuyển khoản: `Hoan tien` kèm mã yêu cầu.
- Bạn nhận đúng số tiền trong yêu cầu, không bị trừ phí hay thuế.
- Chuyển xong, bot báo bạn kèm mã giao dịch ngân hàng. Chuyển lỗi hoặc ngân hàng hoàn lại thì tiền trở lại ví.

**4. Thay đổi mức**
- Mức tối thiểu, hạn mức rút và số ngày giữ tiền có thể thay đổi. Mức đang áp dụng luôn hiện trong 👛 Ví.
- Mức mới áp dụng cho yêu cầu tạo sau khi đổi. Số ngày giữ mới áp dụng cho đơn chưa vào ví; khoản đã vào ví giữ nguyên.

## 🛡 Dữ liệu cá nhân

Giữ nguyên V2, thêm vào "Bot lưu những gì":
- Khi dùng ví: ngân hàng, số tài khoản và tên chủ tài khoản bạn khai; lịch sử yêu cầu rút và chứng từ chuyển khoản (mã giao dịch).

Thêm vào "Bảo vệ và lưu giữ":
- Chứng từ chi trả được giữ để đối soát và kê khai thuế khi cần.

## 📩 Hỗ trợ và khiếu nại

Giữ nguyên V2.
