"""Exercise PLAN-178 through the existing worker using no external services."""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.features.threads.growth import worker
from app.features.threads.growth.config import ABVariant, AccountRole, GrowthLimits, TargetBot, WorkerConfig
from app.features.threads.growth.customer_agents import CustomerAgentStatus
from app.features.threads.growth.runner import GrowthRunner
from app.features.threads.growth.scanner import ScannedPost
from app.features.threads.growth.storage import GrowthStorage

NOW = datetime(2026, 11, 19, 3, tzinfo=timezone.utc)
NEED = "Mình cần mua CapCut Pro 30 ngày để dựng video"
DRAFT = "Bạn có thể xem gói CapCut Pro 30 ngày và giá hiện tại trong bot."
STORE = AccountRole(enabled=True, bots=("ai_store",), max_per_day=16, max_per_hour=4)


class Browser:
    def __init__(self):
        self.opened = 0
        self.sent = []
        self.comments = []
        self.handle = None
        self.on_open = lambda: None

    @contextmanager
    def open(self, _profile):
        self.opened += 1
        self.on_open()
        yield self

    def own_handle(self):
        return self.handle

    def replies_to_me(self, _url):
        return self.comments

    def reply(self, url, text):
        self.sent.append((url, text))
        return url + "/sent"


class Notifier:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    db = GrowthStorage(tmp_path / "growth.sqlite")
    browser = Browser()
    notify = Notifier()
    path = tmp_path / "status.json"
    runner = GrowthRunner(db, lambda: GrowthLimits(min_delay_sec=0, max_delay_sec=0))
    w = worker.GrowthWorker(runner, browser.open, notifier=notify, sleep=lambda _s: None,
                            now=lambda: NOW, agent_status=CustomerAgentStatus(path))
    cfg = WorkerConfig(enabled=True, own_posts_enabled=False, followup_enabled=False)
    roles = {"anlinh": STORE}
    monkeypatch.setattr(worker, "load_worker_config", lambda: cfg)
    monkeypatch.setattr(worker, "load_account_roles", lambda: roles)
    monkeypatch.setattr(w, "_profile_path", lambda _account: "/profile")
    monkeypatch.setattr(worker.conversions, "report", lambda: {})
    monkeypatch.setattr(notify, "cycle_text", lambda _report: "cycle", raising=False)
    w.last_scan = NOW
    return w, db, browser, notify, path


def save(db, code, content=NEED, copy=DRAFT, status="approved", score=80):
    return db.save_post(code, f"https://www.threads.com/@demo/post/{code}", code, content, TargetBot.AI_STORE,
                        ABVariant.VARIANT_A, copy, relevance_score=score, status=status,
                        post_created_at=(NOW - timedelta(hours=1)).isoformat())


def test_scan_stops_after_two_consecutive_page_errors_and_closes_browser(setup, monkeypatch):
    w, _, browser, _, _ = setup
    searches = []
    closed = []

    def search(keyword, **_kwargs):
        searches.append(keyword)
        raise TimeoutError("page load timeout")

    @contextmanager
    def open_browser(_profile):
        try:
            yield browser
        finally:
            closed.append(True)

    browser.search_recent = search
    w.browser_factory = open_browser
    monkeypatch.setattr(worker, "plan_searches", lambda *_a, **_k: [
        (TargetBot.AI_STORE, query, False) for query in ("one", "two", "three")])
    report = worker.CycleReport()
    w.scan("/profile", WorkerConfig(), report, {"ai_store"})
    assert searches == ["one", "two"]
    assert len(report.errors) == 2 and closed == [True]


def test_queue_reaches_eligible_row_after_hold_and_does_not_mutate_held_rows(setup):
    w, db, browser, _, _ = setup
    ids = [save(db, f"bad{i}", "Tuyển editor biết dùng CapCut Pro", score=99) for i in range(22)]
    ids.append(save(db, "wrong_link", copy=DRAFT + " https://t.me/zt_shopee_bot", score=99))
    good = save(db, "valid")
    report = worker.CycleReport()
    w.post_queue("/profile", report, account="anlinh", role=STORE)
    assert report.queue_replies_blocked == len(ids)
    assert {db.get_post_by_id(i)["status"] for i in ids} == {"approved"}
    assert report.posted == 1 and browser.opened == 1
    assert "threads_ai_auto_anlinh" in browser.sent[0][1]
    assert db.get_post_by_id(good)["actual_reply"] == browser.sent[0][1]


def test_queue_respects_rejection_after_loading_batch(setup):
    w, db, browser, _, _ = setup
    post_id = save(db, "edited")
    browser.on_open = lambda: db.update_status(post_id, "rejected")
    w.post_queue("/profile", worker.CycleReport(), account="anlinh", role=STORE)
    assert browser.sent == [] and db.get_post_by_id(post_id)["status"] == "rejected"


def test_profile_mismatch_and_disabled_dm_do_not_interact(setup):
    w, db, browser, _, _ = setup
    save(db, "mismatch")
    browser.handle = "us28qt"
    report = worker.CycleReport()
    w.post_queue("/profile", report, account="anlinh", role=STORE)
    w.dm_inbox("/profile", report, "anlinh")
    assert browser.opened == 1 and browser.sent == [] and report.dm_checks == 0
    assert report.errors == ["Threads profile identity mismatch"]


