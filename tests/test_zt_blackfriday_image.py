"""PLAN-182 image correction: temporary DB/assets and fake browser/PM2 only."""
import hashlib
import importlib.util
import json
import sqlite3
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from PIL import Image

PATH = Path(__file__).resolve().parents[1] / "reports/zt-blackfriday-20261120/image_trial.py"
SPEC = importlib.util.spec_from_file_location("test_bf_image_runtime", PATH)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)
REPLY = "https://www.threads.com/@us28qt/post/image182"
CONFIRM_IDENTITY = trial.confirm_composer_identity


@pytest.fixture
def setup(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    caption = "Ảnh hướng dẫn thật trong ZT báo mã. Chuẩn bị săn Black Friday 27/11."
    parent_text = "Chuẩn bị săn Black Friday 27/11 trong ZT báo mã.\nhttps://t.me/+TestBF26\nCó link tiếp thị liên kết."
    parent_hash = hashlib.sha256(parent_text.encode()).hexdigest()
    original = {"text": parent_text, "text_sha256": parent_hash, "post_url": trial.PARENT,
                "status": "posted", "invite_url": "https://t.me/+TestBF26"}
    (tmp_path / "manifest.json").write_text(json.dumps(original))
    picture = tmp_path / "asset.png"
    Image.effect_noise((600, 750), 20).save(picture)
    m = {"plan": "PLAN-182", "account": "us28qt", "slot": trial.SLOT, "parent_url": trial.PARENT,
         "parent_text_sha256": parent_hash, "caption": caption,
         "caption_sha256": hashlib.sha256(caption.encode()).hexdigest(), "image_path": "asset.png",
         "image_sha256": hashlib.sha256(picture.read_bytes()).hexdigest(), "prepared_at": now.isoformat()}
    db_path = tmp_path / "growth.sqlite"
    with sqlite3.connect(db_path) as db:
        db.executescript("""CREATE TABLE growth_posts(account TEXT,status TEXT,posted_at TEXT);
            CREATE TABLE own_posts(id INTEGER PRIMARY KEY,slot TEXT UNIQUE,kind TEXT,ref TEXT,text TEXT,
            status TEXT,created_at TEXT,account TEXT,post_url TEXT,error_message TEXT);""")
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"phase": "waiting", "heartbeat_at": now.isoformat()}))
    monkeypatch.setattr(trial.base, "AGENT_STATUS", status)
    role = SimpleNamespace(enabled=True, own_posts=True, max_per_hour=3, max_per_day=20, serves=lambda bot: True)
    cfg = SimpleNamespace(enabled=True, quiet_hours="")
    monkeypatch.setattr(trial.base, "load_account_roles", lambda: {"us28qt": role})
    monkeypatch.setattr(trial.base, "load_worker_config", lambda: cfg)
    monkeypatch.setattr(trial.base, "load_limits", lambda: SimpleNamespace(min_delay_sec=180))
    monkeypatch.setattr(trial.base, "login_active", lambda: True)
    monkeypatch.setattr(trial, "profile_locked", lambda *_a: False)
    monkeypatch.setattr(trial.time, "sleep", lambda *_a: None)
    state = {trial.WORKER: {"status": "online", "pid": 123, "restarts": 0},
             "Other": {"status": "online", "pid": 789, "restarts": 0}}
    actions, sent, closed, discarded, discovered = [], [], [], [], []

    def action(command):
        actions.append(command)
        state[trial.WORKER]["status"] = "stopped" if command == "stop" else "online"

    monkeypatch.setattr(trial.base, "pm2_state", lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(trial.base, "pm2_action", action)

    class Button:
        error = None

        def click(self, **kwargs):
            saved = json.loads((tmp_path / "image-publication.json").read_text())
            assert saved["submit_called"] and saved["status"] == "unknown"
            with sqlite3.connect(db_path) as db:
                assert db.execute("SELECT status FROM own_posts WHERE slot=?", (trial.SLOT,)).fetchone() == ("unknown",)
            sent.append(True)
            if self.error:
                raise self.error

    button = Button()
    box = SimpleNamespace(inner_text=lambda: m["caption"])

    class Browser:
        handle = "us28qt"

        def __init__(self, path):
            self.composing = False

            def discover():
                assert not self.composing, "Profile discovery would navigate away from composer"
                discovered.append(self.handle)
                return self.handle

            self.adapter = SimpleNamespace(_discover_own_handle=discover)
            self._payloads = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

    def composer(browser, *_a):
        browser.composing = True
        return SimpleNamespace(), box, button

    monkeypatch.setattr(trial, "prepare_composer", composer)
    monkeypatch.setattr(trial, "confirm_composer_identity", lambda browser, dialog: None)
    monkeypatch.setattr(trial, "preview_count", lambda dialog: 1)
    monkeypatch.setattr(trial, "discard_composer", lambda *_a: discarded.append(True))
    monkeypatch.setattr(trial, "inspect_parent", lambda *_a: {"parent_verified": True, "edit_available": False})
    monkeypatch.setattr(trial, "verify_image", lambda *_a: {"post_url": REPLY, "media_count": 1,
                                                         "caption_verified": True, "parent_page_and_original_text_verified": True})
    return SimpleNamespace(m=m, db=db_path, folder=tmp_path, role=role, cfg=cfg, status=status, now=now,
                           actions=actions, sent=sent, closed=closed, discarded=discarded, browser=Browser,
                           button=button, box=box, picture=picture, discovered=discovered)


def run(s, mode="publish"):
    return trial.execute(s.m, mode=mode, folder=s.folder, db_path=s.db, browser_factory=s.browser)


def prepare(s):
    assert run(s, "prepare")["status"] == "prepared"


def test_default_preflight_is_readonly_without_process_or_browser(setup):
    s = setup
    before = s.db.read_bytes()
    assert run(s, "preflight")["blocked"] == []
    assert s.db.read_bytes() == before
    assert s.actions == s.sent == s.closed == []


def test_inspect_does_not_require_asset_or_public_budget(setup):
    s = setup
    del s.m["image_path"]
    s.role.enabled = False
    before = s.db.read_bytes()
    result = run(s, "inspect")
    assert result["status"] == "inspected" and result["edit_available"] is False
    assert result["worker_restored"] and s.actions == ["stop", "start"]
    assert not s.sent and s.db.read_bytes() == before


def test_prepare_has_image_preview_but_no_public_attempt(setup):
    s = setup
    before = s.db.read_bytes()
    prepare(s)
    assert s.discarded == [True] and not s.sent
    assert s.db.read_bytes() == before and not (s.folder / "image-publication.json").exists()


def test_publish_requires_prepared_identical_asset(setup):
    s = setup
    with pytest.raises(FileNotFoundError):
        run(s)
    assert s.actions == s.sent == []
    prepare(s)
    s.m["caption"] += " Mới."
    s.m["caption_sha256"] = hashlib.sha256(s.m["caption"].encode()).hexdigest()
    with pytest.raises(ValueError, match="reviewed --prepare"):
        run(s)
    assert s.sent == []


def test_single_click_is_fenced_and_second_run_cannot_republish(setup):
    s = setup
    prepare(s)
    result = run(s)
    assert result["status"] == "posted" and result["worker_restored"]
    assert s.sent == [True] and s.closed == [True, True]
    assert s.discovered == ["us28qt", "us28qt"]
    assert run(s)["status"] == "blocked" and s.sent == [True]
    assert result["pm2_before"]["Other"] == result["pm2_after"]["Other"]
    with sqlite3.connect(s.db) as db:
        assert db.execute("SELECT status,post_url FROM own_posts").fetchall() == [("posted", REPLY)]


def test_click_timeout_remains_unknown_without_any_retry(setup):
    s = setup
    prepare(s)
    s.button.error = TimeoutError()
    result = run(s)
    assert result["status"] == "unknown" and result["submit_called"]
    assert result["worker_restored"] and s.sent == [True]
    assert run(s)["status"] == "blocked" and s.sent == [True]


def test_unknown_verify_never_submits_and_requires_unchanged_manifest(setup, monkeypatch):
    s = setup
    prepare(s)
    monkeypatch.setattr(trial, "verify_image", lambda *_a: None)
    assert run(s)["status"] == "unknown"
    before = s.db.read_bytes()
    assert run(s, "verify")["status"] == "unknown"
    assert s.db.read_bytes() == before and s.sent == [True]
    monkeypatch.setattr(trial, "verify_image", lambda *_a: {"post_url": REPLY, "media_count": 1})
    assert run(s, "verify")["status"] == "posted" and s.sent == [True]


def test_identity_mismatch_closes_and_restores_without_fence_or_submit(setup):
    s = setup
    prepare(s)
    s.browser.handle = "other_account"
    assert run(s)["status"] == "not_published"
    assert s.sent == [] and s.actions == ["stop", "start"] * 2
    with sqlite3.connect(s.db) as db:
        assert db.execute("SELECT COUNT(*) FROM own_posts").fetchone() == (0,)


def test_quiet_hours_changing_before_submit_prevents_public_action(setup, monkeypatch):
    s = setup
    prepare(s)
    checks = iter([False, True])
    monkeypatch.setattr(trial.base, "in_quiet_hours", lambda *_a: next(checks))
    assert run(s)["status"] == "not_published" and s.sent == []
    assert s.actions == ["stop", "start"] * 2


def test_missing_or_multiple_media_previews_prevent_submit(setup, monkeypatch):
    s = setup
    prepare(s)
    monkeypatch.setattr(trial, "preview_count", lambda dialog: 2)
    assert run(s)["status"] == "not_published" and not s.sent
    assert s.actions == ["stop", "start"] * 2


def test_interrupt_after_submit_keeps_unknown_and_restores(setup):
    s = setup
    prepare(s)
    s.button.error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run(s)
    proof = json.loads((s.folder / "image-publication.json").read_text())
    assert proof["status"] == "unknown" and proof["worker_restored"]
    assert s.sent == [True] and s.closed == [True, True]


def test_combined_public_quota_includes_originals_and_replies(setup):
    s = setup
    when = (s.now - timedelta(minutes=10)).isoformat()
    with sqlite3.connect(s.db) as db:
        db.execute("INSERT INTO growth_posts VALUES('us28qt','posted',?)", (when,))
        db.executemany("INSERT INTO own_posts(slot,status,created_at,account) VALUES(?,'posted',?,'us28qt')",
                       [("one", when), ("two", when)])
    result = run(s, "prepare")
    assert result["status"] == "blocked" and "hour_budget" in result["preflight"]["blocked"]
    assert result["preflight"]["combined_public_last_hour"] == 3 and not s.actions


@pytest.mark.parametrize("change", ["account", "parent", "caption", "image", "outside", "parent_hash"])
def test_manifest_guards_prevent_all_runtime_actions(setup, change):
    s = setup
    if change == "account":
        s.m["account"] = "anlinh"
    elif change == "parent":
        s.m["parent_url"] = "https://www.threads.com/@other/post/123"
    elif change == "caption":
        s.m["caption"] += " Giảm 90%."
        s.m["caption_sha256"] = hashlib.sha256(s.m["caption"].encode()).hexdigest()
    elif change == "image":
        s.picture.write_bytes(b"not reviewed")
    elif change == "outside":
        s.m["image_path"] = "../outside.png"
    else:
        s.m["parent_text_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        run(s, "prepare")
    assert s.actions == s.sent == []


def test_payload_media_checks_own_exact_caption_and_actual_image_candidates():
    caption = "Actual reviewed caption"
    node = {"code": "reply182", "user": {"username": "us28qt"}, "caption": {"text": caption},
            "image_versions2": {"candidates": [{"url": "https://cdn.example/image.jpg"}]},
            "text_post_app_info": {"is_reply": True, "reply_to_author": {"username": "us28qt"}}}
    media = trial.payload_media([{"posts": [node]}], caption)
    assert media["reply182"] == {"media_count": 1, "is_reply": True, "reply_to_author": "us28qt", "parent_references": []}
    node["user"]["username"] = "other"
    assert trial.payload_media([node], caption) == {}


def test_payload_text_only_does_not_prove_media_attachment():
    node = {"code": "reply182", "user": {"username": "us28qt"}, "caption": {"text": "Caption"},
            "text_post_app_info": {"is_reply": True, "reply_to_author": {"username": "us28qt"}}}
    assert trial.payload_media([node], "Caption")["reply182"]["media_count"] == 0


def test_final_identity_reads_chrome_without_profile_discovery_or_navigation():
    def prohibited():
        raise AssertionError("Profile discovery must never run while composing")

    browser = SimpleNamespace(adapter=SimpleNamespace(_own_handle="us28qt", _discover_own_handle=prohibited),
                              page=SimpleNamespace(evaluate=lambda *_a: ["us28qt"], goto=prohibited))
    dialog = SimpleNamespace(inner_text=lambda: "us28qt\nActual caption")
    CONFIRM_IDENTITY(browser, dialog)
    browser.page.evaluate = lambda *_a: ["other"]
    with pytest.raises(ValueError, match="navigation identity"):
        CONFIRM_IDENTITY(browser, dialog)


def test_parent_scope_accepts_observed_no_pressable_and_shortened_link_text():
    invite = "https://t.me/+02gPhoNuEjcxMmJl"
    original = {"text": "Chuẩn bị săn Black Friday 27/11.\nMình có kênh ZT báo mã.\n" + invite + "\nCó link tiếp thị liên kết.",
                "invite_url": invite}
    observed = {"text": original["text"].replace(invite, "t.me/+02gP..."),
                "timestamp_codes": [trial.PARENT_CODE], "reply_count": 1, "more_count": 1,
                "hrefs": ["https://l.instagram.com/?u=" + quote(invite, safe="")]}
    assert trial.parent_scope_matches(observed, original)
    observed["hrefs"] = ["https://t.me/+another"]
    assert not trial.parent_scope_matches(observed, original)
    observed["hrefs"] = [invite]
    observed["timestamp_codes"].append("another_post")
    assert not trial.parent_scope_matches(observed, original)


def test_invitation_wrapper_must_be_allowed_host_and_exact_target():
    invite = "https://t.me/+TestBF26"
    assert trial.invite_href_matches(invite, invite)
    assert not trial.invite_href_matches("https://evil.example/?u=" + quote(invite, safe=""), invite)
    assert not trial.invite_href_matches(invite + "extra", invite)


def test_observed_title_only_more_svg_is_used_for_scoped_menu(monkeypatch, tmp_path):
    # Real observed markup uses title/child-title with no aria-label.
    markup = ET.fromstring('<div><svg title="Like"><title>Like</title></svg>'
                           '<svg title="More"><title>More</title></svg>'
                           '<svg title="Reply"><title>Reply</title></svg></div>')
    clicks = []

    def matching(selector):
        found = []
        for query in selector.split(","):
            parsed = re.fullmatch(r'(\w*)\[([\w-]+)="([^"]+)"\]', query.strip())
            assert parsed, query
            tag, attribute, value = parsed.groups()
            found.extend(e for e in markup.iter() if (not tag or e.tag == tag) and e.get(attribute) == value)
        return list(dict.fromkeys(found))

    class Control:
        def __init__(self, nodes):
            self.nodes = nodes
            self.first = self

        def count(self):
            return len(self.nodes)

        def click(self, **kwargs):
            clicks.append(self.nodes[0].get("title"))

    container = SimpleNamespace(locator=lambda selector: Control(matching(selector)))
    monkeypatch.setattr(trial, "parent_container", lambda *_a: container)
    monkeypatch.setattr(trial.time, "sleep", lambda *_a: None)
    browser = SimpleNamespace(page=SimpleNamespace(screenshot=lambda **_k: None,
                              locator=lambda _s: SimpleNamespace(all_inner_texts=lambda: ["Copy link", "Pin"]),
                              keyboard=SimpleNamespace(press=lambda _key: None)))
    result = trial.inspect_parent(browser, {}, tmp_path)
    assert clicks == ["More"] and result["edit_available"] is False
    assert [e.get("title") for e in matching(trial.REPLY_SELECTOR)] == ["Reply"]


def test_raw_parent_reference_matches_exact_code_or_normalized_media_id():
    refs = trial.parent_reference_check(["12345_900"], {trial.PARENT_CODE, "12345"})
    assert refs == {"available": True, "verified": True}
    assert trial.parent_reference_check(["wrong_parent"], {trial.PARENT_CODE}) == {"available": True, "verified": False}
    assert trial.parent_reference_check([], {trial.PARENT_CODE}) == {"available": False, "verified": False}
