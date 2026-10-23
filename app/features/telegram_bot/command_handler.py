import logging
import concurrent.futures
import threading
from app.constants import JobStatus

logger = logging.getLogger(__name__)

def send_long_message(client, text: str) -> None:
    chunk = ""
    for block in str(text or "").split("\n\n"):
        nxt = block if not chunk else f"{chunk}\n\n{block}"
        if chunk and len(nxt) > 3500:
            client.send_message(chunk)
            chunk = block
        else:
            chunk = nxt
    if chunk:
        client.send_message(chunk[:4000])


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
            "tainguyen": self._cmd_tainguyen,
            "donrac": self._cmd_donrac,
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
            "han": self._cmd_han,
            "hen": self._cmd_hen,
            "so": self._cmd_so,
            "dadang": self._cmd_dadang,  # ADR-042
            "tai": self._cmd_tai,  # ADR-043
            "caidat": self._cmd_caidat,
        }

    # Menu "/" trong Telegram — MỘT nguồn sự thật với `handler_map` (test canh hai chiều).
    # Thứ tự = thứ Owner dùng hằng ngày trước; luồng Job (cần tài khoản Facebook) xuống cuối.
    MENU: list[tuple[str, str]] = [
        ("sansang", "Video chờ đăng tay: Gửi lại · Chọn đoạn · Chia phần · Đã đăng"),
        ("moi", "Video mới quét về, kèm nút Xử lý"),
        ("nguon", "Nguồn: /nguon · /nguon <id> <min> <max> · /nguon <id> xoa"),
        ("dadang", "Video đã đăng gần nhất (lùi lại nếu bấm nhầm)"),
        ("han", "Còn đăng được bao nhiêu bài: tuần, hôm nay, tháng"),
        ("hen", "/hen <mã> 25/09 20:30 — hẹn hoặc đổi giờ bài đang chờ"),
        ("so", "Chỉ số từng kênh. Bấm tên page để xem bài của page đó"),
        ("tai", "/tai <link> — chỉ tải bản gốc về máy, không xào chẻ"),
        ("caidat", "Xem / đổi cài đặt luồng video ngay tại đây"),
        ("help", "Danh sách lệnh và cách dùng"),
        ("status", "Worker đang chạy hay tạm dừng"),
        ("health", "Sức khoẻ hệ thống"),
        ("tainguyen", "Kiểm tra RAM, CPU, ổ đĩa và tiến trình PM2"),
        ("donrac", "/donrac · /donrac don — kiểm tra hoặc dọn rác ổ đĩa"),
        ("pause", "Tạm dừng worker"),
        ("resume", "Chạy tiếp worker"),
        ("jobs", "Đếm job đang chạy / chờ / nháp (cần tài khoản Facebook)"),
        ("drafts", "Bản nháp chờ duyệt (cần tài khoản Facebook)"),
        ("retry", "/retry <id> — cho một job chạy lại"),
        ("viral", "/viral <min_views> <max_videos> — đổi ngưỡng quét chung"),
        ("discovery", "Quét tìm kênh mới (chạy nền)"),
    ]

    @classmethod
    def menu(cls) -> list[dict]:
        """Danh sách cho ``setMyCommands`` — dựng từ ``MENU``, không chép tay ở chỗ khác."""
        return [{"command": c, "description": d[:256]} for c, d in cls.MENU]

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

    # Nhóm cho /help — cùng nguồn với MENU, chỉ thêm tiêu đề nhóm. Lệnh không nằm nhóm nào
    # sẽ tự rơi vào "Khác" (test canh: không lệnh nào bị bỏ sót).
    HELP_GROUPS: list[tuple[str, tuple[str, ...]]] = [
        ("Luồng video (dùng hằng ngày)", ("sansang", "moi", "nguon", "dadang", "tai", "caidat")),
        ("Hệ thống", ("status", "health", "tainguyen", "donrac", "pause", "resume", "help")),
        ("Luồng Job — cần tài khoản Facebook trong tool", ("jobs", "drafts", "retry", "viral", "discovery")),
    ]

    def _cmd_help(self, args=None):
        """
        ADR-033 — không có lệnh này thì phải mở code mới biết bot làm được gì.

        Sinh từ ``MENU`` (2026-09-11): trước đây /help và menu "/" là hai bản chép tay, lệch
        thứ tự — /help kể luồng Job (Owner có 0 tài khoản) lên đầu, luồng video xuống dưới.
        """
        import html as html_mod

        desc = dict(self.MENU)
        seen: set[str] = set()
        parts = ["🤖 <b>Lệnh dùng được</b>\n━━━━━━━━━━━━━━━━━━"]
        groups = list(self.HELP_GROUPS)
        da_xep = {x for _, cs in groups for x in cs}
        con_lai = tuple(c for c, _ in self.MENU if c not in da_xep)
        if con_lai:
            groups.append(("Khác", con_lai))
        for title, cmds in groups:
            rows = []
            for c in cmds:
                if c not in desc or c in seen:
                    continue
                seen.add(c)
                d = desc[c]
                if "Facebook" in title:
                    d = d.replace(" (cần tài khoản Facebook)", "")  # tiêu đề nhóm đã nói rồi
                d = html_mod.escape(d)
                # Mô tả đã tự ghi cú pháp ("/tai <link> — …") thì không lặp tên lệnh.
                rows.append(d if d.startswith(f"/{c}") else f"/{c} — {d}")
            if rows:
                parts.append(f"\n<b>{html_mod.escape(title)}</b>\n" + "\n".join(rows))
        parts.append("\nHoặc dán thẳng link TikTok/YouTube/Facebook vào đây — tool tự làm video.")
        self.client.send_message("\n".join(parts))

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
    def _page_label(raw) -> str:
        """Id kênh Buffer → tên page. URL page thì lấy đoạn cuối. Trống → chuỗi rỗng."""
        value = str(raw or "").strip()
        if not value:
            return ""
        from app.core import settings as runtime_settings

        for item in runtime_settings.get_json("BUFFER_CHANNELS") or []:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == value:
                return str(item.get("name") or value).strip()
        if value.startswith("http"):
            tail = value.rstrip("/").rsplit("/", 1)[-1]
            return (tail or value)[:40]
        return value[:40]

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
        """Liệt kê nguồn, hoặc đặt / xóa hai số riêng của một nguồn."""
        args = [str(a) for a in (args or [])]
        if args:
            self._dat_nguong_nguon(args)
            return
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
            if s.get("min_views") is None and s.get("max_videos") is None:
                nguong = "mặc định"
            else:
                xem = f"{s['min_views']:,} lượt xem" if s.get("min_views") is not None else "mức xem chung"
                toi_da = f"{s['max_videos']} video" if s.get("max_videos") is not None else "số video chung"
                nguong = f"{xem}, tối đa {toi_da}"
            cho = ""
            if s.get("waiting_count") is not None:
                cho = f"\n⏳ Còn chờ: <b>{int(s['waiting_count'])}</b>"
            self.client.send_message(
                f"📺 <b>@{s['handle']}</b> · {s['platform']} · {trang_thai}\n"
                f"👁 Ngưỡng {nguong}{cho}\n{self._dong_quet(s)}\n"
                f"Đặt riêng: /nguon {s['id']} &lt;mức xem&gt; &lt;số video&gt; · về chung: /nguon {s['id']} xoa",
                reply_markup={"inline_keyboard": [[
                    {"text": "🔍 Quét ngay", "callback_data": f"scan:{s['id']}"},
                    {"text": "⚪ Tắt" if s["enabled"] else "🟢 Bật", "callback_data": f"tgsrc:{s['id']}"},
                ]]},
            )

    def _dat_nguong_nguon(self, args: list[str]):
        """Cùng lệnh /nguon. Sai thì báo và không gọi hook ghi."""
        if len(args) == 2 and args[1].lower() == "xoa":
            try:
                source_id = int(args[0])
            except ValueError:
                self.client.send_message("⚠️ Mã nguồn phải là số nguyên.")
                return
            self._goi_dat_nguong(source_id, None, None)
            return
        if len(args) != 3:
            self.client.send_message(
                "⚠️ Cú pháp: /nguon &lt;mã&gt; &lt;mức xem&gt; &lt;số video&gt; hoặc /nguon &lt;mã&gt; xoa"
            )
            return
        try:
            source_id = int(args[0])
            min_views = int(args[1])
            max_videos = int(args[2])
        except ValueError:
            self.client.send_message("⚠️ Mức xem và số video phải là số nguyên.")
            return
        if min_views < 0:
            self.client.send_message("⚠️ Min views không được âm.")
            return
        if not 1 <= max_videos <= 500:
            self.client.send_message("⚠️ Max video/lần phải trong khoảng 1–500.")
            return
        self._goi_dat_nguong(source_id, min_views, max_videos)

    def _goi_dat_nguong(self, source_id: int, min_views, max_videos):
        from app.core import feature_hooks
        from app.core.database.core import SessionLocal

        with SessionLocal() as db:
            res = feature_hooks.call(
                "viral.set_source_limits", db, source_id, min_views, max_videos,
            ) or {}
        self.client.send_message(res.get("msg") or "Không đặt được ngưỡng.")

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
        "dutru": "viral.source_skip_ready_per_page",  # PLAN-071
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
            hang_dang = []
            if status == "READY":
                page_id = str(m.get("target_page") or "").strip()
                queue_data = f"bq:{m['id']}:{page_id}" if page_id else ""
                page_name = self._page_label(page_id) if page_id else ""
                tools = [
                    {"text": nhan_nut, "callback_data": f"{action}:{m['id']}"},
                    {"text": "Chọn đoạn", "callback_data": f"khung:{m['id']}"},
                ]
                if not m.get("parent_material_id"):
                    tools.append({"text": "Chia phần", "callback_data": f"chia:{m['id']}"})
                if queue_data and len(queue_data.encode()) <= 64:
                    short = (page_name or "page")[:18]
                    hang_dang.append({"text": f"Xếp vào {short}", "callback_data": queue_data})
                    hang2.append({"text": "Đổi page", "callback_data": f"pgask:{m['id']}"})
                else:
                    hang_dang.append({"text": "Chọn page", "callback_data": f"pgask:{m['id']}"})
                hang2.append({"text": "Đã đăng", "callback_data": f"dadang:{m['id']}"})
                nut = tools
            phan = ""
            if status == "POSTED" and m.get("posted_at"):
                phan += "\n📌 đăng lúc " + self._gio(m["posted_at"])
            if m.get("parent_material_id") and m.get("part_index"):
                phan += f"\n🧩 Phần {m['part_index']}/{m.get('part_total') or '?'} của #{m['parent_material_id']}"
            views = int(m.get("views") or 0)
            view_bit = f" · {views:,} views" if views > 0 else ""
            title = str(m.get("title") or "").strip()
            if not title:
                title = str(m.get("ai_caption") or "").strip().split("\n", 1)[0]
            import html

            label = html.escape(title[:80] if title else "(không tiêu đề)")
            page = self._page_label(m.get("target_page")) if status == "READY" else ""
            if status == "READY" and page:
                page_line = f"\n<b>{html.escape(page)}</b>"
            elif status == "READY":
                page_line = "\nChưa chọn page"
            else:
                page_line = ""
            rows = []
            if hang_dang:
                rows.append(hang_dang)
            if hang2:
                rows.append(hang2)
            rows.append(nut)
            self.client.send_message(
                f"<b>#{m['id']}</b>{view_bit}\n{label}{page_line}{phan}{doan}",
                reply_markup={"inline_keyboard": rows},
            )

    def _cmd_han(self, args=None):
        """Hạn đăng Buffer và nút thao tác các bài đang xếp."""
        import app.config as config
        from app.core.notifier.formatting import buffer_post_keyboard
        from app.features.buffer.client import BufferClient, BufferError

        key = (getattr(config, "BUFFER_API_KEY", None) or "").strip()
        if not key:
            self.client.send_message("Chưa có khóa Buffer.")
            return
        try:
            text, posts = BufferClient(key).quota_overview()
        except BufferError as exc:
            self.client.send_message(str(exc)[:300])
            return
        self.client.send_message(text)
        for post in posts:
            self.client.send_message(
                post.get("label") or "Bài đang xếp",
                reply_markup=buffer_post_keyboard(post.get("id") or "", retry=bool(post.get("retry"))),
            )

    def _cmd_hen(self, args=None):
        """Đổi giờ bài đang chờ. Thiếu mã hoặc giờ sai thì không gọi nơi đăng."""
        from app.features.buffer.when import SAMPLE, parse_when

        parts = list(args or [])
        if len(parts) < 3:
            self.client.send_message(f"Giờ không đọc được. Mẫu {SAMPLE}.\n/hen <mã> 25/09 20:30")
            return
        post_id, when_text = parts[0], " ".join(parts[1:])
        ts, err = parse_when(when_text)
        if err or ts is None:
            self.client.send_message(err or f"Giờ không đọc được. Mẫu {SAMPLE}.")
            return
        from app.core.database.core import SessionLocal
        from app.features.buffer.queue_job import reschedule_by_post

        with SessionLocal() as db:
            ok, msg = reschedule_by_post(db, post_id, ts)
        self.client.send_message(("✅ " if ok else "⚠️ ") + msg)

    def _cmd_so(self, args=None):
        """Chỉ số bài đã đăng trong tháng, lấy từ Buffer."""
        import app.config as config
        from app.features.buffer.client import BufferClient, BufferError

        key = (getattr(config, "BUFFER_API_KEY", None) or "").strip()
        if not key:
            self.client.send_message("Chưa có khóa Buffer.")
            return
        try:
            text, channels = BufferClient(key).insights_menu()
        except BufferError as exc:
            self.client.send_message(str(exc)[:300])
            return
        send_long_message(self.client, text)
        rows = [
            [{"text": name[:30], "callback_data": f"bso:{cid}"}]
            for cid, name in channels
            if cid and len(f"bso:{cid}".encode()) <= 64
        ]
        if rows:
            self.client.send_message("Xem riêng một kênh", reply_markup={"inline_keyboard": rows})

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

    def _cmd_tainguyen(self, args=None):
        """Kiểm tra RAM, CPU, ổ đĩa và tiến trình PM2 theo thời gian thực."""
        import json
        import os
        import shutil
        import subprocess
        from pathlib import Path
        import app.config as config
        try:
            import psutil
        except ImportError:
            psutil = None

        # 1. RAM & Swap
        if psutil:
            vm = psutil.virtual_memory()
            ram_total_gb = vm.total / (1024 ** 3)
            ram_used_gb = vm.used / (1024 ** 3)
            ram_free_gb = vm.available / (1024 ** 3)
            ram_pct = vm.percent
            ram_str = f"⚡ RAM: <b>{ram_used_gb:.2f} / {ram_total_gb:.2f} GB</b> ({ram_pct}%)\n   Trống: <b>{ram_free_gb:.2f} GB</b>"

            sw = psutil.swap_memory()
            sw_total_gb = sw.total / (1024 ** 3)
            sw_used_gb = sw.used / (1024 ** 3)
            sw_pct = sw.percent
            swap_str = f"🔄 Swap: <b>{sw_used_gb:.2f} / {sw_total_gb:.2f} GB</b> ({sw_pct}%)"
        else:
            ram_str = "⚡ RAM: Không có psutil"
            swap_str = ""

        # 2. CPU & Load Average
        load1, load5, load15 = os.getloadavg()
        cpu_cores = os.cpu_count() or 1
        cpu_str = f"🖥️ CPU: Load <b>{load1:.2f}</b>, <b>{load5:.2f}</b>, <b>{load15:.2f}</b> ({cpu_cores} cores)"

        # 3. Zombie processes
        zombies = 0
        if psutil:
            try:
                zombies = sum(1 for p in psutil.process_iter(["status"]) if p.info.get("status") == psutil.STATUS_ZOMBIE)
            except Exception:
                pass
        zombie_str = f"🧟 Zombie: <b>{zombies}</b>"

        # 4. Disk breakdown
        storage_root = Path(getattr(config, "STORAGE_DIR", Path(__file__).resolve().parents[3] / "storage"))
        logs_root = Path(getattr(config, "LOGS_DIR", Path(__file__).resolve().parents[3] / "logs"))

        total, used, free = shutil.disk_usage("/")
        disk_total_gb = total / (1024 ** 3)
        disk_used_gb = used / (1024 ** 3)
        disk_free_gb = free / (1024 ** 3)
        disk_pct = (used / total) * 100 if total else 0

        def _dir_size_mb(path: Path) -> float:
            if not path.exists():
                return 0.0
            tot = 0
            try:
                for root, _, files in os.walk(path):
                    for f in files:
                        try:
                            tot += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
            except OSError:
                pass
            return tot / (1024 * 1024)

        media_mb = _dir_size_mb(storage_root / "media")
        profiles_mb = _dir_size_mb(storage_root / "profiles")
        storage_mb = _dir_size_mb(storage_root)
        logs_mb = _dir_size_mb(logs_root)

        disk_summary = (
            f"💽 Ổ đĩa: <b>{disk_used_gb:.1f} / {disk_total_gb:.1f} GB</b> ({disk_pct:.1f}%)\n"
            f"   Còn trống: <b>{disk_free_gb:.1f} GB</b>\n"
            f"   • storage/: <b>{storage_mb:.1f} MB</b> (media: <b>{media_mb:.1f} MB</b>, profiles: <b>{profiles_mb:.1f} MB</b>)\n"
            f"   • logs/: <b>{logs_mb:.1f} MB</b>"
        )

        # 5. PM2 Processes
        pm2_summary = []
        try:
            res = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                raw = res.stdout.strip()
                s_idx = raw.find("[")
                e_idx = raw.rfind("]")
                if s_idx != -1 and e_idx != -1:
                    apps = json.loads(raw[s_idx : e_idx + 1])
                    total_pm2_ram = 0
                    for app in apps:
                        name = app.get("name", "unknown")
                        st = app.get("pm2_env", {}).get("status", "unknown")
                        mem = app.get("monit", {}).get("memory", 0) or 0
                        total_pm2_ram += mem
                        mem_mb = mem / (1024 * 1024)
                        icon = "🟢" if st == "online" else "🔴"
                        pm2_summary.append(f"{icon} {name}: {mem_mb:.1f} MB ({st})")
                    pm2_total_mb = total_pm2_ram / (1024 * 1024)
                    pm2_header = f"🚀 PM2 Daemons ({len(apps)} apps, tổng RAM: <b>{pm2_total_mb:.1f} MB</b>):"
                else:
                    pm2_header = "🚀 PM2: Không đọc được danh sách tiến trình"
            else:
                pm2_header = "🚀 PM2: Không lấy được thông tin"
        except Exception as e:
            pm2_header = f"🚀 PM2: Lỗi kiểm tra ({e})"

        msg_parts = [
            "📊 <b>BÁO CÁO TÀI NGUYÊN HỆ THỐNG</b>",
            "━━━━━━━━━━━━━━━━━━",
            ram_str,
            swap_str,
            cpu_str + f" | {zombie_str}",
            "━━━━━━━━━━━━━━━━━━",
            disk_summary,
            "━━━━━━━━━━━━━━━━━━",
            pm2_header,
        ]
        if pm2_summary:
            msg_parts.append("\n".join(pm2_summary))

        self.client.send_message("\n".join([p for p in msg_parts if p]))

    def _cmd_donrac(self, args=None):
        """Kiểm tra và dọn rác ổ đĩa an toàn, bảo toàn session cookies."""
        args = [str(a).strip().lower() for a in (args or [])]
        from app.features.maintenance.storage_cleanup_service import StorageCleanupService

        if args and args[0] in ("don", "xoa", "now", "chay"):
            self.client.send_message("⏳ Đang tiến hành dọn rác toàn hệ thống…")

            def _run():
                try:
                    res = StorageCleanupService.run_all(retention_days=7)
                    mb = res.reclaimed_bytes / (1024 * 1024)
                    err_msg = f"\n⚠️ Lưu ý: {len(res.errors)} lỗi nhỏ" if res.errors else ""
                    self.client.send_message(
                        f"✅ <b>Dọn rác hoàn tất!</b>\n━━━━━━━━━━━━━━━━━━\n"
                        f"💾 Đã giải phóng: <b>{mb:.1f} MB</b> ({res.reclaimed_bytes:,} bytes){err_msg}\n"
                        f"🛡️ Profile & Cookies: 100% nguyên vẹn an toàn."
                    )
                except Exception as exc:
                    logger.exception("[Telegram] /donrac execution failed")
                    self.client.send_message(f"❌ Dọn rác thất bại: {str(exc)[:150]}")

            threading.Thread(target=_run, name="tg-donrac-exec", daemon=True).start()
            return

        # Audit mode (dry-run)
        try:
            audit = StorageCleanupService.audit()
            reclaim_mb = audit["reclaimable_bytes"] / (1024 * 1024)
            reclaim_bytes = audit["reclaimable_bytes"]
            msg = (
                f"🧹 <b>KIỂM TRA RÁC Ổ ĐĨA</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"💾 Có thể giải phóng: <b>{reclaim_mb:.1f} MB</b> ({reclaim_bytes:,} bytes)\n"
                f"📁 Chi tiết các mục sẽ dọn:\n"
                f"   • Media cache & temp files (&gt; 7 ngày)\n"
                f"   • Chromium GPU / Code / ServiceWorker cache\n"
                f"   • DOM HTML/PNG dump thất bại trong logs/fb/\n"
                f"   • Nén gzip các bản SQL backup cũ\n\n"
                f"🛡️ <b>Cam kết an toàn:</b> Tuyệt đối không xóa Cookies, Session đăng nhập Facebook/Threads.\n\n"
                f"Bấm nút dưới đây hoặc gõ <code>/donrac don</code> để dọn ngay:"
            )
            reply_markup = {
                "inline_keyboard": [[{"text": "🧹 Dọn rác ngay", "callback_data": "donrac:now"}]]
            }
            self.client.send_message(msg, reply_markup=reply_markup)
        except Exception as e:
            logger.exception("[Telegram] /donrac audit failed")
            self.client.send_message(f"❌ Lỗi kiểm tra rác: {str(e)[:150]}")

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
