"""Tự tạo mã VietQR chuyển khoản (chuẩn EMVCo/NAPAS), không gọi dịch vụ ngoài (PLAN-066).

Chuỗi QR gồm các trường TLV: tag (2 số) + độ dài (2 số) + giá trị, cuối là CRC16-CCITT.
Số tài khoản, tên, số tiền của khách không rời máy chủ bot.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata

try:
    import qrcode
except ImportError:  # Chưa cài thì vẫn chạy: admin xem số tài khoản dạng chữ.
    qrcode = None

logger = logging.getLogger(__name__)

NAPAS_GUID = "A000000727"
SERVICE_TO_ACCOUNT = "QRIBFTTA"
CURRENCY_VND = "704"
MAX_AMOUNT_VND = 9_999_999_999_999  # trường 54 dài tối đa 13 ký tự
MAX_NOTE = 25  # nhiều app ngân hàng cắt nội dung QR dài hơn
_BIN = re.compile(r"^\d{6}$")
_ACCOUNT = re.compile(r"^[0-9A-Za-z]{1,19}$")


class VietQRError(ValueError):
    pass


def _tlv(tag: str, value: str) -> str:
    if len(value) > 99:
        raise VietQRError(f"tag {tag} quá dài")
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), 4 ký tự hex viết hoa."""
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def clean_note(text: str) -> str:
    """Nội dung chuyển khoản: bỏ dấu, chỉ chữ số và khoảng trắng, tối đa MAX_NOTE ký tự."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    plain = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    plain = re.sub(r"[^A-Za-z0-9 ]+", " ", plain)
    return " ".join(plain.split())[:MAX_NOTE].strip()


def build_payload(bin_code: str, account_no: str, amount_vnd: int, note: str) -> str:
    if not _BIN.fullmatch(bin_code or ""):
        raise VietQRError("BIN ngân hàng phải gồm 6 chữ số")
    if not _ACCOUNT.fullmatch(account_no or ""):
        raise VietQRError("số tài khoản không hợp lệ")
    if isinstance(amount_vnd, bool) or not isinstance(amount_vnd, int) or not 0 < amount_vnd <= MAX_AMOUNT_VND:
        raise VietQRError("số tiền không hợp lệ")
    merchant = (
        _tlv("00", NAPAS_GUID)
        + _tlv("01", _tlv("00", bin_code) + _tlv("01", account_no))
        + _tlv("02", SERVICE_TO_ACCOUNT)
    )
    body = (
        _tlv("00", "01")
        + _tlv("01", "12")  # 12: mã dùng một lần, có số tiền cố định
        + _tlv("38", merchant)
        + _tlv("53", CURRENCY_VND)
        + _tlv("54", str(amount_vnd))
        + _tlv("58", "VN")
    )
    cleaned = clean_note(note)
    if cleaned:
        body += _tlv("62", _tlv("08", cleaned))
    body += "6304"
    return body + crc16_ccitt(body)


def parse_tlv(payload: str) -> dict[str, str]:
    """Tách lớp TLV ngoài cùng. Dùng để kiểm tra chuỗi tự tạo."""
    fields: dict[str, str] = {}
    pos = 0
    while pos < len(payload):
        tag, size = payload[pos : pos + 2], payload[pos + 2 : pos + 4]
        if len(tag) < 2 or not size.isdigit():
            raise VietQRError("chuỗi QR hỏng")
        length = int(size)
        fields[tag] = payload[pos + 4 : pos + 4 + length]
        if len(fields[tag]) != length:
            raise VietQRError("chuỗi QR bị cắt")
        pos += 4 + length
    return fields


def qr_png(payload: str) -> bytes | None:
    """Ảnh PNG của mã QR. None khi chưa cài `qrcode` hoặc vẽ lỗi; bot vẫn hiện số tài khoản dạng chữ."""
    if qrcode is None:
        logger.warning("[Cashback] chưa cài qrcode, không gửi ảnh QR")
        return None
    try:
        image = qrcode.make(payload, box_size=8, border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        logger.exception("[Cashback] vẽ ảnh QR lỗi")
        return None
