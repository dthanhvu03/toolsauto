# PLAN186 — Đã đăng hai bài content Threads

Yêu cầu trực tiếp của chủbot: đăng hai caption đã duyệt trong chat, không tự sửa nội dung. Hai bài đã đăng trên @us28qt, không ảnh/link/CTA. Agent tăngtrưởng bị hủy trước đó vẫn giữ trạng thái dừng; đây là one-off publish thủ công.

| Bài | Nội dung | URL | Trạng thái |
|---|---|---|---|
| A | Máy tăm nước cho người niềng | https://www.threads.com/@us28qt/post/Df9HXiUCWG1 | Posted; exact caption verified |
| B | Máy hút bụi mini trên sofa | https://www.threads.com/@us28qt/post/Df9ILO9ieoK | Posted; exact caption verified |

Lần nhấn đăng A: 14:25:57 VN; B: 14:33:01 VN20/11 — cách nhau424giây, vượt minspacing180giây. Hai own_posts row đúngslot/status/post_url/text/account; mỗi bài một submit, không retry. Sau từng bài browser đóng, profile mở khóa.

Guard trước mỗi bài: handle us28qt live, ACTIVE, role own_posts enabled, profile rảnh, quiet hours/quota, growth.enabled=false, Threads_Growth + CapCut_Agent_Supervisor vẫn stopped/PID0. Quota sau phát hành2bài trong1h và9bài/24h, thấp hơn3/h và20/day. Không có link, mã, ảnh, reply, DM, like, follow hoặc lịch tự động.

Verification JSON: two-posts-final-verification.json; per-post proof publication-a-water.json and publication-b-vacuum.json. Script one-off publish_two_posts.py; py_compile/Ruff/diff-check pass.

**Giới hạn A/B:** hai caption khác mặt hàng (bấm mi vs máy hút mini), không phải thí nghiệm nhân quả có đối chứng. Tín hiệu sau này chỉ giúp sàng lọc hướng; cần so views/replies/người hỏi đúng nhu cầu/profile visits/link visits và khách dùng thật. Đừng gọi like/reply là khách, hoặc quy kết bài bán hàng nếu thiếu attribution. Chưa có dữ liệu hiệu quả ngay sau đăng.

Đã hoàn thành đúng chỉ đạo; giữ agent dừng và growth.enabled=false. **Execution Done. Cần Claude Code verify + handoff.** Không commit/push.
