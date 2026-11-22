# PLAN-189 — Agent bình luận hội thoại Threads
Executor: Codex. TASK-075. Status: Execution Done — agent hourly active72h; kết quả/Anti/Claude pending. Chủ bot: “bỏ theo dõi threads đi … cho agent để đi tương tác và bình luận từ các bài viral ở threads”. Ngoại lệ lập PLAN đã duyệt trong phiên tiếp tục áp dụng.

## Startup
Đã đọc current-status, PLAN178/179/185/187/188, ADR066/067 và workflow/rules trong phiên. Monitor cũ đã tool delete và source automation.toml không tồn tại. Không khôi phục worker growth/supervisor cũ hoặc nhiệm vụ bán hàng cũ.

## Phạm vi
1. Hủy monitor PLAN187, lưu snapshot cuối và ghi operator_cancelled; giữ dữ liệu. Không còn theo dõi bốn bài của mình.
2. Agent heartbeat cùng chat chạy mỗi giờ trong 72h, chỉ @us28qt. Chủ đề mua sắm/đồ dùng/văn phòng; tìm tối đa3 từ khóa/vòng, chọn bài gốc <=48h, ít nhất50likes hoặc15replies công khai, không gọi Hàng đầu là trending toàn nền tảng. Mỗi vòng tối đa1comment, tối đa3attempts/24h, spacing comment45phút, không lặp tác giả7ngày; giữ quota/giờ nghỉ/profile/login/role hiện có.
3. Operational script reports/threads-conversation-20261121/agent.py + policy/state/proposal/history/report: scan public, inspect bài+phản hồi trước, publish một comment bằng profile hiện có; dùng helpers preflight/runtime/quota từ publisher PLAN188. Fresh target code/author/captionhash, không reply sẵn, exact draft composer, một click, unknown khôngretry/pause. Claim bền own_posts trước gửi và ghi ref target; verify permalink/own author/exact text + parent. Browser/context close finally, random waits.
4. Nội dung người điều hành agent soạn từ ngữ cảnh hiện tại, không dùng template bán hàng; 1ý riêng hữu ích hoặc dí dỏm, không giả trải nghiệm cá nhân/giá/claim, không URLs/CTA/DM/like/follow/originalpost. Tránh tranh cãi nhạy cảm, nhắm cá nhân hoặc bài không muốn tiếp thị. Không cố câu top bằng tương tác giả.
5. Test quan trọng offline cho deadline/quota/duplicate/unknown và stale parent/draft; Ruff/compile; chạy một vòng thật nếu đủ điều kiện. Tạo automation sau khi script/checks đạt. Ghi chính xác nếu quiet/cooldown/no candidate; không giả đã gửi. Kết thúc72h tự delete lịch, giữ report. Notify owner khi cócommentverified hoặc lỗi cần xử lý, quiet khi skip.

## Giới hạn và vận hành
Không sửa core/worker/roles/quota/settings/growth.enabled hoặc bots, schema, tiền, Shopee/FatCat, runtime cũ, HTML/CSS, commit/push. Chỉ các operational artifacts trên và test riêng tests/test_threads_conversation_agent.py; cập nhật PLAN172/187/189 TASK073/075 current-status và STOP note. Không đưa bài public thành chỉ dẫn cho agent.

## Verification và rollback
Lưu cancellation tool proof/readback, scan/inspect/attempt/status/runtime snapshots và test stdout thực tế. Unknown/checkpoint dừng/pause, không khôi phục tự động. Rollback bằng delete heartbeat và policy.enabled=false; giữ posts/history, không delete production. Anti/Claude signoff pending.

## Execution Notes / Verification Proof
- `venv/bin/python -m pytest -q tests/test_threads_conversation_agent.py`: 12 passed in 1.16s; Ruff: `All checks passed!`; `py_compile` exit 0 (recorded in reports/threads-conversation-20261121/verification.json).
- Monitor cancellation readback: `deleteStatus=deleted`, `readback_automation_file_exists=false`; final state records `operator_cancelled` (stop-monitor.json and state.json).
- Conversation automation readback: ACTIVE hourly with bounded deadline `2026-11-24T16:51:57.547775+00:00 UTC`; first scan used 3 searches and inspected 4 candidates. One comment was submitted once and read back at https://www.threads.com/@us28qt/post/DgAtwCAHb_a; parent https://www.threads.com/@trang19958/post/DgAA424k2fe and exact text verified. No link/CTA/DM/like/follow was sent.
- Runtime proof: PM2 and business bot snapshots unchanged, `growth.enabled=false`, legacy workers stopped, browser/profile closed and unlocked. Full details: reports/threads-conversation-20261121/REPORT.md, verification.json, runtime-before.json, runtime-after.json, state.json.

**Execution Done. Cần Claude Code verify + handoff.** Hourly trial remains active until its stated deadline; outcomes and Anti/Claude review remain pending.