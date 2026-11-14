"""AI agent trả lời tin nhắn riêng Threads để chốt khách (PLAN-171, chủ bot giao toàn quyền 13/11).

Mỗi lượt: đọc cả cuộc trò chuyện → AI trả JSON ``{action, reply, note, bot, hot}``:
- ``reply``: nhắn lại khách (hỏi giá, cách dùng, xin link, tặng Canva…).
- ``handoff``: việc cần chủ bot (khiếu nại, hoàn tiền, lỗi đơn / bảo hành, thanh toán, mua sỉ / đại lý, đòi người thật,
  khách đã làm xong bước nhận Canva) → báo Telegram; có thể kèm một câu giữ chân.
- ``skip``: rác, sàm sỡ, người bán chào hàng, chỉ cảm ơn / thả tim, không liên quan → không trả lời (Requests: không Accept).
Kiến thức: bảng giá AI Store (đọc ``store.sqlite`` chỉ đọc), quy tắc mua Cashbot, luồng tặng Canva của chủ bot, kho tâm lý.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from cashback_bot.messages import BUY_RULE, CART_RULE, ITEM_RULE

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.psych_kb.prompting import guidance_block
from app.features.threads.growth.config import CASHBOT_ZALO_URL, TargetBot, channel_url
from app.features.threads.growth.conversions import cashback_db, store_db
from app.features.threads.adapter import ThreadsSessionInvalidError
from app.features.threads.growth.dm import INBOX, REQUESTS, DmBrowser, DmMessage, signature, unanswered

logger = logging.getLogger(__name__)

ACTIONS = ("reply", "handoff", "skip")
HISTORY = 24          # số tin gần nhất đưa AI
# Link đợt tặng Canva chủ bot vẫn dùng (mã nguồn «canva» trong Cashbot) — giữ nguyên để số khách đợt này gộp một chỗ.
CANVA_URL = "https://t.me/zt_shopee_bot?start=canva"
CATALOG_ITEMS = 25
REPLY_LIMIT = 600
_JSON = re.compile(r"\{.*\}", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_TG_USER = re.compile(r"@([A-Za-z][A-Za-z0-9_]{4,31})\b")


@dataclass(frozen=True)
class Decision:
    action: str
    reply: str = ""
    note: str = ""
    bot: str = ""
    hot: int = 0


def _plain(html_text: str) -> str:
    return _TAG.sub("", html_text).replace("•", "-").strip()


def _ro(path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def catalog(limit: int = CATALOG_ITEMS) -> str:
    """Bảng giá AI Store đang bán (giá khách trả, còn hàng hay hết). Lỗi đọc → chuỗi rỗng (agent không báo giá)."""
    try:
        with closing(_ro(store_db())) as conn:
            rows = conn.execute(
                "SELECT name, price, description, upstream_available FROM products WHERE active = 1 "
                "ORDER BY upstream_available DESC, price LIMIT ?", (limit,)
            ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("growth.dm: đọc bảng giá lỗi: %s", exc)
        return ""
    lines = []
    for r in rows:
        stock = "còn hàng" if r["upstream_available"] else "đang hết"
        desc = " ".join((r["description"] or "").split())[:160]
        price = f"{int(r['price']):,}".replace(",", ".")
        lines.append(f"- {r['name']}: {price}đ ({stock}). {desc}")
    return "\n".join(lines)


def cashbot_user(text: str) -> Optional[str]:
    """Khách gửi username Telegram (luồng tặng Canva): kiểm trong DB Cashbot (chỉ đọc) đã vào bot + đã tạo link chưa."""
    m = _TG_USER.search(text or "")
    if not m:
        return None
    name = m.group(1)
    try:
        with closing(_ro(cashback_db())) as conn:
            row = conn.execute(
                "SELECT telegram_user_id FROM telegram_users WHERE lower(username) = lower(?)", (name,)
            ).fetchone()
            if row is None:
                return f"@{name}: CHƯA thấy trong Cashbot (chưa vào bot hoặc gõ sai tên)"
            links = conn.execute(
                "SELECT COUNT(*) FROM link_requests WHERE telegram_user_id = ? AND link_status = 'created'",
                (row[0],),
            ).fetchone()[0]
    except sqlite3.Error as exc:
        logger.warning("growth.dm: đọc Cashbot lỗi: %s", exc)
        return None
    return f"@{name}: đã vào Cashbot, đã tạo {links} link" + ("" if links else " (CHƯA dán link nào)")


def transcript(messages: List[DmMessage], limit: int = HISTORY) -> str:
    return "\n".join(("Mình: " if m.mine else "Khách: ") + m.text[:500] for m in messages[-limit:])


def build_prompt(handle: str, messages: List[DmMessage], folder: str, store_catalog: str, user_check: Optional[str]) -> str:
    cb_link = channel_url(TargetBot.CASHBOT, "dm")
    ai_link = channel_url(TargetBot.AI_STORE, "dm")
    last = " ".join(m.text for m in messages[-3:] if not m.mine)
    kb = guidance_block(last or transcript(messages, 4), "threads", k=2)
    check = f"\nKiểm tra trong hệ thống: {user_check}\n" if user_check else ""
    where = "Tin nhắn chờ (Requests) — người lạ nhắn lần đầu" if folder == "requests" else "Hộp thư"
    return f"""Bạn là chủ tài khoản Threads @us28qt, đang trả lời tin nhắn riêng để chốt khách. Mục tiêu: khách dùng thử
