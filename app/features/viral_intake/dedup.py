"""
ADR-024 — Phát hiện video trùng nội dung ở **tầng material** (trước khi tốn ffmpeg).

Hai tầng chống trùng đã có: URL (`viral_materials.url` UNIQUE) và job (`sha256` + unique
index của PLAN-041/ADR-020). Thiếu đúng tầng ở giữa: cùng một video xuất hiện ở hai kênh
nguồn ⇒ hai material, tải hai lần, chạy ffmpeg hai lần, chép Drive hai bản.

Module này chỉ chứa **hàm thuần** (không đọc file, không gọi ffmpeg) để test được nhanh:

- ``hamming``         — khoảng cách Hamming giữa hai chuỗi hex pHash.
- ``phash_distance``  — trung vị khoảng cách các cặp khung hình đã ghép theo thứ tự thời gian.
- ``find_duplicate``  — tra trong DB, trả ``(material_id, lý_do)``.

Vì sao cần **cả hai** kiểu băm: ``sha256`` chỉ bắt file giống hệt từng byte, mà video đăng
lại ở nền tảng khác luôn bị mã hoá lại ⇒ sha256 khác nhau. Thứ bắt được ca đó là **pHash**
(băm tri giác theo khung hình). sha256 vẫn đáng so trước vì rẻ và chắc chắn.
"""
from __future__ import annotations

import logging
import re
from statistics import median

from sqlalchemy.orm import Session

from app.constants import ViralStatus

logger = logging.getLogger(__name__)

#: Chỉ so với material đã có nội dung thật trong kho. ``NEW``/``PROCESSING``/``FAILED``
#: chưa (hoặc không) có file; ``DUPLICATE`` chính là bản bị chặn nên không dùng làm mốc.
DEDUP_STATUSES: tuple[str, ...] = (
    ViralStatus.READY,
    ViralStatus.DRAFTED,
    ViralStatus.REUP,
    # ADR-042: thu DA DANG la thu KHONG duoc lot vao lai — ly do quan trong nhat de POSTED ton tai.
    ViralStatus.POSTED,
)

#: Khoảng cách "chắc chắn không trùng" khi hai chuỗi hex không cùng độ dài (pHash 64-bit = 16 hex).
UNRELATED_DISTANCE = 999

_SECONDS_RE = re.compile(r"-?\d+(?:\.\d+)?")


def hamming(hex_a: str, hex_b: str) -> int:
    """
    Khoảng cách Hamming giữa hai chuỗi hex pHash (``imagehash.phash`` 64-bit ⇒ 16 ký tự).

    Độ dài khác nhau (hoặc không phải hex) ⇒ trả ``UNRELATED_DISTANCE``: không có cách so
    công bằng hai băm khác kích thước, và coi nhầm là "gần nhau" sẽ chặn oan video khác.
    """
    a = (hex_a or "").strip()
    b = (hex_b or "").strip()
    if not a or not b or len(a) != len(b):
        return UNRELATED_DISTANCE
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return UNRELATED_DISTANCE


def _frame_seconds(key: str) -> float:
    """``"10.00s"`` → ``10.0``. Khoá lạ ⇒ ``inf`` để dồn xuống cuối chứ không nổ."""
    match = _SECONDS_RE.search(str(key or ""))
    return float(match.group()) if match else float("inf")


def _ordered_hashes(phash_map: dict) -> list[str]:
    """
    Danh sách hex theo **thứ tự thời gian của khung hình**.

    Bắt buộc sort theo *số giây*, không sort theo chuỗi: ``"10.00s" < "2.00s"`` khi so chuỗi
    ⇒ khung cuối bị ghép với khung đầu của video kia và khoảng cách phình lên vô lý.
    """
    if not isinstance(phash_map, dict):
        return []
    items = [(k, str(v).strip()) for k, v in phash_map.items() if str(v or "").strip()]
    items.sort(key=lambda kv: _frame_seconds(kv[0]))
    return [v for _, v in items]


def phash_distance(map_a: dict, map_b: dict) -> int | None:
    """
    Trung vị khoảng cách Hamming giữa các khung hình đã ghép theo thứ tự thời gian.

    Dùng **trung vị** chứ không phải trung bình: một khung lệch hẳn (quảng cáo chèn giữa,
    frame đen) không đủ sức kéo cả video thành "không trùng".

    Thiếu dữ liệu một bên (rỗng / không có cặp nào ghép được) ⇒ ``None``.
    """
    hashes_a = _ordered_hashes(map_a)
    hashes_b = _ordered_hashes(map_b)
    if not hashes_a or not hashes_b:
        return None
    pairs = min(len(hashes_a), len(hashes_b))
    distances = [hamming(hashes_a[i], hashes_b[i]) for i in range(pairs)]
    if not distances:
        return None
    return int(median(distances))


def find_duplicate(
    db: Session,
    *,
    content_hash: str | None,
    phash_map: dict | None,
    exclude_id: int | None,
    max_distance: int,
) -> tuple[int, str] | None:
    """
    Tìm material đã có trùng nội dung với video vừa tải.

    Trả ``(material_id, lý_do_tiếng_Việt)`` hoặc ``None``. Thứ tự rẻ → đắt:
    1. ``content_hash`` giống hệt (một câu truy vấn, có index);
    2. pHash: duyệt các material cùng nhóm status có ``phash``, lấy cái **gần nhất** trong
       ngưỡng ``max_distance``.
    """
    from app.core.database.models import ViralMaterial

    base = db.query(ViralMaterial).filter(ViralMaterial.status.in_(DEDUP_STATUSES))
    if exclude_id is not None:
        base = base.filter(ViralMaterial.id != exclude_id)

    if content_hash:
        exact = (
            base.filter(ViralMaterial.content_hash == content_hash)
            .order_by(ViralMaterial.id.asc())
            .first()
        )
        if exact:
            return exact.id, f"Trùng nội dung với #{exact.id} (sha256 giống hệt)"

    if not phash_map:
        return None

    best: tuple[int, int] | None = None  # (khoảng cách, material_id)
    candidates = (
        base.filter(ViralMaterial.phash.isnot(None), ViralMaterial.phash != "")
        .order_by(ViralMaterial.id.asc())
        .all()
    )
    for other in candidates:
        distance = phash_distance(phash_map, other.phash_map)
        if distance is None or distance > max_distance:
            continue
        if best is None or distance < best[0]:
            best = (distance, other.id)
    if best is None:
        return None
    distance, material_id = best
    return material_id, f"Trùng nội dung với #{material_id} (pHash cách {distance})"
