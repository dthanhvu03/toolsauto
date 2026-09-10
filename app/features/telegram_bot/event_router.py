import logging
import re
import threading

from app.constants import JobStatus

# Owner bấm "Chia sẻ" từ app TikTok thì tin kèm cả chữ mô tả, không phải link trần.
_URL_RE = re.compile(r"https?://\S+")

logger = logging.getLogger(__name__)

class TelegramEventRouter:
    def __init__(self, client, command_handler):
        self.client = client
        self.command_handler = command_handler

    def dispatch(self, update: dict):
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback_query(update["callback_query"])

    def _handle_message(self, message: dict):
        text = message.get("text", "")
        if text.startswith("/"):
            parts = text.split()
            cmd = parts[0][1:].split("@")[0].lower()
            args = parts[1:]
            self.command_handler.handle_command(cmd, args)
            return

        # ADR-034: trước đây mọi tin không phải lệnh đều bị vứt — kể cả link Owner gửi vào.
        found = _URL_RE.search(text or "")
        if found:
            self._handle_link(found.group(0).rstrip(".,;)"))

    def _handle_link(self, url: str):
        """
        ADR-034 — link kênh ⇒ nguồn tự quét; link video ⇒ material + xử lý nền ngay.

        Đi qua `feature_hooks` chứ không import thẳng `viral_intake`: import-linter chặn
        feature gọi feature (ADR-007). Không bao giờ ném: lỗi chỉ thành tin nhắn.
        """
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        try:
            with SessionLocal() as db:
                res = feature_hooks.call("viral.add_link", db, url) or {}
        except Exception as exc:
            logger.exception("[Telegram] add_link failed")
            self.client.send_message(f"❌ Không thêm được link: {str(exc)[:150]}")
            return

        msg = str(res.get("msg") or "")
        if not res.get("ok"):
            self.client.send_message(f"⚠️ {msg}")
            return

        if res.get("kind") == "source":
            self.client.send_message(f"✅ Đã thêm nguồn tự quét.\n{msg}")
            return

        material_id = res.get("id")
        self.client.send_message(
            f"✅ {msg}\n⏳ Đang tải và xử lý… sẽ gửi video kèm caption khi xong.",
            reply_markup={"inline_keyboard": [[
                {"text": "➕ Thêm cả kênh này làm nguồn", "callback_data": f"src:{material_id}"},
            ]]},
        )
        self._process_material_async(material_id)

    def _process_material_async(self, material_id: int):
        def _run():
            from app.core import feature_hooks
            from app.core.database.core import SessionLocal
            try:
                with SessionLocal() as db:
                    feature_hooks.call("viral.process_one", db, material_id)
            except Exception:
                logger.exception("[Telegram] process_one #%s failed", material_id)
                self.client.send_message(f"❌ Xử lý video #{material_id} thất bại — xem log.")

        threading.Thread(target=_run, name=f"tg-process-{material_id}", daemon=True).start()

    def _handle_callback_query(self, query: dict):
        callback_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        message_id = message.get("message_id")
        user = query.get("from", {}).get("first_name", "User")

        if ":" not in data: return
        action, target_id = data.split(":", 1)
        
        try:
            if action == "approve":
                self._handle_approve(callback_id, int(target_id), message_id, user)
            elif action == "cancel":
                self._handle_cancel(callback_id, int(target_id), message_id, user)
            elif action.startswith("style"):
                self._handle_style(callback_id, data, int(target_id), message_id, user)
            elif action == "src":
                self._handle_add_source(callback_id, int(target_id))
            # ADR-037: điều khiển luồng video
            elif action in ("scan", "tgsrc", "xuly", "gui", "khung"):
                self._handle_video_action(callback_id, action, int(target_id))
            elif action == "cut":
                self._handle_cut(callback_id, target_id)
        except Exception as e:
            logger.exception("[Telegram] Callback failed")
            self.client.answer_callback_query(callback_id, f"❌ Lỗi: {e}")

    # ── ADR-037 ─────────────────────────────────────────────────────────────

    _HOOK_BY_ACTION = {
        "scan": "viral.scan_source",
        "tgsrc": "viral.toggle_source",
        "gui": "viral.resend_material",
    }

    def _handle_video_action(self, callback_id: str, action: str, target_id: int):
        """Quét nguồn / bật-tắt nguồn / xử lý video / gửi lại / mở dải khung hình."""
        if action == "khung":
            self._handle_frames(callback_id, target_id)
            return
        if action == "xuly":
            # Xử lý mất hàng phút ⇒ trả lời ngay rồi chạy nền, đừng để nút quay mãi.
            self.client.answer_callback_query(callback_id, "⏳ Đang xử lý…")
            self.client.send_message(f"⏳ Đang xử lý video #{target_id}… sẽ gửi khi xong.")
            self._process_material_async(target_id)
            return

        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        # Quét một nguồn cũng mất hàng chục giây ⇒ báo trước rồi chạy nền.
        if action == "scan":
            self.client.answer_callback_query(callback_id, "🔍 Đang quét…")

            def _run():
                try:
                    with SessionLocal() as db:
                        res = feature_hooks.call("viral.scan_source", db, target_id) or {}
                    self.client.send_message(("✅ " if res.get("ok") else "⚠️ ") + str(res.get("msg") or ""))
                except Exception:
                    logger.exception("[Telegram] quét nguồn #%s hỏng", target_id)
                    self.client.send_message(f"❌ Quét nguồn #{target_id} hỏng — xem log.")

            threading.Thread(target=_run, name=f"tg-scan-{target_id}", daemon=True).start()
            return

        with SessionLocal() as db:
            res = feature_hooks.call(self._HOOK_BY_ACTION[action], db, target_id) or {}
        msg = str(res.get("msg") or "")
        self.client.answer_callback_query(callback_id, ("✅ " if res.get("ok") else "⚠️ ") + msg[:180])
        self.client.send_message(("✅ " if res.get("ok") else "⚠️ ") + msg)

    def _handle_frames(self, callback_id: str, material_id: int):
        """Gửi ảnh lưới 4×3 + 12 nút ghi phút. Telegram không cho bấm vào vùng trong ảnh."""
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        with SessionLocal() as db:
            res = feature_hooks.call("viral.material_frames", db, material_id) or {}
        frames = res.get("frames") or []
        if not frames:
            self.client.answer_callback_query(callback_id, "⚠️ Chưa có khung hình")
            self.client.send_message(
                f"⚠️ Video #{material_id} chưa có khung hình. Bấm ⚙️ Xử lý một lần là tool trích luôn."
            )
            return

        self.client.answer_callback_query(callback_id, "✂️ Chọn khung bên dưới")
        rows, hang = [], []
        for _idx, sec in frames:
            hang.append({"text": f"{sec // 60}:{sec % 60:02d}", "callback_data": f"cut:{material_id}:{sec}"})
            if len(hang) == 4:
                rows.append(hang); hang = []
        if hang:
            rows.append(hang)

        markup = {"inline_keyboard": rows}
        sheet = res.get("sheet")
        caption = (
            f"✂️ <b>Chọn đoạn cắt cho #{material_id}</b>\n"
            "Bấm mốc có cảnh đáng lấy — tool cắt lại từ đó rồi gửi video mới."
        )
        if sheet:
            self.client.send_photo(sheet, caption)
        self.client.send_message(caption if not sheet else "👆 Chọn mốc:", reply_markup=markup)

    def _handle_cut(self, callback_id: str, target: str):
        """``cut:<material_id>:<giây>`` — đặt mốc rồi xử lý lại."""
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        material_id, _, sec = str(target).partition(":")
        if not material_id.isdigit() or not sec.isdigit():
            self.client.answer_callback_query(callback_id, "⚠️ Mốc không hợp lệ")
            return
        material_id, sec = int(material_id), int(sec)

        with SessionLocal() as db:
            res = feature_hooks.call("viral.set_clip", db, material_id, sec, None) or {}
        if not res.get("ok"):
            self.client.answer_callback_query(callback_id, "⚠️ " + str(res.get("msg"))[:180])
            self.client.send_message("⚠️ " + str(res.get("msg")))
            return

        self.client.answer_callback_query(callback_id, f"✂️ Cắt từ {sec // 60}:{sec % 60:02d}")
        self.client.send_message(
            f"✂️ Đã đặt mốc {sec // 60}:{sec % 60:02d} cho #{material_id} — đang cắt lại…"
        )
        self._process_material_async(material_id)

    def _handle_add_source(self, callback_id: str, material_id: int):
        """ADR-034 + ADR-028 — biến video vừa dán thành nguồn kênh, dò channel_id từ chính nó."""
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        with SessionLocal() as db:
            res = feature_hooks.call("viral.add_source_from_material", db, material_id) or {}
        msg = str(res.get("msg") or "")
        self.client.answer_callback_query(callback_id, ("✅ " if res.get("ok") else "⚠️ ") + msg[:180])
        self.client.send_message(("✅ " if res.get("ok") else "⚠️ ") + msg)

    def _handle_approve(self, callback_id: str, job_id: int, message_id: int, user_name: str):
        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        from app.core.queue.job import JobService
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or job.status != JobStatus.DRAFT:
                self.client.answer_callback_query(callback_id, "❌ Job không hợp lệ")
                return
            job.status = JobStatus.PENDING
            job.is_approved = True
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Approved by {user_name}")
        self.client.answer_callback_query(callback_id, f"✅ Job #{job_id} approved")
        self.client.edit_message_reply_markup(message_id, reply_markup=None)
        self.client.send_message(f"✅ Approved Job #{job_id} by {user_name}")

    def _handle_cancel(self, callback_id: str, job_id: int, message_id: int, user_name: str):
        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        from app.core.queue.job import JobService
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or job.status not in (JobStatus.DRAFT, JobStatus.PENDING):
                self.client.answer_callback_query(callback_id, "❌ Không thể hủy Job này")
                return
            job.status = JobStatus.CANCELLED
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Cancelled by {user_name}")
        self.client.answer_callback_query(callback_id, f"❌ Job #{job_id} cancelled")
        self.client.edit_message_reply_markup(message_id, reply_markup=None)
        self.client.send_message(f"❌ Cancelled Job #{job_id} by {user_name}")

    def _handle_style(self, callback_id: str, action: str, job_id: int, message_id: int, user_name: str):
        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        from app.core.notifier.service import NotifierService
        style = action.split("_")[1]
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or job.status != JobStatus.AWAITING_STYLE:
                self.client.answer_callback_query(callback_id, "❌ Sai trạng thái")
                return
            if style == "skip":
                job.status = JobStatus.DRAFT
                if job.caption: job.caption = job.caption.replace("[AI_GENERATE]", "").strip()
                db.commit()
                NotifierService.notify_draft_ready(job)
            else:
                job.ai_style = style
                job.status = JobStatus.DRAFT
                db.commit()
        self.client.answer_callback_query(callback_id, f"✅ Style: {style}")
        self.client.edit_message_reply_markup(message_id, reply_markup=None)