và quay lại — trả lời đúng câu hỏi, gỡ băn khoăn, dẫn khách vào đúng bot bằng link.

Cuộc trò chuyện với @{handle} ({where}), cũ → mới:
\"\"\"
{transcript(messages)}
\"\"\"
{check}
HAI THỨ MÌNH CÓ
1) Bot hoàn tiền Shopee (Cashbot) — Telegram: {cb_link} · Zalo: {CASHBOT_ZALO_URL} (nhắn «menu»).
   Cách dùng: mở món trên Shopee → Chia sẻ → Sao chép liên kết → dán vào bot → bot báo số hoàn dự kiến + nút Mua.
   {_plain(BUY_RULE)}
   {_plain(CART_RULE)}
   {_plain(ITEM_RULE)}
   Tiền hoàn là ước tính, vào ví trong bot khi sàn trả hoa hồng, rồi rút về tài khoản ngân hàng. Bot không thu phí.
2) AI Pass Store — bot Telegram bán tài khoản / gói AI, giao tự động sau khi chuyển khoản qua mã QR: {ai_link}
   Bảng giá hiện tại (chỉ được báo đúng giá này; món không có trong bảng thì nói chưa có, không hứa):
{store_catalog or "   (không đọc được bảng giá — đừng báo giá, mời khách vào bot xem giá)"}
3) Tặng slot Canva Pro (chương trình của chủ shop): khách vào {CANVA_URL}, dán thử 1 link
   sản phẩm Shopee bất kỳ, rồi nhắn lại username Telegram. Khi khách đã gửi username → action «handoff» (chủ shop gửi slot),
   reply báo khách «mình kiểm tra rồi gửi slot cho bạn nha». Chưa làm bước nào thì hướng dẫn từng bước, nhẹ nhàng.

QUY TẮC
- Trả lời tin CUỐI của khách, đúng câu hỏi. 1–3 câu, tối đa khoảng 350 ký tự, giọng nhắn tin thật (mình / bạn), teencode nhẹ,
  tối đa 1 emoji. Mỗi tin tối đa 1 link, chỉ link ở trên.
- Không hỏi mật khẩu, mã OTP, thông tin thẻ. Không hứa bảo hành / giá / thời gian ngoài bảng giá và mô tả. Không bịa.
- Khách hỏi thẳng «có phải bot / AI trả lời không» → nói thật là trợ lý tự động của shop, cần người thật thì mình báo chủ shop
  (action «handoff»).
