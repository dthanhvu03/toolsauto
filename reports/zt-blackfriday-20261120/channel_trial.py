"""PLAN-181: one additional invite and one silently pinned channel guide."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import requests

from cashback_bot.config import load_settings
from cashback_bot.voucher import parse as parse_voucher

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
READS = {"getChat", "getMe", "getChatMember", "getChatMemberCount"}
WRITES = {"createChatInviteLink", "sendMessage", "pinChatMessage"}


class TrialError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token):
        self._token = token

    def __call__(self, method, params):
        if method not in READS | WRITES:
            raise TrialError("method_not_allowed")
        try:
            response = requests.post("https://api.telegram.org/bot" + self._token + "/" + method,
                                     json=params, timeout=(5, 15))
            data = response.json()
            if response.status_code != 200 or not isinstance(data, dict) or data.get("ok") is not True:
                raise TrialError("telegram_request_failed")
            return data["result"]
        except Exception:
            raise TrialError("telegram_request_failed") from None


def atomic(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def target_channel(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT value FROM bot_state WHERE key='voucher_channel'").fetchone()
    if not row or not re.fullmatch(r"-100\d+", str(row[0])):
        raise TrialError("channel_not_configured")
    return int(row[0])


def validate_content(content):
    if (content.get("plan") != "PLAN-181" or content.get("channel_title") != "ZT báo mã"
            or content.get("source") != "zt_bf26_guide" or content.get("invite_name") != "ZT BF26 Threads P1"):
        raise TrialError("content_identity_mismatch")
    text = content.get("guide_text")
    if not isinstance(text, str) or not 1 <= len(text) <= 4000 or parse_voucher(text) is not None:
        raise TrialError("invalid_guide_or_voucher_trigger")
    expire = datetime.fromisoformat(content["invite_expire_at"])
    if expire.tzinfo is None or expire.astimezone(timezone.utc).isoformat() != "2026-11-30T16:59:59+00:00":
        raise TrialError("invalid_invite_expiry")
    return int(expire.timestamp()), hashlib.sha256(text.encode()).hexdigest()


def readiness(api, target, content, state):
    chat = api("getChat", {"chat_id": target})
    if (chat.get("id") != target or chat.get("type") != "channel"
            or chat.get("title") != content["channel_title"] or chat.get("username")):
        raise TrialError("wrong_channel_or_privacy")
    me = api("getMe", {})
    if not isinstance(me.get("id"), int) or me.get("is_bot") is not True:
        raise TrialError("invalid_bot_identity")
    member = api("getChatMember", {"chat_id": target, "user_id": me["id"]})
    rights = {k: member.get(k) is True for k in ("can_post_messages", "can_edit_messages", "can_invite_users")}
    if (member.get("user", {}).get("id") != me["id"]
            or member.get("status") != "administrator" or not all(rights.values())):
        raise TrialError("insufficient_channel_rights")
    count = api("getChatMemberCount", {"chat_id": target})
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TrialError("invalid_member_count")
    pin = chat.get("pinned_message")
    own = state.get("guide", {}).get("message_id")
    if pin and (pin.get("message_id") != own or pin.get("text") != content["guide_text"]):
        raise TrialError("existing_pin_conflict")
    if state.get("pin", {}).get("status") == "verified" and not pin:
        raise TrialError("previously_verified_pin_missing")
    return {"channel_title": chat["title"], "channel_type": chat["type"], "public_username": False,
            "member_count": count, "bot_rights": rights, "own_guide_pinned": bool(pin),
            "pinned_message_id": pin.get("message_id") if pin else None}


def execute(api, target, content, *, apply=False, folder=FOLDER):
    folder = Path(folder)
    expiry, digest = validate_content(content)
    state_path = folder / "channel-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state and (state.get("content_sha256") != digest or state.get("channel_id") != target):
        raise TrialError("saved_target_or_content_changed")
    if not apply:
        return {"plan": "PLAN-181", "status": "ready", "readiness": readiness(api, target, content, state),
                "saved_steps": {k: state.get(k, {}).get("status") for k in ("invite", "guide", "pin")}}
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "channel.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state and (state.get("content_sha256") != digest or state.get("channel_id") != target):
            raise TrialError("saved_target_or_content_changed")
        ready = readiness(api, target, content, state)
        if not state:
            state = {"plan": "PLAN-181", "channel_id": target, "content_sha256": digest,
                     "baseline_member_count": ready["member_count"], "status": "ready",
                     "started_at": datetime.now(timezone.utc).isoformat()}
        state["readiness"] = ready
        if ready["own_guide_pinned"]:
            state["pin"] = {"status": "verified", "message_id": state["guide"]["message_id"]}
        for key in ("invite", "guide", "pin"):
            if state.get(key, {}).get("status") in ("unknown", "attempting"):
                atomic(state_path, state)
                raise TrialError("unknown_" + key + "_requires_manual_verification")

        def mutate(key, method, params):
            state[key] = {"status": "unknown", "attempted_at": datetime.now(timezone.utc).isoformat()}
            state["status"] = "partial"
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            atomic(state_path, state)
            return api(method, params)

        try:
            if state.get("invite", {}).get("status") != "done":
                if datetime.now(timezone.utc).timestamp() >= expiry:
                    raise TrialError("invite_expired_before_creation")
                invite = mutate("invite", "createChatInviteLink", {
                    "chat_id": target, "name": content["invite_name"], "expire_date": expiry,
                    "creates_join_request": False})
                url = invite.get("invite_link", "")
                if (not isinstance(url, str) or not re.fullmatch(r"https://t\.me/(?:\+|joinchat/)[A-Za-z0-9_-]+", url)
                        or invite.get("name") != content["invite_name"] or invite.get("expire_date") != expiry
                        or invite.get("is_primary") is not False or invite.get("is_revoked") is not False):
                    raise TrialError("invalid_invite_response")
                state["invite"].update(status="done", invite_link=url, name=invite["name"],
                                       expire_date=expiry, is_primary=False, is_revoked=False)
                atomic(state_path, state)
            if state.get("guide", {}).get("status") != "done":
                message = mutate("guide", "sendMessage", {"chat_id": target, "text": content["guide_text"],
                    "disable_notification": True, "link_preview_options": {"is_disabled": True}})
                mid = message.get("message_id")
                if (message.get("chat", {}).get("id") != target or not isinstance(mid, int) or isinstance(mid, bool)
                        or mid <= 0 or message.get("text") != content["guide_text"]):
                    raise TrialError("invalid_guide_response")
                state["guide"].update(status="done", message_id=mid, text=message["text"])
                atomic(state_path, state)
            if state.get("pin", {}).get("status") != "verified":
                ready = readiness(api, target, content, state)  # do not overwrite a newly pinned message
                mid = state["guide"]["message_id"]
                if not ready["own_guide_pinned"]:
                    if mutate("pin", "pinChatMessage", {"chat_id": target, "message_id": mid,
                                                         "disable_notification": True}) is not True:
                        raise TrialError("invalid_pin_response")
                ready = readiness(api, target, content, state)
                if not ready["own_guide_pinned"]:
                    raise TrialError("pin_not_verified")
                state["pin"] = {"status": "verified", "message_id": mid}
            state.update(status="completed", readiness=readiness(api, target, content, state),
                         updated_at=datetime.now(timezone.utc).isoformat())
            atomic(state_path, state)
            return state
        except Exception as exc:
            state["last_error_type"] = type(exc).__name__
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            atomic(state_path, state)
            raise TrialError(str(exc) if isinstance(exc, TrialError) else "channel_action_uncertain") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        settings = load_settings(dotenv_path=ROOT / ".env")
        db = Path(settings.db_path)
        target = target_channel(db if db.is_absolute() else ROOT / db)
        result = execute(Telegram(settings.bot_token), target, json.loads((FOLDER / "content.json").read_text()),
                         apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked_or_unknown", "error": str(exc) if isinstance(exc, TrialError)
                          else type(exc).__name__}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
