# PLAN-181 — Lời mời săn Black Friday vào ZT báo mã

| Mục | Giá trị |
|---|---|
| Executor | Codex — ngoại lệ lập PLAN đã được chủ bot duyệt |
| TASK | TASK-067 |
| Ngày | 20/11/2026, giờ Việt Nam |
| Trạng thái | Execution Done — pin/invite/Threads đã verify; kết quả/Claude/Anti pending |
| Liên quan | PLAN-172/179; PLAN-180-threads-shopee-content-trial; ADR-066/067 |

## Ủy quyền và startup
Sau khi Codex trình gói một bài hướng dẫn ghim, một link mời riêng và một bài Threads, chủ bot chỉ đạo: “có chiến dịch blackfiday á em nên kêu gọi mọi người vào săn sale”. Tiếp tục gói đã trình theo góc Black Friday; không hỏi duyệt lại cùng hành động. Ngoại lệ Codex lập PLAN từ PLAN178 tiếp tục áp dụng. Đã đọc current-status, các PLAN giao liên quan và ADR066/067, ghi phối hợp PLAN172 trước code/action. Không giả ký Anti.

Kho hiện có hai PLAN180/TASK066 do hai luồng tạo khác nhau; không sửa lịch sử/renumber trong phạm vi này. Đã scan active/archive, dùng số mới181/067, không reuse.

## Baseline và nội dung đã xác minh
Read-only08:47:59VN: kênhTelegram ZT báo mã,3member, chưa publicusername, chưa mô tả/ghim, botadmin có post/edit/invite. Có relay/voucher parser hiện có; chưa có join-per-invite handler. Không coi37voucherrecords thành37bài đã đăng hoặc người theo dõi thật.

NguồnShopee chính thức ads.shopee.vn/news/557, kiểm20/11: lịch25–26/11/2026 khởi động Black Friday,27/11/2026 Siêu Sale Black Friday. Viết “chuẩn bị săn” và mốc27/11, không nói hômnay20/11đãlàsaleday27/11. Không đưa %giảm/mã/freeship/hoa hồng hayhoànXu chưa kiểm. Chương trìnhVIP có điều kiện riêng, không lấy ưu đãi đó hứa mọi khách.

## Đầu ra giới hạn
1. Một link mời bổ sung do bot tạo, tênZT BF26 Threads P1, hết hạn23:59:59VN30/11/2026. Dùng createChatInviteLink, không export/revoke link chính, không đổi privacy/username/admin. Không lấy danh sách thành viên hoặc mời người lạ trực tiếp.
2. Một tin hướng dẫn Black Friday trong kênh, ghim tin đó với disable_notification. Có linkCashbot sourcezt_bf26_guide và thông báo affiliate; phân biệt link công khai với link hoàn riêng. Không sửa/xóa tin cũ/đổi mô tả. Nếu đã có ghim mới của người khác thì dừng không đè.
3. Một originalThreads @us28qt, link mời chiến dịch, tối đa470ký tự, nêu lợi ích theo dõi mã/món/cách dùng, nhãn có affiliate, không giả trải nghiệm/uy tín/khuyến mại. Không thêm reply/DM/broadcast/auto scheduler.
4. Read-only đối chiếuchannel/pin/member_count, permalinkThreads/exacttext/link, user source mới vàoCashbot+link tạo. Tổng tăngmember chỉ là tăng tổng, không hứa per-invite attribution/uniqueusers/impressions/tiền nhận. Giữ riêngKPI PLAN179 và bài Shopee2món trước đó.

## Phạm vi kỹ thuật
Chỉ operational scripts trong reports/zt-blackfriday-20261120/ và test riêng, không sửa core/bot flow/queue/schema/financial/config. Root giữ PLAN/TASK/manifest/nội dung/báo cáo/đo; giaoTelegramcontroller và Threadspublisher cho2agent với file không chồng nhau. Cácagent không gọi API/browser/send/restartthật; root thực thi.

Telegramcontroller: readonlypreflight mặc định, kiểmtitle/type/private/botrights và baselinepin, fcntllock + atomicstate claim trước mỗi API mutation. Mỗi createinvite/sendmessage chỉ1attempt; nếu responsekhông rõ ghiunknown và khôngtựthửlại. Cácbướcđãsavedverified khônggửilại. Pin có thể xác minhgetChat; không tạo thêmtin nếu chưabiếtoutcome. Khônglogtoken/rawAPIURL/IDkhách. Dùngtimeout hữu hạn và methodallowlist.

Threadspublisher: primitiveGrowthBrowser.create_post; rolequyềngiữcũ, quiet00:30–06:30, quota gộp cảoriginal/reply, minspacing, ACTIVEaccount/profileidle, liveidentity ngaytrướcgửi. Fence slotzt-bf26-threads-p1 trongown_posts, claimunknown trướccreate_post và max1call; unknownchỉverifyreadonly. Tạm stop/start riêngThreads_Growth khi cầntránhtranhprofile; luônrestorefinally, PM2/appkhác/systemdbot/configkhôngđổi. Nếu có checkpointdừngkhôngvượt.