- «handoff» khi: khiếu nại, đòi hoàn tiền, lỗi đơn / acc lỗi / bảo hành, chuyển khoản rồi chưa nhận, mua sỉ / làm đại lý,
  đòi gặp người thật, câu hỏi mình không chắc, khách đã gửi username Telegram để nhận Canva.
- «skip» khi: rác, tán tỉnh / sàm sỡ, người bán chào hàng / quảng cáo, chỉ cảm ơn / thả tim / «dạ» không cần đáp,
  tin quá cũ không liên quan, không liên quan gì tới 3 thứ trên.
{kb.text + chr(10) if kb else ''}
Trả về DUY NHẤT một JSON, không giải thích:
{{"action": "reply" | "handoff" | "skip",
 "reply": "...",          // tin gửi khách (rỗng nếu skip; handoff có thể kèm một câu giữ chân)
 "note": "...",           // một câu cho chủ shop: khách cần gì / vì sao handoff / vì sao skip
 "bot": "cashbot" | "ai_store" | "canva" | "none",
 "hot": 0-100}}           // khả năng chốt (mua / dùng thử)
"""


def parse_decision(raw: str) -> Optional[Decision]:
    m = _JSON.search(raw or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    action = str(data.get("action") or "").strip().lower()
    if action not in ACTIONS:
        return None
    reply = " ".join(str(data.get("reply") or "").split()) if action != "skip" else ""
    if action == "reply" and len(reply) < 2:
        return None
    try:
        hot = max(0, min(100, int(data.get("hot") or 0)))
    except (TypeError, ValueError):
        hot = 0
    return Decision(action, reply[:REPLY_LIMIT], str(data.get("note") or "")[:300], str(data.get("bot") or ""), hot)


async def decide(handle: str, messages: List[DmMessage], folder: str) -> Optional[Decision]:
    """None = AI lỗi / không trả JSON hợp lệ → để lượt sau (không đánh dấu đã xử lý)."""
    last_theirs = " ".join(m.text for m in messages if not m.mine)
    prompt = build_prompt(handle, messages, folder, catalog(), cashbot_user(last_theirs))
    try:
        raw, meta = await AIUseCases.generate_text_async(prompt, purpose=AIPurpose.THREADS_REPLY)
    except Exception as exc:
        logger.warning("growth.dm: AI lỗi: %s", exc)
        return None
    decision = parse_decision(raw or "")
    if decision is None:
        logger.info("growth.dm: AI không trả JSON hợp lệ (%s)", (meta or {}).get("fail_reason") or (raw or "")[:120])
    return decision


# ── một nhịp hộp tin ───────────────────────────────────────────
MAX_PER_DAY = 15         # tin gửi đi / tài khoản / 24 giờ (14/11: giảm sau checkpoint 40 → 15)
MAX_PER_HOUR = 4
MAX_PER_THREAD_DAY = 6   # chặn vòng lặp hai bên nhắn qua lại mãi
MAX_OPEN = 8             # số cuộc mở mỗi nhịp
MAX_AGE_DAYS = 14        # cuộc im quá lâu (Requests 1 năm trước…) → bỏ
HOLD = timedelta(hours=24)


def handle_inbox(dmb: DmBrowser, storage, account: str, now: datetime,
                 run: Callable[[Awaitable], Optional[Decision]], decide_fn=None) -> List[Dict]:
    """Đọc Inbox + Requests của ``account``, trả lời / chuyển chủ bot / bỏ qua. Trả danh sách sự kiện để báo cáo.

    Chỉ mở cuộc có chữ hàng đổi so với lần trước. Tin cuối là của mình → không làm gì. AI lỗi → dừng nhịp, không đánh
    dấu (lượt sau thử lại). Gửi lỗi → vẫn đánh dấu đã xử lý (tránh gửi trùng nếu thật ra đã gửi) + báo chủ bot."""
    decide_fn = decide_fn or decide
    events: List[Dict] = []

    def budget() -> bool:
        return (storage.count_dm_sent_since(now - timedelta(days=1), account) < MAX_PER_DAY
                and storage.count_dm_sent_since(now - timedelta(hours=1), account) < MAX_PER_HOUR)

    if not budget():
        return events
    rows = dmb.list(REQUESTS)  # khách lạ nhắn lần đầu, chưa ai đáp → ưu tiên
    rows += dmb.list(INBOX)
    candidates = []
    for row in rows:
        if row.age_days is not None and row.age_days > MAX_AGE_DAYS:
            continue
        state = storage.dm_thread(row.thread_id, account)
        if state and state.get("preview") == row.preview and state.get("folder") == row.folder:
            continue
        candidates.append((row, state))
    for row, state in candidates[:MAX_OPEN]:
        if not budget():
            break
        messages = dmb.read(row.thread_id, row.folder)
        sig = signature(messages)
        tail = unanswered(messages)
        status = (state or {}).get("status") or "open"
        keep = dict(preview=row.preview, status=status, hold_until=(state or {}).get("hold_until"),
                    note=(state or {}).get("note"))
        if not tail or (state and state.get("handled_sig") == sig):
            storage.save_dm_thread(row.thread_id, account, row.handle, row.folder,
                                   handled_sig=(state or {}).get("handled_sig") or sig, **keep)
            continue
        for msg in tail:
            storage.log_dm(row.thread_id, account, row.handle, "in", msg.text)
        theirs = " / ".join(m.text for m in tail)[:300]
        hold = (state or {}).get("hold_until")
        if status == "handoff" and hold and hold > now.isoformat():
            storage.save_dm_thread(row.thread_id, account, row.handle, row.folder, handled_sig=sig, **keep)
            events.append({"handle": row.handle, "folder": row.folder, "action": "handoff_more", "theirs": theirs,
                           "thread_id": row.thread_id})
            continue
        if storage.count_dm_sent_since(now - timedelta(days=1), account, row.thread_id) >= MAX_PER_THREAD_DAY:
            storage.save_dm_thread(row.thread_id, account, row.handle, row.folder, handled_sig=sig,
                                   **{**keep, "status": "handoff", "hold_until": (now + HOLD).isoformat()})
            events.append({"handle": row.handle, "folder": row.folder, "action": "handoff", "theirs": theirs,
                           "note": f"đã nhắn {MAX_PER_THREAD_DAY} tin hôm nay, chuyển anh xử lý tiếp",
                           "thread_id": row.thread_id})
            continue
        decision = run(decide_fn(row.handle, messages, row.folder))
        if decision is None:
            break  # AI lỗi: để lượt sau
        storage.log_dm(row.thread_id, account, row.handle, "note", decision.note or "-", decision.action, decision.hot)
        new_status = {"skip": "ignored" if row.folder == REQUESTS else status, "handoff": "handoff"}.get(
            decision.action, "open")
        hold_until = (now + HOLD).isoformat() if decision.action == "handoff" else None
        event = {"handle": row.handle, "folder": row.folder, "action": decision.action, "theirs": theirs,
                 "reply": decision.reply, "note": decision.note, "hot": decision.hot, "bot": decision.bot,
                 "thread_id": row.thread_id}
        if decision.action != "skip" and decision.reply:
            try:
                dmb.send(row.thread_id, row.folder, decision.reply)
                storage.log_dm(row.thread_id, account, row.handle, "out", decision.reply, decision.action, decision.hot)
            except ThreadsSessionInvalidError:
                raise
            except Exception as exc:
                logger.warning("growth.dm: gửi @%s lỗi: %s", row.handle, exc)
                storage.log_dm(row.thread_id, account, row.handle, "note", f"gửi lỗi: {exc}", "failed")
                event.update(action="failed", note=f"gửi lỗi: {exc} · định gửi: {decision.reply[:120]}")
                new_status, hold_until = "handoff", (now + HOLD).isoformat()
        storage.save_dm_thread(row.thread_id, account, row.handle, row.folder, preview=row.preview, handled_sig=sig,
                               status=new_status, hold_until=hold_until, note=decision.note)
        events.append(event)
        dmb._pause(6.0, 14.0)
    return events
