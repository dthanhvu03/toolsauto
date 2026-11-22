# ZT báo mã — gói nội dung thử đã chuẩn bị

Trạng thái: bản nháp, chưa gửi/ghim/đăng, chưa tạo link mời mới, chưa đổi quyền riêng tư kênh. Chủ bot đang hỏi cách sử dụng kênh; việc mở link mời kênh riêng tư ra Threads cần được duyệt cụ thể.

## 1. Bài hướng dẫn đề xuất ghim

🎟 Bắt đầu ở đây — ZT báo mã

Kênh tổng hợp mã và món Shopee để bạn tham khảo trước khi mua.

• Đọc kỹ đơn tối thiểu, mức giảm tối đa, ngành hàng và thời gian áp dụng; kiểm tra lại ở bước thanh toán. Mã có thể hết lượt hoặc không áp dụng cho tài khoản/món của bạn.
• Muốn xem số hoàn dự kiến: sao chép link sản phẩm, gửi vào Cashbot, rồi mua bằng link bot trả riêng cho bạn. Link mua công khai trong kênh không tự ghi hoàn vào tài khoản Cashbot của bạn.
• Chỉ mua khi giá cuối phù hợp ngân sách. Đừng mua thêm chỉ để đủ điều kiện mã.

Một số đường dẫn là link tiếp thị liên kết.
👉 Mở Cashbot: https://t.me/zt_shopee_bot?start=zt_channel_guide

## 2. Bài Threads đề xuất, chưa đăng

Lưu mã Shopee rồi đến lúc thanh toán lại không dùng được? Nhớ kiểm tra đơn tối thiểu, ngành hàng và giờ áp dụng trước nhé.

Mình gom mã và món tham khảo ở kênh Telegram ZT báo mã. Bạn xem điều kiện trước khi chốt; mã có thể hết lượt, giá có thể đổi.

Kênh ở đây: [chèn link mời chiến dịch sau khi chủ bot duyệt]
Trong kênh có link tiếp thị liên kết.

## 3. Nhiệm vụ có thể triển khai theo từng bước

1. Hướng dẫn người mới: một bài ghim phía trên. Không sửa/xoá bài relay cũ, không gửi DM hoặc broadcast.
2. Thu hút người đọc: một original Threads trên tài khoản Cashbot, một link mời riêng. Giữ kênh riêng tư; không tự đặt username/công khai kênh. Kiểm giờ nghỉ/quota/profile và fence một attempt như lượt trước.
3. Biên tập: chọn tin có điều kiện đủ rõ, ghi thời điểm kiểm, phân biệt tin nguồn relay với nội dung tuyển chọn. Chưa hứa tự kiểm mọi mã hoặc chạy lịch gửi mới khi chưa triển khai.
4. Đo: tổng member_count theo mốc và người mới vào Cashbot qua zt_channel_guide; link tạo/khách dùng thật tách riêng. Tổng tăng member không chứng minh đến từ Threads.

## 4. Những gì đã kiểm chứng

08:47:59VN20/11/2026, đọc Telegram API bằng bot hiện có: titleZT báo mã, typechannel, member_count3, chưa publicusername, có existinginvite, chưa description/pinnedmessage. Botadministrator có can_post_messages/can_edit_messages/can_invite_users. Không lưu/tiết lộ invite link riêng tư đang có và không tạo mới trong bước chuẩn bị.

Code có voucher parser + sale relay đăng vào kênh, link relay dùng AUTOSALE; nguồn này không phải agent tự viết nội dung. getUpdates hiện chỉ nhận message/callback_query/channel_post/edited_channel_post, chưa có handler hoặc bảng ghi join theo từng invite. Vì vậy lượt thử chưa thể hứa số join attribution theo link; muốn đo chuẩn cần một bước kỹ thuật riêng, có kiểm thử và rollout. Mãstartbot có thể theo first-touch người mới, không đo người cũ quay lại hoặc kết luận nguyên nhân.

Chỉ gọi readonly getChat/getChatMemberCount/getMe/getChatMember trong lượt chuẩn bị. Không thay privacy/description/pin, không gửi bài, không đổi config/queue/cadence/quota, không syncShopee/restart/commit/push. Baseline: channel-readiness.json.
