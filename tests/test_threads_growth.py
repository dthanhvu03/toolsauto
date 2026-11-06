"""Unit tests cho Threads Growth Agent (A/B testing, phân loại bot, storage, runner, hạn mức).

Không gọi AI thật: ``AIUseCases.generate_text_async`` bị thay bằng hàm giả (fixture autouse).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.features.threads.adapter import ThreadsSessionInvalidError
from app.features.threads.growth import actions, browser, cli, content, evaluator, worker
from app.features.threads.growth.config import ABVariant, GrowthLimits, TargetBot, WorkerConfig, load_profiles
from app.features.threads.growth.evaluator import GrowthEvaluator
from app.features.threads.growth.runner import GrowthRunner
from app.features.threads.growth.scanner import ScannedPost, ThreadsScanner, is_vietnamese
from app.features.threads.growth.storage import GrowthStorage

LIMITS = GrowthLimits(
    max_replies_per_hour=2, max_replies_per_day=3, min_delay_sec=180, max_delay_sec=420, min_relevance=40
)


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    """AI giả: trả câu theo biến thể có trong prompt; ``calls`` ghi lại từng lần gọi."""
    calls = []

    async def _gen(prompt, *, purpose="generic"):
        calls.append(purpose)
        tag = "A" if "Góc độ A" in prompt else "B"
        return f"Câu trả lời AI cho biến thể {tag} nè", {"provider": "fake", "model": "m"}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(_gen))
    return calls


@pytest.fixture
def storage(tmp_path):
    return GrowthStorage(db_path=tmp_path / "growth.sqlite")


@pytest.fixture
def runner(storage):
    return GrowthRunner(storage=storage, limits=lambda: LIMITS)


def _save(storage, tid, bot=TargetBot.CASHBOT, variant=ABVariant.VARIANT_A, author=None):
    return storage.save_post(
        thread_id=tid, post_url="u", author=author or f"a_{tid}", content="Mã shopee",
        target_bot=bot, variant=variant, suggested_reply="r",
    )


def test_classify_target_bot():
    assert GrowthEvaluator.classify_target_bot("Có ai có mã giảm giá Shopee 50k không?") == TargetBot.CASHBOT
    assert GrowthEvaluator.classify_target_bot("Đợt này săn sale mua sắm tốn kém quá") == TargetBot.CASHBOT
    assert GrowthEvaluator.classify_target_bot("Cần mua tài khoản ChatGPT Plus giá rẻ") == TargetBot.AI_STORE
    assert GrowthEvaluator.classify_target_bot("Có bên nào bán Canva Pro vĩnh viễn uy tín ko") == TargetBot.AI_STORE
    assert GrowthEvaluator.classify_target_bot("Hôm nay trời đẹp đi dạo phố") is None
    # "tài khoản ngân hàng" không còn bị coi là tín hiệu AI Store
    assert GrowthEvaluator.classify_target_bot("Chuyển khoản vào tài khoản ngân hàng bị lỗi") is None
    # Ngang nhau → mơ hồ, không gán bot
    assert GrowthEvaluator.classify_target_bot("shopee hay chatgpt") is None


def test_relevance_calculation():
    high = GrowthEvaluator.calculate_relevance("săn sale shopee mã giảm giá shopee hoàn tiền", TargetBot.CASHBOT)
    low = GrowthEvaluator.calculate_relevance("ngắn", TargetBot.CASHBOT)
    assert high > low
    assert 0 <= low <= high <= 99
    # Bài không có tín hiệu nào của bot rơi dưới ngưỡng mặc định 40 → ngưỡng thật sự có tác dụng
    assert GrowthEvaluator.calculate_relevance("hôm nay trời đẹp quá đi", TargetBot.CASHBOT) < LIMITS.min_relevance


def test_scanner_thread_id():
    assert ThreadsScanner.generate_thread_id("user1", "nội dung") == ThreadsScanner.generate_thread_id("user1", "nội dung")
    assert ThreadsScanner.generate_thread_id("user1", "nội dung") != ThreadsScanner.generate_thread_id("user2", "khác")


def test_storage_crud_and_ab_stats(storage):
    assert not storage.is_thread_scanned("th_01")
    pid = _save(storage, "th_01")
    assert pid > 0
    assert storage.is_thread_scanned("th_01")
    assert _save(storage, "th_01") == 0  # trùng

    pending = storage.get_pending_posts()
    assert [p["id"] for p in pending] == [pid]

    assert storage.update_status(pid, "approved", actual_reply="Duyệt reply")
    post = storage.get_post_by_id(pid)
    assert post["status"] == "approved"
    assert post["actual_reply"] == "Duyệt reply"
    assert storage.get_ab_stats()["cashbot"]["A"]["approved"] == 1


def test_update_status_missing_and_keeps_error(storage):
    assert storage.update_status(999, "rejected") is False
    pid = _save(storage, "th_01")
    storage.update_status(pid, "failed", error_message="timeout")
    storage.update_status(pid, "approved")
    assert storage.get_post_by_id(pid)["error_message"] == "timeout"


def test_reply_uses_ai_with_purpose(runner, fake_ai):
    pid = asyncio.run(runner.ingest_scanned_post(ScannedPost("t1", "u", "a", "Săn sale Shopee nhận mã giảm giá", "k")))
    post = runner.storage.get_post_by_id(pid)
    assert post["suggested_reply"].startswith("Câu trả lời AI")
    assert post["ai_analysis"].startswith("AI [")
    assert fake_ai == ["threads_reply"]


def test_ai_failure_falls_back_with_reason(runner, monkeypatch):
    async def _empty(prompt, *, purpose="generic"):
        return None, {"primary_fail_reason": "router_disabled"}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(_empty))
    pid = asyncio.run(runner.ingest_scanned_post(ScannedPost("t1", "u", "a", "Săn sale Shopee nhận mã giảm giá", "k")))
    post = runner.storage.get_post_by_id(pid)
    assert "router_disabled" in post["ai_analysis"]
    assert post["suggested_reply"] == GrowthEvaluator.get_fallback_reply(TargetBot.CASHBOT, ABVariant(post["variant"]))


def test_low_relevance_skipped(storage):
    strict = GrowthRunner(storage=storage, limits=lambda: GrowthLimits(min_relevance=99))
    assert asyncio.run(strict.ingest_scanned_post(ScannedPost("t1", "u", "a", "voucher shopee", "k"))) is None


def test_ab_split_persists_across_runs(storage):
    texts = ["Săn sale Shopee nhận mã giảm giá", "Áp mã voucher Shopee đơn 500k",
             "Mã giảm giá Shopee cho đơn 300k", "Săn voucher Shopee lương về"]
    variants = []
    for i, text in enumerate(texts):
        fresh = GrowthRunner(storage=storage, limits=lambda: LIMITS)  # mỗi lần = một lần chạy CLI mới
        pid = asyncio.run(fresh.ingest_scanned_post(ScannedPost(f"t{i}", "u", "a", text, "k")))
        variants.append(storage.get_post_by_id(pid)["variant"])
    assert variants == ["A", "B", "A", "B"]


def test_batch_alternates_per_bot(runner):
    posts = [
        ScannedPost("t1", "u1", "a1", "Săn sale Shopee nhận mã giảm giá", "kw1"),
        ScannedPost("t2", "u2", "a2", "Áp mã voucher Shopee đơn 500k", "kw1"),
        ScannedPost("t3", "u3", "a3", "Cần mua tài khoản ChatGPT Plus", "kw2"),
        ScannedPost("t4", "u4", "a4", "Bán Canva Pro bản quyền uy tín", "kw2"),
    ]
    pids = asyncio.run(runner.ingest_batch(posts))
    assert len(pids) == 4
    rows = [runner.storage.get_post_by_id(p) for p in pids]
    assert [r["target_bot"] for r in rows] == ["cashbot", "cashbot", "ai_store", "ai_store"]
    assert {rows[0]["variant"], rows[1]["variant"]} == {"A", "B"}
    assert {rows[2]["variant"], rows[3]["variant"]} == {"A", "B"}


def test_switch_regenerates_with_ai(runner):
    pid = asyncio.run(runner.ingest_scanned_post(ScannedPost("t1", "u", "a", "Săn sale Shopee nhận mã giảm giá", "k")))
    post = asyncio.run(runner.switch_variant(pid, ABVariant.VARIANT_B))
    assert post["variant"] == "B"
    assert post["suggested_reply"] == "Câu trả lời AI cho biến thể B nè"
    assert asyncio.run(runner.switch_variant(999, ABVariant.VARIANT_A)) is None


def test_posting_quota(runner, storage):
    now = datetime.now(timezone.utc)
    assert runner.posting_quota(now).allowed

    p1 = _save(storage, "t1")
    runner.mark_posted(p1)
    q = runner.posting_quota(now + timedelta(seconds=60))
    assert not q.allowed and "tối thiểu" in q.reason and q.wait_sec >= 100

    assert runner.posting_quota(now + timedelta(seconds=200)).allowed

    p2 = _save(storage, "t2")
    runner.mark_posted(p2)
    q = runner.posting_quota(now + timedelta(seconds=400))
    assert not q.allowed and "/ giờ" in q.reason  # 2/giờ

    p3 = _save(storage, "t3")
    runner.mark_posted(p3)
    q = runner.posting_quota(now + timedelta(hours=2))
    assert not q.allowed and "24 giờ" in q.reason  # 3/ngày
    assert runner.posting_quota(now + timedelta(days=2)).allowed

    assert LIMITS.min_delay_sec <= runner.next_delay_sec() <= LIMITS.max_delay_sec


def test_cli_scan_refuses_and_demo_uses_separate_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["cli", "scan"])
    assert cli.main() == 2
    assert "Chưa có quét" in capsys.readouterr().out

    demo_db = tmp_path / "demo.sqlite"
    monkeypatch.setattr(cli, "DEMO_DB_PATH", demo_db)
    monkeypatch.setattr("sys.argv", ["cli", "demo"])
    assert cli.main() == 0
    assert len(GrowthStorage(db_path=demo_db).get_pending_posts()) == 4

    monkeypatch.setattr("sys.argv", ["cli", "--db", str(demo_db), "approve", "999"])
    assert cli.main() == 1


# ── PLAN-158: quét thật + tự đăng ────────────────────────────────────────────

NOW = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
VI_SHOPEE = "Có ai biết chỗ nào săn mã giảm giá Shopee cho đơn 300k không, áp mã toàn hết lượt"


def _node(code, user, text, taken_at, **info):
    """Dạng nút bài trong JSON trang tìm kiếm Threads (rút gọn từ probe 06/11)."""
    return {
        "code": code, "pk": "1", "taken_at": taken_at, "detected_language": None,
        "user": {"username": user}, "caption": {"text": text},
        "text_post_app_info": {"is_reply": False, "can_reply": True, "has_viewer_replied": False, **info},
    }


def test_posts_from_payload_reads_search_json():
    payload = {"data": {"searchResults": {"edges": [
        {"node": {"thread": {"thread_items": [{"post": _node("AbC1", "lan", VI_SHOPEE, 1793952000)}]}}},
        {"node": {"thread": {"thread_items": [{"post": _node("R2", "b", "trả lời", 1793952000, is_reply=True)}]}}},
        {"node": {"thread": {"thread_items": [{"post": _node("L3", "c", "khoá", 1793952000, can_reply=False)}]}}},
        {"node": {"thread": {"thread_items": [{"post": _node("D4", "d", "rồi", 1793952000, has_viewer_replied=True)}]}}},
    ]}}}
    posts = {p.thread_id: p for p in browser.posts_from_payload(payload, "kw")}
    assert set(posts) == {"AbC1", "R2"}  # khoá reply / đã reply → bỏ
    p = posts["AbC1"]
    assert p.post_url == "https://www.threads.com/@lan/post/AbC1"
    assert p.created_at == datetime.fromtimestamp(1793952000, tz=timezone.utc)
    assert not p.is_reply and posts["R2"].is_reply


def test_posts_from_dom_rows_fallback():
    rows = [
        {"href": "/@lan/post/X1", "datetime": "2026-11-06T07:00:00.000Z", "text": f"lan\n2h\n{VI_SHOPEE}"},
        {"href": "/@b/post/X2", "datetime": "", "text": "b\nReplying to @lan\nĐồng ý luôn bạn ơi"},
        {"href": "/@c/media", "datetime": "", "text": "c\nkhông phải bài"},
    ]
    posts = browser.posts_from_dom_rows(rows, "kw")
    assert [p.thread_id for p in posts] == ["X1", "X2"]
    assert posts[0].content == VI_SHOPEE and not posts[0].is_reply
    assert posts[1].is_reply and posts[1].content == "Đồng ý luôn bạn ơi"


def test_is_vietnamese():
    assert is_vietnamese(VI_SHOPEE)
    assert not is_vietnamese("Klaim Voucher 100% milikmu di sini! shopee gratis ongkir")
    assert not is_vietnamese("Happy birthday to meee")
    # Tiếng Bồ / Pháp có «é á ô ã» nhưng không có chữ riêng tiếng Việt.
    assert not is_vietnamese("O Claude é TÃO MELHOR assim do que o ChatGPT? Pergunta genuína.. eu nunca usei.")
    assert not is_vietnamese("Claude se branche maintenant sur vos comptes bancaires, réservée aux abonnés américains")
    assert is_vietnamese("Bên nào thu chatgpt plus giá tốt không")
    assert is_vietnamese("cần tìm canva pro vĩnh viễn")


def test_load_profiles_reads_web_settings(monkeypatch):
    from app.features.threads.growth import config as gconf

    over = {"growth.keywords_cashbot": " Mã Shopee ,mã shopee,\nhoàn tiền ", "growth.cashbot_a_hook": "Câu mới"}
    monkeypatch.setattr(gconf, "_setting", lambda k: over.get(k, gconf.settings.SETTINGS[k].default_getter()))
    prof = gconf.load_profiles()[TargetBot.CASHBOT]
    assert prof.keywords == ["mã shopee", "hoàn tiền"]
    assert prof.variants[ABVariant.VARIANT_A].sample_hook == "Câu mới"
    assert prof.variants[ABVariant.VARIANT_B].tracking_url == "https://t.me/zt_shopee_bot?start=threads_cb_tier"


def test_auto_approve_threshold(runner, monkeypatch):
    pid = asyncio.run(runner.ingest_scanned_post(ScannedPost("t1", "u", "a", VI_SHOPEE, "k"), auto_post_min=50))
    row = runner.storage.get_post_by_id(pid)
    assert row["status"] == "approved" and row["auto_approved"] == 1 and row["actual_reply"]

    pid = asyncio.run(runner.ingest_scanned_post(ScannedPost("t2", "u2", "b", VI_SHOPEE, "k"), auto_post_min=100))
    assert runner.storage.get_post_by_id(pid)["status"] == "pending"

    async def _empty(prompt, *, purpose="generic"):
        return None, {}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(_empty))
    pid = asyncio.run(runner.ingest_scanned_post(ScannedPost("t3", "u3", "c", VI_SHOPEE, "k"), auto_post_min=0))
    assert runner.storage.get_post_by_id(pid)["status"] == "pending"  # câu mẫu không tự đăng


class FakeBrowser:
    def __init__(self, results=None, reply_error=None, invalid=False):
        self.results = results or {}
        self.reply_error = reply_error
        self.invalid = invalid
        self.replies = []
        self.opened = 0

    def __call__(self, profile_path):
        self.opened += 1
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def search_recent(self, keyword, limit=10, top=False):
        """Kết quả tab «Hàng đầu» khai ở khoá ``(keyword, "top")``; mặc định tab «Mới nhất»."""
        if self.invalid:
            raise ThreadsSessionInvalidError("checkpoint")
        return list(self.results.get((keyword, "top") if top else keyword, []))[:limit]

    comments: dict = {}
    posts_made: list = []

    def create_post(self, text):
        self.posts_made.append(text)
        return "https://www.threads.com/@us28qt/post/OWN1"

    def replies_to_me(self, reply_url):
        return list(self.comments.get(reply_url, []))

    def reply(self, url, text):
        if self.reply_error:
            raise RuntimeError(self.reply_error)
        self.replies.append((url, text))
        return url + "/reply"


class FakeNotify:
    def __init__(self):
        self.sent, self.pending = [], []

    def send(self, text, buttons=None):
        self.sent.append(text)
        return True

    def notify_pending(self, post):
        self.pending.append(post["id"])
        return True

    cycle_text = staticmethod(lambda r: f"cycle {r}")
    checkpoint_text = staticmethod(lambda r: f"checkpoint {r}")


def _post(code, author, text=VI_SHOPEE, age_h=1, is_reply=False):
    return ScannedPost(code, f"https://www.threads.com/@{author}/post/{code}", author, text, "kw",
                       NOW - timedelta(hours=age_h), is_reply)


@pytest.fixture
def make_worker(runner, monkeypatch):
    cfg = {"value": WorkerConfig(enabled=True, auto_post_min_relevance=60, posts_per_keyword=10)}
    monkeypatch.setattr(worker, "load_worker_config", lambda: cfg["value"])
    profiles = load_profiles()
    for p in profiles.values():
        p.keywords.clear()
    profiles[TargetBot.CASHBOT].keywords.append("kw")
    monkeypatch.setattr(worker, "load_profiles", lambda: profiles)
    monkeypatch.setattr(worker.GrowthWorker, "_profile_path", lambda self: "/profile")
    monkeypatch.setattr(worker.conversions, "report", lambda: {"total": 1, "last_24h": 1, "active": 0})
    # Bài riêng: mặc định không có deal / dịp sale (không đọc DB Cashbot thật); test riêng tự đặt.
    monkeypatch.setattr(content, "load_deals", lambda now, path=None: [])
    monkeypatch.setattr(content, "next_sale", lambda now, days=4: None)
    disabled = []
    monkeypatch.setattr(worker.settings, "upsert_setting", lambda db, k, v, updated_by=None: disabled.append((k, v)))
    monkeypatch.setattr(worker.growth_session, "mark", lambda db, ok, err=None: disabled.append(("mark", ok)))

    class _DB:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    def make(fake_browser):
        n = FakeNotify()
        w = worker.GrowthWorker(runner=runner, browser_factory=fake_browser, db_factory=_DB,
                                notifier=n, sleep=lambda s: None, now=lambda: NOW)
        return w, n

    make.cfg, make.disabled = cfg, disabled
    return make


def test_worker_cycle_filters_ingests_and_posts(make_worker, runner):
    posts = [
        _post("P1", "lan"),                                        # tự đăng
        _post("P2", "mai", text="Ai có mã shopee không ạ cho mình xin với"),  # điểm thấp hơn → chờ duyệt
        _post("OLD", "cu", age_h=100),                             # quá 48h
        _post("RE", "re", is_reply=True),                          # là reply
        _post("ID", "indo", text="Klaim voucher shopee gratis ongkir kak"),  # không phải tiếng Việt
    ]
    fb = FakeBrowser({"kw": posts})
    w, n = make_worker(fb)
    make_worker.cfg["value"] = WorkerConfig(enabled=True, auto_post_min_relevance=95, posts_per_keyword=10)
    # P1 điểm cao hơn P2: thêm từ khóa của bot vào P1
    posts[0].content = VI_SHOPEE + " — săn sale shopee, voucher shopee, áp mã shopee"
    report = w.tick()
    assert report.scanned == 5 and report.ingested == 2
    assert report.auto == 1 and report.pending == 1
    assert report.posted == 1 and fb.replies[0][0].endswith("/P1")
    p1 = runner.storage.get_post_by_id(1)
    assert p1["status"] == "posted" and p1["reply_url"].endswith("/P1/reply")
    assert n.pending == []  # mặc định tự động hoàn toàn: không hỏi duyệt trên Telegram
    assert any(s.startswith("cycle") for s in n.sent)


def test_worker_telegram_review_sends_pending(make_worker, runner):
    w, n = make_worker(FakeBrowser({"kw": [_post("P2", "mai", text="Ai có mã shopee không ạ cho mình xin với")]}))
    make_worker.cfg["value"] = WorkerConfig(enabled=True, auto_post_min_relevance=95, telegram_review=True)
    report = w.tick()
    assert report.pending == 1 and n.pending == [1]
    assert runner.storage.unnotified_pending() == []


def test_cycle_text_lists_posted_replies():
    from app.features.threads.growth import notify

    text = notify.cycle_text({"posted": 1, "scanned": 9, "ingested": 2, "posted_items": [
        {"id": 1, "bot": "cashbot", "variant": "A", "author": "lan", "post_url": "https://p",
         "reply_url": "https://r", "text": "ủa b <thử>"}]})
    assert "đã reply 1 bài" in text and 'href="https://r"' in text and "&lt;thử&gt;" in text


def test_worker_disabled_does_nothing(make_worker):
    fb = FakeBrowser({"kw": [_post("P1", "lan")]})
    w, _ = make_worker(fb)
    make_worker.cfg["value"] = WorkerConfig(enabled=False)
    assert w.tick() is None and fb.opened == 0


def test_worker_author_cooldown(make_worker, runner):
    pid = _save(runner.storage, "OLD1")
    runner.storage.update_status(pid, "posted")
    runner.storage.switch_variant(pid, ABVariant.VARIANT_A, "r")
    with runner.storage._connection() as c:
        c.execute("UPDATE growth_posts SET author='lan', posted_at=? WHERE id=?", ((NOW - timedelta(days=2)).isoformat(), pid))
    w, _ = make_worker(FakeBrowser({"kw": [_post("P1", "LAN")]}))
    assert w.tick().ingested == 0


def test_worker_stops_at_quota_and_marks_failures(make_worker, runner):
    for i in range(3):
        _save(runner.storage, f"Q{i}")
        runner.approve_and_prepare(i + 1)
    fb = FakeBrowser(reply_error="Không thấy nút Trả lời")
    w, _ = make_worker(fb)
    report = w.tick()
    assert report.failed == 3 and runner.storage.get_post_by_id(1)["status"] == "failed"

    # Hết hạn mức giờ (LIMITS: 2/giờ) → chỉ đăng 2, bài thứ 3 nằm lại approved.
    for i in range(3, 6):
        _save(runner.storage, f"Q{i}")
        runner.approve_and_prepare(i + 1)
    runner_ok = FakeBrowser()
    w2, _ = make_worker(runner_ok)
    w2.now = lambda: datetime.now(timezone.utc)
    w2.runner._limits = lambda: GrowthLimits(max_replies_per_hour=2, max_replies_per_day=10, min_delay_sec=0, max_delay_sec=0)
    report = w2.tick()
    assert report.posted == 2 and "/ giờ" in report.quota_note
    assert len(runner.storage.approved_queue()) == 1


def test_worker_dead_browser_keeps_queue(make_worker, runner):
    """Chromium bị diệt giữa vòng → dừng, KHÔNG đánh «lỗi» cả hàng chờ (06/11: 11 bài bị đánh lỗi oan)."""
    for i in range(3):
        _save(runner.storage, f"D{i}")
        runner.approve_and_prepare(i + 1)
    fb = FakeBrowser(reply_error="Page.goto: Target page, context or browser has been closed")
    w, _ = make_worker(fb)
    report = w.tick()
    assert report.failed == 0 and report.errors
    assert len(runner.storage.approved_queue()) == 3


def test_worker_dead_browser_stops_scan(make_worker, runner):
    class DeadSearch(FakeBrowser):
        calls = 0

        def search_recent(self, keyword, limit=10, top=False):
            DeadSearch.calls += 1
            raise RuntimeError("Page.goto: Target page, context or browser has been closed")

    profiles = worker.load_profiles()
    profiles[TargetBot.CASHBOT].keywords.extend(["kw2", "kw3"])
    w, _ = make_worker(DeadSearch())
    report = w.tick()
    assert DeadSearch.calls == 1 and len(report.errors) == 1


def test_worker_one_post_per_author_per_scan(make_worker, runner):
    w, _ = make_worker(FakeBrowser({"kw": [_post("A1", "shop"), _post("A2", "SHOP"), _post("A3", "khac")]}))
    assert w.tick().ingested == 2


def test_worker_skips_queued_duplicate_author(make_worker, runner):
    for i in range(3):
        _save(runner.storage, f"S{i}", author="pisharevn" if i < 2 else "lan")
        runner.approve_and_prepare(i + 1)
    fb = FakeBrowser()
    w, _ = make_worker(fb)
    w.now = lambda: datetime.now(timezone.utc)
    w.runner._limits = lambda: GrowthLimits(max_replies_per_hour=9, max_replies_per_day=9, min_delay_sec=0, max_delay_sec=0)
    report = w.tick()
    assert report.posted == 2 and len(fb.replies) == 2
    dup = runner.storage.get_post_by_id(2)
    assert dup["status"] == "rejected" and "trùng tác giả" in dup["error_message"]


def test_reach_score_and_payload_engagement():
    from app.features.threads.growth.browser import posts_from_payload
    from app.features.threads.growth.scanner import reach_score

    assert reach_score(0, 0, 0) == 0
    assert reach_score(0, 0, 99) == 20 and reach_score(0, 0, 9999) == 40
    assert reach_score(3, 13, 99) == 20 + 39 + 3
    payload = {"data": [{"code": "C1", "user": {"username": "u", "follower_count": 9999}, "caption": {"text": "x"},
                         "like_count": 4, "text_post_app_info": {"direct_reply_count": 2}}]}
    (p,) = posts_from_payload(payload, "kw")
    assert (p.likes, p.replies, p.author_followers, p.reach) == (4, 2, 9999, 40 + 6 + 4)


def test_worker_scans_top_tab_and_queues_by_reach(make_worker, runner):
    small = _post("SMALL", "nho")
    big = _post("BIG", "lon")
    big.author_followers, big.replies = 50_000, 20
    w, _ = make_worker(FakeBrowser({"kw": [small], ("kw", "top"): [big]}))
    w.runner._limits = lambda: GrowthLimits(max_replies_per_hour=1, max_replies_per_day=10, min_delay_sec=0, max_delay_sec=0)
    w.now = lambda: datetime.now(timezone.utc)
    report = w.tick()
    assert report.ingested == 2 and report.posted == 1
    assert report.posted_items[0]["author"] == "lon"  # suất duy nhất dành cho bài nhiều người xem
    big_row = next(r for r in runner.storage.list_posts("posted"))
    assert big_row["reach"] > 60 and big_row["author_followers"] == 50_000


def test_worker_min_reach_filters(make_worker, runner):
    w, _ = make_worker(FakeBrowser({"kw": [_post("SMALL", "nho")]}))
    make_worker.cfg["value"] = WorkerConfig(enabled=True, auto_post_min_relevance=60, min_reach=30)
    assert w.tick().ingested == 0


def test_worker_drops_stale_queued_post(make_worker, runner):
    pid = _save(runner.storage, "OLDQ")
    runner.approve_and_prepare(pid)
    with runner.storage._connection() as c:
        c.execute("UPDATE growth_posts SET post_created_at=? WHERE id=?", ((NOW - timedelta(hours=100)).isoformat(), pid))
    fb = FakeBrowser()
    w, _ = make_worker(fb)
    w.tick()
    assert fb.replies == [] and runner.storage.get_post_by_id(pid)["status"] == "rejected"


def test_growth_worker_browser_is_protected_from_orphan_purge():
    """Maintenance diệt Chromium «mồ côi»; worker kéo khách phải nằm trong danh sách chủ sở hữu hợp lệ."""
    from app.core.process_scan import is_toolsauto_entrypoint

    assert is_toolsauto_entrypoint(
        ["/home/vu/toolsauto/venv/bin/python", "/home/vu/toolsauto/app/features/threads/growth/worker.py"], "python"
    )


def test_worker_checkpoint_disables(make_worker):
    w, n = make_worker(FakeBrowser(invalid=True))
    report = w.tick()
    assert report.errors and ("growth.enabled", "false") in make_worker.disabled
    assert ("mark", False) in make_worker.disabled
    assert any(s.startswith("checkpoint") for s in n.sent)


def test_actions_and_telegram_callback(runner, monkeypatch):
    monkeypatch.setattr(actions, "_runner", runner)
    pid = _save(runner.storage, "T1")
    assert actions.telegram_callback(None, f"ok:{pid}")[0]
    assert runner.storage.get_post_by_id(pid)["status"] == "approved"
    ok, msg, follow = actions.telegram_callback(None, f"ab:{pid}")
    assert ok and runner.storage.get_post_by_id(pid)["variant"] == "B" and "chờ duyệt" in follow
    assert actions.telegram_callback(None, f"no:{pid}")[0]
    ok, msg, _ = actions.telegram_callback(None, f"ok:{pid}")
    assert not ok and "rejected" in msg
    assert not actions.telegram_callback(None, "ok:999")[0]
    assert not actions.telegram_callback(None, "zz:1")[0]
    with pytest.raises(actions.ActionError):
        actions.approve(_save(runner.storage, "T2"), "x" * 501)


def test_toggle_requires_login(monkeypatch):
    calls = []
    monkeypatch.setattr(actions.growth_session, "status", lambda db: SimpleNamespace(ready=False))
    monkeypatch.setattr(actions.settings, "upsert_setting", lambda *a, **k: calls.append(a))
    with pytest.raises(actions.ActionError):
        actions.set_enabled(None, True, by="t")
    assert actions.set_enabled(None, False, by="t") is False and calls


def test_telegram_command_registered():
    from app.features.telegram_bot.command_handler import TelegramCommandHandler

    assert "keokhach" in TelegramCommandHandler(None).handler_map()
    assert "keokhach" in [c for c, _ in TelegramCommandHandler.MENU]


def test_clean_reply_fixes_glued_links():
    url = "https://t.me/zt_shopee_bot?start=threads_cb_tier"
    out = evaluator.clean_reply('"săn voucher chồng voucher thếtps://t.me/zt_shopee_bot?start=threads_cb_tier"', url)
    assert out == f"săn voucher chồng voucher {url}"
    out = evaluator.clean_reply("ghé t.me/zt_shopee_bot?start=sai nha\nb", url)
    assert out == f"ghé nha b {url}"
    assert evaluator.clean_reply("không có link nha b", url) == "không có link nha b"


def _bot_dbs(tmp_path):
    import sqlite3

    cb, st = tmp_path / "cashback.sqlite", tmp_path / "store.sqlite"
    with sqlite3.connect(cb) as c:
        c.executescript("""
            CREATE TABLE bot_state(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE telegram_users(telegram_user_id INTEGER, username TEXT, created_at TEXT, last_seen_at TEXT);
            CREATE TABLE link_requests(id INTEGER, telegram_user_id INTEGER);
            INSERT INTO telegram_users VALUES (1, 'lan', '2026-11-06T01:03:18Z', NULL), (2, NULL, '2026-11-01T00:00:00Z', NULL),
                                              (3, 'x', '2026-11-06T02:00:00Z', NULL);
            INSERT INTO bot_state VALUES ('src:1', 'threads_cb_tier'), ('src:2', 'threads_cb_save'), ('src:3', 'canva');
            INSERT INTO link_requests VALUES (1, 2), (2, 2);
        """)
    with sqlite3.connect(st) as c:
        c.executescript("""
            CREATE TABLE state(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE users(user_id INTEGER, username TEXT, created_at TEXT, last_seen_at TEXT);
            CREATE TABLE topups(user_id INTEGER, credited INTEGER, status TEXT);
            CREATE TABLE orders(user_id INTEGER, total INTEGER, refunded INTEGER);
            INSERT INTO users VALUES (9, 'mai', '2026-11-06T03:00:00Z', NULL);
            INSERT INTO state VALUES ('src:9', 'threads_ai_price');
            INSERT INTO topups VALUES (9, 100000, 'paid'), (9, 50000, 'pending');
            INSERT INTO orders VALUES (9, 80000, 0);
        """)
    return cb, st


def test_conversions_report_reads_both_bots(tmp_path):
    from app.features.threads.growth import conversions

    cb, st = _bot_dbs(tmp_path)
    rep = conversions.report(now=NOW, cashback_path=cb, store_path=st)
    assert rep["errors"] == [] and rep["total"] == 3 and rep["active"] == 2 and rep["last_24h"] == 2
    assert rep["by_variant"]["cashbot"]["B"] == {"customers": 1, "active": 0}
    assert rep["by_variant"]["cashbot"]["A"] == {"customers": 1, "active": 1}
    assert rep["by_variant"]["ai_store"]["B"] == {"customers": 1, "active": 1}
    store = [c for c in rep["customers"] if c["bot"] == "ai_store"][0]
    assert store["activity"] == "nạp 100.000đ · 1 đơn · 80.000đ"
    assert {c["code"] for c in rep["customers"]} == {"threads_cb_tier", "threads_cb_save", "threads_ai_price"}


def test_conversions_missing_db_does_not_break(tmp_path):
    from app.features.threads.growth import conversions

    cb, _ = _bot_dbs(tmp_path)
    rep = conversions.report(now=NOW, cashback_path=cb, store_path=tmp_path / "nope.sqlite")
    assert rep["total"] == 2 and rep["errors"] and "ai_store" in rep["errors"][0]


def test_vn_time():
    from app.features.threads.growth.notify import vn_time

    assert vn_time("2026-11-06T01:03:18Z") == "06/11 08:03"
    assert vn_time(None) == ""


# ── PLAN-159: bài riêng, trả lời lại, kênh, viết lại câu mẫu ─────────────────────────────

def test_clean_post_keeps_lines_and_single_tracking_link():
    text = content.clean_post('"Deal nè mn\n\n\n- Cây lau 110k t.me/zt_shopee_bot\nvào bot https://t.me/x?start=y"', "L")
    assert text == "Deal nè mn\n\n- Cây lau 110k\nvào bot\nL"


def test_load_deals_reads_cashback_pool(tmp_path):
    import json
    import sqlite3

    db = tmp_path / "cashback.sqlite"
    now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
    fresh, stale = "2026-11-06T07:00:00Z", "2026-11-05T00:00:00Z"
    pool = {
        "1": {"item_id": 1, "name": "Lau nhà", "price": 110000, "usual": 140000, "cashback": 5600, "seen": fresh,
              "lowest_30d": True, "sold_30d": 300},
        "2": {"item_id": 2, "name": "Jean", "price": 100000, "usual": 200000, "seen": fresh, "lowest_30d": True},
        "3": {"item_id": 3, "name": "Cũ", "price": 1, "usual": 9, "seen": stale, "lowest_30d": True},
        "4": {"item_id": 4, "name": "Bỏ", "price": 1, "usual": 9, "seen": fresh, "lowest_30d": True},
        "5": {"item_id": 5, "name": "Ko thấp nhất", "price": 1, "usual": 9, "seen": fresh, "lowest_30d": False},
    }
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE bot_state (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("INSERT INTO bot_state VALUES ('deals_pool', ?), ('deals_removed', '[4]')", (json.dumps(pool),))
    deals = content.load_deals(now, db)
    assert [d.item_id for d in deals] == [2, 1]  # giảm 50% trước 21%
    assert deals[1].off_pct == 21 and deals[1].cashback == 5600


def test_next_sale_finds_big_sale_only():
    assert content.next_sale(datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)).label == "11.11"
    assert content.next_sale(datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)) is None  # 15/11 mini bị bỏ


def test_write_own_post_sale_then_deal_and_no_repeat(monkeypatch):
    deal = content.Deal(7, "Cây lau nhà", 110000, 140000, 5600, 300)
    monkeypatch.setattr(content, "load_deals", lambda now, path=None: [deal])
    now = datetime(2026, 11, 8, 5, 0, tzinfo=timezone.utc)
    first = asyncio.run(content.write_own_post(now, set()))
    assert first.kind == "sale" and first.text.endswith("start=threads_cb_post")
    second = asyncio.run(content.write_own_post(now, {first.ref}))
    assert second.kind == "deal" and second.ref == "deal:7"
    assert asyncio.run(content.write_own_post(now, {first.ref, "deal:7"})) is None


def test_write_own_post_ai_down_returns_none(monkeypatch):
    async def _empty(prompt, *, purpose="generic"):
        return "", {"fail_reason": "circuit_open"}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(_empty))
    monkeypatch.setattr(content, "load_deals", lambda now, path=None: [content.Deal(7, "x", 1, 2, 0, 0)])
    assert asyncio.run(content.write_own_post(datetime(2026, 11, 20, tzinfo=timezone.utc), set())) is None


def test_worker_posts_own_post_once_per_slot(make_worker, runner, monkeypatch):
    monkeypatch.setattr(content, "load_deals", lambda now, path=None: [content.Deal(7, "Cây lau", 110000, 140000, 0, 1)])
    fb = FakeBrowser()
    fb.posts_made = []
    w, n = make_worker(fb)
    make_worker.cfg["value"] = WorkerConfig(enabled=True, own_post_times="20:00", followup_enabled=False)
    w.now = lambda: datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)  # 20:40 VN — đã qua độ lệch tối đa 25 phút
    report = w.tick()
    assert len(fb.posts_made) == 1 and report.own_posts[0]["kind"] == "deal"
    assert any("'own_posts': [{'kind': 'deal'" in t for t in n.sent)
    w.tick()
    assert len(fb.posts_made) == 1  # khung đã đăng
    w.now = lambda: datetime(2026, 11, 6, 15, 30, tzinfo=timezone.utc)  # 22:30 VN — hết khung
    assert not w.runner.storage.own_post_slot_done("2026-11-06 22:30")


def test_replies_to_me_parser():
    payload = {"x": [
        {"code": "Q1", "user": {"username": "lan"}, "caption": {"text": "bot gì vậy b"},
         "text_post_app_info": {"reply_to_author": {"username": "us28qt"}}},
        {"code": "Q2", "user": {"username": "mai"}, "caption": {"text": "ib"},
         "text_post_app_info": {"reply_to_author": {"username": "chu_bai"}}},
        {"code": "Q3", "user": {"username": "us28qt"}, "caption": {"text": "tự reply"},
         "text_post_app_info": {"reply_to_author": {"username": "us28qt"}}},
        {"code": "Q4", "user": {"username": "an"}, "caption": {"text": "đã trả lời rồi"},
         "text_post_app_info": {"reply_to_author": {"username": "us28qt"}, "has_viewer_replied": True}},
    ]}
    found = browser.replies_to_me(payload, "@US28QT")
    assert [p.thread_id for p in found] == ["Q1"] and found[0].post_url.endswith("/@lan/post/Q1")


def test_worker_followups_answer_skip_and_cap(make_worker, runner, monkeypatch):
    pid = _save(runner.storage, "MINE")
    runner.storage.update_status(pid, "posted", actual_reply="t hay dùng @zt_shopee_bot", reply_url="https://r/MINE")
    q = lambda code, who, text: ScannedPost(code, f"https://www.threads.com/@{who}/post/{code}", who, text, "")  # noqa: E731
    fb = FakeBrowser()
    fb.comments = {"https://r/MINE": [q("C1", "lan", "bot gì vậy b"), q("C2", "mai", "cảm ơn"), q("C3", "an", "dùng sao")]}

    async def _followup(bot, our, comment):
        return ("skip", None) if comment == "cảm ơn" else ("answer", f"trả lời: {comment}")

    monkeypatch.setattr(content, "write_followup", _followup)
    w, n = make_worker(fb)
    make_worker.cfg["value"] = WorkerConfig(enabled=True, own_posts_enabled=False, followup_max_per_day=1)
    w.now = lambda: datetime.now(timezone.utc)
    report = w.tick()
    assert [f["author"] for f in report.followups] == ["lan"]  # tối đa 1 / ngày
    assert fb.replies == [("https://www.threads.com/@lan/post/C1", "trả lời: bot gì vậy b")]
    rows = {r["code"]: r["status"] for r in runner.storage.list_followups()}
    assert rows == {"C1": "answered"}
    # Hết suất giữa chừng → reply chưa đánh dấu «đã kiểm»: mai mở lại, trả lời tiếp C3 (C2 chỉ là «cảm ơn» → bỏ).
    assert runner.storage.get_post_by_id(pid)["followup_checked_at"] is None
    make_worker.cfg["value"] = WorkerConfig(enabled=True, own_posts_enabled=False, followup_max_per_day=5)
    w.last_followup = None
    w.tick()
    rows = {r["code"]: r["status"] for r in runner.storage.list_followups()}
    assert rows == {"C1": "answered", "C2": "skipped", "C3": "answered"}
    assert runner.storage.get_post_by_id(pid)["followup_checked_at"] is not None
    assert any("'followups': [{'author': 'lan'" in t for t in n.sent)


def test_worker_followup_ai_down_retries_later(make_worker, runner, monkeypatch):
    pid = _save(runner.storage, "MINE")
    runner.storage.update_status(pid, "posted", reply_url="https://r/MINE")
    fb = FakeBrowser()
    fb.comments = {"https://r/MINE": [ScannedPost("C1", "https://x/C1", "lan", "bot gì", "")]}

    async def _down(bot, our, comment):
        return "error", None

    monkeypatch.setattr(content, "write_followup", _down)
    w, _ = make_worker(fb)
    make_worker.cfg["value"] = WorkerConfig(enabled=True, own_posts_enabled=False)
    w.now = lambda: datetime.now(timezone.utc)
    w.tick()
    assert runner.storage.list_followups() == []
    assert runner.storage.get_post_by_id(pid)["followup_checked_at"] is None  # chưa đánh dấu → lần sau kiểm lại


def test_worker_rewrites_fallback_when_ai_back(make_worker, runner, monkeypatch):
    ai_up = {"value": False}

    async def _flaky(prompt, *, purpose="generic"):
        if ai_up["value"]:
            return "ủa t hay dùng bot này nè b", {"provider": "fake", "model": "m"}
        return "", {"fail_reason": "circuit_open"}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(_flaky))
    w, _ = make_worker(FakeBrowser({"kw": [_post("P1", "lan", text=VI_SHOPEE + " săn sale shopee voucher shopee")]}))
    make_worker.cfg["value"] = WorkerConfig(enabled=True, auto_post_min_relevance=40, own_posts_enabled=False,
                                            followup_enabled=False)
    w.runner._limits = lambda: GrowthLimits(max_replies_per_hour=0, max_replies_per_day=0)
    w.tick()
    assert runner.storage.get_post_by_id(1)["status"] == "pending"  # AI lỗi → câu mẫu, chờ duyệt
    ai_up["value"] = True
    w.last_rewrite = None
    report = w.tick()
    row = runner.storage.get_post_by_id(1)
    assert report.rewritten == 1 and row["status"] == "approved" and not row["ai_analysis"].startswith("Fallback")


def test_channel_codes_and_conversions_by_channel(tmp_path):
    import sqlite3

    from app.features.threads.growth import config, conversions

    assert config.channel_url(TargetBot.CASHBOT, "post") == "https://t.me/zt_shopee_bot?start=threads_cb_post"
    assert config.code_channel("threads_cb_tier") == "reply B" and config.code_channel("threads_ai_conv") == "trả lời lại"
    cb = tmp_path / "cb.sqlite"
    with sqlite3.connect(cb) as c:
        c.execute("CREATE TABLE bot_state (key TEXT, value TEXT)")
        c.execute("CREATE TABLE telegram_users (telegram_user_id INTEGER, username TEXT, created_at TEXT, last_seen_at TEXT)")
        c.execute("CREATE TABLE link_requests (telegram_user_id INTEGER)")
        c.executemany("INSERT INTO bot_state VALUES (?, ?)", [("src:1", "threads_cb_post"), ("src:2", "threads_cb_save")])
        c.executemany("INSERT INTO telegram_users VALUES (?, NULL, '2026-11-06T01:00:00Z', NULL)", [(1,), (2,)])
    rep = conversions.report(cashback_path=cb, store_path=tmp_path / "none.sqlite")
    assert rep["by_channel"] == {"bài riêng": {"customers": 1, "active": 0}, "reply A": {"customers": 1, "active": 0}}


def test_cycle_text_own_posts_followups_and_channels():
    from app.features.threads.growth import notify

    text = notify.cycle_text({
        "posted": 0, "own_posts": [{"kind": "sale", "url": "https://p/1", "text": "còn 3 ngày là 11.11 <3"}],
        "followups": [{"author": "lan", "comment": "bot gì", "text": "bot hoàn tiền nè", "url": "https://f"}],
        "rewritten": 2,
        "customers": {"total": 3, "last_24h": 1, "active": 1, "by_channel": {"bài riêng": {"customers": 1}}},
    })
    assert "đăng 1 bài riêng" in text and "trả lời lại 1 người" in text and "nhắc sale" in text
    assert "&lt;3" in text and "@lan" in text and "viết lại 2 bài" in text and "bài riêng 1" in text


def test_watchdog_sleep_rearms_alarm(monkeypatch):
    alarms, slept = [], []
    monkeypatch.setattr(worker.signal, "alarm", alarms.append)
    monkeypatch.setattr(worker.time, "sleep", slept.append)
    worker.watchdog_sleep(300)
    assert slept == [300] and alarms == [300 + worker.WATCHDOG_SEC, worker.WATCHDOG_SEC]


def test_own_post_prompt_has_cashbot_buy_rules_and_cart_note(monkeypatch):
    prompts = []

    async def _gen(prompt, *, purpose="generic"):
        prompts.append(prompt)
        return "Deal nè mn\n- Lau nhà 110k", {"provider": "fake"}  # AI «quên» nhắc giỏ hàng

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(_gen))
    monkeypatch.setattr(content, "load_deals", lambda now, path=None: [content.Deal(7, "Lau nhà", 110000, 140000, 0, 1)])
    draft = asyncio.run(content.write_own_post(datetime(2026, 11, 20, tzinfo=timezone.utc), set()))
    assert "xoá đi rồi mở lại bằng link của bot" in prompts[0]  # nguyên văn quy tắc CART_RULE của Cashbot
    lines = draft.text.split("\n")
    assert lines[-2] == content.CART_NOTE and lines[-1].endswith("start=threads_cb_post")
    assert content.with_buy_note("nhớ xoá giỏ hàng trước nha") == "nhớ xoá giỏ hàng trước nha"
