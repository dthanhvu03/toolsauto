"""
Sao chép ngoại vi sang thư mục đồng bộ đám mây (Google Drive for Desktop) — ADR-012.

Backup nằm cùng ổ đĩa với dữ liệu thì hỏng ổ là mất cả hai. Module này chép thêm
một bản sang thư mục Drive đã gắn.

Ba nguyên tắc, đừng phá khi sửa về sau:

1. **Sao chép, không di chuyển.** Bản chính luôn ở máy; Drive là bản thứ hai.
2. **Lỗi ở đây không được làm hỏng việc chính.** Chưa gắn ổ, mất mạng, hết dung
   lượng — chỉ ghi log cảnh báo rồi trả None. Backup vẫn tính là thành công vì bản
   local đã có; job đăng bài vẫn chạy tiếp.
3. **KHÔNG BAO GIỜ** chép database đang chạy hay profile trình duyệt lên đây. Drive
   đồng bộ liên tục còn hai thứ đó ghi liên tục — xung đột đồng bộ làm hỏng dữ liệu
   một cách âm thầm, và profile hỏng nghĩa là mất phiên đăng nhập.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from app.utils.logger import setup_shared_logger

logger = setup_shared_logger(__name__)

# Thư mục con trong Drive theo loại nội dung. Khoá phải khớp tham số `kind`.
SUBDIRS: dict[str, str] = {
    "backup": "backups",
    "video": "videos",
}


def _settings():
    """Đọc cấu hình runtime (DB ghi đè env). Import trong hàm để tránh vòng import."""
    from app.core import settings as runtime_settings

    return runtime_settings


def get_root() -> Optional[Path]:
    """Thư mục gốc trên Drive, hoặc None khi tắt / chưa cấu hình."""
    rs = _settings()
    try:
        if not rs.get_bool("DRIVE_COPY_ENABLED"):
            return None
        raw = (rs.get_str("DRIVE_ROOT_DIR") or "").strip()
    except Exception as exc:  # pragma: no cover - phụ thuộc trạng thái DB
        logger.debug("[offsite] khong doc duoc cau hinh: %s", exc)
        return None
    return Path(raw) if raw else None


def check_root(root: Optional[Path] = None) -> tuple[bool, str]:
    """
    Kiểm tra thư mục Drive dùng được không. Trả (ok, thông điệp tiếng Việt).

    Tách riêng khỏi `copy_out` để trang settings và lệnh CLI kiểm tra được **trước**
    khi bật, thay vì để Owner phát hiện sai đường dẫn lúc cần khôi phục.
    """
    if root is None:
        root = get_root()
    if root is None:
        return False, "Sao lưu ngoại vi đang tắt hoặc chưa nhập đường dẫn."
    if not root.exists():
        return False, f"Không thấy thư mục: {root}. Google Drive đã đăng nhập và gắn ổ chưa?"
    if not root.is_dir():
        return False, f"Đường dẫn không phải thư mục: {root}"
    probe = root / ".toolsauto_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, f"Không ghi được vào {root}: {exc}"
    return True, f"Thư mục dùng được: {root}"


def copy_out(src: str | os.PathLike[str], kind: str) -> Optional[Path]:
    """
    Chép một file sang Drive. Trả đường dẫn đích, hoặc None khi bỏ qua/thất bại.

    KHÔNG BAO GIỜ ném lỗi ra ngoài: người gọi là lệnh backup và luồng đăng bài, hai
    chỗ đó không được chết chỉ vì Drive chưa gắn ổ.
    """
    root = get_root()
    if root is None:
        return None

    src_path = Path(src)
    if not src_path.is_file():
        logger.warning("[offsite] bo qua, khong thay file nguon: %s", src_path)
        return None

    ok, message = check_root(root)
    if not ok:
        logger.warning("[offsite] bo qua: %s", message)
        return None

    dest_dir = root / SUBDIRS.get(kind, kind)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src_path.name
        # copy2 giữ mtime — cần cho việc dọn bản cũ theo thời gian về sau.
        shutil.copy2(src_path, dest)
    except OSError as exc:
        # Hết dung lượng, mất mạng giữa chừng, Drive khoá file — đều rơi vào đây.
        logger.warning("[offsite] chep %s sang %s that bai: %s", src_path.name, dest_dir, exc)
        return None

    logger.info("[offsite] da chep %s -> %s", src_path.name, dest)
    return dest
