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
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from app.utils.logger import setup_shared_logger

logger = setup_shared_logger(__name__)

# Thư mục con trong Drive theo loại nội dung. Khoá phải khớp tham số `kind`.
SUBDIRS: dict[str, str] = {
    "backup": "backups",
    "video": "videos",
}


# Ký tự Windows từ chối trong tên file, cộng ký tự điều khiển.
_BAD_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# Cắt phần tiêu đề, KHÔNG tính số ID và đuôi file. Windows giới hạn cả đường dẫn ở 260 ký tự
# và bản chép còn nằm sâu trong thư mục Drive, nên chừa rộng tay.
_TITLE_MAX_LEN = 80


def safe_video_name(src_name: str, material_id: Optional[int], title: Optional[str]) -> str:
    """
    Tên file cho bản chép trên Drive: ``949 - Nay tui đi câu mực nha anh em.mp4`` (ADR-030).

    Giữ **ID ở đầu** chứ không chỉ mỗi tiêu đề: kênh nguồn có nhiều video **trùng tên nhau**
    (4 clip cùng tên "Muốn giàu phải ra biển") — bỏ ID là chúng ghi đè lẫn nhau; và ID khớp
    số hiển thị trên web nên đối chiếu được.

    **Giữ dấu tiếng Việt**: Windows và Drive đều chịu được UTF-8, bỏ dấu là mất đúng cái dễ
    đọc mà tên này sinh ra để có. Chỉ bỏ thứ hệ thống tệp thật sự từ chối.

    ``title`` phải **đã sạch marker** (``[AI_GENERATE]``, ``### … ###``): module này nằm ở
    ``app/core`` nên không được biết chuyện của feature — import-linter chặn cứng.
    Không còn gì sau khi làm sạch ⇒ lùi về tên gốc, không bao giờ trả chuỗi rỗng.
    """
    suffix = Path(src_name).suffix or ".mp4"
    clean = _BAD_FILENAME_CHARS.sub(" ", str(title or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = clean[:_TITLE_MAX_LEN].strip()
    # Windows từ chối tên kết thúc bằng dấu chấm hoặc khoảng trắng.
    clean = clean.rstrip(". ")
    if not clean:
        return src_name
    prefix = f"{material_id} - " if material_id else ""
    return f"{prefix}{clean}{suffix}"


def relative_to_root(dest: Optional[Path]) -> Optional[str]:
    """Đường dẫn tương đối trong Drive (``videos/2026-09/…mp4``) để hiện cho người dùng.

    KHÔNG phải link bấm được: Drive for Desktop chỉ gắn ổ đĩa, tool không biết link
    ``drive.google.com`` của file. Muốn link thật phải gọi Drive API — ngoài phạm vi ADR-030.
    """
    if dest is None:
        return None
    # Bọc TOÀN BỘ: hàm này hay được gọi ngay trong danh sách tham số của `notify_*`, tức chạy
    # TRƯỚC khi vào hàm đó — mọi try/except bên trong notifier không đỡ được. Một dòng chỉ để
    # hiển thị thì không có quyền làm hỏng lượt xử lý đã commit xong.
    try:
        root = get_root()
        if root is None:
            return None
        return dest.relative_to(root).as_posix()
    except Exception as exc:
        logger.debug("[offsite] khong dung duoc duong dan tuong doi: %s", exc)
        return getattr(dest, "name", None)


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


def copy_video_if_enabled(
    src: str | os.PathLike[str],
    *,
    material_id: Optional[int] = None,
    title: Optional[str] = None,
) -> Optional[Path]:
    """
    Chép video ``_reup`` sang Drive khi Owner bật "Chép video đã xử lý" (ADR-023).

    Tách riêng khỏi ``copy_out`` để cờ ``DRIVE_COPY_VIDEOS`` nằm cạnh logic Drive khác,
    người gọi trong luồng reup chỉ còn một dòng. Cùng cam kết: KHÔNG BAO GIỜ ném lỗi —
    Drive chưa gắn ổ hay hết dung lượng không được làm hỏng việc xử lý video.
    """
    # `try` phải bọc CẢ việc dựng tên file, không riêng lượt đọc cài đặt: hàm này chạy SAU
    # khi video đã xử lý xong, để một ngoại lệ thoát ra là hỏng cả lượt xử lý chỉ vì bản chép
    # phụ. Đúng bẫy ADR-027 đã dính — bọc phần đắt tiền mà bỏ sót phần rẻ ngay cạnh.
    try:
        if not _settings().get_bool("DRIVE_COPY_VIDEOS"):
            return None
        # ADR-030: tên theo tiêu đề + thư mục theo tháng. `title` phải đã sạch marker.
        dest_name = safe_video_name(Path(src).name, material_id, title)
    except Exception as exc:
        logger.debug("[offsite] bo qua chep video: %s", exc)
        return None
    return copy_out(src, "video", dest_name=dest_name, month_folder=True)


def copy_out(
    src: str | os.PathLike[str],
    kind: str,
    *,
    dest_name: Optional[str] = None,
    month_folder: bool = False,
) -> Optional[Path]:
    """
    Chép một file sang Drive. Trả đường dẫn đích, hoặc None khi bỏ qua/thất bại.

    ``dest_name`` đổi tên bản chép (bản gốc trên máy giữ nguyên); ``month_folder`` xếp thêm
    một cấp ``YYYY-MM``. Cả hai mặc định tắt để ``kind="backup"`` giữ nguyên chỗ cũ — lệnh
    khôi phục đang trông vào thư mục phẳng đó (ADR-030).

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
    if month_folder:
        dest_dir = dest_dir / time.strftime("%Y-%m")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (dest_name or src_path.name)
        # ADR-024: ban dich da y het thi bo qua — moi lan "Reup lai" khong phai tai len
        # lai ca video 30 MB. Ten file da gan material_id nen cung ten + cung co la cung ban.
        if dest.is_file() and dest.stat().st_size == src_path.stat().st_size:
            logger.debug("[offsite] bo qua, ban dich da y het: %s", dest)
            return dest
        # copy2 giữ mtime — cần cho việc dọn bản cũ theo thời gian về sau.
        shutil.copy2(src_path, dest)
    except OSError as exc:
        # Hết dung lượng, mất mạng giữa chừng, Drive khoá file — đều rơi vào đây.
        logger.warning("[offsite] chep %s sang %s that bai: %s", src_path.name, dest_dir, exc)
        return None

    logger.info("[offsite] da chep %s -> %s", src_path.name, dest)
    return dest
