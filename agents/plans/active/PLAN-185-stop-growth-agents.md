# PLAN-185 — Hủy các agent tăng trưởng theo yêu cầu chủ bot

Executor: Codex. TASK-071. Ngày20/11/2026 VN. Status: Execution Done — đã dừng/xác minh; chiến lược mới chờ chọn.

## Yêu cầu và startup
Chủ bot: “em hủy toàn bộ agent đi em để mình tìm hướng mới dựa vào research đã làm”. Đây là chỉ đạo dừng trực tiếp, thay quyền chạy nền trước đó. Đã đọc current-status/fullPLAN184 và ADR066/067. Không tạo agent mới; các subagent nghiên cứu trong chat đã completed. Đã inventoryPM2/lịch tự động: agent tăng trưởng nằm trong Threads_Growth và CapCut_Agent_Supervisor; một heartbeat theo-d-i-t-th-capcut15phút.

## Phạm vi được giao
1. Hủy heartbeat theo-d-i-t-th-capcut (đã tooldelete thành công đầu lượt), không tiếp tục báo định kỳ.
2. Dừng riêng Threads_Growth và CapCut_Agent_Supervisor, xác minh stopped/PID0, lưu trạng tháiPM2 để không tự sống lại khi restore/reboot. Tắt growth.enabled bằng settingsAPI hiện có để vô hiệu hoạt động tự động khi process vô tình được chạy lại; giữ quyền/login/roles/quota và queue để xem lại.
3. Xác minh không còn process của hai scriptworker/supervisor; subagents chat không running. Không triển khai cách làm mới khi chưa chọn hướng; không đăng/DM/reply/like/quét/AI thêm.
4. Giữ research126mẫu, nội dung/ảnh/queue/history/sourcecode và cácbot kinh doanh. Không xóaDB/post/link/kênh/file/code/processPM2definition; khôngrestartStore/Cashbot/Zalo/nativepilot hoặcdừngweb/maintenance/studio/9router/bridge.
5. Lưu snapshot trước/sau chỉpid/status/hash/counters/settingskeykhôngsecret; cậpnhậtstatus/PLAN172/TASK và stopreport. Khôngcommit/push.

## Proof/handoff
PM2jlist before/after, `pm2 stop` hai tên chính xác, settings growth.enabled=false readback, `pm2 save` và dumpstatuschỉhaiapps, quét/proc exactscriptpaths, systemdPID/starttime/PM2khác/hashenvrolessame. Không viết testschooperationstop cóthểđảongược; proof làruntime thật. Kết thúc “Execution Done. Cần Claude Code verify + handoff.”; không tựbậtlại trước chỉđạo mới.

## Execution Notes / Verification Proof
-11:26VN20/11: settings.upsert_setting(growth.enabled,false) vàfreshDBreadbackfalse; `pm2 stop Threads_Growth`/`pm2 stop CapCut_Agent_Supervisor` đềuexit0, stopped/PID0/restarts0. `pm2 save`exit0, actualdaemon /root/.pm2/dump.pm2 saved2statusstopped; không đổi daemon hoặcxóadefinition.
-automation_update(mode=delete,id=theo-d-i-t-th-capcut) trảdeleteStatusdeleted; scantấtcảautomation.toml khôngcònlịchidnày/cùngchat. collaboration.list_agents khôngcònchildrunning,3childcompleted; khôngspawnmới.
-11:29:27VN proofstop-20261120.json: two_workers_stopped/growth_disabled/saved_as_stopped/no_worker_processes/other_pm2_same/business_bots_same/env_roles_research_same/chat_automation_removed đềutrue. /proc exactscriptmatches=[]; khôngrestartStore/Cashbot/Zalo, PM2khác/roles/env/researchhashkhớp. Generatedreportsghioperator_stop/stopped/PID0, giữheartbeatcũ.
-ImportSessionLocalđầu nhầm module, dừngtrướcmutation; sửađúngapp.core.database.core. VerifyPM2dumpđầu nhầmuserVu cũ, đãtheooutputsaveđọcđúng/rootdump vàxácminh2stopped. Khônglấylỗiverifyđó làmproofthànhcông.
-Fullreports/customer-agents/STOP-20261120.md vàstop-20261120.json. PLAN176/178/179 đãcóbannerownerstopped ưu tiênhơnchỉdẫnchạynềncũ; research126mẫu/nháp/history/queuegiữnguyên. Khôngđăng/DM/reply/like/AI/Shopeesync/commit/push hoặcchạyhướngmới.

**Execution Done. Cần Claude Code verify + handoff.** Toàn bộ agent tăngtrưởng/lịchtựđộngcũđãhủy; khôngtựbậtlạitrướcchỉđạomới. Chiếnlượcmớichờchọn từresearch, khôngbịkhóabởireviewcũ.
