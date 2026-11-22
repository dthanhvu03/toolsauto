# PLAN-181 — Đã phát hành lời mời săn Black Friday

## Kết quả thực tế20/11/2026, giờ Việt Nam
- KênhZT báo mã vẫn riêng tư. Đã tạo đúng1linkmời bổ sung tênZT BF26 Threads P1, không export/revoke linkchính: https://t.me/+02gPhoNuEjcxMmJl . Link chiến dịch hết hạn23:59:59VN30/11/2026.
-09:04:35–09:04:45VN: gửi đúng1hướng dẫn743ký tự, message617, ghim imlặng. TelegramgetChat đọc lại đúngmessage_id/toàntext; baseline3member, không gọi3khách. Không sửa mô tả/quyền/admin/relay hoặc tin cũ.
- Threads @us28qt: **https://www.threads.com/@us28qt/post/Df8jAaUCVmk**. Attempt09:07:29VN, verifyvàkhôiphụcworker09:08:32VN. Đúng1create_post, mộtown_posts rowzt-bf26-threads-p1/statusposted, liveidentitykhớp, permalinkđọc lại exacttext308ký tựvàinviteURL. Không DM/reply/broadcast hoặc tự thêm lịch đăng.

## Nội dung và nguồn
Lời mời“Chuẩn bị săn Black Friday27/11cùngnhau”, kênhgom mãShopee/mónthamkhảo/lưuýđiềukiện; khônghứa%giảm/mã/freeship/hoànthật/tồnkho/uytínchưakiểm. Có thôngbáoaffiliate. Tin ghim hướngdẫnlêndanhsách/kiểmđiềukiện/giácuối, muốnxemsốhoàndựkiếnthìdánlinkmónvàoCashbotvàmua bằnglinktrảriêng. Linkmua côngkhaitrongkênh khôngtựghicashbackkhách.

NguồnprimaryShopee kiểmtratronglượt: https://ads.shopee.vn/news/557 , mụcngàySiêuSaletháng11/2026 ghi25–26/11khởiđộng,27/11BlackFriday. Khôngnói20/11làngàyBlackFriday. APIprimary https://core.telegram.org/bots/api . Nội dungnguyênvăn/contenthashởcontent.json,CONTENT.md,manifest.json.

## Lệnh và proof
```
venv/bin/python -m pytest -q tests/test_zt_blackfriday_channel.py tests/test_zt_blackfriday_threads.py tests/test_zt_blackfriday_measurement.py
37 passed in 1.70s
Ruff: All checks passed!
py_compile + git diff --check: exit0

PYTHONPATH=. venv/bin/python reports/zt-blackfriday-20261120/channel_trial.py
preflight statusready, member_count3, no priorpin

PYTHONPATH=. venv/bin/python -u reports/zt-blackfriday-20261120/channel_trial.py --apply
statuscompleted, invite/guide done, pinverified/message617

PYTHONPATH=. venv/bin/python reports/zt-blackfriday-20261120/threads_trial.py
blocked=[], combined_public_last_hour0, combined_public_last_day8

PYTHONPATH=. venv/bin/python -u reports/zt-blackfriday-20261120/threads_trial.py --publish
posted, create_post_calledtrue, verified_live_handleus28qt
permalink_content_and_links_verifiedtrue, worker_restoredtrue
```
TrướcThreadsđãchạyTelegramreadonlypreflightmới, xácnhậnghim/linkstate, khônggửilạitin. Saupháthànhreadonlypreflightcũngxácnhậnghimđúng/private. MỗiTelegrammutationđượcclaimunknowntrướccall; unknowninvite/sendkhôngretry, pinunknownchỉresolve bằngexactreadback. Threadsfencechặnmọiattemptđãcó; verifykhôngrepost. TestsđềuAPI/browser/PM2giảvàSQLite tạm. Reviewerđộclập34testspass4,11s, khôngblocker trướcrollout.

SnapshotđầugặpKeyErrorpiddoentryDB_BackupdừngkhôngcóPID. Đây làlỗicapturetrướcmọiPM2action, khônglỗigửi. Đãđọc stateTelegram trước khi tiếp tục, khôngchạy--applylạibằngphỏngđoán; controllerđãcompleted. SửahẹpnewThreadssnapshotdùnggetpid+testregression. runtime-baseline.json đượcghirõsauTelegram/trướcpauseThreads; khônggiảlàmảnhchụptrướcTelegram.

## Khôi phục và phạm vi giữ nguyên
Threads_Growthđượcpause/restoređểtránhtranhprofile:PID26025→895556,online,restartcounter0giữnguyên. PM2khácPID/status/counterkhớpngaytrướcsauphiên, supervisor26028khôngđổi. Store25744/Cashbot25731/Zalo25732active, PID/starttimekhớp; .envvàroleshashkhớp. Không đổiPRIMARY/native/bridgepilot, khôngsyncShopee/mua/QR/ví/giá/schema/queue, khôngrestartsystemdbot hoặccommit/push. Không sửa2PLAN180đangtrùngsố ởluồngkhác.

## Đo và theo dõi
`measure_trial.py` chỉSQLite mode=ro vàTelegramgetChat/getChatMemberCount, không có APIgửi/invite/pin. Lọcadmin/testđãcấuhình, nguồnriêngzt_bf26_guide. Baselinebusiness0 và tổngmember3 đãlưu trướcpháthành; từ09:04:35VN dùngmốccampaignstartedkhikếhoạchbắtđầuthựchiện, khôngkhẳngđịnhđúnggiâyguidexuấthiện.

09:10:28VN: channelavailable/private/pinđúng, **3membertổng,0ngườimớivàoCashbotquanguồn,0kháchtạolink**. Đây làsốbanđầu,chưađánhgiáhiệuquả. Chưa cójoin-per-invitehandler, nênkhôngđođượcngườivàokênhtừbàiThreads; tăngtổngmemberkhônglàcausalattribution. Sourcebotchỉfirsttouchngườimới, khôngđokháchcũquaylại. Linkcreatedlàdùng, chưaphảimua/hoa hồngnhận. Impressions/cashreceivedunavailable.

Heartbeatcũtheo-d-i-t-th-capcutđãcậpnhậtquaautomation_update,ACTIVE/15phút/cùngchat, readbackhasPLAN181/post/measuretrue. Giới hạn2Telegramreadmethods cho báo cáo mới, khôngchoheartbeatgửi/ghim/tạolink/restart. Cómetadatapháthànhđãbáo, tránhbáolại. Theo dõitổngmemberlầnđầutăng/mốc5/10, ngườiCashbotmớidùngthật, lỗiđángxửlý; khônghứalịchcontenttựđăngmới.

**Execution Done. Cần Claude Code verify + handoff.** Đãcópin/link/bàithật; kếtquảkinhdoanhvàAnti/Claude vẫn pending, khôngDone/archive mục tiêutăngtrưởng.
