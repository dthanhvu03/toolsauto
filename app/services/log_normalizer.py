from typing import Any, Dict

from app.schemas.log import CanonicalLogEvent

class LogNormalizer:
    """
    Responsible for converting raw logs from various sources (files, databases)
    into a unified CanonicalLogEvent.
    """

    @staticmethod
    def _translate_message(msg: str) -> str:
        if not msg:
            return ""
        
        import re
        
        # 1. Aggressive cleaning using regex (User View)
        # Strip timestamps e.g., 2026-04-17 03:26:37
        msg = re.sub(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?[:\s]*', '', msg)
        # Strip [Job XXX] tags
        msg = re.sub(r'\[Job \d+\]\s*', '', msg)
        # Strip [IDLE] tags
        msg = re.sub(r'\[IDLE\]\s*', '', msg)
        # Strip technical backlog info e.g. Backlog=14 >= 10
        msg = re.sub(r'Backlog=\d+\s*>=?\s*\d+\.\s*', '', msg)
        # Strip PM2 prefixes
        msg = re.sub(r'^\[[A-Za-z0-9_-]+\]\s*', '', msg)
        # Strip absolute file paths (common in cleanup logs)
        msg = re.sub(r'/[a-zA-Z0-9._/-]+', '[file]', msg)
        # Strip technical class prefixes
        msg = re.sub(r'^FacebookAdapter:\s*', '', msg)
        msg = re.sub(r'^[a-z_]+:\s*', '', msg) # Strip any service: prefix (like fb_publisher:)
        translations = {
            # Worker Lifecycle & Polling
            "Publisher Worker started. Press Ctrl+C to stop.": "Hệ thống Publisher đã bắt đầu hoạt động.",
            "Staggering startup: sleeping for": "Đang chuẩn bị khởi động trong giây lát...",
            "Checking for crashed (stale heartbeat) jobs to recover...": "Đang quét và khôi phục các công việc bị lỗi...",
            "Entering polling loop.": "Bắt đầu quét danh sách công việc.",
            "Publisher process completed gracefully.": "Hệ thống đã tắt an toàn.",
            "Waiting for Job": "Đang chờ hoàn tất công việc",
            "before exiting...": "trước khi tắt...",
            "Claimed for account": "Đã nhận việc cho tài khoản",
            "on facebook": "trên Facebook",
            
            # Idle & Backlog
            "Skipping idle engagement.": "Đang tạm nghỉ vì còn nhiều việc tồn đọng.",
            
            # Publishing Accents & Polish
            "Bat dau dang Reel len Facebook...": "Bắt đầu đăng Reel lên Facebook...",
            "Successfully published!": "Đã đăng bài thành công!",
            "Terminal state reached. Cleaning up processed media:": "Dọn dẹp tệp tin tạm sau khi hoàn tất bài đăng.",
            "Terminal state reached. Cleaning up original media:": "Xóa tệp gốc sau khi đăng bài thành công.",
            "Nghỉ ngơi 55s để giả lập người thật trước khi chốt Job...": "Đang tạm nghỉ 55 giây để giả lập người thật...",
            
            # Core Job States (Normalized)
            "Job marked DONE": "Tác vụ hoàn tất thành công",
            "Job marked FAILED": "Tác vụ bị lỗi/từ chối",
            "Job claimed for processing": "Đã nhận tác vụ và đang chuẩn bị...",
            
            # Phase transitions
            "[Phase 1]": "[Bước 1]", "[Phase 2]": "[Bước 2]", "[Phase 3]": "[Bước 3]",
            "[Phase 4]": "[Bước 4]", "[Phase 5]": "[Bước 5]",
            
            # Auth / Login / Logout
            "Navigating to Facebook login page...": "Đang mở trang đăng nhập Facebook...",
            "Attempting login for user": "Đang tiến hành đăng nhập tài khoản",
            "Cookie login failed": "Đăng nhập bằng cookie thất bại, đang thử cách khác...",
            "Login successful": "Đăng nhập thành công.",
            "Identity check bypassed": "Đã bỏ qua bước xác minh danh tính.",
            "Account is logged out or requires verification.": "⚠️ Tài khoản đã bị đăng xuất hoặc cần xác minh lại (Checkpoint).",
            "Could not find avatar menu icon.": "Không tìm thấy menu tài khoản. Vui lòng kiểm tra trạng thái đăng nhập.",
            "Avatar menu switch failed or unnecessary.": "Chuyển tài khoản thất bại hoặc không cần thiết.",
            "Verifying active context...": "Đang xác minh trạng thái phiên đăng nhập...",
            
            # UI Actions
            "Clicking POST button": "Đang bấm nút Đăng bài...",
            "Post button clicked": "Đã bấm nút Đăng bài thành công.",
            "Waiting for post submission": "Đang đợi Facebook xác nhận tải lên...",
            "Dialog closed and disappeared naturally": "Quá trình đăng bài hoàn tất.",
            "Neutralizing overlays": "Đang xử lý các thông báo che khuất màn hình...",
            "Media attached. Waiting for preview": "Đã tải video lên, đang chờ xử lý...",
            "Caption typed into active publish surface": "Đã nhập nội dung bài viết.",
            "Caption already present in active surface": "Nội dung bài viết đã có sẵn.",
            "Saved debug screenshot of typed caption": "Đã lưu ảnh chụp nội dung đã nhập.",
            "Waiting for post submission to complete (dialog to close)...": "Đang đợi Facebook hoàn tất quá trình đăng...",
            "Detected schedule modal! Dismissing...": "Phát hiện bảng thông báo lịch đăng, đang đóng...",
            "Schedule modal dismissed": "Đã đóng bảng thông báo lịch đăng.",
            "Found Success/Dismiss button, clicking it to unblock...": "Đã tìm thấy nút xác nhận thành công.",
            
            # Verification
            "[Fast-Track] Checking for success toast link": "Đang tìm link bài viết nhanh qua thông báo...",
            "Post URL captured INSTANTLY via toast": "Đã lấy được link bài viết ngay lập tức!",
            "Post URL captured via current URL redirect": "Đã lấy được link bài viết qua chuyển hướng trang.",
            "Starting profiling scan": "Đang quét trang cá nhân để tìm link bài viết...",
            "Verification attempt": "Lần thử xác nhận link bài viết",
            "Navigating to Reels tab for fast verification": "Đang mở tab Thước phim để kiểm tra link...",
            "Post URL captured via Reels tab scan": "Đã tìm thấy link bài viết trong danh sách Thước phim.",
            "Deep-diving into latest reels": "Đang kiểm tra chi tiết các video mới nhất...",
            "Post verified": "Xác nhận bài viết thành công:",
            
            # Common errors
            "No post button found": "Không tìm thấy nút Đăng. Có thể giao diện bài viết bị lỗi.",
            "Failed to click the Post button": "Không thể bấm nút Đăng. Vui lòng kiểm tra lại.",
            "Post submission timed out": "Hệ thống phản hồi chậm khi đăng bài.",
            
            # Compliance / Audit
            "Compliance violation: caption": "Vi phạm chính sách: Nội dung (caption)",
            "Compliance violation:": "Vi phạm chính sách:",
            "Audit action: LOGIN": "Hành động hệ thống: Đăng nhập",
            "Audit action:": "Hành động hệ thống:",
        }

        # Apply translations
        for eng, vie in translations.items():
            if eng in msg:
                msg = msg.replace(eng, vie)
                
        # Final cleanup
        msg = msg.replace("step", "bước")
        msg = msg.replace("Attempt", "Lần thử")
        msg = msg.replace("[file]", "").strip()
        msg = re.sub(r'\s+', ' ', msg) # Collapse spaces
            
        return msg
            
        return msg

    @staticmethod
    def normalize_domain_row(row_dict: Dict[str, Any], category: str = "all") -> CanonicalLogEvent:
        """
        Takes a raw dictionary returned from LogQueryService and converts it.
        """
        msg = row_dict.get("message", "")
        if category == "user":
            msg = LogNormalizer._translate_message(msg)

        return CanonicalLogEvent(
            timestamp=row_dict.get("timestamp"),
            source=row_dict.get("source", "unknown"),
            source_type="domain",
            level=row_dict.get("level"),
            event_type=row_dict.get("event_type"),
            job_id=row_dict.get("job_id"),
            actor=row_dict.get("actor"),
            message=msg,
            metadata=row_dict.get("metadata")
        )
