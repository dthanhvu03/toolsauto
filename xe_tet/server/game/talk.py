"""Câu nói của Anh Tư lơ xe (PLAN-128, sửa PLAN-131): chợ búa như lơ xe ngoài bến thật, ba kiểu nói anh chọn trên /control.

- «ben»: lơ xe bến xe miền Nam — cha nội, hổng chờ, nhích vô, đứng đó ngó hoài.
- «genz»: gét gô, khum, toang, quay xe, ét ô ét, đỉnh nóc kịch trần, uy tín.
- «geny»: chuẩn không cần chỉnh, bó tay chấm com, chất như nước cất, quẩy lên.
- «mix» (mặc định): mỗi lần nói bốc ngẫu nhiên trong cả ba kiểu.

Giọng đọc đều, không nhấn nhá: câu chỉ có dấu phẩy, dấu chấm (không «!»), không đuôi «nha». Chữ lóng tiếng Anh viết theo
cách đọc tiếng Việt (gét gô, ét ô ét) vì máy đọc tiếng Việt đọc sai chữ Anh. Không chửi thề (TikTok khoá live).
Mỗi tình huống vài câu, bốc ngẫu nhiên: nghe lại không lặp y chang. Sửa câu chỉ cần sửa bảng LINES; {tên} là chỗ điền.
"""

import random
import re

STYLES = ("ben", "genz", "geny")
TALK_STYLES = ("mix", *STYLES)

