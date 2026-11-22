> OWNER CANCELLED 22/11/2026 00:07 VN — chủ bot hủy monitor, thay bằng PLAN189 bình luận. Automation cũ đã delete/file absent. Lịch sử dưới đây giữ để audit, không còn hiệu lực chạy.

# PLAN-187 — Theo dõi hai bài Threads đã đăng

Executor: Codex. TASK: TASK-073. Ngày20/11/2026 VN. Status: Cancelled by owner on 22/11/2026; automation deleted and final snapshot retained.

## Ủy quyền và startup
Chủ bot chỉ đạo “cho agent theo dõi 2 bài này”. Đã đọc current-status, PLAN186/185 và ADR066/067; đánh số187/073 chưa reuse. Phạm vi này là monitor chỉ đọc hai permalink A/B, không khôi phục đội tăng trưởng đã hủy.

## Phạm vi
1. Theo dõi riêng https://www.threads.com/@us28qt/post/Df9HXiUCWG1 và https://www.threads.com/@us28qt/post/Df9ILO9ieoK, từ baseline đã lưu đến 27/11/2026 14:33 VN (7 ngày sau khi đăng bài B).
2. Dùng Chromium public, không đăng nhập/shared profile/PM2/Threads_Growth. Đọc lượt xem/like/reply/repost nếu công khai và exact caption/author; raw user IDs, usernames và private inbox không thu thập. Public views labels có thể làm tròn; null khác zero.
3. Lưu snapshot baseline/delta trong reports/threads-content-research-20261120/monitor-state.json. Chỉ alert thay đổi có ích: reply count tăng, likes tăng ít nhất5 hoặc public-view label thay đổi; nếu fetch lỗi/stale qua ít nhất hai vòng báo một lần. Bình thường im lặng.
4. Heartbeat15phút trong đúng chat hiện tại; không restart/start agent, không content generation, AI/generator, post/reply/like/follow/DM/broadcast, không thay growth.enabled=false, quota, roles, queue, code runtime hay bots.
5. Kết thúc tự xóa automation sau deadline; giữ report snapshot làm evidence, sau 7 ngày không gia hạn tự động.

## Proof/handoff
Lưu baseline URL/metrics/time hiện tại, automation result/id/status/schedule, test parser fixture offline, 1 manual run real read-only, unchanged PM2/bot state. Cập nhật PLAN/TASK/current-status/PLAN172. Ghi “Execution Done. Cần Claude Code verify + handoff.”; lượt xem/tương tác không phải khách/conversion.

## Execution Notes / Verification Proof
- Baseline captured logged-out for both exact URLs at16:13VN20/11: A210views/0likes/4replies; B318views/0likes/5replies. Exact caption hashes/author readback verified.
- One post-automation manual run16:16VN: A227views/0/4, B325views/0/5; view labels +17/+7 (may be rounded), no new likes/replies. Script returned notify=true for the changed view labels. These are views/interactions, not customers.
- Offline5assertions parser/view/threshold/atomicwrite passed;  pass, RuffAllchecks passed,  pass. Manual public run status=checked/HTTP200/caption verified both, public_actions0.
- Automation  active FREQ=MINUTELY;INTERVAL=15; exact7-day cutoff27/11 14:33VN in state/prompt. Prompt deletes automation when script marks complete.
- State stores aggregate metrics only (no comment text/usernames/reply IDs); each post gets a fresh temporary page that closes after reading. Guard checks growth.enabled=false+bothold workersstopped.

**Execution Done. Cần Claude Code verify + handoff.** Monitor remains active until deadline; no agent workers, publishing, reply, follow, like, DMs or customer causality claim.
