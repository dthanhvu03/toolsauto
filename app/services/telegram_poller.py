"""
TelegramPoller — Long-polling daemon cho Telegram Bot.

Xử lý 2 loại update:
    1. callback_query — User click inline buttons (Approve/Cancel)
    2. message — User gõ bot commands (/status, /pause, /resume, /health, /jobs)

Chạy trong 1 daemon thread riêng, không cần domain public.

Dùng:
    from app.services.telegram_poller import TelegramPoller
    poller = TelegramPoller(bot_token, chat_id)
    poller.start()
    poller.stop()
"""
import threading
import logging
import time

logger = logging.getLogger(__name__)


class TelegramPoller:
    """
    Long-polling daemon thread cho Telegram Bot.
    
    Xử lý:
    - Inline button callbacks (approve/cancel jobs)
    - Bot commands (/status, /pause, /resume, /health, /jobs)
    
    Edge cases: double-click, job không tồn tại, sai trạng thái,
    network errors (backoff), unauthorized user, unknown commands.
    """

    def __init__(self, bot_token: str, chat_id: str, poll_timeout: int = 30):
        from app.services.telegram_client import TelegramClient
        self.client = TelegramClient(bot_token, chat_id)
        self.authorized_chat_id = str(chat_id)  # Chỉ cho phép chat_id đã config
        self.poll_timeout = poll_timeout
        self._offset = 0
        self._running = False
        self._thread = None

        # Button callback registry
        self._callback_handlers = {
            "approve": self._handle_approve,
            "cancel": self._handle_cancel,
        }

        # Bot command registry
        self._command_handlers = {
            "/status": self._cmd_status,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/health": self._cmd_health,
            "/jobs": self._cmd_jobs,
            "/drafts": self._cmd_drafts,
            "/help": self._cmd_help,
            # Phase 2: New commands
            "/retry": self._cmd_retry,
            "/cancel": self._cmd_cancel,
            "/failed": self._cmd_failed,
            "/done": self._cmd_done,
            "/sys": self._cmd_sys,
            "/stats": self._cmd_stats,
            "/safemode": self._cmd_safemode,
            "/restart": self._cmd_restart,
            "/spy": self._cmd_spy,
            "/reup": self._cmd_reup,
        }

    # ─── Lifecycle ────────────────────────────────

    LOCK_FILE = "/tmp/telegram_poller.lock"

    def start(self):
        """Bắt đầu polling trong daemon thread. Chỉ 1 process được chạy."""
        import fcntl
        import os
        if self._running:
            logger.warning("TelegramPoller đã đang chạy.")
            return

        # Cross-process lock: chỉ 1 worker được chạy poller
        try:
            self._lock_fd = open(self.LOCK_FILE, "w")
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
        except (IOError, OSError):
            # Lock held — check if owning PID is still alive
            try:
                with open(self.LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                # Check if that PID still exists
                os.kill(old_pid, 0)  # signal 0 = check existence only
                logger.info("TelegramPoller: another process (PID %d) already polling — skipped.", old_pid)
                return
            except (ValueError, FileNotFoundError, ProcessLookupError, PermissionError):
                # PID is dead or file empty → stale lock, force reclaim
                logger.warning("TelegramPoller: stale lock detected. Reclaiming...")
                try:
                    os.remove(self.LOCK_FILE)
                except OSError:
                    pass
                try:
                    self._lock_fd = open(self.LOCK_FILE, "w")
                    fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._lock_fd.write(str(os.getpid()))
                    self._lock_fd.flush()
                except (IOError, OSError):
                    logger.error("TelegramPoller: failed to reclaim lock even after cleanup.")
                    return

        self.client.delete_webhook()

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="TelegramPoller",
            daemon=True,
        )
        self._thread.start()
        logger.info("TelegramPoller started (daemon thread, timeout=%ds)", self.poll_timeout)

    def stop(self):
        """Dừng polling + release lock."""
        import fcntl
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        # Release lock cho process khác
        if hasattr(self, "_lock_fd") and self._lock_fd:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                self._lock_fd.close()
            except Exception:
                pass
        logger.info("TelegramPoller stopped.")

    # ─── Core Poll Loop ──────────────────────────

    def _poll_loop(self):
        """Main loop: long-poll → dispatch → repeat."""
        consecutive_errors = 0

        while self._running:
            try:
                updates = self.client.get_updates(
                    offset=self._offset,
                    timeout=self.poll_timeout,
                )

                if updates:
                    consecutive_errors = 0
                    for update in updates:
                        self._process_update(update)
                        self._offset = update["update_id"] + 1
                else:
                    consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error("Poller error (%d liên tiếp): %s", consecutive_errors, e)
                backoff = min(5 * consecutive_errors, 60)
                time.sleep(backoff)

    # ─── Update Dispatcher ───────────────────────

    def _process_update(self, update: dict):
        """Dispatch update tới callback hoặc command handler."""
        # 1. Inline button callback
        callback_query = update.get("callback_query")
        if callback_query:
            self._dispatch_callback(callback_query)
            return

        # 2. Text message (bot command)
        message = update.get("message")
        if message:
            self._dispatch_command(message)

    def _dispatch_callback(self, callback_query: dict):
        """Xử lý inline button click."""
        callback_id = callback_query.get("id", "")
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")
        user_name = callback_query.get("from", {}).get("first_name", "Unknown")

        parts = data.split(":", 1)
        if len(parts) != 2:
            self.client.answer_callback_query(callback_id, "⚠️ Dữ liệu không hợp lệ")
            return

        action, job_id_str = parts

        try:
            job_id = int(job_id_str)
        except ValueError:
            self.client.answer_callback_query(callback_id, "⚠️ Job ID không hợp lệ")
            return

        handler = self._callback_handlers.get(action)
        if handler:
            handler(callback_id=callback_id, job_id=job_id,
                    message_id=message_id, user_name=user_name)
        else:
            self.client.answer_callback_query(callback_id, f"⚠️ Action '{action}' không hỗ trợ")

    def _dispatch_command(self, message: dict):
        """Xử lý bot command text."""
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()
        user_name = message.get("from", {}).get("first_name", "User")

        # Bảo mật: chỉ xử lý từ chat_id đã config
        if chat_id != self.authorized_chat_id:
            logger.warning("Unauthorized command from chat_id=%s: %s", chat_id, text)
            return

        if not text.startswith("/"):
            return  # Bỏ qua tin nhắn thường

        # Parse: "/command@botname arg1 arg2" → cmd="/command", args=["arg1", "arg2"]
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        handler = self._command_handlers.get(cmd)
        if handler:
            logger.info("[Telegram] Command '%s' args=%s from %s", cmd, args, user_name)
            try:
                # Truyền args cho handler nếu handler chấp nhận
                import inspect
                sig = inspect.signature(handler)
                if len(sig.parameters) > 0:
                    handler(args=args)
                else:
                    handler()
            except Exception as e:
                logger.exception("[Telegram] Command '%s' error: %s", cmd, e)
                self.client.send_message(f"❌ Lỗi khi xử lý <code>{cmd}</code>: {e}")
        else:
            self.client.send_message(
                f"❓ Lệnh <code>{cmd}</code> không hỗ trợ.\n"
                f"Gõ /help để xem danh sách lệnh."
            )

    # ─── Bot Command Handlers ─────────────────────

    def _cmd_help(self):
        """Hiện danh sách lệnh."""
        msg = (
            "🤖 <b>Auto Publisher Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "\n📋 <b>Jobs:</b>\n"
            "/jobs — Danh sách jobs đang chờ\n"
            "/drafts — Xem & duyệt DRAFT jobs\n"
            "/done — 5 bài đăng gần nhất\n"
            "/failed — Jobs lỗi + nút Retry\n"
            "/retry &lt;id&gt; — Retry 1 job\n"
            "/cancel &lt;id&gt; — Hủy job + xóa file\n"
            "\n🕵️ <b>Đối thủ & Reup:</b>\n"
            "/spy &lt;acc&gt; &lt;url&gt; — Thêm link đối thủ\n"
            "/reup &lt;url&gt; — Reup video (TikTok/YT/FB)\n"
            "\n⚙️ <b>Worker:</b>\n"
            "/status — Trạng thái worker\n"
            "/pause — Tạm dừng worker\n"
            "/resume — Tiếp tục worker\n"
            "/safemode — Bật/tắt Safe Mode\n"
            "/restart — Restart worker\n"
            "\n📊 <b>Giám sát:</b>\n"
            "/health — Health score hệ thống\n"
            "/sys — CPU / RAM / Disk\n"
            "/stats — Thống kê hôm nay\n"
            "/help — Hiện menu này"
        )
        self.client.send_message(msg)

    def _cmd_status(self):
        """Gửi trạng thái worker hiện tại."""
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService

        with SessionLocal() as db:
            state = WorkerService.get_or_create_state(db)

            now = int(time.time())
            hb_age = (now - state.heartbeat_at) if state.heartbeat_at else None
            uptime = (now - state.worker_started_at) if state.worker_started_at else None

            # Status emoji
            if state.worker_status == "RUNNING":
                status_icon = "🟢"
            elif state.worker_status == "PAUSED":
                status_icon = "⏸️"
            else:
                status_icon = "🔴"

            msg = f"{status_icon} <b>Worker: {state.worker_status}</b>\n"

            if state.current_job_id:
                msg += f"📋 Đang xử lý: Job #{state.current_job_id}\n"

            if hb_age is not None:
                if hb_age < 60:
                    msg += f"💓 Heartbeat: {hb_age}s trước\n"
                else:
                    msg += f"💓 Heartbeat: {hb_age // 60}m trước ⚠️\n"

            if uptime is not None:
                hours = uptime // 3600
                mins = (uptime % 3600) // 60
                msg += f"⏱ Uptime: {hours}h {mins}m\n"

            if state.safe_mode:
                msg += "🛡 Safe Mode: BẬT\n"

        self.client.send_message(msg)

    def _cmd_pause(self):
        """Tạm dừng worker."""
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService

        with SessionLocal() as db:
            state = WorkerService.get_or_create_state(db)
            if state.worker_status == "PAUSED":
                self.client.send_message("⏸️ Worker <b>đã đang tạm dừng</b> rồi.")
                return
            WorkerService.set_status(db, "PAUSED")
        self.client.send_message("⏸️ Worker đã <b>tạm dừng</b>!\nGõ /resume để tiếp tục.")

    def _cmd_resume(self):
        """Tiếp tục worker."""
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService

        with SessionLocal() as db:
            state = WorkerService.get_or_create_state(db)
            if state.worker_status == "RUNNING":
                self.client.send_message("🟢 Worker <b>đang chạy</b> rồi!")
                return
            WorkerService.set_status(db, "RUNNING")
        self.client.send_message("🟢 Worker đã <b>tiếp tục chạy</b>!")

    def _cmd_health(self):
        """Gửi health report. Chạy trong thread riêng với timeout vì psutil có thể chậm."""
        import concurrent.futures
        from app.database.core import SessionLocal
        from app.services.health import HealthService

        def _fetch():
            with SessionLocal() as db:
                return HealthService.get_system_health(db)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_fetch)
                h = future.result(timeout=10)  # Max 10s cho health check
        except concurrent.futures.TimeoutError:
            self.client.send_message("⏱ Health check bị timeout (>10s). Thử lại sau.")
            return
        except Exception as e:
            self.client.send_message(f"❌ Health check lỗi: {e}")
            return

        status = h.get("status", "unknown")
        worker = h.get("worker", {})
        jobs = h.get("jobs", {})
        accounts = h.get("accounts", {})
        system = h.get("system", {})
        metrics = h.get("metrics", {})

        # Status emoji
        if status == "ok":
            status_icon = "🟢"
        elif status == "degraded":
            status_icon = "🟡"
        else:
            status_icon = "🔴"

        msg = (
            f"{status_icon} <b>Health: {status.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👷 Worker: {worker.get('status', '?')}"
        )

        # Uptime
        uptime_h = worker.get("uptime_hours", 0)
        if uptime_h:
            msg += f" ({uptime_h}h)"
        msg += "\n"

        if worker.get("safe_mode"):
            msg += "🛡 Safe Mode: BẬT\n"

        msg += (
            f"🔄 Running: {jobs.get('running', 0)} | "
            f"❌ Failed 24h: {jobs.get('failed_24h', 0)}\n"
        )

        orphans = jobs.get("orphans", 0)
        if orphans:
            msg += f"👻 Orphans: {orphans}\n"

        msg += f"👤 Invalid accounts: {accounts.get('disabled_or_invalid', 0)}\n"

        # System resources
        cpu = system.get("cpu_percent", 0)
        ram_pct = system.get("sys_memory_percent", 0)
        ram_used = system.get("sys_memory_used_gb", 0)
        ram_total = system.get("sys_memory_total_gb", 0)
        disk_pct = system.get("disk_percent", 0)
        msg += f"🖥 CPU: {cpu}%"
        if cpu > 85:
            msg += " 🔴"
        msg += f" | RAM: {ram_used}/{ram_total}GB ({ram_pct}%)"
        if ram_pct > 85:
            msg += " 🔴"
        msg += f"\n💿 Disk: {disk_pct}%"
        if disk_pct > 90:
            msg += " 🔴"
        msg += f" | 🌐 Chrome: {system.get('browser_processes', 0)}\n"

        # Metrics
        views = metrics.get("total_views", 0)
        clicks = metrics.get("total_clicks", 0)
        if views or clicks:
            msg += f"📈 Views: {views:,} | Clicks: {clicks:,}\n"

        reasons = h.get("reasons", [])
        if reasons:
            msg += "\n⚠️ <b>Issues:</b>\n"
            for r in reasons[:5]:
                msg += f"  • {r}\n"

        self.client.send_message(msg)

    def _cmd_jobs(self):
        """Liệt kê jobs đang chờ xử lý (PENDING + DRAFT)."""
        from app.database.core import SessionLocal
        from app.database.models import Job

        with SessionLocal() as db:
            pending = db.query(Job).filter(Job.status == "PENDING").order_by(Job.schedule_ts.asc()).limit(10).all()
            drafts = db.query(Job).filter(Job.status == "DRAFT").limit(10).all()
            running = db.query(Job).filter(Job.status == "RUNNING").first()

            total_pending = db.query(Job).filter(Job.status == "PENDING").count()
            total_draft = db.query(Job).filter(Job.status == "DRAFT").count()

            msg = "📋 <b>Danh sách Jobs</b>\n━━━━━━━━━━━━━━━━━━\n"

            if running:
                account_name = running.account.name if running.account else "?"
                msg += f"🔄 <b>Đang chạy:</b> Job #{running.id} ({account_name})\n\n"

            if pending:
                msg += f"⏳ <b>Pending ({total_pending}):</b>\n"
                for j in pending:
                    acc = j.account.name if j.account else "?"
                    # Format schedule time
                    if j.schedule_ts:
                        from datetime import datetime
                        from zoneinfo import ZoneInfo
                        from app.config import TIMEZONE
                        dt = datetime.fromtimestamp(j.schedule_ts, tz=ZoneInfo(TIMEZONE))
                        t = dt.strftime("%H:%M")
                    else:
                        t = "?"
                    caption_short = (j.caption or "")[:30].replace("\n", " ")
                    msg += f"  #{j.id} {acc} ⏰{t} — {caption_short}…\n"

                if total_pending > 10:
                    msg += f"  <i>...và {total_pending - 10} jobs khác</i>\n"
            else:
                msg += "⏳ Không có job PENDING nào.\n"

            msg += "\n"

            if drafts:
                msg += f"📝 <b>Draft ({total_draft}):</b>\n"
                for j in drafts:
                    acc = j.account.name if j.account else "?"
                    caption_short = (j.caption or "")[:30].replace("\n", " ")
                    msg += f"  #{j.id} {acc} — {caption_short}…\n"
            else:
                msg += "📝 Không có DRAFT nào.\n"

        self.client.send_message(msg)

    def _cmd_drafts(self):
        """Hiển thị tất cả DRAFT jobs kèm nút Approve/Cancel luôn."""
        from app.database.core import SessionLocal
        from app.database.models import Job

        with SessionLocal() as db:
            drafts = db.query(Job).filter(Job.status == "DRAFT").all()

            if not drafts:
                self.client.send_message("📝 Hiện tại không có bản nháp (DRAFT) nào chờ duyệt.")
                return

            self.client.send_message(f"📝 <b>Đang có {len(drafts)} bản nháp cần duyệt:</b>\n━━━━━━━━━━━━━━━━━━")

            for job in drafts:
                acc = job.account.name if job.account else "Unknown Account"
                plat = job.platform or "Unknown"
                caption_preview = (job.caption or "").strip()
                if len(caption_preview) > 200:
                    caption_preview = caption_preview[:200] + "..."

                msg = f"📋 <b>Job #{job.id}</b> | {plat} ({acc})\n"
                if job.target_page:
                    msg += f"🚩 Target: {job.target_page}\n"
                msg += f"\n✍️ <i>{caption_preview}</i>"

                buttons = [[
                    {"text": "✅ Approve", "callback_data": f"approve:{job.id}"},
                    {"text": "❌ Cancel", "callback_data": f"cancel:{job.id}"},
                ]]

                self.client.send_message(msg, reply_markup={"inline_keyboard": buttons})

    # ─── Phase 2: New Command Handlers ────────────

    def _cmd_retry(self, args=None):
        """Retry 1 job FAILED. Usage: /retry <id>"""
        if not args:
            self.client.send_message("⚠️ Thiếu Job ID.\nCú pháp: <code>/retry 123</code>")
            return

        try:
            job_id = int(args[0])
        except ValueError:
            self.client.send_message(f"⚠️ <code>{args[0]}</code> không phải số hợp lệ.")
            return

        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.job import JobService

        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()

            if not job:
                self.client.send_message(f"❌ Job #{job_id} không tồn tại.")
                return

            if job.status != "FAILED":
                self.client.send_message(
                    f"⚠️ Job #{job_id} đang ở trạng thái <b>{job.status}</b>, không phải FAILED.\n"
                    f"Chỉ retry được job FAILED."
                )
                return

            try:
                JobService.retry_job(db, job_id)
                acc = job.account.name if job.account else "?"
                self.client.send_message(
                    f"✅ <b>Job #{job_id}</b> ({acc}) đã được retry!\n"
                    f"Trạng thái: FAILED → PENDING"
                )
            except ValueError as e:
                self.client.send_message(f"⚠️ Không thể retry Job #{job_id}: {e}")

    def _cmd_cancel(self, args=None):
        """Hủy job + xóa file media. Usage: /cancel <id>"""
        import os

        if not args:
            self.client.send_message("⚠️ Thiếu Job ID.\nCú pháp: <code>/cancel 123</code>")
            return

        try:
            job_id = int(args[0])
        except ValueError:
            self.client.send_message(f"⚠️ <code>{args[0]}</code> không phải số hợp lệ.")
            return

        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.job import JobService

        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()

            if not job:
                self.client.send_message(f"❌ Job #{job_id} không tồn tại.")
                return

            if job.status not in ("PENDING", "DRAFT", "AI_PROCESSING"):
                self.client.send_message(
                    f"⚠️ Job #{job_id} đang ở trạng thái <b>{job.status}</b>.\n"
                    f"Chỉ cancel được PENDING, DRAFT hoặc AI_PROCESSING."
                )
                return

            acc = job.account.name if job.account else "?"
            files_deleted = []

            try:
                # Cancel trong DB
                JobService.cancel_job(db, job_id)

                # Xóa file media
                for path in [job.media_path, job.processed_media_path]:
                    if path and os.path.exists(path):
                        try:
                            os.unlink(path)
                            files_deleted.append(os.path.basename(path))
                        except Exception as e:
                            logger.warning("[Telegram] Could not delete %s: %s", path, e)

                # Clear paths trong DB
                job.media_path = None
                job.processed_media_path = None
                db.commit()

                msg = f"❌ <b>Job #{job_id}</b> ({acc}) đã bị hủy!"
                if files_deleted:
                    msg += f"\n🗑 Đã xóa: {', '.join(files_deleted)}"
                else:
                    msg += "\n📂 Không có file media cần xóa."
                self.client.send_message(msg)

            except ValueError as e:
                self.client.send_message(f"⚠️ Không thể cancel Job #{job_id}: {e}")

    def _cmd_failed(self):
        """Xem 10 jobs FAILED gần nhất kèm nút Retry."""
        from app.database.core import SessionLocal
        from app.database.models import Job

        with SessionLocal() as db:
            jobs = (
                db.query(Job)
                .filter(Job.status == "FAILED")
                .order_by(Job.finished_at.desc())
                .limit(10)
                .all()
            )

            total = db.query(Job).filter(Job.status == "FAILED").count()

            if not jobs:
                self.client.send_message("✅ Không có job FAILED nào! Mọi thứ ổn.")
                return

            msg = f"❌ <b>Jobs FAILED ({total} tổng cộng):</b>\n━━━━━━━━━━━━━━━━━━\n"
            for j in jobs:
                acc = j.account.name if j.account else "?"
                error_short = (j.last_error or "Unknown")[:40]
                msg += f"#{j.id} {acc} [{j.tries}/{j.max_tries}] — {error_short}\n"

            msg += f"\n💡 Gõ <code>/retry ID</code> để retry."
            self.client.send_message(msg)

    def _cmd_done(self):
        """5 jobs DONE gần nhất kèm URL bài đăng."""
        from app.database.core import SessionLocal
        from app.database.models import Job

        with SessionLocal() as db:
            jobs = (
                db.query(Job)
                .filter(Job.status == "DONE")
                .order_by(Job.finished_at.desc())
                .limit(5)
                .all()
            )

            if not jobs:
                self.client.send_message("📝 Chưa có job nào hoàn thành.")
                return

            msg = "✅ <b>5 bài đăng gần nhất:</b>\n━━━━━━━━━━━━━━━━━━\n"
            for j in jobs:
                acc = j.account.name if j.account else "?"
                views = j.view_24h if j.view_24h is not None else "-"
                url = j.post_url or "N/A"
                # Rút gọn URL cho dễ đọc
                if url and len(url) > 50:
                    url_display = url[:50] + "..."
                else:
                    url_display = url
                msg += f"#{j.id} {acc} | 👁 {views}\n"
                if j.post_url:
                    msg += f"  🔗 <a href=\"{j.post_url}\">{url_display}</a>\n"

            self.client.send_message(msg)

    def _cmd_sys(self):
        """Hiển thị thông số phần cứng: CPU, RAM, Disk."""
        import psutil

        try:
            cpu = psutil.cpu_percent(interval=1)  # 1s sampling cho chính xác
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Count Chrome/Playwright processes
            chrome_count = sum(
                1 for p in psutil.process_iter(['name'])
                if "chrome" in p.info.get('name', '').lower()
                   or "playwright" in p.info.get('name', '').lower()
            )

            cpu_icon = "🔴" if cpu > 85 else ("🟡" if cpu > 60 else "🟢")
            ram_icon = "🔴" if vm.percent > 85 else ("🟡" if vm.percent > 60 else "🟢")
            disk_icon = "🔴" if disk.percent > 90 else ("🟡" if disk.percent > 70 else "🟢")

            msg = (
                "🖥 <b>System Resources</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"{cpu_icon} CPU: <b>{cpu}%</b>\n"
                f"{ram_icon} RAM: <b>{vm.used / (1024**3):.1f}</b> / {vm.total / (1024**3):.1f} GB ({vm.percent}%)\n"
                f"   Available: {vm.available / (1024**3):.1f} GB\n"
                f"{disk_icon} Disk: <b>{disk.used / (1024**3):.1f}</b> / {disk.total / (1024**3):.1f} GB ({disk.percent}%)\n"
                f"   Free: {disk.free / (1024**3):.1f} GB\n"
                f"🌐 Chrome Processes: {chrome_count}"
            )
            self.client.send_message(msg)

        except Exception as e:
            logger.error("[Telegram] /sys error: %s", e)
            self.client.send_message(f"❌ Không thể lấy thông số hệ thống: {e}")

    def _cmd_stats(self):
        """Thống kê nhanh: jobs hôm nay, views, clicks."""
        from app.database.core import SessionLocal
        from app.database.models import Job
        from sqlalchemy import func
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.config import TIMEZONE

        with SessionLocal() as db:
            # Tính mốc đầu ngày hôm nay (theo timezone VN)
            now_dt = datetime.now(ZoneInfo(TIMEZONE))
            start_of_day = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            start_ts = int(start_of_day.timestamp())
            now_ts = int(time.time())

            done_today = db.query(Job).filter(
                Job.status == "DONE", Job.finished_at >= start_ts
            ).count()

            failed_today = db.query(Job).filter(
                Job.status == "FAILED", Job.finished_at >= start_ts
            ).count()

            pending = db.query(Job).filter(Job.status == "PENDING").count()
            draft = db.query(Job).filter(Job.status == "DRAFT").count()
            running = db.query(Job).filter(Job.status == "RUNNING").count()

            # All-time metrics
            total_views = db.query(func.sum(Job.view_24h)).filter(
                Job.view_24h != None
            ).scalar() or 0
            total_clicks = db.query(func.sum(Job.click_count)).filter(
                Job.click_count != None, Job.click_count > 0
            ).scalar() or 0
            avg_views = db.query(func.avg(Job.view_24h)).filter(
                Job.view_24h != None
            ).scalar() or 0

            # Avg job duration today
            avg_duration = db.query(func.avg(Job.finished_at - Job.started_at)).filter(
                Job.status == "DONE",
                Job.finished_at >= start_ts,
                Job.started_at != None,
                Job.finished_at != None
            ).scalar()

            msg = (
                f"📊 <b>Thống kê {now_dt.strftime('%d/%m/%Y')}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ Done hôm nay: <b>{done_today}</b>\n"
                f"❌ Failed hôm nay: <b>{failed_today}</b>\n"
                f"⏳ Pending: {pending} | 📝 Draft: {draft} | 🔄 Running: {running}\n"
                f"\n📈 <b>Metrics tổng:</b>\n"
                f"👁 Views: {total_views:,}\n"
                f"🖱 Clicks: {total_clicks:,}\n"
                f"📊 Avg views/post: {round(avg_views, 1)}\n"
            )
            if avg_duration:
                msg += f"⏱ Avg thời gian xử lý: {int(avg_duration)}s ({int(avg_duration)//60}m{int(avg_duration)%60}s)\n"

        self.client.send_message(msg)

    def _cmd_safemode(self):
        """Bật/tắt Safe Mode từ xa."""
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService

        with SessionLocal() as db:
            state = WorkerService.toggle_safe_mode(db)
            if state.safe_mode:
                self.client.send_message(
                    "🛡 Safe Mode: <b>BẬT</b>\n"
                    "Bot sẽ làm mọi thứ nhưng KHÔNG bấm nút Đăng.\n"
                    "Gõ /safemode lần nữa để tắt."
                )
            else:
                self.client.send_message(
                    "🟢 Safe Mode: <b>TẮT</b>\n"
                    "Bot sẽ đăng bài thật. Cẩn thận!"
                )

    def _cmd_restart(self):
        """Gửi lệnh restart worker."""
        from app.database.core import SessionLocal
        from app.services.worker import WorkerService

        with SessionLocal() as db:
            state = WorkerService.get_or_create_state(db)

            # Kiểm tra xem đã có lệnh pending chưa
            if state.pending_command:
                self.client.send_message(
                    f"⚠️ Worker đang có lệnh chờ: <b>{state.pending_command}</b>\n"
                    f"Hãy đợi lệnh trước hoàn tất."
                )
                return

            if state.current_job_id:
                self.client.send_message(
                    f"⏳ Worker đang xử lý Job #{state.current_job_id}.\n"
                    f"Lệnh restart sẽ được thực thi sau khi job hoàn tất."
                )

            WorkerService.set_command(db, "RESTART_REQUESTED")
            self.client.send_message(
                "🔄 Đã gửi lệnh <b>RESTART</b> cho worker.\n"
                "Worker sẽ tự thoát và tmux sẽ restart."
            )

    def _cmd_spy(self, args=None):
        """Thêm link đối thủ cho account. Usage: /spy <account_name> <competitor_url>"""
        if not args or len(args) < 2:
            self.client.send_message(
                "⚠️ Cú pháp: <code>/spy TenAcc https://facebook.com/doithu</code>\n"
                "Ví dụ: <code>/spy NgocVi https://facebook.com/shopee.vn</code>"
            )
            return

        account_name = args[0]
        competitor_url = args[1]

        # Validate URL cơ bản
        if not competitor_url.startswith("http"):
            competitor_url = "https://" + competitor_url

        import json
        from app.database.core import SessionLocal
        from app.database.models import Account

        with SessionLocal() as db:
            account = db.query(Account).filter(Account.name == account_name).first()
            if not account:
                self.client.send_message(f"❌ Account <b>{account_name}</b> không tồn tại.")
                return

            # Parse existing competitor_urls (JSON list or empty)
            existing = []
            if account.competitor_urls:
                try:
                    existing = json.loads(account.competitor_urls)
                    if not isinstance(existing, list):
                        existing = [str(existing)]
                except (json.JSONDecodeError, TypeError):
                    existing = [u.strip() for u in account.competitor_urls.split(",") if u.strip()]

            if competitor_url in existing:
                self.client.send_message(f"ℹ️ Link này đã có trong danh sách đối thủ của <b>{account_name}</b>.")
                return

            existing.append(competitor_url)
            account.competitor_urls = json.dumps(existing, ensure_ascii=False)
            db.commit()

            self.client.send_message(
                f"✅ Đã thêm đối thủ cho <b>{account_name}</b>:\n"
                f"🔗 {competitor_url}\n"
                f"📋 Tổng: {len(existing)} link đối thủ"
            )
            logger.info("[Telegram] /spy: Added competitor '%s' to account '%s'", competitor_url, account_name)

    def _cmd_reup(self, args=None):
        """Reup video từ URL bất kỳ. Usage: /reup [AccName] <url> [TargetPage]"""
        if not args:
            self.client.send_message(
                "⚠️ Cú pháp: <code>/reup URL</code> hoặc <code>/reup TenAcc URL</code> hoặc <code>/reup TenAcc URL TenPageHocURL</code>\n"
                "Ví dụ:\n"
                "<code>/reup https://tiktok.com/@user/video/123</code>\n"
                "<code>/reup HoangKhoa https://tiktok.com/@user/video/123</code>\n"
                "<code>/reup HoangKhoa https://tiktok.com/@user/video/123 Demariki</code> (Tự tìm URL Fanpage)\n"
                "<code>/reup HoangKhoa https://tiktok.com/@user/video/123 https://facebook.com/PageName</code>"
            )
            return

        from app.database.core import SessionLocal
        from app.database.models import ViralMaterial, Account

        # Parse args to find source URL, account name, and optional target page
        account_name = None
        url = None
        target_page_arg = None
        target_page_url = None

        # Look for URLs in the arguments
        urls = [arg for arg in args if arg.startswith("http")]
        
        if len(urls) == 0:
            # Fallback: assume last arg is URL even if missing http
            url = args[-1]
            if not url.startswith("http"):
                url = "https://" + url
            if len(args) > 1:
                account_name = " ".join(args[:-1])
        elif len(urls) == 1:
            url = urls[0]
            # Everything before the URL is account name
            url_idx = args.index(url)
            if url_idx > 0:
                account_name = " ".join(args[:url_idx])
            # Anything after URL could be target_page (if they format it weirdly), but we specified [AccName] <url> [TargetPage]
            if url_idx < len(args) - 1:
                target_page_arg = " ".join(args[url_idx+1:])
        else:
            # At least 2 URLs found. First is source, second is target page.
            url = urls[0]
            target_page_arg = urls[-1] # Usually the second one
            url_idx = args.index(url)
            if url_idx > 0:
                account_name = " ".join(args[:url_idx])

        if target_page_arg and target_page_arg.startswith("http"):
            target_page_url = target_page_arg

        # Auto-detect platform từ domain
        platform = "unknown"
        domain = url.lower()
        if "tiktok.com" in domain:
            platform = "tiktok"
        elif "youtube.com" in domain or "youtu.be" in domain:
            platform = "youtube"
        elif "facebook.com" in domain or "fb.watch" in domain:
            platform = "facebook"
        elif "instagram.com" in domain:
            platform = "instagram"

        with SessionLocal() as db:
            # Resolve account nếu có chỉ định
            target_account_id = None
            account = None
            if account_name:
                account = db.query(Account).filter(Account.name == account_name).first()
                if not account:
                    self.client.send_message(f"❌ Account <b>{account_name}</b> không tồn tại.")
                    return
                target_account_id = account.id

            # Tự động tìm Page URL nếu target_page_arg không phải là HTTP link
            if target_page_arg and not target_page_url and account:
                pages = account.managed_pages_list
                target_page_arg_lower = target_page_arg.lower()
                
                matched = False
                for p in pages:
                    # Nếu chuỗi tìm kiếm nằm trong tên page (case-insensitive)
                    if target_page_arg_lower in p.get("name", "").lower():
                        target_page_url = p.get("url")
                        matched = True
                        break
                        
                if not matched:
                    self.client.send_message(f"❌ Account <b>{account.name}</b> không quản lý Page nào có tên chứa '{target_page_arg}'.\nVui lòng cung cấp link URL chính xác hoặc dùng Sync Pages trên Dashboard.")
                    return

            # Check trùng
            existing = db.query(ViralMaterial).filter(ViralMaterial.url == url).first()
            if existing:
                self.client.send_message(
                    f"ℹ️ URL này đã có trong hệ thống (ID #{existing.id}, status: {existing.status})."
                )
                return

            mat = ViralMaterial(
                url=url,
                platform=platform,
                views=0,
                title=f"Manual reup via Telegram",
                status="REUP",
                scraped_by_account_id=target_account_id,
                target_page=target_page_url,
            )
            db.add(mat)
            db.commit()

            platform_emoji = {
                "tiktok": "🎵", "youtube": "▶️", "facebook": "📘",
                "instagram": "📷", "unknown": "🔗"
            }
            emoji = platform_emoji.get(platform, "🔗")
            acc_label = f" → <b>{account_name}</b>" if account_name else " → acc mặc định"

            msg_lines = [
                "✅ Đã thêm video vào hàng đợi reup!",
                f"{emoji} Platform: <b>{platform}</b>",
                f"👤 Account:{acc_label}"
            ]
            if target_page_url:
                msg_lines.append(f"🚩 Target Page: {target_page_url}")
                
            msg_lines.extend([
                f"🔗 {url}",
                f"📋 ID: #{mat.id}",
                "⏳ Maintenance worker sẽ tải + tạo DRAFT trong vòng 5 phút."
            ])
            
            self.client.send_message("\n".join(msg_lines))
            logger.info("[Telegram] /reup: Added '%s' (%s) as REUP material #%s, account=%s", url, platform, mat.id, account_name or "default")

    # ─── Callback Handlers (Inline Buttons) ──────

    def _handle_approve(self, callback_id: str, job_id: int, message_id: int, user_name: str):
        """User click ✅ Approve → DRAFT → PENDING."""
        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.job import JobService

        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()

            if not job:
                self.client.answer_callback_query(callback_id, f"❌ Job #{job_id} không tồn tại!")
                return

            if job.status != "DRAFT":
                self.client.answer_callback_query(
                    callback_id,
                    f"ℹ️ Job #{job_id} đang ở trạng thái {job.status}"
                )
                self.client.edit_message_reply_markup(message_id, reply_markup=None)
                return

            job.status = "PENDING"
            job.is_approved = True
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Approved via Telegram by {user_name}")

            logger.info("[Telegram] Job #%d approved by %s", job_id, user_name)
            self.client.answer_callback_query(callback_id, f"✅ Job #{job_id} đã được duyệt!")
            self.client.edit_message_reply_markup(message_id, reply_markup=None)
            self.client.send_message(f"✅ <b>Đã duyệt Job #{job_id}</b> (bởi {user_name})")

    def _handle_cancel(self, callback_id: str, job_id: int, message_id: int, user_name: str):
        """User click ❌ Cancel → DRAFT/PENDING → CANCELLED."""
        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.job import JobService

        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()

            if not job:
                self.client.answer_callback_query(callback_id, f"❌ Job #{job_id} không tồn tại!")
                return

            if job.status not in ("DRAFT", "PENDING"):
                self.client.answer_callback_query(
                    callback_id,
                    f"ℹ️ Job #{job_id} đang ở trạng thái {job.status}"
                )
                self.client.edit_message_reply_markup(message_id, reply_markup=None)
                return

            prev_status = job.status
            job.status = "CANCELLED"
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Cancelled via Telegram by {user_name} (was {prev_status})")

            logger.info("[Telegram] Job #%d cancelled by %s (was %s)", job_id, user_name, prev_status)
            self.client.answer_callback_query(callback_id, f"❌ Job #{job_id} đã bị hủy!")
            self.client.edit_message_reply_markup(message_id, reply_markup=None)
            self.client.send_message(f"❌ <b>Đã hủy Job #{job_id}</b> (bởi {user_name})")
