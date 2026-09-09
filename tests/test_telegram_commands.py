"""
ADR-033 — mọi lệnh Telegram phải làm đúng điều nó nói.

Kiểm 2026-09-09 bằng cách gọi thẳng từng lệnh: `/status` và `/pause` **ném lỗi** (gọi hàm và
hằng số không tồn tại), còn `/retry`, `/discovery`, `/viral` **báo thành công cho việc không
xảy ra**. Không có test nào nên chúng nằm im như thế không ai biết.

Nguyên tắc của file này: **gọi thật**, không đọc mã nguồn. Hai lỗi kia đọc code cũng khó thấy
— chỉ gọi mới lộ.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.database.core as dbcore
from app.core.database.models import Base
from app.features.telegram_bot.command_handler import TelegramCommandHandler

ALL_COMMANDS = ["status", "pause", "resume", "health", "jobs", "drafts", "help", "start"]


class StubClient:
    """Kênh giả: ghi lại tin thay vì gửi đi."""

    def __init__(self):
        self.msgs: list[str] = []
        self.markups: list[dict | None] = []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)
        self.markups.append(reply_markup)

    def answer_callback_query(self, *a, **k):
        pass

    @property
    def text(self) -> str:
        return " ".join(self.msgs)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """
    `settings.get_overrides` có bộ nhớ đệm TOÀN CỤC theo thời gian (`_cache_values`), không
    theo DB. Trong production chỉ có một DB nên không sao, nhưng giữa các test thì giá trị
    test này rò sang test kia — chính nó làm 3 test dưới đỏ khi chạy cả file mà xanh khi chạy
    riêng.
    """
    from app.core import settings as runtime_settings

    runtime_settings._cache_values = {}
    runtime_settings._cache_ts = 0.0
    yield
    runtime_settings._cache_values = {}
    runtime_settings._cache_ts = 0.0


@pytest.fixture
def db_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tg.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(dbcore, "SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def bot(db_factory):
    client = StubClient()
    return TelegramCommandHandler(client), client


# ── không lệnh nào được ra "❌ Lỗi" ──────────────────────────────────────────


@pytest.mark.parametrize("cmd", ALL_COMMANDS)
def test_khong_lenh_nao_nem_loi(bot, cmd):
    """
    `handle_command` bọc try/except và in "❌ Lỗi: …" — nên lệnh gãy KHÔNG làm bot chết,
    nó chỉ im lặng vô dụng. Đó là lý do hai lệnh hỏng nằm im lâu như vậy.
    """
    handler, client = bot

    handler.handle_command(cmd)

    assert client.msgs, f"/{cmd} không trả lời gì"
    assert "❌ Lỗi" not in client.text, f"/{cmd} vẫn ném lỗi: {client.text[:120]}"


def test_lenh_la_thi_bao_khong_ho_tro(bot):
    handler, client = bot

    handler.handle_command("khongcolenhnay")

    assert "không hỗ trợ" in client.text


# ── /status /pause /resume: trạng thái WORKER, không mượn JobStatus ──────────


def test_pause_roi_status_phai_bao_PAUSED(bot, db_factory):
    """
    Hồi quy: `/pause` cũ dùng `JobStatus.PAUSED` — hằng số **không tồn tại**; `/status` cũ gọi
    `WorkerService.get_status` — hàm **không tồn tại**. Trạng thái worker và trạng thái job là
    hai thứ khác nhau; mượn lẫn nhau chính là gốc lỗi.
    """
    handler, client = bot

    handler.handle_command("pause")
    handler.handle_command("status")

    assert "tạm dừng" in client.msgs[0]
    assert "PAUSED" in client.msgs[1]

    from app.core.queue.worker import WorkerService

    with db_factory() as db:
        assert WorkerService.get_or_create_state(db).worker_status == "PAUSED"


def test_resume_dua_ve_RUNNING(bot, db_factory):
    handler, client = bot

    handler.handle_command("pause")
    handler.handle_command("resume")
    handler.handle_command("status")

    assert "RUNNING" in client.msgs[-1]

    from app.core.queue.worker import WorkerService

    with db_factory() as db:
        assert WorkerService.get_or_create_state(db).worker_status == "RUNNING"


# ── /retry: phải gọi thật, không chỉ in chữ ─────────────────────────────────


def test_retry_goi_that_JobService(bot, db_factory, monkeypatch):
    from app.core.database.models import Job
    from app.core.queue.job import JobService

    goi = {"ids": []}
    monkeypatch.setattr(JobService, "retry_job", staticmethod(lambda db, job_id: goi["ids"].append(job_id)))

    with db_factory() as db:
        job = Job(status="FAILED", caption="x")
        db.add(job)
        db.commit()
        jid = job.id

    handler, client = bot
    handler.handle_command("retry", [str(jid)])

    assert goi["ids"] == [jid], "phải gọi JobService.retry_job, không chỉ in chữ"
    assert "chạy lại" in client.text


def test_retry_job_khong_ton_tai_thi_bao_ro(bot):
    handler, client = bot

    handler.handle_command("retry", ["9999"])

    assert "Không tìm thấy" in client.text


@pytest.mark.parametrize("arg", ["abc", "12x"])
def test_retry_id_khong_phai_so_thi_nhac_cu_phap(bot, arg):
    handler, client = bot

    handler.handle_command("retry", [arg])

    assert "phải là số" in client.text


def test_retry_thieu_id_thi_nhac(bot):
    handler, client = bot

    handler.handle_command("retry")

    assert "Thiếu ID" in client.text


# ── /viral: phải ghi vào chỗ nguồn MỚI thật sự đọc ──────────────────────────


def test_viral_ghi_ca_RuntimeSetting_lan_WorkerState(bot, db_factory):
    """
    Hồi quy: bản cũ chỉ ghi `WorkerState`, mà nguồn ADR-019 (thứ Owner đang dùng) đọc
    `viral.min_views` từ **RuntimeSetting**. Nên nó báo "✅ Đã cập nhật" cho một việc không
    tác dụng gì với nguồn đang chạy.
    """
    from app.core import settings as runtime_settings
    from app.core.queue.worker import WorkerService

    handler, client = bot
    handler.handle_command("viral", ["5000", "30"])

    with db_factory() as db:
        assert int(runtime_settings.get_int("viral.min_views", 0, db=db)) == 5000
        assert int(runtime_settings.get_int("viral.max_videos_per_channel", 0, db=db)) == 30
        state = WorkerService.get_or_create_state(db)
        assert state.viral_min_views == 5000
        assert state.viral_max_videos_per_channel == 30

    assert "5,000" in client.text


@pytest.mark.parametrize("args", [None, ["5000"], ["abc", "def"]])
def test_viral_tham_so_sai_thi_nhac_khong_ghi(bot, db_factory, args):
    """
    Kiểm bằng DÒNG trong bảng `runtime_settings`, không bằng `get_int`: `upsert_setting` còn
    gọi `_push_config_value` đẩy giá trị vào cấu hình TIẾN TRÌNH (cố ý, để tiến trình đang
    chạy nhận ngay). Nên `get_int` vẫn thấy giá trị test trước để lại dù DB này hoàn toàn mới
    — đo `get_int` là đo nhầm thứ.
    """
    from app.core.database.models import RuntimeSetting

    handler, client = bot
    handler.handle_command("viral", args)

    assert "⚠️" in client.text
    with db_factory() as db:
        assert db.query(RuntimeSetting).filter(RuntimeSetting.key == "viral.min_views").first() is None


# ── /discovery: phải gọi hook thật ──────────────────────────────────────────


def test_discovery_goi_hook_that_va_bao_so_kenh(bot, monkeypatch):
    """Hồi quy: bản cũ in "Đang quét…" rồi ngay "✅ hoàn tất", hai câu liền nhau."""
    from app.core import feature_hooks

    monkeypatch.setattr(feature_hooks, "call", lambda name, db: ([], ["ca", "muc"], 7))

    handler, client = bot
    handler.handle_command("discovery")

    # chạy nền — chờ luồng xong
    import threading
    import time

    for _ in range(50):
        if len(client.msgs) >= 2:
            break
        time.sleep(0.05)
    for t in threading.enumerate():
        if t.name == "tg-discovery":
            t.join(timeout=5)

    assert "Đang quét" in client.msgs[0]
    assert "7" in client.msgs[-1] and "kênh mới" in client.msgs[-1]


def test_discovery_hook_no_thi_bao_loi_khong_bao_hoan_tat(bot, monkeypatch):
    from app.core import feature_hooks

    def boom(name, db):
        raise RuntimeError("scraper chết")

    monkeypatch.setattr(feature_hooks, "call", boom)

    handler, client = bot
    handler.handle_command("discovery")

    import threading
    import time

    for _ in range(50):
        if len(client.msgs) >= 2:
            break
        time.sleep(0.05)
    for t in threading.enumerate():
        if t.name == "tg-discovery":
            t.join(timeout=5)

    assert "❌" in client.msgs[-1] and "scraper chết" in client.msgs[-1]
    assert "hoàn tất" not in client.msgs[-1], "không được báo xong khi đã hỏng"


# ── /help liệt kê đúng những lệnh có thật ───────────────────────────────────


def test_help_liet_ke_dung_lenh_dang_chay(bot):
    handler, client = bot

    handler.handle_command("help")

    for cmd in ("/status", "/pause", "/resume", "/health", "/jobs", "/drafts", "/retry", "/discovery", "/viral"):
        assert cmd in client.text, f"{cmd} thiếu trong /help"


def test_help_khong_quang_cao_lenh_khong_ton_tai(bot):
    """Liệt kê một lệnh không có trong bảng điều phối cũng là một kiểu nói dối."""
    handler, client = bot
    handler.handle_command("help")

    import re

    listed = set(re.findall(r"(?:^|\s)/([a-z]+)", client.text))
    supported = {"status", "pause", "resume", "health", "jobs", "drafts", "retry", "discovery", "viral", "help", "start"}

    assert listed <= supported, f"/help nhắc tới lệnh không có: {listed - supported}"


# ── /drafts giữ nút Duyệt/Huỷ ───────────────────────────────────────────────


def test_drafts_co_nut_duyet_va_huy(bot, db_factory):
    from app.constants import JobStatus
    from app.core.database.models import Job

    with db_factory() as db:
        db.add(Job(status=JobStatus.DRAFT, caption="Cá to lắm anh em"))
        db.commit()

    handler, client = bot
    handler.handle_command("drafts")

    markup = next(m for m in client.markups if m)
    data = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert any(d.startswith("approve:") for d in data)
    assert any(d.startswith("cancel:") for d in data)


# ── thông báo không được quảng cáo lệnh không tồn tại (ADR-033, vá 2026-09-09) ──


SUPPORTED_COMMANDS = {
    "status", "pause", "resume", "health", "jobs", "drafts",
    "retry", "viral", "discovery", "help", "start",
}


def test_thong_bao_khong_nhac_toi_lenh_khong_ton_tai():
    """
    Owner nhận tin *"Đổi ngưỡng: … hoặc /viral_settings"*, gõ vào thì bot trả
    "❓ Lệnh /viral_settings không hỗ trợ". Quảng cáo lệnh không có cũng là nhãn nói dối —
    tệ hơn lệnh hỏng, vì nó chủ động bảo người dùng làm một việc bất khả thi.
    """
    import pathlib
    import re

    from app.core.notifier import formatting, service
    from app.features.system_panel.workers import maintenance

    bad: list[str] = []
    for mod in (maintenance, formatting, service):
        code = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # ghi chú được phép nhắc tên lệnh cũ để giải thích
            for cmd in re.findall(r"[\s\"'>(]/([a-z_]{3,})", line):
                if cmd not in SUPPORTED_COMMANDS and not cmd.startswith(("app", "code", "chat", "b")):
                    bad.append(f"{mod.__name__}: /{cmd}")

    assert not bad, f"thông báo nhắc lệnh không tồn tại: {bad}"


def test_khong_quet_kenh_nao_thi_khong_nhan_gi(monkeypatch):
    """
    Owner có 0 account ⇒ đường quét cũ luôn "Quét 0 kênh đối thủ" ⇒ trước đây nhắn mỗi giờ
    một tin vô nghĩa. Tin rác làm người ta bỏ qua cả những tin thật.
    """
    from app.core import feature_hooks
    from app.core.notifier.service import NotifierService
    from app.features.system_panel.workers import maintenance

    sent: list[str] = []
    monkeypatch.setattr(NotifierService, "_broadcast", staticmethod(lambda msg, *a, **k: sent.append(msg)))
    monkeypatch.setattr(maintenance, "_last_tiktok_scrape_ts", 0)
    monkeypatch.setattr(feature_hooks, "call", lambda name, db, *a: (0, 0) if name == "viral.tiktok_scan" else 16800)

    maintenance._scrape_tiktok_competitors(db=None)

    assert sent == [], f"không quét kênh nào mà vẫn nhắn: {sent}"


def test_co_quet_ma_khong_ra_video_thi_van_bao_kem_cu_phap_dung(monkeypatch):
    from app.core import feature_hooks
    from app.core.notifier.service import NotifierService
    from app.features.system_panel.workers import maintenance

    sent: list[str] = []
    monkeypatch.setattr(NotifierService, "_broadcast", staticmethod(lambda msg, *a, **k: sent.append(msg)))
    monkeypatch.setattr(maintenance, "_last_tiktok_scrape_ts", 0)
    monkeypatch.setattr(feature_hooks, "call", lambda name, db, *a: (0, 3) if name == "viral.tiktok_scan" else 16800)

    maintenance._scrape_tiktok_competitors(db=None)

    assert len(sent) == 1
    assert "/viral 16800 50" in sent[0], "phải chỉ đúng cú pháp lệnh thật"
    assert "/viral_settings" not in sent[0]
