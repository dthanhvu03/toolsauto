"""
Ngưỡng recovery phải lớn hơn deadline của một job (AUDIT-001 P0-1C, ADR-011).

Đây là bất biến giữa hai hằng số ở hai chỗ khác nhau trong config, nên rất dễ bị
phá lúc ai đó chỉnh một bên. Test này là cái chốt: hạ ngưỡng xuống dưới deadline là
đỏ ngay, kèm lý do.
"""
from __future__ import annotations

import app.config as config


def test_recovery_threshold_must_exceed_publish_deadline():
    threshold = config.WORKER_CRASH_THRESHOLD_SECONDS
    deadline = config.PUBLISHER_PUBLISH_DEADLINE_SEC

    assert threshold > deadline, (
        f"WORKER_CRASH_THRESHOLD_SECONDS={threshold} không được nhỏ hơn hoặc bằng "
        f"PUBLISHER_PUBLISH_DEADLINE_SEC={deadline}. Ngưỡng nhỏ hơn nghĩa là một job "
        "vẫn đang chạy trong hạn cho phép đã bị coi là crash, bị đặt về PENDING và bị "
        "worker khác claim — bài sẽ được đăng hai lần."
    )


def test_recovery_threshold_covers_long_video_upload_ceiling():
    """
    PLAN-056 cho phép chờ upload một video dài tới 420s. Ngưỡng recovery phải phủ
    được cả khoảng đó, nếu không job video dài luôn là ứng viên bị recovery oan.
    """
    assert config.WORKER_CRASH_THRESHOLD_SECONDS > 420
