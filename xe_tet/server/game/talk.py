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
