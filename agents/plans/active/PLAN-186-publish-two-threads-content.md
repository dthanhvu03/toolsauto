# PLAN-186 — Đăng hai bài Threads test A/B

Executor: Codex — chủ bot đã yêu cầu trực tiếp “oke em triển khai 2 bài này đi em”.
TASK: TASK-072. Ngày20/11/2026 VN. Status: Execution Done — hai bài đã đăng/verify; engagement/conversion pending.

## Startup và scope
Đã đọc current-status, PLAN185 stop, PLAN184 research, ADR066/067 và scan active/archive trước khi cấp số186/072. Agent nền vẫn bị hủy: không bật Threads_Growth/CapCut_Agent_Supervisor, không đổi growth.enabled=false, không tạo lịch/automation. Đây là một lần đăng thủ công có fence riêng, dùng profile us28qt nhưng không chạy worker.

Đăng đúng hai caption đã chốt trong chat:
1. A — máy tăm nước cho người đang niềng: hỏi có đáng sắm, nỗi lười rửa bình, hỏi trải nghiệm dùng đều/vệ sinh.
2. B — máy hút bụi mini: hỏi hút tóc/vụn bánh sofa, nỗi mua rồi cất tủ, hỏi có đáng tiền.

Không thêm link, mã, giá, claim đã dùng, ảnh người khác, reply/DM/like/follow, hoặc CTA nhóm. Không gộp thành một bài; không đăng lại các bài PLAN180/181/182. Nếu không có ảnh sản phẩm hợp lệ đã kiểm, đăng text-only theo đúng caption; không lấy ảnh research làm asset.

## Guard và runtime
Preflight account live handle us28qt, role own_posts, profile unlocked, spacing/hour/day quota, growth.enabled=false giữ nguyên, worker PM2 stopped/PID0. Dùng exact caption/hash/slot độc lập A/B trong own_posts; claim unknown trước mỗi Post click, mỗi slot chỉ một submit, unknown không retry. Đóng browser finally. Sau mỗi submit readback exact permalink/content; nếu first outcome unknown dừng và chỉ verify read-only. Không khởi động worker hoặc đổi settings.

## Proof/handoff
Lưu manifest, preflight, publication proof, runtime before/after, DB own_posts readback và exact output trong reports/threads-content-research-20261120/. Kiểm hai caption length/hash/link=0, duplicate guard, compile/diff. Cập nhật TASK/current-status/PLAN172 sau khi hoàn tất. Ghi “Execution Done. Cần Claude Code verify + handoff.”; kết quả user/replies/conversion pending. Không commit/push.

## Execution Notes / Verification Proof
- Exact user-approved captions đã đăng: A https://www.threads.com/@us28qt/post/Df9HXiUCWG1, B https://www.threads.com/@us28qt/post/Df9ILO9ieoK. Hai row own_posts status posted/text/hash/slot/author verified; mỗi row một submit, không retry.
- AttemptA14:25:57VN, B14:33:01VN20/11; cách nhau424s. Quota readback2bài/1h,9bài/24h <3/h,20/day. py_compile/Ruff/diff-checkpass.
- Cả hai lần: accountACTIVE/handleus28qt/role own_posts/profile un/locked/quota/quiet pass; growth.enabled false; workers vẫn stoppedPID0. Không bật worker/cấu hình/automation. Không gửi ảnh/link/reply/DM/like/follow.
- Full proof: reports/threads-content-research-20261120/TWO-POSTS-REPORT.md, two-posts-final-verification.json, publication-a-water.json, publication-b-vacuum.json. No business outcomes yet.

**Execution Done. Cần Claude Code verify + handoff.** Hai bài khác mặt hàng nên phép so sánh exploratory, không phải A/B nhân quả. Views/replies/conversion pending; agent vẫn dừng.
