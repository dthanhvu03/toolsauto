"""
Cấu hình chung cho toàn bộ test.

Test KHÔNG được ghi vào ``logs/app.log`` thật: ngày 2026-09-11 lần log tìm lỗi quét TikTok
của Owner thì gặp toàn dòng ``@a: ERROR: boom`` do bộ test sinh ra — tiếng ồn giả trộn vào
log production, đến lúc cần lần lỗi thật thì lạc. ``setup_shared_logger`` đọc ``LOG_DIR``
từ môi trường, nên đặt nó TRƯỚC khi bất kỳ module ``app.*`` nào được import.
"""
import os
import tempfile

os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="toolsauto-test-logs-"))