LINES: dict[str, dict[str, tuple[str, ...]]] = {
    # ---- lơ xe bến xe ------------------------------------------------------------------------------
    "ben": {
        "fuel": (  # đổ xăng lúc chờ khách (PLAN-137)
            "{name} đổ xăng cho xe, bình được {n} phần trăm rồi, đầy bình là chạy bon bon.",
            "Cảm ơn {name} đổ xăng, {n} phần trăm, ai đổ tiếp cho đầy bình coi.",
        ),
        "wash": (
            "{name} xịt nước rửa xe, sạch {n} phần trăm rồi, bóng loáng về quê cho đẹp.",
            "Rửa xe nè, {name} chà kỹ ghê, xe sạch {n} phần trăm rồi.",
        ),
        "this_trip": (  # gom người khác hướng (anh dặn 02/11)
            "Đây là chuyến đi {dest} nghe bà con, ai đi {others} thì đợi chuyến sau, Anh Tư giữ chỗ rồi.",
            "Xe này chạy {dest}, mấy người {others} đứng chờ chuyến sau, hổng có quên đâu.",
        ),
        "board_lock": (  # 10 giây cuối giờ đón: không xuống / đổi tỉnh được nữa
            "Sắp chạy rồi {name}, ngồi yên đó, hổng xuống được nữa đâu.",
            "Đóng cửa rồi {name} ơi, giờ này hổng đổi được, ngồi yên.",
        ),
        "back_again": (  # vừa được thả về quê đã đặt vé tiếp (PLAN-136, live 02/11)
            "Ủa {name} mới về {prov} đã quay ra bến nữa hả, quên đồ hay sao.",
            "{name} về {prov} chưa nóng chỗ đã ra bến, chắc thương Anh Tư quá.",
        ),
        "station_vote": (  # gọi xe ra bến khác
            "{name} gọi xe ra {station}, mới {n} trên {need} người, ai cũng muốn thì gõ theo.",
            "Ghi nhận {name} gọi {station}, đủ {need} người là Anh Tư lái xe ra liền.",
        ),
        "pickup_wait": (  # bắt xe dọc đường (PLAN-136): hẹn ra điểm đón
            "Được {name}, ra điểm đón ở {place} đứng chờ, Anh Tư tấp vô đón.",
            "{name} ra điểm đón {place} chờ chút, xe tới liền, nhớ đứng trong lề.",
        ),
        "pickup": (
            "Tấp vô điểm đón {place} rước {name}, lên lẹ cái coi.",
            "Tới {place} rồi, {name} lên xe đi, Anh Tư xếp giường sẵn rồi.",
        ),
        "passed": (
            "Xe qua {prov} rồi {name} ơi, giữ chỗ chuyến sau, hổng bỏ đâu.",
            "Trễ rồi {name}, xe chạy qua {prov} mất rồi, chờ chuyến sau.",
        ),
        "same_home": (  # lên xe gặp người cùng tỉnh (PLAN-134 D)
            "{name} với {other} cùng về {prov} kìa, đồng hương nằm gần nhau cho vui.",
            "Lại thêm một người {prov}, {name} ơi có {other} cùng quê trên xe đó.",
        ),
        "welcome_trips": (  # khách buổi trước quay lại, đã về quê rồi (PLAN-134 D)
            "Ủa {name} quay lại bến nữa hả, đã về {prov} {n} chuyến rồi mà còn ghé, quý quá.",
            "{name} đây rồi, khách quen về {prov}, nay đi tiếp chuyến nữa hông.",
        ),
        "welcome_back": (
            "{name} ghé bến lần nữa nè, bữa trước chưa lên xe, nay gõ tên tỉnh đi.",
            "Thấy {name} quen quen, ghé lại hả, nay về quê thì gõ tên tỉnh lẹ.",
        ),
        "invite": (  # thả tim nhiều mà chưa có vé: gọi tên mời lên xe, mỗi người một lần mỗi buổi
            "{name} thả tim nãy giờ mà chưa lên xe, quê đâu gõ tên tỉnh đi, Anh Tư chừa giường cho.",
            "Ê {name}, tim nhiều vậy mà đứng ngoài hoài, gõ tên tỉnh quê là có giường liền.",
        ),
        "invite_home": (
            "{name} thả tim quá trời, năm nay về {prov} nữa hông, gõ {prov} là Anh Tư xếp giường.",
            "Ủa {name} khách quen tuyến {prov} mà, gõ {prov} lên xe luôn cho rồi.",
        ),
        "screen_relief": (  # màn hình chuyển sang xe tăng cường (PLAN-142): lơ xe theo xe đang chiếu
            "Qua xe số {no} nè bà con, xe đi {dest} chở {n} người, còn {km} ki lô mét tới {next}.",
            "Ngó xe số {no} chút, chạy hướng {dest}, {n} khách, sắp tới {next} rồi.",
        ),
        "screen_main": (
            "Về lại xe số {no} đi {dest}, {n} khách đang nằm ngủ ngon lành.",
            "Quay về xe số {no} hướng {dest} nghe bà con, {n} người trên xe.",
        ),
        "rules": (  # đọc luật chơi định kỳ / khi có người mới vô (PLAN-142)
            "Mới vô thì nghe nè, gõ tên tỉnh quê mình là có giường về quê, thả tim cho xe chạy nhanh, gõ xe nào để coi vé.",
            "Luật dễ ẹc bà con, gõ tên tỉnh là lên xe, hổng về thì gõ không về, tặng quà là có hiệu ứng trên xe.",
            "Ai chưa biết chơi, gõ tên tỉnh quê vô bình luận, Anh Tư xếp giường, xe chạy tới quê là thả xuống đầu ngõ.",
        ),
        "board_home": (  # «lên xe» không nói tỉnh, khách quen biết quê (rà soát 02/11)
            "{name} về {prov} như bữa trước hả, Anh Tư xếp liền, quê khác thì gõ tên tỉnh.",
            "Rồi {name}, về {prov} như lần trước, đổi quê thì gõ tên tỉnh khác.",
        ),
        "board_hint": (
            "{name} muốn lên xe thì gõ tên tỉnh quê vô, ví dụ Nghệ An hay Cà Mau, Anh Tư xếp giường liền.",
            "Lên xe thì gõ tên tỉnh {name} ơi, gõ Huế là về Huế, gõ Thanh Hóa là về Thanh Hóa.",
        ),
        "priority": (  # người đang chờ tặng quà → lên đầu hàng (PLAN-144)
            "{name} tặng quà, Anh Tư cho lên đầu hàng xe {dest} liền, giờ thứ {pos} rồi đó.",
            "Cảm ơn {name}, chuyến {dest} kế tiếp {name} lên trước, thứ {pos} trong hàng.",
        ),
        "turbo": (  # quà = xe chạy nhanh gấp đôi (anh 03/11)
            "{name} tặng quà, Anh Tư đạp ga chạy gấp đôi, xe về bến sớm đón người chờ.",
            "Cảm ơn {name}, xe chạy nhanh gấp đôi thêm {secs} giây, chuyến sau tới sớm hơn.",
        ),
        "toll": (  # trạm thu phí: góp quà qua trạm (anh 03/11)
            "Tới {place} rồi bà con, phí qua trạm {goal} xu, ai thương xe tặng quà góp cho Anh Tư qua cái.",
            "Trạm thu phí {place} chặn đầu, thiếu {goal} xu là chưa qua được, bà con góp quà giùm.",
        ),
        "police": (
            "Chết, công an thổi còi, {reason}, phạt {goal} xu, bà con góp quà nộp phạt cho xe đi tiếp.",
            "Công an kiểm tra giấy tờ, {reason}, bị phạt {goal} xu rồi, ai góp quà giúp Anh Tư với.",
        ),
        "speeding": (
            "Thôi xong, chạy nhanh quá bị bắn tốc độ, phạt {goal} xu, bà con góp quà nộp phạt giùm.",
            "Công an bắn tốc độ, xe chạy quá tốc độ rồi, phạt {goal} xu, góp quà cho xe đi tiếp.",
        ),
        "rollcall": (
            "{name} còn ở đây không, thả tim hoặc bình luận trong {seconds} giây để giữ giường.",
            "Tới lượt {name} lên xe rồi, còn xem thì thả cái tim cho Anh Tư biết, giường đang giữ.",
        ),
        "rollcall_ok": (
            "{name} có mặt, mời lên giường.",
            "Rồi, {name} còn đây, lên xe lẹ.",
        ),
        "rollcall_skip": (
            "Gọi hoài không thấy {name}, giường này nhường người sau, {name} đi chuyến tới.",
            "{name} chắc đang bận, vé vẫn giữ, lùi xuống chuyến sau.",
        ),
        "rollcall_drop": (
            "Hai lần gọi không thấy {name}, Anh Tư nhả vé cho bà con khác, quay lại thì gõ tỉnh đặt lại.",
            "{name} vắng hai chuyến rồi, vé nhường người khác, về lại thì gõ tỉnh là có vé.",
        ),
        "block_remind": (
            "Còn thiếu {left} xu nữa là {what}, ai tặng quà góp thêm cho xe đi tiếp.",
            "Xe đang đứng chờ, thiếu {left} xu {what}, bà con góp quà một chút.",
        ),
        "block_paid": (
            "Đủ tiền rồi, cảm ơn {name} với bà con góp quà, xe {what} chạy tiếp.",
            "Cảm ơn {name}, góp đủ rồi, Anh Tư {what} xong, lên đường.",
        ),
        "hungry_vendor": (
            "{name} sắp đói rồi đó, gõ nem, bì hay bánh mì cho {vendor} mang tới giường.",
            "Coi bộ {name} đói bụng rồi, {vendor} đang đi bán nè, gõ tên món là có.",
        ),
        "hungry_call": (
            "{name} sắp đói rồi, bà con góp quà gọi {vendor} lên xe bán nem, bì, bánh mì.",
            "Bụng {name} kêu rồi đó, ai góp quà gọi {vendor} lên bán đồ ăn.",
        ),
        "quiz_ask": (  # đố vui (anh 03/11): gõ A, B, C
            "Đố vui nè bà con, {q}. A, {a}. B, {b}. C, {c}. Gõ A, B hoặc C, ba người đúng sớm nhất được đọc tên.",
            "Anh Tư đố cái, {q}. A là {a}, B là {b}, C là {c}. Gõ A, B hay C lẹ lên.",
        ),
        "quiz_win": (
            "Đáp án là {ans}. {name} trả lời đúng sớm nhất, giỏi quá trời, cộng điểm cho tỉnh nhà.",
            "Đúng rồi, {ans}. Hoan hô {name}, đố câu sau nhanh tay nữa nghe.",
        ),
        "quiz_none": (
            "Hổng ai trúng hết, đáp án là {ans}. Câu sau bà con ráng nghen.",
            "Đáp án là {ans}, lần này chưa ai đúng, để câu sau.",
        ),
        "fact": (
            "Xe đang chạy ngang, {fact}, ai quê ở đây thả cái tim coi.",
            "Bà con biết hông, {fact}, về Tết nhớ ghé.",
        ),
        "weather_drizzle": (
            "Mưa phùn lất phất rồi bà con, lạnh thì đắp mền vô.",
            "Trời mưa phùn, đường trơn, bác tài chạy chậm chút cho chắc.",
        ),
        "weather_rain": (
            "Trời đổ mưa rồi, ai ngồi gần cửa sổ kéo rèm lại giùm.",
            "Mưa rào tới rồi, bác tài bật gạt nước chạy từ từ.",
        ),
        "weather_fog": (
            "Sương mù dày quá, bác tài bật đèn sương mù chạy chậm lại.",
            "Sương giăng kín đường rồi bà con, ngó ra cửa sổ thấy mờ mờ đẹp ghê.",
        ),
        "weather_clear": (
            "Trời tạnh rồi, nắng lên đẹp quá bà con.",
            "Hết mưa rồi, đường khô ráo, xe chạy bon bon.",
        ),
        "tire": (  # sự cố dọc đường: tự xong, tim làm nhanh hơn
            "Chết, xe xẹp lốp ở {place}, Anh Tư xuống thay liền, bà con thả tim cho Anh Tư làm lẹ, tặng {goal} xu gọi thợ là xong ngay.",
            "Nổ lốp rồi bà con, đợi Anh Tư thay cái bánh, thả tim tiếp sức coi.",
        ),
        "jam": (
            "Kẹt xe ở {place} rồi bà con, xe nhích từng chút, thả tim cho đường thông lẹ.",
            "Đường {place} kẹt cứng, ráng chờ chút, bà con thả tim, tặng {goal} xu là Anh Tư xin đường đi trước.",
        ),
        "cattle": (
            "Đàn trâu qua đường ở {place}, xe dừng chờ chút, thả tim cho trâu đi lẹ.",
            "Ê trâu ơi tránh đường cho xe về quê ăn Tết, bà con thả tim cho đàn trâu qua lẹ.",
        ),
        "incident_clear": (
            "Xong rồi bà con, {what} xong, xe chạy tiếp.",
            "Ổn rồi, cảm ơn bà con thả tim, xe lên đường.",
        ),
        "vendor_pool": (
            "{name} góp quà gọi cô bán hàng, thêm {left} xu nữa là cô Ba lên xe bán nem, bì, bánh mì.",
            "Cảm ơn {name}, còn {left} xu nữa là có nem chua, bánh mì lên tận giường.",
        ),
        "vendor_board": (
            "Nhờ {name} góp quà, xe tấp vô {prov} rước {vendor} bán nem, bì, bánh mì lên xe.",
            "{vendor} lên xe rồi bà con, cảm ơn {name}, ai ăn gì gõ nem, bì hay bánh mì.",
        ),
        "vendor_board_admin": (
            "Xe tấp vô {prov} cho {vendor} lên bán nem, bì, bánh mì.",
            "{vendor} bán hàng rong lên xe rồi, ai đói gõ nem, bì, bánh mì.",
        ),
        "vendor_sell": (
            "{name} đi dọc xe nè, gõ nem, bì hay bánh mì là có liền, tặng quà là bao cả xe.",
            "Nem chua, bì cuốn, bánh mì nóng đây, gõ tên món là {name} đưa tận giường.",
        ),
        "vendor_treat": (
            "{name} bao cả xe {item}, bà con cảm ơn {name} một tiếng.",
            "Chịu chơi quá, {name} bao nguyên xe {item}.",
        ),
        "vendor_end": (
            "{name} bán được {n} phần, cảm ơn bà con, cô xuống xe đây.",
            "Hết hàng rồi, {name} xuống xe, chúc bà con ăn ngon thượng lộ bình an.",
        ),
        "block_cover": (
            "Thôi Anh Tư bù lỗ {missing} xu {what} cho xe đi, về quê ăn Tết quan trọng hơn.",
            "Thiếu {missing} xu, Anh Tư móc túi bù lỗ luôn, xe đi tiếp bà con.",
        ),
        "goal_step": (  # mục tiêu buổi live: qua mốc (anh 03/11)
            "Mục tiêu buổi live tới {xu} xu rồi, cảm ơn {name} với bà con, {label} cho cả phòng.",
            "Qua mốc {xu} xu, {label} nè bà con, cảm ơn {name}.",
        ),
        "race_lead": (  # đua tỉnh (anh 03/11)
            "Đua tỉnh nè bà con, {prov} đang dẫn đầu, tỉnh nào bình luận, thả tim, tặng quà nhiều là chuyến sau đi tỉnh đó.",
            "{prov} vượt lên dẫn đầu đua tỉnh rồi, tỉnh khác đâu, bình luận thả tim kéo tỉnh mình lên.",
        ),
        "race_win": (
            "{prov} thắng đua tỉnh, chuyến này Anh Tư chạy hướng {prov}, bà con chuẩn bị lên xe.",
            "Chúc mừng {prov} thắng đua tỉnh, xe đi hướng {prov} liền.",
        ),
        "versus_start": (  # đối kháng (anh 03/11): hai hướng đầu hàng chờ giành chuyến sau
            "Đối kháng chuyến sau nè bà con, hướng {lead} đấu hướng {rival}, quê bên nào thì bình luận, thả tim, tặng quà cho bên đó, bên nào nhiều điểm chạy trước.",
            "Chuyến sau ai đi trước, {lead} hay {rival}, bà con quê bên nào kéo điểm cho bên đó, chưa gõ quê thì gõ tên tỉnh vô.",
        ),
        "versus_lead": (
            "Hướng {lead} đang dẫn điểm hướng {rival} rồi, bà con {rival} đâu, thả tim kéo lên coi.",
            "{lead} vượt lên rồi bà con, {rival} mà không kéo là chờ chuyến sau đó.",
        ),
        "level_up": (  # điểm hành trình qua mốc cấp (rank.py)
            "Chúc mừng {name} lên cấp {title}, Anh Tư nhớ mặt rồi đó.",
            "{name} giờ là {title} của nhà xe rồi, ghé bến hoài là vậy đó.",
        ),
        "level_near": (
            "{name} còn đúng một chuyến hay một ngày ghé nữa là lên {title}, ráng lên.",
            "Ê {name}, sắp lên {title} rồi, mai ghé bến tiếp là đủ.",
        ),
        "welcome_streak": (  # ghé live nhiều ngày liền
            "{name} ghé bến {n} ngày liền rồi, chăm dữ vậy, Anh Tư thương.",
            "Lại là {name}, ngày thứ {n} liên tiếp, giữ chuỗi nghen.",
        ),
        "streak_reward": (  # mốc chuỗi ngày: thưởng lên đầu hàng
            "{name} ghé {n} ngày liền, Anh Tư thưởng suất lên đầu hàng, gõ tên tỉnh là có giường trước.",
            "Chuỗi {n} ngày của {name} nè, thưởng lên đầu hàng chờ, gõ tỉnh liền đi.",
        ),
        "versus_win": (
            "Hướng {lead} thắng đối kháng, chuyến này Anh Tư chạy hướng {lead}, bà con {rival} ráng chuyến sau.",
            "{lead} thắng {rival} rồi, xe chạy hướng {lead} liền, bà con lên xe.",
        ),
        "show_start": (  # bảng quảng cáo: dừng xe xem video
            "Dừng xe xem chút nè bà con, trên bảng đang chiếu {title}.",
            "Tấp vô lề coi cái bảng quảng cáo nè, {title}, xem xong chạy tiếp.",
        ),
        "show_end": (
            "Xem xong rồi, lên đường tiếp bà con.",
            "Hết video rồi, Anh Tư chạy tiếp đây.",
        ),
        "new_owner": (  # người tặng nhiều nhất buổi
            "{name} lên làm chủ nhà xe rồi bà con, {xu} xu, Anh Tư cúi đầu cảm ơn.",
            "Nhà xe có chủ mới, {name} với {xu} xu, chịu chơi số một.",
        ),
        "parcels": (  # thùng quà Tết người tặng quà gửi theo xe, tới quê giao tận cổng (PLAN-134 C)
            "Bốc thùng quà của {names} xuống, Anh Tư bê tận cổng cho, khỏi lo.",
            "Thùng quà Tết của {names} tới nơi rồi, ra cổng nhận đi.",
        ),
        "boarding_peak": (  # 23 → 28 Chạp: cao điểm chiều về (PLAN-134 C)
            "{lunar} rồi bà con, bến chật cứng, xe {dest} đây, gõ tên tỉnh lẹ kẻo hết giường.",
            "Cao điểm về quê rồi, {lunar}, ai về {dest} gõ tên tỉnh, Anh Tư xếp giường liền.",
        ),
        "boarding_eve": (
            "Giao thừa rồi, chuyến chót năm nay đi {dest}, ai chưa về thì lên lẹ cho kịp cúng ông bà.",
            "Chuyến cuối năm đây, {dest} đây, lên lẹ còn kịp đón giao thừa với má.",
        ),
        "boarding_tet": (
            "Năm mới an khang, xe {dest} vẫn chạy, ai đi chúc Tết thì gõ tên tỉnh.",
            "{lunar} rồi, xe {dest} vẫn chạy, ai đi thăm họ hàng thì lên xe.",
        ),
        "boarding": (
            "{dest} đây, {dest} đây, đi hông đi, gõ tên tỉnh lẹ lên.",
            "Ai về {dest} hông, đứng đó ngó hoài, gõ tên tỉnh rồi lên xe cái coi.",
            "Xe Tết đi {dest} nè mấy ông mấy bà, giường còn trống trơn, lên lẹ.",
            "Đi đâu đi đâu, {dest} hả, gõ tên tỉnh đi cha nội, Anh Tư xếp giường cho.",
        ),
        "seats_left": (
            "Còn có {n} giường à, ai đi thì lẹ cái chân lên.",
            "{n} giường nữa thôi đó, chậm là ở lại ăn Tết với nhà xe.",
            "Còn {n} chỗ, gõ lẹ lên, Anh Tư hổng chờ đâu.",
        ),
        "last_seat": (
            "Còn đúng một giường chót, ai lẹ tay người đó được, hổng giành.",
            "Một chỗ cuối, gõ lẹ đi, chậm là đứng ngoài ngó xe chạy.",
        ),
        "full": (
            "Kín giường rồi, đóng cửa, anh tài ơi chạy.",
            "Đủ rồi đủ rồi, hết chỗ, ai chưa lên ráng chờ chuyến sau.",
            "Chật ních rồi bà con, nằm sát vô, chạy nè.",
        ),
        "switch_lane": (
            "Thôi đổi tuyến, xe này chạy {dest}, ai chờ {dest} lên lẹ.",
            "Bên {dest} đông quá, quay đầu chạy {dest} luôn, lên lên.",
        ),
        "departure": (
            "Nhà xe dọn qua {station} rồi, ai về quê gõ tên tỉnh, lẹ lên kẻo hết giường.",
        ),
        "depart": (
            "Xe chạy, ngồi yên đó, đừng có đi tới đi lui, {hours} là tới {dest}.",
            "Xuất bến, giày dép bỏ bọc, đồ đạc nhét gầm giường, nằm im cho Anh Tư nhờ, {hours} tới {dest}.",
            "Anh tài đạp ga, đường {dest} {hours}, ai còn thức thả tim cho ổng chạy lẹ.",
        ),
        "rest": (
            "Ghé {place} nghỉ mười lăm phút, ai đi vệ sinh thì đi lẹ, nhớ biển số xe, lạc ráng chịu.",
            "Tới {place} rồi, ở đây có {specialty}, ai mua quà thì mua lẹ, đừng trả giá lâu.",
            "Dừng ăn cơm ở {place}, ăn lẹ lẹ, mười lăm phút xe chạy, hổng chờ ai đâu.",
        ),
        "via": (  # xe chạy qua tỉnh không ai xuống (PLAN-134): vẫn gọi bà con quê đó
            "Xe đang chạy ngang {place}, bà con {place} có ai đang coi thì thả tim chào xe cái coi.",
            "Tới địa phận {place} rồi, ai quê {place} thì thả tim cho Anh Tư biết mặt.",
            "Ngang qua {place} nè, quê ai ở {place} gõ tên tỉnh, chuyến sau Anh Tư ghé tận nơi.",
        ),
        "honk": (
            "Bíp bíp, lên xe lên xe, còn ai ở dưới hông.",
            "Lên lẹ cái coi, đếm đủ đầu là chạy.",
            "Trời đất, còn ai trong nhà vệ sinh hông, ra lẹ, xe chạy bỏ đó.",
        ),
        "dropoff_bubble": (
            "{prov}, {prov}, ai xuống {prov} ôm đồ ra cửa lẹ.",
        ),
        "finish": (
            "Hết khách, anh tài quay đầu về bến rước chuyến mới.",
            "Xong một chuyến, ai chưa đi gõ tên tỉnh chờ đó, Anh Tư về liền.",
        ),
        "likes": (
            "{total} tim rồi, anh tài phê quá đạp ga luôn.",
            "Trời ơi tim gì nhiều dữ, {total} tim rồi, thả nữa đi bà con.",
        ),
        "relief_auto": (
            "Đông quá trời đông, nhà xe kêu thêm xe đi {dest}, ai chờ hướng đó lên luôn.",
            "Thêm xe nè, xe đi {dest} chạy liền, khỏi đứng chờ mỏi giò.",
        ),
        "relief_gift": (
            "Chịu chơi, {name} bao nguyên chiếc xe cho bà con đi {dest}, lên lẹ đi.",
            "{name} bao xe rồi, ai về {dest} lên ngồi miễn phí, cảm ơn {name} cái coi.",
        ),
        "relief_admin": (
            "Nhà xe cho thêm chuyến đi {dest}, ai chờ hướng đó lên lẹ lên.",
        ),
        "home": (
            "Trời đất {name}, ở ngay {prov} mà đòi đi xe, đi bộ về đi cha nội.",
            "{name} ở {prov} luôn hả, khỏi lên, về nhà ăn bánh tét đi.",
        ),
        "treat": (
            "{name} bao trà đá cả xe, chịu chơi dữ.",
            "Có {name} khao trà đá nè, uống lẹ đi bà con.",
        ),
        "board": (
            "{names} về {prov}, lên lên, nhích vô trong.",
            "{names} đi {prov} hả, lên lẹ, nằm giường trong cho Anh Tư.",
            "Rồi, {names} về {prov}, lên xe, người sau lẹ lên.",
        ),
        "board_mixed": (
            "{names} lên rồi, dồn vô trong cho người sau lên.",
            "Lên lẹ lên {names}, đừng đứng chắn cửa.",
        ),
        "dropoff": (
            "{prov}, {prov}, {names} xuống lẹ, coi lại đồ đạc, quên ráng chịu.",
            "Tới {prov} rồi, {names} ôm đồ xuống lẹ, xe còn chạy nữa.",
            "{names} ơi, {prov} tới rồi, còn ngủ hả, dậy xuống xe lẹ.",
        ),
        "gift": (
            "Ui, {name} tặng quà, chịu chơi quá, năm nay phát tài.",
            "{name} chơi lớn dữ, cảm ơn, Tết này hốt bạc.",
            "Cảm ơn {name}, có quà là Anh Tư la to hơn nè.",
        ),
        "gift_prov": (
            "Cảm ơn {name} quê {prov} tiếp lửa cho cả xe, chúc bà con {prov} năm mới phát tài.",
            "{name} ở {prov} tặng quà tiếp xăng cho xe chạy lẹ, quý quá trời.",
        ),
        "first_gift": (
            "{name} mở hàng chuyến thứ {n}, đỏ cả chuyến rồi, cảm ơn {name} nhiều.",
            "Có {name} mở hàng chuyến {n} rồi bà con, nổ pháo hoa lấy hên đầu chuyến.",
        ),
    },
    # ---- gen Z -----------------------------------------------------------------------------------------
    "genz": {
        "fuel": (
            "{name} đổ xăng cho xe, bình {n} phần trăm, full bình là chạy như bay.",
            "Xăng lên {n} phần trăm nhờ {name}, uy tín.",
        ),
        "wash": (
            "{name} rửa xe sạch bong, {n} phần trăm rồi, xe xịn xò.",
            "Xe được {name} tắm cho, sạch {n} phần trăm, đẹp trai hẳn.",
        ),
        "this_trip": (
            "Chuyến này đi {dest} đó, ai đi {others} chờ chuyến sau, giữ chỗ rồi khỏi lo.",
            "Xe này chạy {dest}, team {others} đợi chuyến sau, uy tín giữ chỗ.",
        ),
        "board_lock": (
            "Sắp lăn bánh rồi {name}, khum xuống được nữa đâu.",
            "Đóng cửa rồi {name}, ngồi yên tận hưởng chuyến đi.",
        ),
        "back_again": (
            "{name} mới về {prov} đã comeback bến xe, nghiện đi xe Tết rồi đó.",
            "Ơ {name} về {prov} rồi mà, quay xe ra bến chi vậy, thôi lên luôn.",
        ),
        "station_vote": (
            "{name} vote xe ra {station}, {n} trên {need} rồi, team đó vào gõ đi.",
            "Đủ {need} người gọi {station} là xe quay đầu liền, giờ mới {n}.",
        ),
        "pickup_wait": (
            "Oke {name}, ra điểm đón {place} đứng chờ, xe tới đón liền, uy tín.",
            "{name} ra điểm đón {place} đứng đợi, xe tới trong một nốt nhạc.",
        ),
        "pickup": (
            "Tới điểm đón {place} rồi, {name} lên xe, gét gô.",
            "Rước {name} ở {place} rồi nè, đỉnh nóc.",
        ),
        "passed": (
            "Xe qua {prov} mất tiêu rồi {name}, quay xe chờ chuyến sau.",
            "Toang, xe vừa qua {prov}, {name} giữ chỗ chuyến sau.",
        ),
        "same_home": (
            "{name} với {other} cùng team {prov}, đồng hương gặp nhau trên xe, xịn xò.",
            "Hội {prov} có thêm {name}, {other} có bạn rồi nè.",
        ),
        "welcome_trips": (
            "{name} comeback rồi nè, đã về {prov} {n} chuyến, khách ruột uy tín.",
            "Khách quen {name} của tuyến {prov} điểm danh, đỉnh nóc kịch trần.",
        ),
        "welcome_back": (
            "{name} quay lại rồi kìa, lần này lên xe luôn đi, khum là toang.",
            "Ơ {name} ghé lại nè, gõ tên tỉnh cái là có giường liền.",
        ),
        "invite": (
            "{name} thả tim đỉnh nóc mà chưa lên xe, gõ tên tỉnh cái là có giường liền.",
            "Ơ {name} tim nhiều thế mà đứng ngoài, gõ tên tỉnh quê lên xe đi, gét gô.",
        ),
        "invite_home": (
            "{name} thả tim xịn xò, năm nay về {prov} khum, gõ {prov} là có giường.",
            "Team {prov} thiếu {name} nè, gõ {prov} lên xe liền, uy tín.",
        ),
        "screen_relief": (
            "Chuyển cảnh qua xe số {no} nè, đi {dest}, {n} người, còn {km} ki lô mét tới {next}.",
            "Xe số {no} lên sóng, team {dest} {n} người, sắp tới {next}, uy tín.",
        ),
        "screen_main": (
            "Quay về xe số {no} đi {dest}, {n} người đang chill trên xe.",
            "Back về xe số {no} hướng {dest} rồi mấy bồ, {n} người trên xe.",
        ),
        "rules": (
            "Người mới vô gõ tên tỉnh quê là có giường, thả tim cho xe chạy nhanh, gõ xe nào để check vé, dễ ợt.",
            "Chơi sao hả, gõ tên tỉnh là lên xe, tặng quà là có hiệu ứng, gõ không về là ở lại, gét gô.",
        ),
        "board_home": (
            "{name} về {prov} như lần trước luôn, quê khác thì gõ tên tỉnh, uy tín.",
            "Oke {name}, chốt {prov} như bữa trước, muốn đổi thì gõ tỉnh khác.",
        ),
        "board_hint": (
            "{name} gõ tên tỉnh quê là lên xe liền, ví dụ Nghệ An, dễ ợt.",
            "Muốn lên xe thì gõ tên tỉnh {name} ơi, gõ Huế là về Huế.",
        ),
        "priority": (
            "{name} tặng quà nên được lên đầu hàng xe {dest}, thứ {pos}, uy tín.",
            "Cảm ơn {name}, vé ưu tiên xe {dest}, giờ đứng thứ {pos} rồi.",
        ),
        "turbo": (
            "{name} bơm xăng xịn, xe bay gấp đôi {secs} giây, chuyến sau tới sớm luôn.",
            "{name} tặng quà, xe chạy gấp đôi, người chờ sắp được lên rồi.",
        ),
        "toll": (
            "Tới trạm thu phí {place}, phí {goal} xu, ae tặng quà góp cho xe qua trạm cái.",
            "Barie {place} hạ xuống rồi, cần {goal} xu qua trạm, góp quà đi ae.",
        ),
        "police": (
            "Toang, công an tuýt còi, {reason}, phạt {goal} xu, ae góp quà nộp phạt giùm.",
            "Bị kiểm tra giấy tờ, {reason}, phạt {goal} xu, ai góp quà là xe đi liền.",
        ),
        "speeding": (
            "Bay quá bị bắn tốc độ luôn, phạt {goal} xu, ae góp quà nộp phạt thôi.",
            "Quá tốc độ rồi ae, công an phạt {goal} xu, góp quà cho xe đi tiếp.",
        ),
        "rollcall": (
            "{name} ơi còn online không, thả tim trong {seconds} giây để giữ giường.",
            "Tới lượt {name} rồi, còn xem thì thả tim báo danh, giường đang giữ cho á.",
        ),
        "rollcall_ok": (
            "{name} điểm danh rồi, lên giường liền.",
            "{name} còn on, lên xe thôi.",
        ),
        "rollcall_skip": (
            "{name} offline rồi hả, giường nhường người sau, {name} đi chuyến tới.",
            "Gọi {name} không thấy rep, vé vẫn giữ, lùi chuyến sau.",
        ),
        "rollcall_drop": (
            "{name} vắng hai chuyến, vé nhả cho ae khác, quay lại gõ tỉnh là có vé liền.",
            "Hai lần không thấy {name}, nhường vé nhé ae, về lại gõ tỉnh đặt lại.",
        ),
        "block_remind": (
            "Còn thiếu {left} xu là {what}, ae góp thêm chút quà.",
            "Xe đứng im chờ ae, thiếu {left} xu {what}, góp quà đi.",
        ),
        "block_paid": (
            "Đủ rồi, {name} với ae uy tín, xe {what} chạy tiếp.",
            "{name} chốt đơn, góp đủ, {what} xong, lên đường.",
        ),
        "hungry_vendor": (
            "{name} sắp đói rồi, gõ nem, bì, bánh mì để {vendor} ship tận giường.",
            "{name} hết pin bụng rồi, order liền đi, {vendor} đang trên xe.",
        ),
        "hungry_call": (
            "{name} sắp đói rồi, ae góp quà gọi {vendor} lên bán đồ ăn.",
            "Bụng {name} biểu tình rồi, góp quà gọi {vendor} lên xe đi ae.",
        ),
        "quiz_ask": (
            "Đố vui nè ae, {q}. A, {a}. B, {b}. C, {c}. Gõ A, B hoặc C, ba người nhanh nhất được xướng tên.",
            "Câu đố siêu dễ nè, {q}. A là {a}, B là {b}, C là {c}. Gõ đáp án lẹ đi ae.",
        ),
        "quiz_win": (
            "Đáp án là {ans}. {name} đỉnh nóc kịch trần, cộng điểm cho tỉnh nhà.",
            "Chuẩn luôn, {ans}. {name} uy tín, câu sau nhanh tay nữa nghen.",
        ),
        "quiz_none": (
            "Toang, không ai trúng, đáp án là {ans}. Câu sau gỡ lại ae.",
            "Đáp án là {ans}, ae khum ai trúng hết, câu sau làm lại.",
        ),
        "fact": (
            "Ae biết không, {fact}, ai quê đây điểm danh cái.",
            "Chuyện hay nè, {fact}, Tết về nhớ ghé chéc in.",
        ),
        "weather_drizzle": (
            "Mưa phùn lất phất, chill dữ thần luôn ae.",
            "Trời mưa phùn rồi, lạnh run, ae đắp mền vô.",
        ),
        "weather_rain": (
            "Mưa rồi ae ơi, không khí về quê chuẩn phim luôn.",
            "Trời đổ mưa, tài xế chạy chậm lại cho an toàn nghen.",
        ),
        "weather_fog": (
            "Sương mù dày đặc, cảnh như phim, tài xế bật đèn chạy chậm.",
            "Sương giăng kín đường, ảo ma thật sự ae.",
        ),
        "weather_clear": (
            "Tạnh rồi ae, nắng đẹp quá trời.",
            "Hết mưa rồi, đường khô, quẩy tiếp thôi.",
        ),
        "tire": (
            "Toang, xe xẹp lốp ở {place}, Anh Tư thay liền, ae thả tim tiếp sức, tặng {goal} xu gọi thợ là xong ngay.",
            "Nổ lốp rồi ae, chờ xíu thay bánh, thả tim cho lẹ.",
        ),
        "jam": (
            "Kẹt xe ở {place} rồi ae, thả tim cho đường thông lẹ.",
            "Kẹt cứng luôn, ae thả tim, tặng {goal} xu là Anh Tư xin đường đi trước.",
        ),
        "cattle": (
            "Đàn trâu qua đường ở {place}, xe đứng hình, ae thả tim cho trâu đi lẹ.",
            "Trâu ơi tránh đường cho xe về quê, ae thả tim hối trâu đi.",
        ),
        "incident_clear": (
            "Xong rồi ae, {what} xong, gét gô.",
            "Ổn áp rồi, cảm ơn ae thả tim, chạy tiếp thôi.",
        ),
        "vendor_pool": (
            "{name} góp quà gọi cô bán hàng, thêm {left} xu nữa là có nem, bì, bánh mì lên xe.",
            "Còn {left} xu là cô Ba lên xe bán đồ ăn, {name} mở bát rồi đó ae.",
        ),
        "vendor_board": (
            "{name} góp đủ, {vendor} lên xe ở {prov}, ae gõ nem, bì, bánh mì để order.",
            "Nhờ {name}, {vendor} lên xe bán đồ ăn, order bằng cách gõ tên món.",
        ),
        "vendor_board_admin": (
            "{vendor} lên xe ở {prov} bán nem, bì, bánh mì, ae order liền.",
            "Có {vendor} bán đồ ăn lên xe, gõ nem, bì hay bánh mì.",
        ),
        "vendor_sell": (
            "{name} đang đi dọc xe, gõ nem, bì, bánh mì là có, tặng quà là bao cả xe.",
            "Order đi ae, nem chua, bì cuốn, bánh mì, {name} giao tận giường.",
        ),
        "vendor_treat": (
            "{name} bao cả xe {item}, đỉnh thật sự.",
            "Ae ơi {name} bao nguyên xe {item}, cảm ơn {name}.",
        ),
        "vendor_end": (
            "{name} bán được {n} phần, cô xuống xe đây ae.",
            "Sold out, {name} xuống xe, ae ăn ngon.",
        ),
        "block_cover": (
            "Thôi Anh Tư bù lỗ {missing} xu {what}, xe đi tiếp, về quê là chính.",
            "Thiếu {missing} xu, Anh Tư tự bù lỗ, đi tiếp thôi ae.",
        ),
        "goal_step": (
            "Mốc {xu} xu done, {label} cho cả phòng, {name} uy tín.",
            "Cả phòng góp tới {xu} xu, mở khoá {label}, cảm ơn {name}.",
        ),
        "race_lead": (
            "{prov} đang top một đua tỉnh, tỉnh khác vào bình luận thả tim kéo lên đi ae.",
            "Đua tỉnh căng lắm, {prov} dẫn đầu, tỉnh nào nhiều điểm chuyến sau đi tỉnh đó.",
        ),
        "race_win": (
            "{prov} win đua tỉnh, chuyến này chạy hướng {prov} luôn.",
            "Team {prov} thắng rồi, xe đi {prov} ae ơi.",
        ),
        "versus_start": (
            "Pê ka chuyến sau nè ae, team {lead} đấu team {rival}, quê bên nào thì com men, thả tim, tặng quà cho bên đó, team nào nhiều điểm chạy trước.",
            "{lead} hay {rival} chạy trước đây ae, chưa gõ quê thì gõ tên tỉnh vô để vào team.",
        ),
        "versus_lead": (
            "Team {lead} đang dẫn team {rival}, team {rival} đâu rồi, thả tim gánh team đi ae.",
            "{lead} vượt lên rồi, {rival} không kéo là chờ chuyến sau đó ae.",
        ),
        "level_up": (
            "{name} lên cấp {title} rồi mọi người ơi, đỉnh nóc kịch trần.",
            "Chúc mừng {name} up lên {title}, khách ruột uy tín.",
        ),
        "level_near": (
            "{name} còn một chuyến nữa là lên {title}, gét gô.",
            "{name} sắp up {title} rồi, mai ghé tiếp là xong.",
        ),
        "welcome_streak": (
            "{name} giữ chuỗi {n} ngày liền, quá cháy.",
            "Ngày thứ {n} liên tiếp của {name}, chuỗi đẹp đừng để đứt.",
        ),
        "streak_reward": (
            "{name} chuỗi {n} ngày, thưởng lên đầu hàng luôn, gõ tỉnh là có giường trước.",
            "Chuỗi {n} ngày của {name} nè, quà là lên đầu hàng chờ, gét gô.",
        ),
        "versus_win": (
            "Team {lead} win pê ka, chuyến này chạy hướng {lead}, team {rival} hẹn chuyến sau.",
            "{lead} thắng {rival} rồi ae, xe chạy hướng {lead} luôn.",
        ),
        "show_start": (
            "Dừng xe hóng cái bảng quảng cáo nè ae, {title}.",
            "Tạm dừng xem video hot, {title}, xem xong chạy tiếp.",
        ),
        "show_end": (
            "Xem xong, đi tiếp thôi ae.",
            "Hết video, xe chạy tiếp nè.",
        ),
        "new_owner": (
            "{name} chính thức làm chủ nhà xe, {xu} xu, đỉnh nóc kịch trần.",
            "Chủ nhà xe mới là {name} đó mấy bồ, {xu} xu, xịn xò.",
        ),
        "parcels": (
            "Ship tận cổng thùng quà của {names}, uy tín luôn.",
            "Thùng quà của {names} hạ cánh an toàn, chuẩn đét.",
        ),
        "boarding_peak": (
            "{lunar} rồi mấy bồ, bến đông muốn xỉu, xe {dest} còn giường, gét gô.",
            "Cao điểm về quê nè, ai đi {dest} gõ tên tỉnh lẹ, chậm là toang.",
        ),
        "boarding_eve": (
            "Giao thừa rồi, chuyến chót đi {dest}, lên lẹ cho kịp coi pháo hoa với nhà.",
            "Chuyến cuối năm đi {dest}, ai còn kẹt ở thành phố thì quay xe về quê liền.",
        ),
        "boarding_tet": (
            "Năm mới đỉnh nóc kịch trần, xe {dest} vẫn chạy, ai đi chúc Tết gõ tên tỉnh.",
            "{lunar} rồi, đi chơi Tết {dest} thì lên xe, uy tín.",
        ),
        "boarding": (
            "Ai về {dest} điểm danh, gõ tên tỉnh vô, lên xe gét gô.",
            "Xe đi {dest} tới công chuyện rồi, gõ tên tỉnh là có giường, khum lằng nhằng.",
            "{dest} đây mọi người ơi, ai về quê ăn Tết thì gõ tên tỉnh, chốt đơn liền.",
            "Ủa alo, ai về {dest} mà còn đứng đó, gõ tên tỉnh lẹ đi.",
        ),
        "seats_left": (
            "Còn {n} giường thôi, chậm là ét ô ét đó.",
            "{n} chỗ cuối, ai nhanh tay thì chốt, chậm là toang.",
            "Còn {n} giường, gõ tên tỉnh liền, khum là lỡ chuyến.",
        ),
        "last_seat": (
            "Giường cuối cùng, ai lụm được là đỉnh nóc kịch trần.",
            "Một chỗ cuối, ai chậm là trầm cảm luôn đó.",
        ),
        "full": (
            "Kín giường rồi, đóng cửa, anh tài gét gô.",
            "Hết chỗ rồi, ai chưa lên thì chờ chuyến sau, đừng dỗi.",
            "Đủ người rồi, xe chạy liền, nằm thả lỏng đi mọi người.",
        ),
        "switch_lane": (
            "Bất ngờ chưa, xe này đổi qua đi {dest}, ai chờ hướng đó lên liền.",
            "Bên {dest} đông quá trời, xe quay xe chạy {dest} luôn.",
        ),
        "departure": (
            "Nhà xe dời qua {station} rồi, ai về quê gõ tên tỉnh, điểm danh liền.",
        ),
        "depart": (
            "Gét gô, xe lăn bánh rồi, {hours} là tới {dest}, ngủ một giấc là tới nơi.",
            "Xe chạy rồi mọi người, đường về {dest} {hours}, ai còn thức thì thả tim cho anh tài có động lực.",
            "Xuất phát, cất điện thoại đi, mà thôi cứ cầm xem live cũng được, {hours} là tới {dest}.",
        ),
        "rest": (
            "Tới {place} rồi, nghỉ mười lăm phút, đi vệ sinh, chụp hình sống ảo lẹ lẹ.",
            "Trạm {place} có {specialty}, ai mua làm quà thì mua, đừng để mẹ chê keo.",
            "Ghé {place} ăn lẹ mười lăm phút, ăn xong lên xe liền, đừng bắt cả xe chờ, kỳ lắm.",
        ),
        "via": (
            "Đang lướt qua {place}, team {place} điểm danh cái, thả tim cho uy tín.",
            "Qua {place} rồi đó, người {place} đâu hết rồi, thả tim cái cho xe có động lực.",
        ),
        "honk": (
            "Ê mọi người, lên xe, anh tài sắp chạy rồi đó.",
            "Còn ai ở dưới hông, lên lẹ, khum là ở lại trạm luôn.",
            "Đếm người nè, thiếu ai là toang, lên xe lẹ.",
        ),
        "dropoff_bubble": (
            "Tới {prov} rồi, ai về {prov} xách đồ xuống, về nhà khoe với họ hàng.",
        ),
        "finish": (
            "Xong chuyến, mãi đỉnh, xe quay về bến đón đợt mới.",
            "Hết khách rồi, ai chưa đi thì gõ tên tỉnh chờ, Anh Tư quay lại liền.",
        ),
        "likes": (
            "{total} tim rồi, cháy quá, anh tài đạp ga.",
            "Tim nhiều dữ vậy trời, {total} tim, xe chạy như bay luôn.",
        ),
        "relief_auto": (
            "Đông quá xỉu ngang, nhà xe kêu thêm xe đi {dest}, ai chờ hướng đó lên luôn.",
            "Thêm xe rồi, xe đi {dest} chạy liền, khỏi chờ mòn mỏi.",
        ),
        "relief_gift": (
            "{name} bao nguyên chiếc xe đi {dest}, đỉnh nóc kịch trần bay phấp phới.",
            "{name} chơi lớn bao xe, ai về {dest} lên liền, cảm ơn {name} nhiều.",
        ),
        "relief_admin": (
            "Nhà xe thêm chuyến đi {dest}, ai chờ hướng đó lên liền.",
        ),
        "home": (
            "Ủa {name} ở ngay {prov} mà, đi bộ về nhà đi, khum cần xe đâu.",
            "{name} ở {prov} luôn hả, vậy về nhà ăn Tết luôn, khỏi lên xe.",
        ),
        "treat": (
            "{name} bao trà đá cả xe, mãi đỉnh.",
            "{name} khao trà đá, uy tín luôn.",
        ),
        "board": (
            "{names} về {prov}, lên xe, gét gô.",
            "{names} đã lên xe về {prov}, uy tín.",
            "Điểm danh {names}, về {prov}, lên xe liền.",
        ),
        "board_mixed": (
            "{names} lên xe rồi, xích vô cho người sau.",
            "Chào {names}, lên xe, nằm giường nào cũng được, khum kén.",
        ),
        "dropoff": (
            "Tới {prov} rồi, {names} xuống xe, về nhà khoe họ hàng đi.",
            "{names} ơi, {prov} tới rồi, xách đồ xuống, đừng bỏ quên sạc dự phòng.",
            "{prov} tới công chuyện, {names} xuống xe lẹ.",
        ),
        "gift": (
            "{name} tặng quà, uy tín, năm nay giàu.",
            "Cảm ơn {name}, đỉnh nóc kịch trần.",
            "{name} chơi lớn quá, Tết này nhận lì xì mỏi tay.",
        ),
        "gift_prov": (
            "{name} team {prov} tặng quà tiếp lửa cho cả xe, uy tín luôn.",
            "Cảm ơn {name} quê {prov} bơm xăng cho xe phóng vèo vèo, đỉnh nóc.",
        ),
        "first_gift": (
            "{name} mở bát chuyến thứ {n}, nổ pháo hoa khai xuân, uy tín luôn.",
            "Chuyến số {n} có {name} mở hàng rồi, vía tốt cả xe chạy mượt.",
        ),
    },
    # ---- gen Y -----------------------------------------------------------------------------------------
    "geny": {
        "fuel": (
            "{name} đổ xăng, bình đầy {n} phần trăm, chuẩn không cần chỉnh.",
            "Cảm ơn {name}, xăng lên {n} phần trăm rồi.",
        ),
        "wash": (
            "{name} rửa xe, sạch {n} phần trăm, về quê cho bảnh.",
            "Xe sạch {n} phần trăm nhờ {name}, bóng như mới.",
        ),
        "this_trip": (
            "Đây là chuyến đi {dest}, ai về {others} vui lòng đợi chuyến sau, đã giữ chỗ.",
            "Xe này đi {dest}, bà con {others} chờ chuyến sau nhé.",
        ),
        "board_lock": (
            "Xe sắp chạy rồi {name}, giờ không đổi được nữa.",
            "Chốt sổ rồi {name}, ngồi yên xe chạy.",
        ),
        "back_again": (
            "{name} vừa về {prov} đã ra bến lại, chắc quên quà cho mẹ.",
            "Mới về {prov} xong {name} lại ra bến, chăm đi xe ghê.",
        ),
        "station_vote": (
            "{name} muốn xe ra {station}, đang {n} trên {need} người, ai cùng ý thì gõ theo.",
            "Ghi nhận {name} gọi xe ra {station}, đủ {need} người là đi.",
        ),
        "pickup_wait": (
            "{name} ra điểm đón {place} chờ, xe tới đón, chuẩn không cần chỉnh.",
            "Ok {name}, đứng ở điểm đón {place}, xe ghé rước liền.",
        ),
        "pickup": (
            "Ghé điểm đón {place} rước {name}, lên xe thôi.",
            "{name} lên xe ở {place} rồi, đi tiếp.",
        ),
        "passed": (
            "Xe qua {prov} rồi {name}, hẹn chuyến sau.",
            "Tiếc ghê, xe vừa qua {prov}, {name} chờ chuyến sau nhé.",
        ),
        "same_home": (
            "{name} với {other} cùng về {prov}, đồng hương chuẩn không cần chỉnh.",
            "Thêm {name} về {prov}, có {other} đi cùng cho đỡ buồn.",
        ),
        "welcome_trips": (
            "Chào {name} quay lại, đã về {prov} {n} chuyến rồi, khách quen chuẩn không cần chỉnh.",
            "{name} lại ghé bến, tuyến {prov} nhớ mặt rồi, chúc chuyến này cũng thuận buồm.",
        ),
        "welcome_back": (
            "{name} ghé lại bến rồi, lần này gõ tên tỉnh lên xe luôn cho chất.",
            "Chào {name} quay lại, quê ở đâu thì gõ tên tỉnh, Anh Tư xếp giường cho.",
        ),
        "invite": (
            "{name} thả tim nãy giờ mà chưa lên xe, quê ở đâu thì gõ tên tỉnh, Anh Tư giữ giường cho.",
            "Cảm ơn {name} thả tim, gõ tên tỉnh quê là lên xe luôn, chuẩn không cần chỉnh.",
        ),
        "invite_home": (
            "{name} thả tim nhiều quá, năm nay về {prov} nữa không, gõ {prov} là có giường.",
            "Khách quen {prov} {name} đây rồi, gõ {prov} lên xe cho chất.",
        ),
        "screen_relief": (
            "Giờ mời bà con xem xe số {no} đi {dest}, chở {n} người, còn {km} ki lô mét tới {next}.",
            "Xe số {no} hướng {dest} lên sóng, {n} khách, sắp tới {next}.",
        ),
        "screen_main": (
            "Quay lại xe số {no} đi {dest}, {n} khách trên xe.",
            "Trở về xe số {no} hướng {dest}, {n} người đang về quê.",
        ),
        "rules": (
            "Ai mới vào thì gõ tên tỉnh quê mình là lên xe, thả tim cho xe chạy nhanh, gõ xe nào để xem vé của mình.",
            "Luật đơn giản thôi, gõ tên tỉnh là có giường, tặng quà là có hiệu ứng, gõ không về nếu ở lại, chuẩn không cần chỉnh.",
        ),
        "board_home": (
            "{name} về {prov} như lần trước, muốn đổi quê thì gõ tên tỉnh khác.",
            "Ghi nhận {name} về {prov} như chuyến trước, chuẩn không cần chỉnh.",
        ),
        "board_hint": (
            "{name} muốn lên xe thì gõ tên tỉnh quê mình, ví dụ Nghệ An, Cà Mau.",
            "Lên xe đơn giản lắm {name}, gõ tên tỉnh quê vào bình luận là có giường.",
        ),
        "priority": (
            "Cảm ơn {name}, được lên đầu hàng chờ xe {dest}, hiện là thứ {pos}.",
            "{name} tặng quà, chuyến {dest} sau được lên trước, thứ {pos} trong hàng.",
        ),
        "turbo": (
            "Cảm ơn {name}, xe chạy nhanh gấp đôi, ai đang chờ sắp tới lượt rồi.",
            "{name} tặng quà, xe tăng tốc thêm {secs} giây, về bến sớm đón bà con.",
        ),
        "toll": (
            "Xe tới trạm thu phí {place}, phí {goal} xu, mọi người tặng quà góp để xe qua trạm.",
            "Trạm thu phí {place} rồi, cần {goal} xu, ai góp quà là xe qua liền.",
        ),
        "police": (
            "Công an ra hiệu dừng xe, {reason}, phạt {goal} xu, mọi người góp quà nộp phạt giúp.",
            "Bị kiểm tra giấy tờ, {reason}, phạt {goal} xu, góp quà để xe đi tiếp.",
        ),
        "speeding": (
            "Xe chạy quá tốc độ bị công an bắn tốc độ, phạt {goal} xu, mọi người góp quà giúp.",
            "Quá tốc độ rồi, phạt {goal} xu, ai góp quà là xe đi tiếp.",
        ),
        "rollcall": (
            "{name} còn xem không, thả tim hoặc bình luận trong {seconds} giây để giữ giường.",
            "Tới lượt {name} lên xe, còn ở đây thì thả tim cho Anh Tư biết.",
        ),
        "rollcall_ok": (
            "{name} có mặt, mời lên xe.",
            "Cảm ơn {name}, mời lên giường.",
        ),
        "rollcall_skip": (
            "Chưa thấy {name} trả lời, giường nhường người sau, {name} đi chuyến tới.",
            "{name} chưa có mặt, vé vẫn giữ, lùi xuống chuyến sau.",
        ),
        "rollcall_drop": (
            "Hai lần gọi không thấy {name}, vé nhường người khác, quay lại thì gõ tỉnh để đặt lại.",
            "{name} vắng hai chuyến, Anh Tư nhả vé, về lại gõ tỉnh là có vé.",
        ),
        "block_remind": (
            "Còn thiếu {left} xu là {what}, mọi người góp thêm quà nhé.",
            "Xe đang đứng chờ, thiếu {left} xu {what}.",
        ),
        "block_paid": (
            "Cảm ơn {name} và mọi người, góp đủ rồi, xe {what} đi tiếp.",
            "Đủ tiền rồi, cảm ơn {name}, xe {what} lên đường.",
        ),
        "hungry_vendor": (
            "{name} sắp đói rồi, gõ nem, bì hoặc bánh mì để {vendor} mang tới.",
            "{name} đói bụng rồi, {vendor} đang bán trên xe, gõ tên món để mua.",
        ),
        "hungry_call": (
            "{name} sắp đói rồi, mọi người góp quà gọi {vendor} lên xe bán đồ ăn.",
            "{name} đói bụng rồi, góp quà để {vendor} lên xe bán nem, bì, bánh mì.",
        ),
        "quiz_ask": (
            "Đố vui nè mọi người, {q}. A, {a}. B, {b}. C, {c}. Gõ A, B hoặc C, ba người đúng sớm nhất được đọc tên.",
            "Câu đố đây, {q}. A là {a}, B là {b}, C là {c}. Mọi người gõ A, B hay C.",
        ),
        "quiz_win": (
            "Đáp án là {ans}. {name} chuẩn không cần chỉnh, cộng điểm cho tỉnh nhà.",
            "Chính xác, {ans}. Chúc mừng {name}, câu sau nhanh tay nữa.",
        ),
        "quiz_none": (
            "Bó tay chấm com, chưa ai đúng, đáp án là {ans}.",
            "Đáp án là {ans}, câu này khó quá, để câu sau.",
        ),
        "fact": (
            "Mọi người biết không, {fact}, ai quê ở đây thả tim nào.",
            "Xe đang đi ngang, {fact}, Tết này nhớ ghé.",
        ),
        "weather_drizzle": (
            "Mưa phùn rồi, lạnh như nước cất, mọi người đắp chăn vào.",
            "Trời mưa phùn lất phất, đường trơn, tài xế chạy chậm thôi.",
        ),
        "weather_rain": (
            "Trời đổ mưa rồi, ai gần cửa sổ kéo rèm giúp.",
            "Mưa rào tới, tài xế bật gạt nước, chạy từ từ.",
        ),
        "weather_fog": (
            "Sương mù dày quá, tài xế bật đèn sương mù chạy chậm lại.",
            "Sương giăng kín đường, nhìn ra cửa sổ mờ mờ đẹp lắm.",
        ),
        "weather_clear": (
            "Tạnh mưa rồi, nắng lên đẹp quá.",
            "Hết mưa rồi, đường khô ráo, xe chạy êm.",
        ),
        "tire": (
            "Xe xẹp lốp ở {place} rồi, Anh Tư thay ngay, mọi người thả tim tiếp sức, tặng {goal} xu gọi thợ là xong liền.",
            "Nổ lốp rồi, chờ chút thay bánh, mọi người thả tim cho nhanh.",
        ),
        "jam": (
            "Kẹt xe ở {place} rồi, mọi người thả tim cho đường thông nhanh.",
            "Đường kẹt cứng, thả tim nào, tặng {goal} xu là Anh Tư xin đường đi trước.",
        ),
        "cattle": (
            "Đàn trâu qua đường ở {place}, xe dừng chờ, thả tim cho trâu đi nhanh.",
            "Trâu ơi tránh đường cho xe về quê ăn Tết, mọi người thả tim nào.",
        ),
        "incident_clear": (
            "Xong rồi, {what} xong, xe đi tiếp.",
            "Ổn rồi, cảm ơn mọi người thả tim, lên đường thôi.",
        ),
        "vendor_pool": (
            "Cảm ơn {name}, thêm {left} xu nữa là cô bán hàng lên xe bán nem, bì, bánh mì.",
            "{name} góp gọi cô bán hàng, còn {left} xu nữa.",
        ),
        "vendor_board": (
            "Nhờ {name} góp quà, {vendor} lên xe ở {prov}, ai muốn ăn gõ nem, bì hoặc bánh mì.",
            "{vendor} lên xe rồi, cảm ơn {name}, mọi người gõ tên món để mua.",
        ),
        "vendor_board_admin": (
            "Xe dừng ở {prov} cho {vendor} lên bán nem, bì, bánh mì.",
            "{vendor} lên xe bán đồ ăn, mọi người gõ tên món để mua.",
        ),
        "vendor_sell": (
            "{name} đang đi dọc xe, gõ nem, bì hoặc bánh mì để mua, tặng quà để bao cả xe.",
            "Có nem chua, bì cuốn, bánh mì, mọi người gõ tên món, {name} mang tới giường.",
        ),
        "vendor_treat": (
            "Cảm ơn {name} đã bao cả xe {item}.",
            "{name} bao cả xe {item}, mọi người cảm ơn {name} nhé.",
        ),
        "vendor_end": (
            "{name} bán được {n} phần, cảm ơn mọi người, cô xuống xe.",
            "Hết hàng, {name} xuống xe, chúc mọi người ngon miệng.",
        ),
        "block_cover": (
            "Anh Tư bù lỗ {missing} xu {what}, xe đi tiếp cho kịp về quê.",
            "Thiếu {missing} xu, Anh Tư bù lỗ, xe đi tiếp.",
        ),
        "goal_step": (
            "Mục tiêu buổi live đạt {xu} xu, {label} cho mọi người, cảm ơn {name}.",
            "Đã tới mốc {xu} xu, {label}, cảm ơn {name} và mọi người.",
        ),
        "race_lead": (
            "{prov} đang dẫn đầu đua tỉnh, mọi người bình luận, thả tim, tặng quà để tỉnh mình lên đầu.",
            "Đua tỉnh: {prov} dẫn đầu, tỉnh thắng được đi chuyến sau.",
        ),
        "race_win": (
            "{prov} thắng đua tỉnh, chuyến này đi hướng {prov}.",
            "Chúc mừng {prov}, xe đi hướng {prov}.",
        ),
        "versus_start": (
            "Đối kháng chuyến sau: hướng {lead} đấu hướng {rival}, mọi người quê bên nào thì bình luận, thả tim, tặng quà cho bên đó, bên nhiều điểm hơn chạy trước.",
            "Chuyến sau đi {lead} hay {rival} là do mọi người, ai chưa gõ quê thì gõ tên tỉnh để vào phe.",
        ),
        "versus_lead": (
            "Hướng {lead} đang dẫn điểm hướng {rival}, mọi người {rival} cố lên.",
            "{lead} đang dẫn trước {rival}, còn kịp lật kèo.",
        ),
        "level_up": (
            "Chúc mừng {name} lên cấp {title}, cảm ơn đã đồng hành cùng nhà xe.",
            "{name} vừa lên {title}, chuẩn không cần chỉnh.",
        ),
        "level_near": (
            "{name} chỉ còn một chuyến hoặc một ngày ghé nữa là lên {title}.",
            "{name} sắp lên {title} rồi, hẹn gặp lại ở bến.",
        ),
        "welcome_streak": (
            "{name} ghé bến {n} ngày liên tiếp, cảm ơn đã luôn có mặt.",
            "Ngày thứ {n} liền của {name}, giữ chuỗi nhé.",
        ),
        "streak_reward": (
            "{name} ghé {n} ngày liền, nhà xe tặng suất lên đầu hàng chờ, gõ tên tỉnh là có giường trước.",
            "Chuỗi {n} ngày của {name}, phần thưởng là lên đầu hàng chờ.",
        ),
        "versus_win": (
            "Hướng {lead} thắng đối kháng, chuyến này đi hướng {lead}, hướng {rival} đi chuyến sau.",
            "Chúc mừng {lead}, xe đi hướng {lead}, {rival} hẹn chuyến sau.",
        ),
        "show_start": (
            "Xe dừng một chút để mọi người xem video trên bảng, {title}.",
            "Mời mọi người xem video {title}, xem xong xe chạy tiếp.",
        ),
        "show_end": (
            "Xem xong rồi, xe chạy tiếp.",
            "Hết video, mình lên đường tiếp.",
        ),
        "new_owner": (
            "Chúc mừng {name} lên làm chủ nhà xe với {xu} xu, cảm ơn nhiều.",
            "{name} giờ là chủ nhà xe, {xu} xu, quá chất.",
        ),
        "parcels": (
            "Giao tận cổng thùng quà Tết của {names}, chuẩn không cần chỉnh.",
            "Quà Tết của {names} về tới nhà rồi, cả nhà mở quà thôi.",
        ),
        "boarding_peak": (
            "{lunar} rồi, cao điểm về quê, xe {dest} còn chỗ, gõ tên tỉnh chuẩn không cần chỉnh.",
            "Bến đông như hội, ai về {dest} thì gõ tên tỉnh lẹ lên.",
        ),
        "boarding_eve": (
            "Giao thừa rồi, chuyến cuối năm đi {dest}, lên xe về kịp cúng giao thừa.",
            "Chuyến chót năm nay đi {dest}, ai chưa về thì quẩy lên xe liền.",
        ),
        "boarding_tet": (
            "Năm mới vạn sự như ý, xe {dest} vẫn chạy, ai đi chúc Tết thì gõ tên tỉnh.",
            "{lunar} rồi, xe {dest} chạy đều, ai đi thăm họ hàng thì lên xe.",
        ),
        "boarding": (
            "Ai về {dest} thì gõ tên tỉnh, lên xe, chuẩn không cần chỉnh.",
            "Xe đi {dest} đây, ngon lành cành đào, gõ tên tỉnh là có giường.",
            "{dest} đây bà con, về quê ăn Tết thì gõ tên tỉnh, đừng ngồi chém gió nữa.",
            "Về {dest} hông, gõ tên tỉnh đi, kẻo hết giường lại ngồi khóc ròng.",
        ),
        "seats_left": (
            "Còn {n} giường thôi, chậm là bó tay chấm com.",
            "{n} chỗ nữa thôi, ai về quê thì nhanh tay kẻo lỡ.",
            "Còn {n} giường, gõ tên tỉnh liền, kẻo hết vé lại than trời.",
        ),
        "last_seat": (
            "Giường cuối cùng, ai nhanh thì được, chậm thì thôi xong.",
            "Còn đúng một chỗ, ai lẹ tay người đó hưởng.",
        ),
        "full": (
            "Kín chỗ rồi, xe chạy, quẩy lên anh tài.",
            "Hết giường rồi, ai chưa lên thì chuyến sau, kệ đi gì căng.",
            "Đủ khách, đóng cửa, lên đường thôi.",
        ),
        "switch_lane": (
            "Đổi tuyến, xe này đi {dest}, ai chờ hướng đó lên liền.",
            "Bên {dest} đông quá, xe này chạy {dest} luôn, chuẩn bài.",
        ),
        "departure": (
            "Nhà xe dời qua {station} rồi, ai về quê gõ tên tỉnh để xếp giường.",
        ),
        "depart": (
            "Lên đường thôi, {hours} là về tới {dest}, ai mệt thì làm một giấc cho khỏe.",
            "Xe chạy rồi, đường về {dest} {hours}, ngồi yên mà hưởng.",
            "Xuất bến, nhạc lên, quẩy lên, {hours} là tới {dest}.",
        ),
        "rest": (
            "Ghé {place} nghỉ mười lăm phút, ăn uống vệ sinh cho xong, nhớ biển số xe.",
            "Trạm {place} có {specialty}, mua về biếu ông bà là chuẩn cơm mẹ nấu.",
            "Dừng ăn cơm ở {place}, ăn nhanh còn đi, đừng ngồi tám chuyện.",
        ),
        "via": (
            "Xe đang qua {place}, bà con {place} thả tim chào xe một cái, chuẩn không cần chỉnh.",
            "Ngang {place} rồi, ai quê {place} điểm danh, chuyến sau ghé tận cổng.",
        ),
        "honk": (
            "Lên xe lên xe, ai còn ở dưới thì nhanh, xe chạy rồi.",
            "Đếm người nè, thiếu ai thì gọi, xe sắp đi.",
            "Ai còn ăn dở thì gói mang theo, xe chạy liền.",
        ),
        "dropoff_bubble": (
            "Tới {prov} rồi, ai xuống {prov} chuẩn bị đồ đạc.",
        ),
        "finish": (
            "Xong chuyến, hết sẩy, xe về bến đón khách mới.",
            "Hết khách rồi, ai chưa đi thì gõ tên tỉnh chờ chuyến sau.",
        ),
        "likes": (
            "{total} tim rồi, bá đạo thật, anh tài chạy hết tốc lực.",
            "Tim nhiều quá, {total} tim rồi, cảm ơn bà con.",
        ),
        "relief_auto": (
            "Đông quá, nhà xe tăng cường thêm xe đi {dest}, ai chờ hướng đó lên luôn.",
            "Có xe tăng cường đi {dest} rồi, khỏi chờ.",
        ),
        "relief_gift": (
            "{name} bao nguyên chiếc xe đi {dest}, bá đạo thật sự.",
            "Có {name} bao xe cho bà con về {dest}, chất như nước cất.",
        ),
        "relief_admin": (
            "Nhà xe thêm chuyến đi {dest}, ai chờ hướng đó lên xe.",
        ),
        "home": (
            "{name} ở ngay {prov} mà, đi bộ về cho khỏe, đi xe chi cho tốn.",
            "{name} ở {prov} luôn hả, thôi về nhà ăn Tết, khỏi lên xe.",
        ),
        "treat": (
            "{name} bao trà đá cả xe, chất như nước cất.",
            "Có {name} khao trà đá, quý hóa quá.",
        ),
        "board": (
            "{names} về {prov}, lên xe đi.",
            "{names} lên xe về {prov} rồi, chuẩn không cần chỉnh.",
            "Có {names} về {prov}, mời lên xe.",
        ),
        "board_mixed": (
            "{names} lên xe rồi, vô trong ngồi cho người sau lên.",
            "Mời {names} lên xe, nằm đâu cũng được.",
        ),
        "dropoff": (
            "Tới {prov} rồi, {names} xuống xe, nhớ coi lại đồ đạc.",
            "{prov} đây, {names} chuẩn bị xuống, về nhà ăn Tết vui vẻ.",
            "{names} ơi, tới {prov} rồi, xuống xe về với gia đình thôi.",
        ),
        "gift": (
            "Cảm ơn {name}, quý hóa quá, năm mới phát tài.",
            "{name} tặng quà, chất như nước cất, cảm ơn nhiều.",
            "Cảm ơn {name}, chúc năm mới an khang, tiền vô như nước.",
        ),
        "gift_prov": (
            "Cảm ơn {name} quê {prov} tiếp lửa cho chuyến xe, chuẩn không cần chỉnh.",
            "{name} ở {prov} tặng quà tiếp sức cho bác tài, chất như nước cất.",
        ),
        "first_gift": (
            "{name} mở hàng chuyến thứ {n}, đầu xuôi đuôi lọt, cảm ơn {name}.",
            "Chuyến thứ {n} được {name} mở hàng may mắn, chúc cả xe thượng lộ bình an.",
        ),
    },
}


