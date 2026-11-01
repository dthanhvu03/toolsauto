"""Giả lập phòng đông để thử màn hình khi chưa nối TikTok."""

import random

from .game.provinces import PROVINCES

NAMES = (
    "Minh Anh", "Hoàng Tín 192", "Ngọc Thiện", "anh thơ", "Bé Nhỏ 2004", "Linh Thùy", "hoang bach",
    "Thịnh rio", "Phùng Mạnh Dũng", "Chocolate", "Sonia", "Tan Phong", "Edward Le", "Đặng Trần",
    "mèo mập", "Tuấn xe ôm", "Hà Vy", "Quang Huy 99", "Bảo Châu", "cô Ba Sài Gòn", "Út Ráng",
    "Lan Hương", "Khánh Vy", "Đức Mạnh", "Thu Trang", "Phương Nam", "Tèo Em", "Kim Ngân",
    "Trọng Nghĩa", "Mai Phương", "Sơn Tùng fan", "Vy Vy", "Hải Đăng", "Ngọc Hân", "Long Nhật",
    "Thảo My", "Gia Bảo", "Cường Đô La", "Hồng Nhung", "Anh Khoa", "bé Su", "Duy Mạnh",
)
CHATS = ("nhớ nhà quá", "năm nay về sớm", "mẹ ơi con về", "xe chạy êm ghê", "đói quá",
         "ai cùng quê không", "hihi", "tết tết tết", "bác tài chạy chậm thôi", "ngủ tí đã")
REST = ("phở", "bánh mì", "trà đá", "cà phê", "cơm", "wc", "đi vệ sinh", "mua quà")
STAY = ("không về", "ko về được", "năm nay chưa về")
GIFTS = (("Hoa hồng", 1), ("Kẹo", 1), ("Đèn lồng", 20), ("Bao lì xì", 99), ("Pháo hoa", 299),
         ("Xe Tết", 1000))


def next_event(phase: str) -> dict:
    name = random.choice(NAMES)
    roll = random.random()
    if phase == "REST" and roll < 0.35:
        return {"type": "comment", "name": name, "text": random.choice(REST)}
    if roll < 0.12:
        return {"type": "join", "name": name}
    if roll < 0.40:
        p = random.choice(PROVINCES)
        text = random.choice((p.name, p.name.lower(), p.plates[0], f"về {p.name} thôi"))
        return {"type": "comment", "name": name, "text": text}
    if roll < 0.52:
        return {"type": "comment", "name": name, "text": random.choice(CHATS)}
    if roll < 0.84:
        return {"type": "like", "name": name, "count": random.choice((5, 10, 15, 30))}
    if roll < 0.88:
        gift, diamonds = random.choices(GIFTS, weights=(40, 30, 12, 8, 4, 1))[0]
        return {"type": "gift", "name": name, "gift": gift, "diamonds": diamonds}
    if roll < 0.93:
        return {"type": "follow", "name": name}
    if roll < 0.97:
        return {"type": "share", "name": name}
    return {"type": "comment", "name": name, "text": random.choice(STAY)}