## Trình tự
1. Tạo/đọcfullPLAN, phối hợp172, chốt copy và sourcefacts; baselineconfig/runtime.
2. Viết operationalfences/mocktests, reviewnội dungđộdàilinkguard; root tạo1invite+1tin+pin saupreflight.
3. Root đăng1bàiThreads, verifypermalink/text/link; ghi trạngtháibền, khôiphụcworker.
4. Snapshot readonly banđầu; cậpnhậtheartbeat hiệncó khôngthêmlịch, chỉbáokếtquảđángkể. GhiproofPLAN/TASK/current-status/172.

## Verify và giới hạn
MockAPI/browser/tempSQLite: wrongtarget/rights, pinconflict, invite/sendunknownnoreplay, completedstepsskip, nodoublepublish, role/quiet/quota/identity, workerrestore. Ruff/compile/diff. Proof thậtphảicóreadbackpintext/link, permalinkThreads/exactmatch, sốattempt vàownrow, memberbaseline/firsttouchbaseline, configs/PIDs untouched.

Không syncShopee, tạoorder/QR, mua hàng, sửaví/giá, restartCashbot/Store/Zalo, bậtAnLinhDM, mởkênhcôngkhai, thayrelay/cadence/quota, tựđăngthêm/commit/push. Link hết hạnlàtham số chiến dịch, khôngđá ngườiđãthamgia. Không gọi mọiadmin/member làkháchthật.

## Rollback/handoff
Không tựxóa tin/bài/inviteđãphát hành hoặcproductiondata; unknownphảixácminhtrướcmọiretry. Khôiphụcworkerfinally. Kếtthúcghi “Execution Done. Cần Claude Code verify + handoff.”, giữ kếtquảkinhdoanh/AntiClaude pending.

## Execution Notes / Verification Proof
- Haiagents triểnhaioperationalcontroller+Threadspublisher ởfilekhôngchồng; rootchuẩnbịcopy/measurevàthựcthiAPIs/browser. Reviewerđộclập34testspass4,11s, khôngblocker. Giữnguyênguồncode/wip/luồngkhách khác.
- Copydựa lịchShopeeprimary25–26/11khởiđộng,27/11BlackFriday; guide743ký tựvàThreads308ký tự,khôngmứckhuyếnmạichưakiểm. Códisclosureaffiliate, hướngdẫnlinkmónquaCashbotđểlấylinkhoànriêng.
```
venv/bin/python -m pytest -q tests/test_zt_blackfriday_channel.py tests/test_zt_blackfriday_threads.py tests/test_zt_blackfriday_measurement.py
37 passed in 1.70s
Ruff All checks passed!; py_compile và git diff --check exit0
channel preflightready/member3/no priorpin
channel --apply completed: invite/guide done, pinverified message617
Threads preflight blocked=[], public_hour0/public_day8
Threads --publish posted, create_post_calledtrue, livehandleus28qt
permalink exacttext+invite verified, worker_restoredtrue
own_posts đúng1row slotzt-bf26-threads-p1/posted
```
-09:04:35–09:04:45VN20/11: tạo1invite bổ sung https://t.me/+02gPhoNuEjcxMmJl , hết23:59:59VN30/11; gửi/ghim1guide message617. Giữprivate, khôngexport/revokelinkchính/sửatin/description/admin/relay. ReadonlygetChatmớitrước/sauThreads đều đúngpin/text/private.
- Bàithật **https://www.threads.com/@us28qt/post/Df8jAaUCVmk**, attempt09:07:29→verify/finally09:08:32VN, đúng1createcall/1postedrow. KhôngDM/reply/broadcast/auto scheduler.
- Threadspause/restorePID26025→895556online; PM2khác/statuscounter vàsystemdPID/starttimekhớp, env/roleshashsame. SnapshotđầulỗiKeyErrorpidtừDB_BackupstoppedtrướcmọiPM2action;đãfixgetpid+test, khôngretryTelegrammutations. Baseline ghiđúngphạmvisauTelegram/trướcThreads,khônggiảproof.
-09:10:28VNmeasurementreadonly: tổngmember3,0Cashbotnewfirsttouch/0usedquazt_bf26_guide; pinđúng. Chưacójoin-per-invite/impressions/cashreceived,khôngquytổngmemberchoThreads hoặcclaimeddoanhthu. HeartbeatcũACTIVE15phút/cùngchatđãthêmcampaign,readbackconfirmed, khôngthêmlịch.

Fullproof reports/zt-blackfriday-20261120/REPORT.md, channel-state.json, manifest.json, trial-publication.json, runtime-baseline.json/runtime-after.json, measurement.json vàheartbeat-proof.json. **Execution Done. Cần Claude Code verify + handoff.** Kếtquảkinhdoanh/Claude/Anti pending, khôngDone/archive.
