"""PLAN-181 channel mutations use fake Telegram and temporary state only."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "reports/zt-blackfriday-20261120/channel_trial.py"
SPEC = importlib.util.spec_from_file_location("bf_channel", PATH)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)
TARGET = -10012345


@pytest.fixture
def setup(tmp_path):
    content = {"plan": "PLAN-181", "channel_title": "ZT báo mã", "source": "zt_bf26_guide",
               "guide_text": "Chuẩn bị săn Black Friday. Xem điều kiện trước khi mua.\nLink tiếp thị liên kết.",
               "invite_name": "ZT BF26 Threads P1", "invite_expire_at": "2026-11-30T23:59:59+07:00"}

    class API:
        def __init__(self):
            self.calls, self.fail = [], None
            self.chat = {"id": TARGET, "type": "channel", "title": "ZT báo mã"}
            self.rights = {"user": {"id": 7}, "status": "administrator", "can_post_messages": True,
                           "can_edit_messages": True, "can_invite_users": True}

        def __call__(self, method, params):
            self.calls.append((method, params))
            if method == self.fail:
                raise TimeoutError("secret URL must not be exported")
            if method == "getChat":
                return self.chat
            if method == "getMe":
                return {"id": 7, "is_bot": True}
            if method == "getChatMember":
                return self.rights
            if method == "getChatMemberCount":
                return 3
            state = json.loads((tmp_path / "channel-state.json").read_text())
            key = {"createChatInviteLink": "invite", "sendMessage": "guide", "pinChatMessage": "pin"}[method]
            assert state[key]["status"] == "unknown"
            if method == "createChatInviteLink":
                return {"invite_link": "https://t.me/+Trial181", "name": params["name"],
                        "expire_date": params["expire_date"], "is_primary": False, "is_revoked": False,
                        "creator": {"id": 7, "username": "private"}}
            if method == "sendMessage":
                assert params["text"] == content["guide_text"] and params["disable_notification"] is True
                return {"message_id": 42, "chat": {"id": TARGET}, "text": params["text"]}
            assert params["disable_notification"] is True
            self.chat["pinned_message"] = {"message_id": 42, "text": content["guide_text"]}
            return True

    return tmp_path, content, API()


def run(s, apply=True):
    folder, content, api = s
    return trial.execute(api, TARGET, content, folder=folder, apply=apply)


def test_readonly_default_and_completed_reentry_send_exactly_once(setup):
    folder, content, api = setup
    assert run(setup, False)["status"] == "ready"
    assert not (folder / "channel-state.json").exists()
    assert not any(m in trial.WRITES for m, _ in api.calls)
    result = run(setup)
    assert result["status"] == "completed" and result["baseline_member_count"] == 3
    assert result["guide"]["text"] == content["guide_text"]
    assert "creator" not in result["invite"]
    before = list(api.calls)
    assert run(setup)["status"] == "completed"
    assert not any(m in trial.WRITES for m, _ in api.calls[len(before):])
    assert run(setup, False)["readiness"]["own_guide_pinned"] is True


@pytest.mark.parametrize("method,key", [("createChatInviteLink", "invite"), ("sendMessage", "guide")])
def test_unknown_mutation_never_retried(setup, method, key):
    folder, _, api = setup
    api.fail = method
    with pytest.raises(trial.TrialError):
        run(setup)
    state = json.loads((folder / "channel-state.json").read_text())
    assert state[key]["status"] == "unknown"
    assert "secret" not in json.dumps(state)
    api.fail = None
    before = list(api.calls)
    with pytest.raises(trial.TrialError, match="unknown_" + key):
        run(setup)
    assert not any(m in trial.WRITES for m, _ in api.calls[len(before):])


@pytest.mark.parametrize("bad", ["target", "title", "public", "rights", "pin"])
def test_target_permission_pin_guards_block_all_mutations(setup, bad):
    _, _, api = setup
    if bad == "target":
        api.chat["id"] = -100999
    elif bad == "title":
        api.chat["title"] = "Other"
    elif bad == "public":
        api.chat["username"] = "public"
    elif bad == "rights":
        api.rights["can_edit_messages"] = False
    else:
        api.chat["pinned_message"] = {"message_id": 99, "text": "Someone else"}
    with pytest.raises(trial.TrialError):
        run(setup)
    assert not any(m in trial.WRITES for m, _ in api.calls)


def test_voucher_shaped_guide_rejected_without_api(setup):
    _, content, api = setup
    content["guide_text"] = "Mã: FAKE123\nGiảm: 90%"
    with pytest.raises(trial.TrialError, match="voucher_trigger"):
        run(setup)
    assert api.calls == []


def test_unknown_pin_can_only_recover_from_exact_readback_without_repin(setup):
    folder, content, api = setup
    api.fail = "pinChatMessage"
    with pytest.raises(trial.TrialError):
        run(setup)
    before = list(api.calls)
    api.fail = None
    with pytest.raises(trial.TrialError, match="unknown_pin"):
        run(setup)
    assert not any(m in trial.WRITES for m, _ in api.calls[len(before):])
    api.chat["pinned_message"] = {"message_id": 42, "text": content["guide_text"]}
    before = list(api.calls)
    assert run(setup)["status"] == "completed"
    assert not any(m in trial.WRITES for m, _ in api.calls[len(before):])
    assert json.loads((folder / "channel-state.json").read_text())["pin"]["status"] == "verified"


def test_preflight_does_not_claim_health_when_saved_pin_disappears(setup):
    _, _, api = setup
    run(setup)
    del api.chat["pinned_message"]
    with pytest.raises(trial.TrialError, match="pin_missing"):
        run(setup, False)


def test_transport_errors_never_expose_token_or_url(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("https://api.telegram.org/botSECRET/getChat")

    monkeypatch.setattr(trial.requests, "post", fail)
    with pytest.raises(trial.TrialError) as caught:
        trial.Telegram("SECRET")("getChat", {"chat_id": TARGET})
    assert str(caught.value) == "telegram_request_failed"
    with pytest.raises(trial.TrialError, match="method_not_allowed"):
        trial.Telegram("SECRET")("deleteMessage", {})
