# PLAN-188 — Đăng hai bài Threads sau khi học văn phong

Executor: Codex — chủ bot duyệt trực tiếp “em đăng đi em”; áp dụng ngoại lệ lập PLAN đã có trong phiên.
TASK-074. Ngày 21/11/2026 VN. Status: Execution Done — publish verified; kết quả/Anti/Claude pending.

## Startup và phạm vi
Đã đọc current-status, đầy đủ PLAN186/187, WORKFLOW, RULES và ADR066/067; kiểm số cao nhất active/archive: PLAN187/TASK073. PLAN185 giữ hiệu lực dừng agent; chỉ đạo mới chỉ cho phép đăng đúng hai caption sau nghiên cứu bốn bài công khai.
A — bàn phím: giọng đùa; B — hộp cơm hâm nóng: giọng hỏi chuyện. Dùng đúng text đã trình và duyệt, cùng @us28qt. Không thêm link, ảnh, topic, CTA, giả trải nghiệm hoặc đăng lại hai bài cũ. Hai chủ đề và văn phong khác nhau nên chỉ là thử khám phá, không kết luận A/B nhân quả.

## Bước thực hiện
1. Tạo publisher operational reports/threads-genz-20261121/publish_two_posts.py dựa bản PLAN186 đã dùng thành công; chỉ thay captions, slots và metadata kế hoạch. Ghi manifest exact text/hash trước khi chạy. Compile/Ruff, preflight mỗi bài.
2. Đăng từng bài khi handle/ACTIVE/role/profile/quota/giờ nghỉ/minspacing 180s đạt. Claim unknown bền trước một lần submit. Mọi unknown dừng gửi và chỉ đọc xác minh, không retry. Đóng browser finally.
3. Xác minh permalink/caption/author; lưu publication JSON, đọc lại hai own_posts. Chụp runtime trước/sau, cập nhật báo cáo, TASK, PLAN172 và current-status.

## Giới hạn
Giữ growth.enabled=false; Threads_Growth và CapCut_Agent_Supervisor stopped. Không restart dịch vụ, sửa core/customer-flow/schema/config/roles/quota, AI/API/Shopee sync, reply/like/DM/follow, tạo hoặc đổi automation, commit/push. Không đụng WIP khác.

## Validation và xử lý lỗi
Proof thật gồm py_compile/Ruff, preflight, đúng một submit/bài, URL+caption verified, slots DB và PID/status/processes trước/sau. Không test mirror cho caption/metadata; giữ guards publisher cũ. Không xóa/repost bài đã đăng để rollback. Unknown không replay; hết quota/giờ nghỉ/login không hợp lệ thì báo blocker thật.

## Execution Notes / Verification Proof
- `venv/bin/python -m py_compile reports/threads-genz-20261121/publish_two_posts.py`: exit 0.
- `venv/bin/python -m ruff check reports/threads-genz-20261121/publish_two_posts.py`: All checks passed!
- Preflight A: blocked=[], account ACTIVE/own_posts/profile/quota/quiet/minspacing pass; 0 posts/hour, 0 posts/24h.
- A posted https://www.threads.com/@us28qt/post/DgAq_INHSvP; one submit 2026-11-21T16:34:55.894969+00:00, exact_caption_verified=true, profile_unlocked_after=true, growth=false/workers stopped.
- B posted https://www.threads.com/@us28qt/post/DgArf-lnagr; exact caption verified, one submit.
- Full verification: reports/threads-genz-20261121/verification.json; {"both_posted": true, "db_matches": true, "public_readback": true, "spacing_pass": true, "pm2_same": true, "business_bots_same": true, "growth_disabled": true, "profile_unlocked": true}; spacing 269.088708s.
- Báo cáo: reports/threads-genz-20261121/REPORT.md.

**Execution Done. Cần Claude Code verify + handoff.**

## Anti / Claude
Review pending; không giả sign-off, không archive. Khi thực thi xong ghi “Execution Done. Cần Claude Code verify + handoff.”