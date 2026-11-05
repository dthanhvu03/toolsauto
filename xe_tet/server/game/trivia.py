"""Đố vui + chuyện từng tỉnh (anh 03/11: game lặp đi lặp lại chán, TikTok hạn chế live vì tưởng phát lại video quay sẵn).

- `FAMOUS`: mỗi tỉnh một điều ai cũng biết (đặc sản / thắng cảnh). Xe qua tỉnh nào lơ xe kể một câu về tỉnh đó.
- `make_quiz`: câu đố ba lựa chọn A, B, C dựng từ dữ liệu chắc chắn đúng — đặc sản của tỉnh nào, biển số của tỉnh nào, tỉnh
  thuộc miền nào. Người xem gõ A / B / C (không gõ tên tỉnh: gõ tên tỉnh là lên xe).
"""

import random

from .parser import normalize
from .provinces import BY_KEY, PROVINCES

FAMOUS: dict[str, str] = {
    "hanoi": "Hồ Gươm, Văn Miếu",
    "haiphong": "bánh đa cua",
    "quangninh": "vịnh Hạ Long",
    "haiduong": "bánh đậu xanh",
    "hungyen": "nhãn lồng",
    "thaibinh": "bánh cáy",
    "namdinh": "phở bò",
    "hanam": "chùa Tam Chúc",
    "ninhbinh": "Tràng An, cơm cháy",
    "bacninh": "dân ca quan họ",
    "bacgiang": "vải thiều Lục Ngạn",
    "vinhphuc": "Tam Đảo",
    "phutho": "Đền Hùng",
    "thainguyen": "chè Tân Cương",
    "hoabinh": "thủy điện Hòa Bình",
    "sonla": "cao nguyên Mộc Châu",
    "dienbien": "chiến thắng Điện Biên Phủ",
    "laocai": "Sa Pa, đỉnh Fansipan",
    "yenbai": "ruộng bậc thang Mù Cang Chải",
    "tuyenquang": "cây đa Tân Trào",
    "hagiang": "cột cờ Lũng Cú",
    "caobang": "thác Bản Giốc",
    "backan": "hồ Ba Bể",
    "langson": "vịt quay, động Tam Thanh",
    "thanhhoa": "nem chua",
    "nghean": "làng Sen quê Bác",
    "hatinh": "kẹo cu đơ",
    "quangbinh": "động Phong Nha",
    "quangtri": "thành cổ Quảng Trị",
    "hue": "bún bò, Đại Nội",
    "danang": "cầu Rồng, Bà Nà",
    "quangnam": "phố cổ Hội An, mì Quảng",
    "quangngai": "tỏi Lý Sơn",
    "binhdinh": "đất võ Tây Sơn",
    "phuyen": "Gành Đá Đĩa",
    "khanhhoa": "biển Nha Trang",
    "ninhthuan": "vườn nho, tháp Chàm",
    "binhthuan": "đồi cát Mũi Né, thanh long",
    "kontum": "nhà thờ gỗ",
    "gialai": "Biển Hồ Pleiku",
    "daklak": "cà phê Buôn Ma Thuột",
    "daknong": "công viên địa chất núi lửa",
    "lamdong": "Đà Lạt ngàn hoa",
    "hcm": "chợ Bến Thành",
    "dongnai": "bưởi Tân Triều",
    "binhduong": "khu du lịch Đại Nam",
    "binhphuoc": "hạt điều",
    "tayninh": "núi Bà Đen, bánh tráng phơi sương",
    "bariavungtau": "bánh khọt, biển Vũng Tàu",
    "longan": "gạo Nàng Thơm Chợ Đào",
    "tiengiang": "hủ tiếu Mỹ Tho",
    "bentre": "kẹo dừa",
    "vinhlong": "bưởi Năm Roi",
    "travinh": "ao Bà Om, chùa Khmer",
    "dongthap": "sen hồng, nem Lai Vung",
    "angiang": "rừng tràm Trà Sư, núi Sam",
    "kiengiang": "đảo Phú Quốc",
    "cantho": "chợ nổi Cái Răng",
    "haugiang": "chợ nổi Ngã Bảy",
    "soctrang": "bánh pía",
    "baclieu": "nhà công tử Bạc Liêu",
    "camau": "mũi Cà Mau",
}

REGION_NAMES = {"bac": "miền Bắc", "trung": "miền Trung", "taynguyen": "Tây Nguyên", "nam": "miền Nam"}
LETTERS = ("A", "B", "C")
_ANSWER_LEAD = {"", "cau", "dap an", "chon", "la", "toi chon", "em chon", "chon cau"}


def fact(key: str) -> str | None:
    """«Nam Định nổi tiếng với phở bò» — câu lơ xe kể khi xe qua tỉnh; None khi chưa có dữ liệu."""
    return f"{BY_KEY[key].name} nổi tiếng với {FAMOUS[key]}" if key in FAMOUS else None


def _quizzable(key: str) -> bool:
    """Đố «… là của tỉnh nào» được khi câu không lộ tên tỉnh («thành cổ Quảng Trị» thì khỏi đố)."""
    return key in FAMOUS and normalize(BY_KEY[key].name) not in normalize(FAMOUS[key])


def _others(rng: random.Random, key: str, pool: list[str]) -> list[str]:
    """Hai tỉnh khác làm đáp án nhiễu: ưu tiên cùng miền (khó hơn đoán mò), thiếu thì lấy cả nước."""
    region = BY_KEY[key].region
    near = [k for k in pool if k != key and BY_KEY[k].region == region]
    far = [k for k in pool if k != key and BY_KEY[k].region != region]
    rng.shuffle(near)
    rng.shuffle(far)
    return (near + far)[:2]


def make_quiz(rng: random.Random, prefer: str | None = None, recent: tuple[str, ...] = ()) -> dict:
    """Một câu đố {key, question, options[3], answer (0..2)}. `prefer`: tỉnh xe đang qua (đố về chính tỉnh đó); `recent`:
    tỉnh vừa đố (không đố lại liền)."""
    keys = [p.key for p in PROVINCES]
    key = prefer if prefer in BY_KEY and prefer not in recent else rng.choice([k for k in keys if k not in recent] or keys)
    p = BY_KEY[key]
    kinds = ["plate", "region"] + (["famous"] * 3 if _quizzable(key) else [])
    kind = rng.choice(kinds)
    if kind == "region":
        wrong = [r for r in REGION_NAMES if r != p.region]
        rng.shuffle(wrong)
        options = [REGION_NAMES[p.region], *(REGION_NAMES[r] for r in wrong[:2])]
        question = f"{p.name} thuộc vùng nào"
    else:
        pool = [k for k in keys if _quizzable(k)] if kind == "famous" else keys
        options = [p.name, *(BY_KEY[k].name for k in _others(rng, key, pool))]
        question = (f"{FAMOUS[key][0].upper()}{FAMOUS[key][1:]} là của tỉnh nào" if kind == "famous"
                    else f"Biển số xe {p.plates[0]} là của tỉnh nào")
    order = [0, 1, 2]
    rng.shuffle(order)
    return {"key": key, "kind": kind, "question": question, "options": [options[i] for i in order],
            "answer": order.index(0)}


def answer_of(text: str) -> int | None:
    """Comment là câu trả lời A / B / C («b», «câu C», «đáp án a», «chọn B»…) → 0..2; còn lại None."""
    norm = normalize(text)
    if not norm:
        return None
    words = norm.split()
    letter = words[-1]
    if letter not in ("a", "b", "c") or " ".join(words[:-1]) not in _ANSWER_LEAD:
        return None
    return "abc".index(letter)
