import logging
import concurrent.futures
import threading
from app.constants import JobStatus

logger = logging.getLogger(__name__)

class TelegramCommandHandler:
    def __init__(self, client):
        self.client = client

    def handler_map(self) -> dict:
        """
        Bảng lệnh, tách riêng để test đọc được (ADR-037).

        Trước đây bảng nằm trong `handle_command` nên test phải chép tay danh sách lệnh — thêm
        lệnh mới là danh sách lệch, và cái canh "đừng quảng cáo lệnh không tồn tại" báo nhầm.
        """
        return {
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
            # ADR-037: nối vào luồng video, không chỉ luồng job cũ
            "nguon": self._cmd_nguon,
            "moi": self._cmd_moi,
            "sansang": self._cmd_sansang,
            "dadang": self._cmd_dadang,  # ADR-042
            "tai": self._cmd_tai,  # ADR-043
            "caidat": self._cmd_caidat,
        }

    def handle_command(self, cmd: str, args: list = None):
        handler = self.handler_map().get(cmd.lower())
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
            "/viral &lt;min_views&gt; &lt;max_videos&gt; — đổi ngưỡng quét chung\n"
            "\n<b>Luồng video</b>\n"
            "/nguon — nguồn tự quét, kèm nút Quét ngay / Bật-Tắt\n"
            "/moi — video mới chưa xử lý, kèm nút Xử lý\n"
            "/sansang — video chờ đăng tay, kèm nút Gửi lại, Chọn đoạn, Chia phần, Đã đăng\n"
            "/dadang — 10 video đã đăng gần nhất, kèm nút Chưa đăng (bấm nhầm)\n"
            "/tai &lt;link&gt; — chỉ tải bản gốc về máy để xem, không xào chẻ, không vào danh sách đăng\n"
            "/caidat — xem / đổi cài đặt luồng video ngay tại đây (độ dài cắt, giữ file gốc, caption tự động…)\n"
            "\nHoặc dán thẳng link TikTok/YouTube vào đây."
        )

    # ── ADR-037: điều khiển luồng video ─────────────────────────────────────

    @staticmethod
    def _mmss(seconds) -> str:
        total = int(seconds or 0)
        return f"{total // 60}:{total % 60:02d}"

    @staticmethod
    def _gio(ts) -> str:
        """
        Epoch → ``dd/mm HH:MM`` theo ``config.TIMEZONE``, KHÔNG theo đồng hồ tiến trình.

        2026-09-11: laptop chạy bot theo UTC nên `/nguon` ghi "06:24" cho lượt quét lúc 13:24 —
        Owner tưởng lỗi cũ từ sáng, thực ra vừa quét xong. Trang web đã né bẫy này bằng
        ``ZoneInfo(TIMEZONE)``; Telegram phải đi cùng một múi giờ.
        """
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        import app.config as config

        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(ZoneInfo(config.TIMEZONE))
        return dt.strftime("%d/%m %H:%M")

    @staticmethod
    def _dong_quet(s: dict) -> str:
        """
        Một dòng nói thật về lượt quét gần nhất: LÚC NÀO, và ra sao.

        Trước đây chỉ có "tìm được lần cuối: 0" + cục lỗi — không biết lần cuối là 2 phút hay
        2 giờ trước, và "0" không phân biệt được "không có gì mới" với "quét hỏng".
        """
        import html as html_mod

        ts = s.get("last_scanned_at")
        if not ts:
            return "🕐 Chưa quét lần nào — bấm 🔍 Quét ngay."
        luc = TelegramCommandHandler._gio(ts)
        if s.get("last_error"):
            return f"🕐 Quét lúc {luc}: ❌ hỏng — {html_mod.escape(str(s['last_error'])[:300])}"
        found = int(s.get("last_found") or 0)
        return f"🕐 Quét lúc {luc}: " + (f"✅ {found} video mới" if found else "⚪ không có video mới")

    def _cmd_nguon(self, args=None):
        """Liệt kê nguồn tự quét, mỗi nguồn kèm nút Quét ngay / Bật-Tắt."""
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        with SessionLocal() as db:
            rows = feature_hooks.call("viral.sources_summary", db) or []
        if not rows:
            self.client.send_message(
                "📭 Chưa có nguồn nào.\nDán thẳng link kênh (hoặc link một video) vào đây là tool tự thêm."
            )
            return

        for s in rows:
            trang_thai = "🟢 Bật" if s["enabled"] else "⚪ Tắt"
            nguong = f"{s['min_views']:,}" if s.get("min_views") else "mặc định"
            self.client.send_message(
                f"📺 <b>@{s['handle']}</b> · {s['platform']} · {trang_thai}\n"
                f"👁 Ngưỡng {nguong}\n{self._dong_quet(s)}",
                reply_markup={"inline_keyboard": [[
                    {"text": "🔍 Quét ngay", "callback_data": f"scan:{s['id']}"},
                    {"text": "⚪ Tắt" if s["enabled"] else "🟢 Bật", "callback_data": f"tgsrc:{s['id']}"},
                ]]},
            )

    def _cmd_moi(self, args=None):
        """Video mới quét về, chưa xử lý — kèm nút Xử lý."""
        self._liet_ke_material("NEW", "🆕 <b>Video mới chưa xử lý</b>", "xuly", "⚙️ Xử lý",
                               "📭 Không có video mới nào đang chờ.")

    def _cmd_sansang(self, args=None):
        """Video đã xử lý, đang chờ đăng tay — kèm nút Gửi lại."""
        self._liet_ke_material("READY", "🎬 <b>Sẵn sàng đăng tay</b>", "gui", "📤 Gửi lại",
                               "📭 Chưa có video nào sẵn sàng.")

    def _cmd_tai(self, args=None):
        """
        ADR-043 — `/tai <link>`: tải bản gốc về máy, KHÔNG reup, không vào /moi hay /sansang.

        Tải cả file mất hàng chục giây tới vài phút ⇒ trả lời ngay rồi chạy nền. Gửi file lên
        Telegram chỉ khi ≤ 50 MB; hơn thì gửi đường dẫn — hứa gửi rồi lỗi 413 là nhãn nói dối.
        """
        import threading

        url = next((a for a in (args or []) if a.lower().startswith(("http://", "https://"))), None)
        if not url:
            self.client.send_message(
                "⚠️ Cú pháp: /tai &lt;link video&gt;\n"
                "Tải bản gốc về máy để xem, không xào chẻ, không vào danh sách đăng. "
                "Link trần (không /tai) thì tool sẽ làm video như thường."
            )
            return
        self.client.send_message("📥 Đang tải bản gốc… gửi lại khi xong (file ≤ 50 MB mới gửi được qua Telegram).")

        def _run():
            from app.core import feature_hooks
            from app.core.database.core import SessionLocal

            try:
                with SessionLocal() as db:
                    res = feature_hooks.call("viral.fetch_original", db, url) or {}
                msg = str(res.get("msg") or "")
                if not res.get("ok"):
                    self.client.send_message("⚠️ " + msg)
                    return
                if res.get("sendable") and res.get("path") and hasattr(self.client, "send_video"):
                    self.client.send_video(res["path"], msg)
                else:
                    self.client.send_message(msg + "\n(quá 50 MB — Telegram không cho gửi; lấy từ máy hoặc Drive)")
            except Exception:
                logger.exception("[Telegram] /tai hỏng: %s", url)
                self.client.send_message("❌ Tải hỏng — xem log.")

        threading.Thread(target=_run, name="tg-tai", daemon=True).start()

    # Tên ngắn tiếng Việt cho các ô Owner hay chỉnh nhất. Giá trị thật, kiểu, min/max đều đọc từ
    # bảng SETTINGS của web (`app.core.settings`) — không chép tay, thêm ô ở web là ở đây tự đúng.
    _CAIDAT_ALIAS = {
        "dodai": "reup.max_duration_sec",
        "giugoc": "viral.keep_source_days",
        "caption": "viral.auto_caption_on_ready",
        "nguong": "viral.min_views",
        "sovideo": "viral.max_videos_per_channel",
        "quet": "viral.source_scan_interval_min",
        "trung": "viral.phash_max_distance",
        "diachi": "PUBLIC_BASE_URL",  # ADR-044
    }

    def _cmd_caidat(self, args=None):
        """
        `/caidat` — xem; `/caidat <tên> <giá trị>` — đổi. Owner hỏi "mấy setting này setting ở
        tele được không" sau khi video bị cắt 1:30 mà phải mở web mới tìm ra ô "Độ dài tối đa".

        Ghi bằng chính `upsert_setting` của web (validate min/max, ghi audit, bust cache, đẩy
        vào config) rồi ĐỌC LẠI giá trị hiệu lực để trả lời — không trả lại thứ Owner vừa gõ.
        """
        import html as html_mod

        from app.core import settings as rs
        from app.core.database.core import SessionLocal

        def _spec(name: str):
            key = self._CAIDAT_ALIAS.get(name.lower(), name)
            return key, rs.SETTINGS.get(key)

        def _fmt(spec, value) -> str:
            if spec.type == "bool":
                return "bật" if bool(value) else "tắt"
            unit = f" {spec.unit}" if getattr(spec, "unit", None) else ""
            return f"{value}{unit}"

        args = args or []
        if not args:
            with SessionLocal() as db:
                rows = []
                for alias, key in self._CAIDAT_ALIAS.items():
                    spec = rs.SETTINGS.get(key)
                    if not spec:
                        continue
                    val = rs.get_effective(db, key)
                    extra = ""
                    if key == "reup.max_duration_sec":
                        extra = " (0 = không cắt)"
                    rows.append(f"<code>{alias}</code> = <b>{html_mod.escape(_fmt(spec, val))}</b>{extra} — {html_mod.escape(spec.title)}")
            self.client.send_message(
                "⚙️ <b>Cài đặt luồng video</b>\n" + "\n".join(rows)
                + "\n\nĐổi: <code>/caidat dodai 0</code> · <code>/caidat caption tat</code>"
            )
            return

        key, spec = _spec(args[0])
        if spec is None:
            self.client.send_message(f"⚠️ Không có ô <code>{html_mod.escape(args[0])}</code>. Gõ /caidat để xem danh sách.")
            return
        if len(args) < 2:
            with SessionLocal() as db:
                val = rs.get_effective(db, key)
            self.client.send_message(f"<code>{html_mod.escape(args[0])}</code> = <b>{html_mod.escape(_fmt(spec, val))}</b> — {html_mod.escape(spec.title)}")
            return

        raw = " ".join(args[1:]).strip()
        if spec.type == "bool":
            low = raw.lower()
            if low in ("bat", "bật", "on", "1", "true", "co", "có"):
                raw = "true"
            elif low in ("tat", "tắt", "off", "0", "false", "khong", "không"):
                raw = "false"
            else:
                self.client.send_message("⚠️ Ô này chỉ nhận bật/tắt.")
                return
        try:
            with SessionLocal() as db:
                rs.upsert_setting(db, key, raw, updated_by="telegram")
                val = rs.get_effective(db, key)
        except (ValueError, TypeError) as exc:
            gioi_han = ""
            if spec.min is not None or spec.max is not None:
                gioi_han = f" (từ {spec.min:g} tới {spec.max:g})"
            self.client.send_message(f"⚠️ Không nhận: {html_mod.escape(str(exc)[:120])}{gioi_han}")
            return
        ghi_chu = " Áp dụng cho video xử lý từ giờ; video đã có thì bấm Xử lý lại." if key == "reup.max_duration_sec" else ""
        self.client.send_message(
            f"✅ <code>{html_mod.escape(args[0])}</code> = <b>{html_mod.escape(_fmt(spec, val))}</b> — {html_mod.escape(spec.title)}.{ghi_chu}"
        )

    def _cmd_dadang(self, args=None):
        """ADR-042 — video đã đăng gần nhất, kèm nút lùi lại khi bấm nhầm."""
        self._liet_ke_material("POSTED", "📌 <b>Đã đăng gần đây</b>", "chuadang", "↩️ Chưa đăng",
                               "📭 Chưa đánh dấu video nào là đã đăng. Bấm ✅ Đã đăng dưới tin video sau khi đăng.")

    def _liet_ke_material(self, status, tieu_de, action, nhan_nut, khi_rong):
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        with SessionLocal() as db:
            rows = feature_hooks.call("viral.list_materials", db, status, 10) or []
        if not rows:
            self.client.send_message(khi_rong)
            return

        self.client.send_message(f"{tieu_de} — {len(rows)} video")
        for m in rows:
            doan = ""
            if m.get("clip_start_sec") or m.get("clip_length_sec"):
                doan = f"\n✂️ từ {self._mmss(m.get('clip_start_sec'))}" + (
                    f", dài {m['clip_length_sec']}s" if m.get("clip_length_sec") else ""
                )
            nut = [{"text": nhan_nut, "callback_data": f"{action}:{m['id']}"}]
            hang2 = []
            if status == "READY":
                nut.append({"text": "✂️ Chọn đoạn", "callback_data": f"khung:{m['id']}"})
                hang2.append({"text": "✅ Đã đăng", "callback_data": f"dadang:{m['id']}"})  # ADR-042
                # ADR-041: chỉ video GỐC mới chia được; phần con không chia tiếp.
                if not m.get("parent_material_id"):
                    hang2.append({"text": "🧩 Chia phần", "callback_data": f"chia:{m['id']}"})
            phan = ""
            if status == "POSTED" and m.get("posted_at"):
                phan += "\n📌 đăng lúc " + self._gio(m["posted_at"])
            if m.get("parent_material_id") and m.get("part_index"):
                phan += f"\n🧩 Phần {m['part_index']}/{m.get('part_total') or '?'} của #{m['parent_material_id']}"
            self.client.send_message(
                f"#{m['id']} · {int(m.get('views') or 0):,} views\n"
                f"📝 {str(m.get('title') or '(không tiêu đề)')[:80]}{phan}{doan}",
                reply_markup={"inline_keyboard": [nut] + ([hang2] if hang2 else [])},
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
            # ADR-037: rỗng vì chưa nối tài khoản chứ không phải hệ thống chết — phải nói rõ,
            # không thì "Pending: 0 | Draft: 0" trông y như hỏng.
            if not (pending or draft or running):
                msg += ("\n\nℹ️ Chưa nối tài khoản Facebook nên không có job nào. "
                        "Video đi đường đăng tay — xem /sansang.")
        self.client.send_message(msg)

    def _cmd_drafts(self, args=None):
        from app.core.database.core import SessionLocal
        from app.core.database.models import Job
        with SessionLocal() as db:
            drafts = db.query(Job).filter(Job.status == JobStatus.DRAFT).all()
            if not drafts:
                self.client.send_message(
                    "📝 Không có bản nháp nào.\n"
                    "ℹ️ Bản nháp chỉ sinh khi có tài khoản Facebook. Chưa nối thì video đi đường "
                    "đăng tay — xem /sansang."
                )
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
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                self.client.send_message(f"❓ Không tìm thấy Job #{job_id}.")
                return
            # `retry_job` chỉ nhận job FAILED và ném ValueError tiếng Anh cho mọi ca khác —
            # kiểm TRƯỚC ở đây để Owner nhận câu tiếng Việt nói rõ vì sao, thay vì
            # "❌ Lỗi: Job is not in FAILED state or does not exist."
            if job.status != JobStatus.FAILED:
                self.client.send_message(
                    f"⚠️ Job #{job_id} đang ở trạng thái <b>{job.status}</b>. "
                    "Chỉ job <b>FAILED</b> mới chạy lại được."
                )
                return
            if not job.resolved_media_path:
                self.client.send_message(
                    f"⚠️ Job #{job_id} đã mất file video — không chạy lại được, phải xử lý lại từ đầu."
                )
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
        # ADR-037: nguồn nào đặt ngưỡng RIÊNG thì code lấy số riêng trước ⇒ lệnh này không đụng
        # tới. Báo "đã cập nhật" mà không nói điều đó là nửa sự thật.
        self.client.send_message(
            f"✅ Đã cập nhật ngưỡng <b>chung</b>: tối thiểu <b>{min_views:,}</b> views, "
            f"tối đa <b>{max_videos}</b> video/kênh.\n"
            "⚠️ Nguồn nào đã đặt ngưỡng riêng thì vẫn dùng số riêng của nó — xem /nguon."
        )

    def _cmd_discovery(self, args=None):
        """
        ADR-033 — trước đây in "Đang quét…" rồi ngay "✅ hoàn tất", hai câu liền nhau, không
        quét gì. Nay gọi hook `viral.force_discovery` thật và chạy nền vì có thể lâu.
        """
        # ADR-037: quét theo `competitor_urls` của TÀI KHOẢN. Không có tài khoản thì nó quét 0
        # kênh và báo "xong" — nói trước để Owner khỏi tưởng hỏng.
        self.client.send_message(
            "⏳ Đang quét Discovery… sẽ báo lại khi xong.\n"
            "ℹ️ Lệnh này quét theo từ khoá của <b>tài khoản Facebook</b>. Chưa nối tài khoản thì "
            "kết quả sẽ là 0 — nguồn tự quét của bạn dùng /nguon."
        )

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
