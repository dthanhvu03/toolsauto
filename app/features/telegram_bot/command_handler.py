import logging
import concurrent.futures
import threading
from app.constants import JobStatus

logger = logging.getLogger(__name__)

class TelegramCommandHandler:
    def __init__(self, client):
        self.client = client

    def handle_command(self, cmd: str, args: list = None):
        handler_map = {
            "status": self._cmd_status,
            "pause": self._cmd_pause,
            "resume": self._cmd_resume,
            "health": self._cmd_health,
            "jobs": self._cmd_jobs,
            "drafts": self._cmd_drafts,
            "retry": self._cmd_retry,
            "viral": self._cmd_viral,
            "discovery": self._cmd_discovery,
            "help": self._cmd_help,
            "start": self._cmd_help,
        }
        handler = handler_map.get(cmd.lower())
        if handler:
            try:
                handler(args)
            except Exception as e:
                logger.exception(f"[Telegram] Command /{cmd} failed")
                self.client.send_message(f"❌ Lỗi: {str(e)[:100]}")
        else:
            self.client.send_message(f"❓ Lệnh /{cmd} không hỗ trợ.")

    def _cmd_help(self, args=None):
        """ADR-033 — không có lệnh này thì phải mở code mới biết bot làm được gì."""
        self.client.send_message(
            "🤖 <b>Lệnh dùng được</b>\n━━━━━━━━━━━━━━━━━━\n"
            "/status — worker đang chạy hay tạm dừng\n"
            "/pause · /resume — tạm dừng / chạy tiếp worker\n"
            "/health — sức khoẻ hệ thống\n"
            "/jobs — đếm job đang chạy / chờ / nháp\n"
            "/drafts — liệt kê bản nháp, kèm nút Duyệt / Huỷ\n"
            "/retry &lt;id&gt; — cho một job chạy lại\n"
            "/discovery — quét tìm kênh mới (chạy nền, hơi lâu)\n"
            "/viral &lt;min_views&gt; &lt;max_videos&gt; — đổi ngưỡng quét"
        )

    def _cmd_status(self, args=None):
        # ADR-033: trạng thái WORKER nằm ở `SystemState.worker_status` ("RUNNING"/"PAUSED"),
        # không phải `JobStatus`. Mượn lẫn nhau chính là gốc của lỗi cũ: `JobStatus.PAUSED`
        # không tồn tại và `WorkerService.get_status` cũng không.
        from app.core.database.core import SessionLocal
        from app.core.queue.worker import WorkerService
        with SessionLocal() as db:
            status = str(WorkerService.get_or_create_state(db).worker_status or "UNKNOWN")
        status_icon = "🟢" if status.upper() == "RUNNING" else "🟠"
        self.client.send_message(f"{status_icon} Worker status: <b>{status}</b>")

    def _cmd_pause(self, args=None):
        from app.core.database.core import SessionLocal
        from app.core.queue.worker import WorkerService
        with SessionLocal() as db:
            WorkerService.set_status(db, "PAUSED")  # giống worker_router.py của web
        self.client.send_message("🟠 Worker đã <b>tạm dừng</b>!")

    def _cmd_resume(self, args=None):
        from app.core.database.core import SessionLocal
        from app.core.queue.worker import WorkerService
        with SessionLocal() as db:
            WorkerService.set_status(db, "RUNNING")
        self.client.send_message("🟢 Worker đã <b>tiếp tục chạy</b>!")

    def _cmd_health(self, args=None):
        from app.core.database.core import SessionLocal
        from app.core.observability.health import HealthService
        def _fetch():
            with SessionLocal() as db:
                return HealthService.get_system_health(db)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_fetch)
                h = future.result(timeout=10)
        except Exception as e:
            self.client.send_message(f"❌ Health check lỗi: {e}")
            return
        status = h.get("status", "unknown")
        status_icon = "🟢" if status == "ok" else "🟡" if status == "degraded" else "🔴"
        msg = f"{status_icon} <b>Health: {status.upper()}</b>\n━━━━━━━━━━━━━━━━━━\n"
        msg += f"👷 Worker: {h.get('worker', {}).get('status', '?')}\n"
        msg += f"🔄 Running: {h.get('jobs', {}).get('running', 0)}\n"
        self.client.send_message(msg)

    def _cmd_jobs(self, args=None):
        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        with SessionLocal() as db:
            pending = db.query(Job).filter(Job.status == JobStatus.PENDING).count()
            draft = db.query(Job).filter(Job.status == JobStatus.DRAFT).count()
            running = db.query(Job).filter(Job.status == JobStatus.RUNNING).first()
            msg = "📋 <b>Danh sách Jobs</b>\n━━━━━━━━━━━━━━━━━━\n"
            if running: msg += f"🔄 Đang chạy: Job #{running.id}\n"
            msg += f"⏳ Pending: {pending} | 📝 Draft: {draft}"
        self.client.send_message(msg)

    def _cmd_drafts(self, args=None):
        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        with SessionLocal() as db:
            drafts = db.query(Job).filter(Job.status == JobStatus.DRAFT).all()
            if not drafts:
                self.client.send_message("📝 Không có bản nháp nào.")
                return
            for job in drafts:
                msg = f"📋 <b>Job #{job.id}</b>\n✍️ {job.caption[:150]}..."
                buttons = [[
                    {"text": "✅ Approve", "callback_data": f"approve:{job.id}"},
                    {"text": "❌ Cancel", "callback_data": f"cancel:{job.id}"},
                ]]
                self.client.send_message(msg, reply_markup={"inline_keyboard": buttons})

    def _cmd_retry(self, args=None):
        """ADR-033 — trước đây chỉ in "Đang thử lại…" rồi kết thúc, không thử lại gì."""
        if not args:
            self.client.send_message("⚠️ Thiếu ID. VD: /retry 123")
            return
        try:
            job_id = int(str(args[0]).strip())
        except (TypeError, ValueError):
            self.client.send_message(f"⚠️ ID phải là số. VD: /retry 123 (nhận: {args[0]})")
            return

        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        from app.core.queue.job import JobService
        with SessionLocal() as db:
            if not db.query(Job).filter(Job.id == job_id).first():
                self.client.send_message(f"❓ Không tìm thấy Job #{job_id}.")
                return
            JobService.retry_job(db, job_id)
        self.client.send_message(f"🔄 Đã cho Job #{job_id} chạy lại.")

    def _cmd_viral(self, args=None):
        if not args or len(args) < 2:
            self.client.send_message("⚠️ Cú pháp: /viral <min_views> <max_videos>")
            return
        try:
            min_views, max_videos = int(args[0]), int(args[1])
        except (TypeError, ValueError):
            self.client.send_message("⚠️ Cả hai phải là số. VD: /viral 5000 30")
            return

        from app.core import settings as runtime_settings
        from app.core.database.core import SessionLocal
        from app.core.queue.worker import WorkerService
        with SessionLocal() as db:
            # ADR-033: nguồn kiểu mới (ADR-019) đọc RuntimeSetting, KHÔNG đọc WorkerState —
            # nên bản cũ chỉ ghi WorkerState là báo "đã cập nhật" cho một việc không tác dụng
            # với nguồn Owner đang dùng. Ghi cả hai: RuntimeSetting cho nguồn mới, WorkerState
            # để đường quét cũ theo account không đổi hành vi.
            runtime_settings.upsert_setting(db, "viral.min_views", str(min_views), "telegram")
            runtime_settings.upsert_setting(db, "viral.max_videos_per_channel", str(max_videos), "telegram")
            state = WorkerService.get_or_create_state(db)
            state.viral_min_views = min_views
            state.viral_max_videos_per_channel = max_videos
            db.commit()
        self.client.send_message(
            f"✅ Đã cập nhật: tối thiểu <b>{min_views:,}</b> views, tối đa <b>{max_videos}</b> video/kênh.\n"
            "Áp cho nguồn tự quét và cả đường quét cũ theo tài khoản."
        )

    def _cmd_discovery(self, args=None):
        """
        ADR-033 — trước đây in "Đang quét…" rồi ngay "✅ hoàn tất", hai câu liền nhau, không
        quét gì. Nay gọi hook `viral.force_discovery` thật và chạy nền vì có thể lâu.
        """
        self.client.send_message("⏳ Đang quét Discovery… sẽ báo lại khi xong.")

        def _run():
            from app.core.database.core import SessionLocal
            from app.core import feature_hooks
            try:
                with SessionLocal() as db:
                    channels, keywords, found = feature_hooks.call("viral.force_discovery", db)
                self.client.send_message(
                    f"✅ Discovery xong: <b>{found}</b> kênh mới "
                    f"({len(keywords or [])} từ khoá đã quét)."
                )
            except Exception as exc:
                logger.exception("[Telegram] /discovery failed")
                self.client.send_message(f"❌ Discovery lỗi: {str(exc)[:150]}")

        threading.Thread(target=_run, name="tg-discovery", daemon=True).start()
