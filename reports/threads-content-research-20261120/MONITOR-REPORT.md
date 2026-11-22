# PLAN187 — Theo dõi hai bài Threads A/B

Automation heartbeat15phút: `theo-d-i-2-b-i-threads-a-b`, active trong chat hiện tại. Chỉ đọc hai permalink public, logged-out Chromium; kết thúc tự xóa sau 27/11/2026 14:33 VN. Không dùng profile đăng nhập/agent workers.

| Bài | Baseline16:13 VN20/11 | Snapshot16:16 VN20/11 | Delta nhìn thấy |
|---|---:|---:|---:|
| A máy tăm nước | 210 views, 0 likes, 4 replies | 227 views, 0 likes, 4 replies | view label +17 (có thể làm tròn) |
| B máy hút bụi mini | 318 views, 0 likes, 5 replies | 325 views, 0 likes, 5 replies | view label +7 (có thể làm tròn) |

Hai lượt đọc có caption hash/author/permalink verified; không đọc/lưu nội dung comment, usernames hay reply IDs. Không có lượt thích/phản hồi mới trong khoảng đối chiếu này. Đây là lượt xem và tương tác công khai, không phải khách/conversion.

Ngưỡng báo: reply count tăng, likes tăng ≥5 hoặc views tăng ít nhất25; lỗi mới báo sau2vòng liên tiếp. Automation prompt chỉ chạy `monitor_two_posts.py`; script guard growth.enabled=false và hai worker cũ stopped trước khi browse; nếu trạng thái đổi sẽ dừng/alert, không tự phục hồi. Code compile/Ruff pass, một lần manual read-only check thành công, `public_actions=0`.

Snapshot aggregate: `monitor-state.json`. Cũ agent `Threads_Growth`/`CapCut_Agent_Supervisor` giữ stopped, không khôi phục.
