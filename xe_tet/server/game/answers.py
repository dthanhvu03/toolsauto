"""Lơ xe trả lời câu hỏi trong comment (PLAN-135): nhận ra câu hỏi + câu trả lời sẵn cho câu hay gặp (không tốn tiền, luôn
đúng). Câu khác (khi admin bật AI) đi tiếp sang `server/ai_reply.py`.

Người xem hỏi «có ghé dọc đường hông bác tài» (live 02/11) mà game coi là tán gẫu, bỏ qua — câu trả lời lại có sẵn.
"""

from .parser import normalize

# gọi lơ xe / tài xế → coi là đang hỏi chuyện
_CALLS = ("bac tai", "anh tu", "lo xe", "tai xe", "phu xe", "chu tai", "anh tai")
# từ hỏi đứng bất kỳ đâu
_ASK = ("sao", "bao gio", "bao lau", "the nao", "o dau", "lam sao", "may gio", "bao nhieu", "duoc khong", "duoc ko",
        "phai khong", "co phai", "la gi", "lam gi", "duoc gi", "gi vay")
# đuôi câu hỏi (chỉ tính ở cuối câu: «không về» ở đầu câu là lệnh ở lại, đã xử lý trước)
_TAIL = ("khong", "hong", "ko", "k", "chua", "ha", "hok", "hem", "vay", "ta")

FAQ: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("via", ("ghe doc duong", "doc duong", "co ghe", "ghe khong", "ghe hong", "ghe ko", "dung doc duong", "ghe ngang")),
    ("how", ("lam sao len xe", "len xe sao", "len xe the nao", "cach choi", "choi sao", "choi the nao", "lam sao choi",
             "len xe kieu gi", "choi kieu gi")),
    ("depart", ("khi nao chay", "bao gio chay", "may gio chay", "khi nao xe chay", "bao gio xe chay", "may gio xe chay",
                "sao chua chay", "bao gio xuat ben", "khi nao xuat ben", "chay chua", "chua chay", "sao xe dung",
                "xe dung lam gi")),
    ("gift", ("tang qua", "qua de lam gi", "qua duoc gi")),
    ("newname", ("tinh moi", "ten moi", "sap nhap", "tinh cu")),
)


def _has(norm: str, phrase: str) -> bool:
    return f" {phrase} " in f" {norm} "


def is_question(text: str) -> bool:
    """Câu hỏi hoặc gọi lơ xe — chỉ xét comment không phải lệnh game (tỉnh, xe nào, phở / WC, không về)."""
    if "?" in text:
        return True
    norm = normalize(text)
    if not norm:
        return False
    return (any(_has(norm, w) for w in _CALLS + _ASK)
            or norm.split()[-1] in _TAIL and len(norm.split()) >= 2)


def faq(text: str) -> str | None:
    """Khoá câu trả lời sẵn («via», «how», «depart», «gift», «newname») hoặc None."""
    norm = normalize(text)
    return next((key for key, phrases in FAQ if any(_has(norm, p) for p in phrases)), None)
