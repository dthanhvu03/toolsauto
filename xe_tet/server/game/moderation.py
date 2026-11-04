"""Lọc chữ hiện lên live và được đọc thành tiếng: tên TikTok, bong bóng chat, câu AI trả lời (TikTok quét cả chữ trên màn hình
lẫn giọng đọc — anh dặn 02/11: từ tục, tên đặt tầm bậy, phân biệt vùng miền).

Bốn lớp, đều trên chữ thường:
1. Từ CÓ DẤU khớp nguyên từ (bỏ dấu sẽ nhầm «đi» với «đĩ», «các» với «cặc», «lớn» với «lồn», «đeo» với «đéo»).
2. Chữ tắt / tiếng lóng KHÔNG DẤU chỉ có một nghĩa (dm, vcl, djt…), sau khi gộp chữ lặp («dmmmm») và đổi ký tự lách («l0z»).
3. Cụm từ không dấu (dit me, oc cho, bac ky…): bậy / miệt thị vùng miền, dân tộc.
4. Chữ cái đứng rời ghép lại («đ.m», «d m», «v c l»).
Tên dính từ bậy → thay CẢ tên bằng «Khách 123» (che một phần «*** Biết» thì giọng lơ xe vẫn đọc dở câu lên sóng).
"""

import re
import unicodedata
import zlib

BAD_WORDS = frozenset({
    "địt", "đụ", "lồn", "cặc", "đéo", "đĩ", "buồi", "đjt", "djt", "loz", "lìn", "cặk", "cak", "dái", "điếm", "phò",
    "chịch", "nứng", "đmm", "đcm", "đkm", "đmcs", "vãilồn", "cứt", "đít",
})
# không dấu, chỉ có một nghĩa (không đưa «lon / cac / deo / di / du / buoi / nung / chich» vào: trùng «lớn, các, đeo, đi,
# du, buổi, nung, chích»)
BAD_PLAIN = frozenset({
    "dm", "dmm", "dcm", "dkm", "dkmm", "dmcs", "dcmm", "vl", "vcl", "vkl", "vcc", "vlz", "cc", "cl", "clgt", "cmm", "clm",
    "dit", "djt", "ditme", "dme", "dmay", "lz", "loz", "lozz", "cak", "cek", "dis", "fuck", "fck", "fuk", "shit", "bitch",
    "porn", "sex", "jav", "xxx", "duma", "dume", "occho", "sucvat",
})
# cụm không dấu: tục / chửi / miệt thị vùng miền, dân tộc (khớp nguyên cụm trong câu đã bỏ dấu)
BAD_PHRASES = (
    # không đưa cụm trùng nghĩa vô hại khi bỏ dấu: «bo may» (bộ máy), «con cho» (con chó nhà mình), «do cho» (đồ cho mẹ),
    # «cai lon» (cái lon), «con cac» (còn các bạn), «moi ro» (mới rõ), «du ma» (đủ mà), «me may» (mẹ may áo)
    "dit me", "dit con me", "con me may", "oc cho", "suc vat", "thang cho", "vai lon", "vai l", "an cut",
    # vùng miền / dân tộc: TikTok khoá live vì phân biệt
    "bac ky", "bac ki", "nam ky", "nam ki", "trung ky", "trung ki", "parky", "packy", "bake", "baki", "nam kiki",
    "ba que", "3 que", "tau khua",
)
_ALLOWED_PHRASES = ("nam ky khoi nghia", "nam ki khoi nghia")  # tên đường / sự kiện lịch sử
_WORD = re.compile(r"[\wÀ-ỹđĐ]+", re.UNICODE)
_LINK = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|vn|net|me|io|xyz|shop|link)\b|t\.me/|zalo)", re.IGNORECASE)
_PHONE = re.compile(r"(?:\d[\s.\-]?){9,}")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "@": "a", "$": "s", "!": "i", "|": "l"})


def _plain(text: str, leet: bool = True) -> str:
    """Bỏ dấu, chữ thường, (đổi ký tự lách), chỉ giữ chữ + số, mỗi từ cách một khoảng."""
    text = text.lower().translate(_LEET) if leet else text.lower()
    text = unicodedata.normalize("NFD", text.replace("đ", "d"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _squash(word: str) -> str:
    return re.sub(r"(.)\1+", r"\1", word)


def is_bad(text: str) -> bool:
    """Có từ tục / chửi / miệt thị vùng miền, dân tộc."""
    if not text:
        return False
    if any(w.lower() in BAD_WORDS for w in _WORD.findall(text)):
        return True
    plain = _plain(text)
    words = plain.split()
    if any(w in BAD_PLAIN or _squash(w) in BAD_PLAIN for w in words):
        return True
    for variant in (plain, _plain(text, leet=False)):  # «3 que»: số là chữ thật, không phải ký tự lách
        padded = f" {variant} "
        for allowed in _ALLOWED_PHRASES:
            padded = padded.replace(f" {allowed} ", " ")
        if any(f" {p} " in padded for p in BAD_PHRASES):
            return True
    joined, run = [], []  # «đ.m», «d m», «v c l»: chữ cái đứng rời liền nhau ghép lại
    for w in [*words, ""]:
        if len(w) == 1:
            run.append(w)
            continue
        if len(run) >= 2:
            joined.append("".join(run))
        run = []
    return any(j in BAD_PLAIN or _squash(j) in BAD_PLAIN for j in joined)


def clean_name(name: str) -> str:
    """Tên vẫn hiện (người xem cần thấy mình); tên dính từ bậy / miệt thị → «Khách 123» (cố định theo tên gốc)."""
    if is_bad(name):
        return f"Khách {zlib.crc32(name.encode()) % 1000:03d}"
    return name


# Tên sàn / app khác + lời kéo người ra khỏi TikTok (anh 04/11 «live TikTok mà nói sàn khác thì cấm live»): không hiện, không
# đọc trên live. Blog người bán live ở VN liệt kê; TikTok ghi: kéo người mua ngoài TikTok bị giảm hiển thị, cố lách bị khoá.
OFF_PLATFORM_PLAIN = frozenset({
    "shopee", "shoppe", "sopee", "sopi", "lazada", "tiki", "sendo", "telegram", "tele", "zalo", "facebook", "fb", "messenger",
    "instagram", "insta", "youtube", "inbox", "ib", "link", "website", "qr", "bot",
})
OFF_PLATFORM_PHRASES = ("sop pi", "san cam", "so dien thoai", "chuyen khoan", "ket ban", "lien he", "trang web", "ma qr")


def off_platform(text: str) -> bool:
    """Có tên sàn / app khác, link, «inbox», «chuyển khoản»… — nói hay hiện trên live dễ bị TikTok dừng live."""
    plain = _plain(text or "", leet=False)
    padded = f" {plain} "
    return any(w in OFF_PLATFORM_PLAIN for w in plain.split()) or any(f" {p} " in padded for p in OFF_PLATFORM_PHRASES)


def allow_chat(text: str) -> bool:
    """Bong bóng chat / câu AI: có từ bậy, miệt thị, link, số điện thoại, tên sàn / app khác thì không hiện, không đọc."""
    if _LINK.search(text) or _PHONE.search(text) or off_platform(text):
        return False
    return not is_bad(text)
