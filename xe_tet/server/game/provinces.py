"""63 tỉnh theo tên cũ: biển số, cách gõ, vùng.

Từ 1/7/2025 cả nước còn 34 tỉnh, thành (Nghị quyết 202/2025/QH15) nhưng người xem vẫn nhớ quê theo tên cũ và biển số cũ
(«quê Bình Định», «biển 77»); 34 tên mới đều trùng một tên cũ nên gõ tên mới vẫn nhận. Toạ độ tỉnh lỵ ở `geo.CAPITALS`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Province:
    key: str
    name: str
    region: str  # bac | trung | taynguyen | nam
    plates: tuple[str, ...]
    aliases: tuple[str, ...] = ()  # cụm từ, khớp trong câu (đã bỏ dấu)
    codes: tuple[str, ...] = ()  # viết tắt, chỉ khớp khi cả comment đúng bằng nó


_P = Province

PROVINCES: tuple[Province, ...] = (
    # Bắc Bộ
    _P("hanoi", "Hà Nội", "bac", ("29", "30", "31", "32", "33", "40"), ("thu do",), ("hn",)),
    _P("haiphong", "Hải Phòng", "bac", ("15", "16"), (), ("hp",)),
    _P("quangninh", "Quảng Ninh", "bac", ("14",), ("ha long",), ("qninh",)),
    _P("haiduong", "Hải Dương", "bac", ("34",), (), ("hd",)),
    _P("hungyen", "Hưng Yên", "bac", ("89",), (), ("hy",)),
    _P("thaibinh", "Thái Bình", "bac", ("17",), (), ("tb",)),
    _P("namdinh", "Nam Định", "bac", ("18",), (), ("nd",)),
    _P("hanam", "Hà Nam", "bac", ("90",), (), ()),
    _P("ninhbinh", "Ninh Bình", "bac", ("35",), (), ("nb",)),
    _P("bacninh", "Bắc Ninh", "bac", ("99",), (), ("bn",)),
    _P("bacgiang", "Bắc Giang", "bac", ("98",), (), ("bg",)),
    _P("vinhphuc", "Vĩnh Phúc", "bac", ("88",), (), ("vp",)),
    _P("phutho", "Phú Thọ", "bac", ("19",), ("viet tri",), ("pt",)),
    _P("thainguyen", "Thái Nguyên", "bac", ("20",), (), ("tn",)),
    _P("hoabinh", "Hòa Bình", "bac", ("28",), (), ()),
    _P("sonla", "Sơn La", "bac", ("26",), (), ()),
    _P("dienbien", "Điện Biên", "bac", ("27",), (), ()),
    _P("laichau", "Lai Châu", "bac", ("25",), (), ()),
    _P("laocai", "Lào Cai", "bac", ("24",), ("sa pa", "sapa"), ()),
    _P("yenbai", "Yên Bái", "bac", ("21",), (), ()),
    _P("tuyenquang", "Tuyên Quang", "bac", ("22",), (), ()),
    _P("hagiang", "Hà Giang", "bac", ("23",), (), ()),
    _P("caobang", "Cao Bằng", "bac", ("11",), (), ()),
    _P("backan", "Bắc Kạn", "bac", ("97",), ("bac can",), ()),
    _P("langson", "Lạng Sơn", "bac", ("12",), (), ()),
    # Trung Bộ
    _P("thanhhoa", "Thanh Hóa", "trung", ("36",), ("xu thanh",), ("th",)),
    _P("nghean", "Nghệ An", "trung", ("37",), ("xu nghe",), ("na",)),
    _P("hatinh", "Hà Tĩnh", "trung", ("38",), (), ("ht",)),
    _P("quangbinh", "Quảng Bình", "trung", ("73",), (), ("qb",)),
    _P("quangtri", "Quảng Trị", "trung", ("74",), (), ("qt",)),
    _P("hue", "Huế", "trung", ("75",), ("hue", "thua thien hue"), ("tth",)),
    _P("danang", "Đà Nẵng", "trung", ("43",), (), ("dn",)),
    _P("quangnam", "Quảng Nam", "trung", ("92",), ("hoi an",), ("qnam",)),
    _P("quangngai", "Quảng Ngãi", "trung", ("76",), (), ("qng",)),
    _P("binhdinh", "Bình Định", "trung", ("77",), ("quy nhon",), ()),
    _P("phuyen", "Phú Yên", "trung", ("78",), ("tuy hoa",), ()),
    _P("khanhhoa", "Khánh Hòa", "trung", ("79",), ("nha trang",), ()),
    _P("ninhthuan", "Ninh Thuận", "trung", ("85",), ("phan rang",), ()),
    _P("binhthuan", "Bình Thuận", "trung", ("86",), ("phan thiet",), ()),
    # Tây Nguyên
    _P("kontum", "Kon Tum", "taynguyen", ("82",), ("kontum",), ()),
    _P("gialai", "Gia Lai", "taynguyen", ("81",), ("pleiku",), ("gl",)),
    _P("daklak", "Đắk Lắk", "taynguyen", ("47",), ("daklak", "dac lac", "buon ma thuot"), ()),
    _P("daknong", "Đắk Nông", "taynguyen", ("48",), ("daknong", "dac nong"), ()),
    _P("lamdong", "Lâm Đồng", "taynguyen", ("49",), ("da lat", "dalat"), ()),
    # Nam Bộ
    _P("hcm", "TP.HCM", "nam", ("41", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59"),
       ("ho chi minh", "tp ho chi minh", "sai gon", "saigon", "thanh pho ho chi minh"), ("hcm", "tphcm", "sg")),
    _P("dongnai", "Đồng Nai", "nam", ("60",), ("bien hoa",), ("dnai",)),
    _P("binhduong", "Bình Dương", "nam", ("61",), (), ("bd",)),
    _P("binhphuoc", "Bình Phước", "nam", ("93",), (), ("bp",)),
    _P("tayninh", "Tây Ninh", "nam", ("70",), (), ()),
    _P("bariavungtau", "Bà Rịa – Vũng Tàu", "nam", ("72",), ("vung tau", "ba ria", "ba ria vung tau"), ("brvt",)),
    _P("longan", "Long An", "nam", ("62",), (), ()),
    _P("tiengiang", "Tiền Giang", "nam", ("63",), ("my tho",), ()),
    _P("bentre", "Bến Tre", "nam", ("71",), (), ()),
    _P("vinhlong", "Vĩnh Long", "nam", ("64",), (), ()),
    _P("travinh", "Trà Vinh", "nam", ("84",), (), ()),
    _P("dongthap", "Đồng Tháp", "nam", ("66",), ("cao lanh", "sa dec"), ()),
    _P("angiang", "An Giang", "nam", ("67",), ("long xuyen", "chau doc"), ("ag",)),
    _P("kiengiang", "Kiên Giang", "nam", ("68",), ("rach gia", "phu quoc"), ("kg",)),
    _P("cantho", "Cần Thơ", "nam", ("65",), (), ("ct",)),
    _P("haugiang", "Hậu Giang", "nam", ("95",), (), ()),
    _P("soctrang", "Sóc Trăng", "nam", ("83",), (), ()),
    _P("baclieu", "Bạc Liêu", "nam", ("94",), (), ()),
    _P("camau", "Cà Mau", "nam", ("69",), (), ()),
)

BY_KEY: dict[str, Province] = {p.key: p for p in PROVINCES}

REGION_NAMES = {"bac": "miền Bắc", "trung": "miền Trung", "taynguyen": "Tây Nguyên", "nam": "miền Nam"}

# Đặc sản bán ở trạm dừng chân theo vùng của chặng.
SPECIALTIES = {  # dự phòng theo vùng khi tỉnh chưa có trong PROVINCE_SPECIALTIES
    "bac": "bánh cuốn · chè lam",
    "trung": "bánh lọc · mè xửng",
    "taynguyen": "cà phê · bơ sáp",
    "nam": "bánh pía · bánh tét",
}

# Đặc sản nổi tiếng nhất của từng tỉnh — trạm dừng chân bán đúng đặc sản nơi xe đang nghỉ (Phú Yên không bán mè xửng Huế).
# Chỉ ghi món ai cũng biết gắn với tỉnh đó; thêm / sửa thì sửa bảng này.

# Tên thành phố tỉnh lỵ / nơi quen gọi (đã bỏ dấu) — người xem hay gõ tên thành phố thay tên tỉnh («Vinh», «Đồng Hới»,
# «BMT»); anh dặn 02/11 nhận đủ 63 tỉnh. Cụm nhiều chữ khớp trong câu; cụm một chữ ngắn dễ trùng tên người («Vinh») vẫn
# chỉ thành đặt vé khi phần còn lại của comment là chữ đệm («về Vinh», «Vinh nè»).
CITY_ALIASES: dict[str, tuple[str, ...]] = {
    "hanam": ("phu ly",), "namdinh": ("tp nam dinh",), "thaibinh": ("tp thai binh",), "haiduong": ("tp hai duong",),
    "bacninh": ("tu son",), "bacgiang": ("tp bac giang",), "phutho": ("viet tri",), "vinhphuc": ("vinh yen",),
    "hoabinh": ("tp hoa binh",), "sonla": ("tp son la", "moc chau"), "dienbien": ("dien bien phu",), "laichau": ("tp lai chau",),
    "laocai": ("sa pa",), "yenbai": ("tp yen bai",), "hagiang": ("tp ha giang",), "tuyenquang": ("tp tuyen quang",),
    "hungyen": ("pho hien",), "caobang": ("tp cao bang",), "backan": ("tp bac kan",), "thainguyen": ("tp thai nguyen",), "langson": ("tp lang son",),
    "quangninh": ("cam pha", "mong cai", "uong bi"), "ninhbinh": ("tam diep", "trang an"), "thanhhoa": ("sam son",),
    "nghean": ("vinh", "cua lo"), "hatinh": ("tp ha tinh",), "quangbinh": ("dong hoi",), "quangtri": ("dong ha",),
    "hue": ("tt hue", "thua thien"), "quangnam": ("tam ky", "hoi an"), "quangngai": ("tp quang ngai",),
    "binhdinh": ("quy nhon",), "phuyen": ("tuy hoa",), "khanhhoa": ("nha trang", "cam ranh"), "ninhthuan": ("phan rang",),
    "binhthuan": ("phan thiet", "mui ne"), "kontum": ("tp kon tum",), "gialai": ("pleiku", "play cu"),
    "daklak": ("buon ma thuot", "buon me thuot", "bmt"), "daknong": ("gia nghia",), "lamdong": ("da lat", "bao loc"),
    "binhphuoc": ("dong xoai",), "tayninh": ("tp tay ninh",), "binhduong": ("thu dau mot", "di an", "thuan an"),
    "dongnai": ("bien hoa", "long khanh"), "bariavungtau": ("vung tau", "ba ria"), "longan": ("tan an",),
    "tiengiang": ("my tho",), "bentre": ("tp ben tre",), "travinh": ("tp tra vinh",), "vinhlong": ("tp vinh long",),
    "dongthap": ("cao lanh", "sa dec"), "angiang": ("long xuyen", "chau doc"), "kiengiang": ("rach gia", "phu quoc", "ha tien"),
    "cantho": ("ninh kieu",), "haugiang": ("vi thanh",), "soctrang": ("tp soc trang",), "baclieu": ("tp bac lieu",),
    "camau": ("tp ca mau",),
}

PROVINCE_SPECIALTIES = {
    "hanoi": "bánh cốm · ô mai", "haiphong": "bánh đa cua · nem cua bể", "quangninh": "chả mực Hạ Long",
    "haiduong": "bánh đậu xanh · bánh gai", "hungyen": "nhãn lồng", "thaibinh": "bánh cáy",
    "namdinh": "phở bò · kẹo Sìu Châu", "hanam": "chuối ngự Đại Hoàng", "ninhbinh": "thịt dê · cơm cháy",
    "bacninh": "bánh phu thê Đình Bảng", "bacgiang": "vải thiều Lục Ngạn", "vinhphuc": "su su Tam Đảo",
    "phutho": "bánh tai · thịt chua Thanh Sơn", "thainguyen": "chè Tân Cương", "hoabinh": "cơm lam · rượu cần",
    "sonla": "mận hậu · thịt trâu gác bếp", "dienbien": "gạo tám Điện Biên", "laichau": "chè Tam Đường",
    "laocai": "thắng cố · táo mèo", "yenbai": "cốm Tú Lệ", "tuyenquang": "cam sành Hàm Yên",
    "hagiang": "mật ong bạc hà", "caobang": "hạt dẻ Trùng Khánh", "backan": "miến dong",
    "langson": "vịt quay · khâu nhục", "thanhhoa": "nem chua", "nghean": "nhút Thanh Chương · cháo lươn",
    "hatinh": "kẹo cu đơ", "quangbinh": "khoai deo · cháo canh", "quangtri": "tiêu Vĩnh Linh",
    "hue": "mè xửng · bánh lọc", "danang": "chả bò · bánh tráng cuốn thịt heo", "quangnam": "mì Quảng · cao lầu",
    "quangngai": "mạch nha · kẹo gương", "binhdinh": "bánh ít lá gai · nem chợ Huyện", "phuyen": "cá ngừ · bánh hỏi",
    "khanhhoa": "nem Ninh Hòa · yến sào", "ninhthuan": "nho · táo Ninh Thuận",
    "binhthuan": "nước mắm Phan Thiết · thanh long", "kontum": "gỏi lá Kon Tum", "gialai": "phở khô Gia Lai",
    "daklak": "cà phê Buôn Ma Thuột", "daknong": "mắc ca · cà phê", "lamdong": "dâu tây · mứt Đà Lạt",
    "hcm": "bánh mì · cơm tấm", "dongnai": "bưởi Tân Triều", "binhduong": "măng cụt Lái Thiêu",
    "binhphuoc": "hạt điều", "tayninh": "bánh tráng phơi sương · muối tôm", "bariavungtau": "bánh khọt Vũng Tàu",
    "longan": "lạp xưởng · rượu Gò Đen", "tiengiang": "hủ tiếu Mỹ Tho", "bentre": "kẹo dừa",
    "vinhlong": "bưởi Năm Roi", "travinh": "bánh tét Trà Cuôn", "dongthap": "nem Lai Vung",
    "angiang": "mắm Châu Đốc", "kiengiang": "nước mắm Phú Quốc", "cantho": "bánh tét lá cẩm",
    "haugiang": "khóm Cầu Đúc", "soctrang": "bánh pía", "baclieu": "muối hột · bánh tằm",
    "camau": "ba khía · mắm tôm chà",
}


def specialty_of(province: str) -> str:
    return PROVINCE_SPECIALTIES.get(province) or SPECIALTIES[BY_KEY[province].region]
