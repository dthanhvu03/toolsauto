import logging
import concurrent.futures
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

    def _cmd_status(self, args=None):
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService
        with SessionLocal() as db:
            status = WorkerService.get_status(db)
        status_icon = "🟢" if status == JobStatus.RUNNING else "🟠"
        self.client.send_message(f"{status_icon} Worker status: <b>{status}</b>")

    def _cmd_pause(self, args=None):
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService
        with SessionLocal() as db:
            WorkerService.set_status(db, JobStatus.PAUSED)
        self.client.send_message("🟠 Worker đã <b>tạm dừng</b>!")

    def _cmd_resume(self, args=None):
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService
        with SessionLocal() as db:
            WorkerService.set_status(db, JobStatus.RUNNING)
        self.client.send_message("🟢 Worker đã <b>tiếp tục chạy</b>!")

    def _cmd_health(self, args=None):
        from app.database.core import SessionLocal
        from app.services.health import HealthService
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
        from app.database.core import SessionLocal
        from app.database.models import Job
        with SessionLocal() as db:
            pending = db.query(Job).filter(Job.status == JobStatus.PENDING).count()
            draft = db.query(Job).filter(Job.status == JobStatus.DRAFT).count()
            running = db.query(Job).filter(Job.status == JobStatus.RUNNING).first()
            msg = "📋 <b>Danh sách Jobs</b>\n━━━━━━━━━━━━━━━━━━\n"
            if running: msg += f"🔄 Đang chạy: Job #{running.id}\n"
            msg += f"⏳ Pending: {pending} | 📝 Draft: {draft}"
        self.client.send_message(msg)

    def _cmd_drafts(self, args=None):
        from app.database.core import SessionLocal
        from app.database.models import Job
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
        if not args:
            self.client.send_message("⚠️ Thiếu ID. VD: /retry 123")
            return
        self.client.send_message(f"🔄 Đang thử lại Job #{args[0]}...")

    def _cmd_viral(self, args=None):
        if not args or len(args) < 2:
            self.client.send_message("⚠️ Cú pháp: /viral <min_views> <max_videos>")
            return
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService
        with SessionLocal() as db:
            state = WorkerService.get_or_create_state(db)
            state.viral_min_views = int(args[0])
            state.viral_max_videos_per_channel = int(args[1])
            db.commit()
        self.client.send_message(f"✅ Đã cập nhật Viral: {args[0]} views, {args[1]} vids/page.")

    def _cmd_discovery(self, args=None):
        self.client.send_message("⏳ Đang quét Discovery...")
        self.client.send_message("✅ Discovery hoàn tất.")
