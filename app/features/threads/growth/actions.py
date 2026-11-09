"""Thao tác dùng chung cho web + Telegram (PLAN-158): duyệt / bỏ / đổi A-B / bật-tắt / tổng quan."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core import settings
from app.features.threads.growth import conversions, notify
from app.features.threads.growth import session as growth_session
from app.features.threads.growth.config import (
    ACCOUNTS,
    ABVariant,
    TargetBot,
    bio_url,
    load_account_roles,
    load_limits,
    load_worker_config,
    save_account_role,
)
from app.features.threads.growth.runner import GrowthRunner

_runner: Optional[GrowthRunner] = None


def runner() -> GrowthRunner:
    global _runner
    if _runner is None:
        _runner = GrowthRunner()
    return _runner


class ActionError(ValueError):
    pass


def _editable(post_id: int) -> Dict[str, Any]:
    post = runner().storage.get_post_by_id(post_id)
    if not post:
        raise ActionError(f"Không có bài #{post_id}")
    if post["status"] not in ("pending", "failed", "approved"):
        raise ActionError(f"Bài #{post_id} đang ở trạng thái {post['status']}")
    return post


def approve(post_id: int, reply: Optional[str] = None) -> Dict[str, Any]:
    """Duyệt → worker đăng ở lượt tới (trong hạn mức). Bài lỗi duyệt lại = đăng lại."""
    _editable(post_id)
    text = (reply or "").strip() or None
    if text is not None and len(text) > 500:
        raise ActionError("Reply tối đa 500 ký tự")
    return runner().approve_and_prepare(post_id, text)


def reject(post_id: int, reason: str = "user_rejected") -> Dict[str, Any]:
    _editable(post_id)
    runner().reject(post_id, reason)
    return runner().storage.get_post_by_id(post_id)


def switch(post_id: int, variant: Optional[str] = None) -> Dict[str, Any]:
    post = _editable(post_id)
    target = ABVariant(variant) if variant else (ABVariant.VARIANT_B if post["variant"] == "A" else ABVariant.VARIANT_A)
    return asyncio.run(runner().switch_variant(post_id, target))


def set_enabled(db: Session, enabled: bool, by: str) -> bool:
    if enabled and not growth_session.status(db).ready:
        raise ActionError("Chưa đăng nhập Threads — bấm «Đăng nhập Threads» trước")
    settings.upsert_setting(db, "growth.enabled", "true" if enabled else "false", updated_by=by)
    return enabled


def _account_rows(db: Session) -> list:
    """Mỗi tài khoản: vai, đăng nhập, hạn mức riêng đang dùng, link bio (PLAN-167)."""
    r = runner()
    rows = []
    for key, role in load_account_roles().items():
        acc = ACCOUNTS[key]
        st = growth_session.status(db, key)
        quota = r.posting_quota(account=key, max_per_day=role.max_per_day, max_per_hour=role.max_per_hour)
        lim = load_limits()
        rows.append({
            "key": key,
            "handle": acc.handle,
            "profile": acc.profile,
            "running": role.enabled and st.ready,
            "role": {**asdict(role), "bots": list(role.bots)},
            "login": {"login_status": st.login_status, "ready": st.ready, "login_error": st.login_error},
            "quota": {**asdict(quota),
                      "max_per_day": role.max_per_day if role.max_per_day is not None else lim.max_replies_per_day,
                      "max_per_hour": role.max_per_hour if role.max_per_hour is not None else lim.max_replies_per_hour},
            "bio_links": {b.value: bio_url(b, key) for b in TargetBot},
        })
    return rows


def update_account(key: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Đổi vai một tài khoản từ web: bật/tắt, bot mời, hạn mức riêng, bài riêng."""
    if key not in ACCOUNTS:
        raise ActionError(f"Không có tài khoản {key}")
    allowed = {"enabled", "bots", "max_per_day", "max_per_hour", "own_posts"}
    clean = {k: v for k, v in changes.items() if k in allowed}
    if "bots" in clean and not [b for b in clean["bots"] or [] if b in {t.value for t in TargetBot}]:
        raise ActionError("Chọn ít nhất một bot")
    role = save_account_role(key, clean)
    return {**asdict(role), "bots": list(role.bots)}


def overview(db: Session) -> Dict[str, Any]:
    r = runner()
    st = growth_session.status(db)
    quota = r.posting_quota()
    return {
        "enabled": load_worker_config().enabled,
        "worker": asdict(load_worker_config()),
        "limits": asdict(load_limits()),
        "login": {**asdict(st), "ready": st.ready},
        "quota": asdict(quota),
        "stats": r.get_ab_summary(),
        # PLAN-167: tài khoản Threads + reply theo tài khoản × bot + link bio riêng để đếm khách theo tài khoản.
        "accounts": _account_rows(db),
        "account_stats": r.storage.get_account_stats(),
        "customers": conversions.report(),
        "counts": {s: len(r.storage.list_posts(s, limit=1000)) for s in ("pending", "approved", "posted", "failed")},
        "settings_url": "/app/settings",
    }


# ── Telegram (gọi qua feature_hooks, đăng ký ở app/bootstrap_hooks.py) ──────────────
def telegram_callback(db: Session, target: str) -> tuple[bool, str, Optional[str]]:
    """Nút ``gr:<lệnh>[:<id>]``. Trả (ok, câu trả lời nút, tin nhắn gửi thêm hoặc None) — không ném."""
    cmd, _, raw_id = target.partition(":")
    try:
        if cmd in ("on", "off"):
            set_enabled(db, cmd == "on", by="telegram")
            return True, "Đã bật" if cmd == "on" else "Đã tắt", None
        post_id = int(raw_id)
        if cmd == "ok":
            approve(post_id)
            return True, f"#{post_id} sẽ được đăng ở lượt tới", None
        if cmd == "no":
            reject(post_id)
            return True, f"Đã bỏ #{post_id}", None
        if cmd == "ab":
            post = switch(post_id)
            return True, f"#{post_id} sang biến thể {post['variant']}", notify.pending_text(post)
    except (ActionError, ValueError) as exc:
        return False, str(exc)[:180], None
    return False, "Nút không hợp lệ", None


def telegram_summary(db: Session) -> tuple[str, list]:
    data = overview(db)
    text = notify.summary_text(
        data["stats"], runner().posting_quota(), data["enabled"], data["login"]["login_status"], data["customers"]
    )
    return text, notify.toggle_buttons(data["enabled"])