def test_inbound_support_still_hands_off_at_public_quota_and_dedupes(setup, monkeypatch):
    w, db, browser, notify, _ = setup
    target = save(db, "older", status="posted")
    db.update_status(target, "posted", reply_url="https://threads.com/@shop/post/one", account="anlinh")
    browser.comments = [
        ScannedPost("faq", "https://threads.com/@demo/post/faq", "demo", "Dùng bot thế nào?", ""),
        ScannedPost("support", "https://threads.com/@demo/post/support", "demo", "Mình đã chuyển khoản", ""),
    ]
    model = AsyncMock(side_effect=AssertionError("No model needed"))
    monkeypatch.setattr(worker.content, "write_followup", model)
    cfg = WorkerConfig(enabled=True, followup_max_per_day=0)
    report = worker.CycleReport()
    w.followups("/profile", cfg, report, "anlinh")
    w.last_followup.clear()
    w.followups("/profile", cfg, report, "anlinh")
    assert [(row["code"], row["status"]) for row in db.list_followups()] == [("support", "handoff")]
    assert len(notify.messages) == report.support_handoffs == 1
    assert not browser.sent and model.await_count == 0


def test_fallback_does_not_invoke_model_for_ineligible_post(setup, monkeypatch):
    w, db, _, _, _ = setup
    pid = save(db, "bad", content="Tuyển người biết CapCut", status="pending")
    db.switch_variant(pid, ABVariant.VARIANT_A, DRAFT, ai_analysis="Fallback: outage")
    model = AsyncMock(side_effect=AssertionError("No model needed"))
    monkeypatch.setattr(w.runner, "switch_variant", model)
    w.rewrite_fallbacks(WorkerConfig(), worker.CycleReport())
    assert model.await_count == 0
    assert db.get_post_by_id(pid)["status"] == "pending"


def test_status_idle_paused_unready_and_error(setup, monkeypatch):
    w, _, _, _, path = setup
    w.tick()
    assert json.loads(path.read_text())["phase"] == "waiting"
    monkeypatch.setattr(worker, "load_worker_config", lambda: WorkerConfig(enabled=False))
    assert w.tick() is None
    assert json.loads(path.read_text())["phase"] == "disabled"
    monkeypatch.setattr(worker, "load_worker_config", lambda: WorkerConfig(enabled=True, quiet_hours="09:00-11:00"))
    assert w.tick() is None
    assert json.loads(path.read_text())["phase"] == "quiet_hours"
    monkeypatch.setattr(worker, "load_worker_config", lambda: WorkerConfig(enabled=True))
    monkeypatch.setattr(w, "_profile_path", lambda _a: None)
    assert w.tick() is None
    assert json.loads(path.read_text())["phase"] == "no_ready_account"

    def fail(_account):
        raise RuntimeError("private failure context")

    monkeypatch.setattr(w, "_profile_path", fail)
    with pytest.raises(RuntimeError):
        w.tick()
    status = path.read_text()
    assert json.loads(status)["error_type"] == "RuntimeError"
    assert "private failure context" not in status


def test_status_distinguishes_active_role_and_omits_private_report_fields(setup):
    w, _, _, _, path = setup
    report = worker.CycleReport(posted=2, errors=["private error"], dms=[
        {"sent": True, "action": "reply", "handle": "secret-customer", "reply": "private text"},
        {"sent": False, "action": "handoff", "note": "secret note"},
    ])
    assert w.agent_status.update(phase="working", now=NOW, cfg=WorkerConfig(),
                                 roles={"anlinh": STORE}, report=report, active_role="engagement")
    raw = path.read_text()
    status = json.loads(raw)
    assert status["agents"]["engagement"]["state"] == "working"
    assert status["agents"]["acquisition"]["state"] == "waiting"
    assert status["current_cycle"]["counts"]["dm_replies_sent"] == 1
    assert status["current_cycle"]["counts"]["handoffs"] == 1
    assert all(s not in raw for s in ("secret", "private", "anlinh"))
    assert sorted(p.name for p in path.parent.iterdir() if p.name.startswith(".customer-agents-")) == []


def test_held_rows_are_unique_across_both_queue_checks(setup):
    w, db, _, _, _ = setup
    save(db, "job", content="Tuyển editor biết CapCut")
    report = worker.CycleReport()
    assert w._eligible_queue("anlinh", STORE, report) == []
    assert w._eligible_queue("anlinh", STORE, report) == []
    assert report.queue_replies_blocked == 1
    assert "_held_ids" not in report.as_dict()
    json.dumps(report.as_dict())


def test_help_reply_without_legacy_metadata_never_gets_sales_link(setup):
    w, db, browser, _, _ = setup
    pid = save(db, "help", content="CapCut không xuất được video, làm sao kiểm tra?",
               copy="Bạn thử kiểm tra tài nguyên Pro trong timeline rồi xem lại thông báo khi xuất nhé.")
    report = worker.CycleReport()
    w.post_queue("/profile", report, "anlinh", STORE)
    assert report.posted == report.help_replies_sent == 1
    assert report.buyer_replies_sent == 0
    assert db.get_post_by_id(pid)["status"] == "posted"
    assert "http" not in browser.sent[0][1] and "t.me" not in browser.sent[0][1]


def test_idle_hold_does_not_replace_last_real_activity(setup):
    w, _, _, _, path = setup
    writer = w.agent_status
    args = dict(phase="waiting", now=NOW, cfg=WorkerConfig(), roles={"anlinh": STORE})
    writer.update(**args, report=worker.CycleReport(posted=1))
    original = json.loads(path.read_text())["last_activity"]
    writer.update(**{**args, "now": NOW + timedelta(minutes=1)},
                  report=worker.CycleReport(queue_replies_blocked=24))
    assert json.loads(path.read_text())["last_activity"] == original