def options(kind: str, style: str = "mix") -> tuple[str, ...]:
    """Các câu cho tình huống `kind` theo kiểu nói; «mix» (hoặc kiểu lạ) = gộp cả ba kiểu."""
    if style in STYLES:
        return LINES[style][kind]
    return tuple(text for s in STYLES for text in LINES[s][kind])


def line(kind: str, rng: random.Random | None = None, style: str = "mix", **fields) -> str:
    """Một câu cho tình huống `kind` (bốc ngẫu nhiên theo kiểu nói), điền {tên} từ `fields`."""
    text = (rng or random).choice(options(kind, style)).format(**fields)
    # chỗ điền đứng đầu câu («… nhờ. {hours} tới …» → «Chừng 6 tiếng») thì viết hoa lại
    return re.sub(r"(^|[.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), text)


def hours_phrase(hours: float) -> str:
    """Giờ xe chạy nói kiểu phụ xe: «chừng 40 phút», «chừng 26 tiếng»."""
    if hours < 1:
        return f"chừng {max(10, round(hours * 6) * 10)} phút"
    return f"chừng {round(hours)} tiếng"


def spoken_list(text: str) -> str:
    """«cá ngừ · bánh hỏi» → «cá ngừ, bánh hỏi» (dấu chấm giữa đọc không tự nhiên)."""
    return text.replace(" · ", ", ")
