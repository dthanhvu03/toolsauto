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
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from cashback_bot.messages import BUY_RULE, CART_RULE, ITEM_RULE

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.psych_kb.prompting import guidance_block
from app.features.threads.growth.config import (
    ACCOUNTS, CASHBOT_ZALO_URL, DEFAULT_ACCOUNT, TargetBot, channel_url, load_account_roles,
)
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
_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.|(?:t|telegram|zalo)\.me/)\S+", re.IGNORECASE)
_DOMAIN = re.compile(r"(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}"
                     r"(?::\d{1,5})?(?:[/?#]\S*)?", re.IGNORECASE)
_HANDOFF_PATTERNS = (
    ("refund_or_complaint", re.compile(r"\b(?:hoan (?:lai )?tien|tra (?:lai )?tien|refund|chargeback|khieu nai|complaint)\b")),
    ("human_requested", re.compile(r"\b(?:nguoi that|live agent|(?:gap|noi chuyen voi|ket noi voi|chuyen (?:cho|qua)|"
                                    r"nho|can|goi) (?:duoc )?(?:nhan vien|chu shop|admin)|"
                                    r"(?:speak|talk) to (?:a )?human)\b")),
    ("warranty_or_access", re.compile(r"\b(?:bao hanh|warranty|(?:acc|tai khoan) (?:bi )?loi|"
                                       r"khong dang nhap|khong dung duoc)\b")),
    ("payment_already_made", re.compile(r"\b(?:(?:da|vua) (?:ck|thanh toan|chuyen(?: khoan)?|nap(?: tien)?|"
                                        r"quet (?:ma )?qr)|(?:thanh toan|chuyen khoan|nap tien|quet (?:ma )?qr) "
                                        r"(?:xong|roi)|(?:ck|chuyen(?: khoan)?|nap(?: tien)?)\b.{0,30}\b(?:xong|roi)|"
                                        r"(?:bi )?tru tien|tien bi tru)\b")),
    ("order_support", re.compile(r"\b(?:chua nhan|khong nhan (?:duoc|hang)|ma don|tinh trang don|kiem tra don|"
                                 r"(?:don(?: hang)?|order) (?:cua|bi|loi|chua|sai|hong)|(?:da|vua) (?:mua|dat hang))\b")),
    ("wholesale", re.compile(r"\b(?:mua si|dai ly)\b")),
)
_CASHBACK_TOPIC = re.compile(r"\b(?:bot hoan tien|hoan tien (?:shopee|tiktok)|cashback)\b")
_CASHBACK_PROBLEM = re.compile(r"\b(?:doi|yeu cau|hoan lai|tra lai|khieu nai|refund|chua nhan|khong thay|"
                               r"chua (?:duoc hoan|ve vi|cong)|khong (?:duoc hoan|ve vi|cong)|"
                               r"hoan tien (?:shopee|tiktok) (?:giup|minh muon|cho (?:em|minh|toi)))\b")


@dataclass(frozen=True)
class Decision:
    action: str
    reply: str = ""
    note: str = ""
    bot: str = ""
    hot: int = 0


@dataclass(frozen=True)
class _Scope:
    account: str
    bots: tuple[str, ...]


def _scope(account: str, allowed_bots: Optional[Iterable[str | TargetBot]] = None) -> Optional[_Scope]:
    """Resolve current permissions; omitted/malformed/disabled DM roles cannot open an inbox."""
    if account not in ACCOUNTS:
        return None
    try:
        role = load_account_roles().get(account)
        if role is None or not role.enabled or not role.dm:
            return None
        requested = role.bots if allowed_bots is None else allowed_bots
        if isinstance(requested, (str, TargetBot)):
            requested = (requested,)
        bots = tuple(dict.fromkeys(b.value if isinstance(b, TargetBot) else str(b) for b in requested))
        if not bots or any(b not in {t.value for t in TargetBot} or b not in role.bots for b in bots):
            return None
        return _Scope(account, bots)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _normalized(text: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", (text or "").lower().replace("đ", "d"))
                            if not unicodedata.combining(c)).split())


def interaction_handoff_reason(text: str) -> Optional[str]:
    """Pure support gate shared with public follow-ups; simple price/how-to FAQs stay eligible."""
    value = _normalized(text)
    for reason, pattern in _HANDOFF_PATTERNS:
        if reason == "refund_or_complaint" and _CASHBACK_TOPIC.search(value) and not _CASHBACK_PROBLEM.search(value):
            continue  # Normal cashback product questions are different from refund or missing-money complaints.
        if pattern.search(value):
            return reason
    return None


def _handoff(reason: str) -> Decision:
    return Decision("handoff", note=f"needs_human:{reason}", bot="none")


def _allowed_links(scope: _Scope) -> dict[str, set[str]]:
    links = {b: {channel_url(TargetBot(b), "dm", scope.account)} for b in scope.bots}
    if TargetBot.CASHBOT.value in scope.bots:
        links[TargetBot.CASHBOT.value].add(CASHBOT_ZALO_URL)
        if scope.account == DEFAULT_ACCOUNT:
            links["canva"] = {CANVA_URL}
    return links


def _validate_decision(decision: Decision, scope: _Scope) -> Decision:
    """Model output and legacy injected deciders share the same deterministic send boundary."""
    if not isinstance(decision, Decision) or decision.action not in ACTIONS:
        return _handoff("invalid_decision")
    if decision.action == "skip":
        return Decision("skip", note=decision.note, bot="none")
    # Human handoff never sends an AI acknowledgement or pitch, including injected legacy decisions.
    if decision.action == "handoff":
        return Decision("handoff", note=decision.note or "needs_human:review", bot="none")
    links = _allowed_links(scope)
    if decision.bot not in {*links, "none"}:
        return _handoff("off_role_bot")
    if not isinstance(decision.reply, str) or not 2 <= len(decision.reply.strip()) <= REPLY_LIMIT:
        return _handoff("invalid_reply")
    urls = [match.rstrip(".,;:!?)…") for match in _URL.findall(decision.reply)]
    if (len(urls) > 1 or any(url not in links.get(decision.bot, set()) for url in urls)
            or _DOMAIN.search(_URL.sub("", decision.reply))):
        return _handoff("unapproved_link")
    for key, account in ACCOUNTS.items():
        if key != scope.account and re.search(r"(?<!\w)@?" + re.escape(account.handle) + r"(?!\w)", decision.reply, re.I):
            return _handoff("wrong_identity")
    value = _normalized(decision.reply)
    if TargetBot.AI_STORE.value not in scope.bots and re.search(
        r"\b(?:ai pass store|aipass_shop_bot|capcut|chatgpt|gemini|claude pro|goi ai|tai khoan ai)\b", value
    ):
        return _handoff("off_role_offer")
    if TargetBot.CASHBOT.value not in scope.bots and re.search(
        r"\b(?:cashbot|zt_shopee_bot|canva free|tang (?:slot )?canva|hoan tien shopee|bot hoan tien)\b", value
    ):
        return _handoff("off_role_offer")
    if (TargetBot.AI_STORE.value not in scope.bots and re.search(r"\bcanva\b", value)
            and re.search(r"\bgia\b|\b\d+[.,]?\d*\s*(?:d|dong|k|tr|vnd)\b|₫", value)):
        return _handoff("off_role_offer")
    return decision


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


def build_prompt(handle: str, messages: List[DmMessage], folder: str, store_catalog: str, user_check: Optional[str],
                 *, account: str = DEFAULT_ACCOUNT,
                 allowed_bots: Optional[Iterable[str | TargetBot]] = None) -> str:
    scope = _scope(account, allowed_bots)
    if scope is None:
        raise ValueError("DM account permission unavailable")
    knowledge = []
    if TargetBot.CASHBOT.value in scope.bots:
        cb_link = channel_url(TargetBot.CASHBOT, "dm", account)
        knowledge.append(f"""Bot hoàn tiền Shopee (Cashbot) — Telegram: {cb_link} · Zalo: {CASHBOT_ZALO_URL} (nhắn «menu»).
   Cách dùng: mở món trên Shopee → Chia sẻ → Sao chép liên kết → dán vào bot → bot báo số hoàn dự kiến + nút Mua.
   {_plain(BUY_RULE)}
   {_plain(CART_RULE)}
   {_plain(ITEM_RULE)}
   Tiền hoàn là ước tính, vào ví trong bot khi sàn trả hoa hồng, rồi rút về tài khoản ngân hàng. Bot không thu phí.""")
        if account == DEFAULT_ACCOUNT:
            knowledge.append(f"""Tặng slot Canva Pro (chương trình đã duyệt của chủ shop): khách vào {CANVA_URL},
   dán thử 1 link sản phẩm Shopee rồi nhắn username Telegram. Khách đã gửi username để nhận slot → handoff,
   chủ shop kiểm tra/gửi slot. Không tự cấp slot hay hứa đã kiểm tra.""")
    if TargetBot.AI_STORE.value in scope.bots:
        ai_link = channel_url(TargetBot.AI_STORE, "dm", account)
        knowledge.append(f"""AI Pass Store — bot Telegram bán tài khoản / gói AI: {ai_link}
   Cách mua: xem mô tả món → chọn số lượng → quét QR hoặc dùng số dư ví; tình trạng giao xem trong bot.
   Không hứa giao ngay khi chưa biết trạng thái đơn/tồn hiện tại. Việc chuyển khoản/đơn/bảo hành → handoff.
   Bảng giá đang đọc (chỉ nói đúng bảng này; món ngoài bảng thì mời khách xem trong bot, không hứa):
{store_catalog or '   (không đọc được bảng giá — không báo giá, mời khách vào bot xem thông tin)'}""")
    last = " ".join(m.text for m in messages[-3:] if not m.mine)
    kb = guidance_block(last or transcript(messages, 4), "threads", k=2)
    check = (f"\nKiểm tra trong hệ thống: {user_check}\n"
             if user_check and TargetBot.CASHBOT.value in scope.bots else "")
    where = "Tin nhắn chờ (Requests) — người lạ nhắn lần đầu" if folder == "requests" else "Hộp thư"
    bots = " | ".join(f'"{bot}"' for bot in (*_allowed_links(scope), "none"))
    return f"""Bạn là trợ lý tự động của shop, đang hỗ trợ hộp tin tài khoản Threads @{ACCOUNTS[account].handle}.
Trả lời đúng câu hỏi inbound bằng phạm vi được giao, chỉ giới thiệu đúng bot/link của tài khoản này.
Không giả làm khách từng mua/dùng, không bịa trải nghiệm cá nhân, không tự nhận là chủ shop/người thật.

Cuộc trò chuyện với @{handle} ({where}), cũ → mới:
\"\"\"
{transcript(messages)}
\"\"\"
{check}
PHẠM VI VÀ KIẾN THỨC ĐƯỢC GIAO
{chr(10).join(knowledge)}

QUY TẮC
- Trả lời tin CUỐI của khách, đúng câu hỏi. 1–3 câu, tối đa khoảng 350 ký tự, giọng nhắn tin thật (mình / bạn), teencode nhẹ,
  tối đa 1 emoji. Mỗi tin tối đa 1 link, chỉ link ở trên.
- Chỉ dùng kiến thức/bot/link trong PHẠM VI trên. Không chào bán dịch vụ khác, không đổi mã nguồn tài khoản.
- Không hỏi mật khẩu, mã OTP, thông tin thẻ. Không hứa bảo hành / giá / thời gian ngoài bảng giá và mô tả. Không bịa.
- Khách hỏi thẳng «có phải bot / AI trả lời không» → nói thật là trợ lý tự động của shop, cần người thật thì mình báo chủ shop
  (action «handoff»).
- «handoff» khi: khiếu nại, đòi hoàn tiền, lỗi đơn / acc lỗi / bảo hành, đã chuyển khoản/thanh toán, mua sỉ / làm đại lý,
  đòi gặp người thật, câu hỏi mình không chắc hoặc ngoài phạm vi. Handoff không kèm tin gửi khách.
- «skip» khi: rác, tán tỉnh / sàm sỡ, người bán chào hàng / quảng cáo, chỉ cảm ơn / thả tim / «dạ» không cần đáp,
  tin quá cũ không liên quan, không cần trả lời.
{kb.text + chr(10) if kb else ''}
Trả về DUY NHẤT một JSON, không giải thích:
{{"action": "reply" | "handoff" | "skip",
 "reply": "...",          // tin gửi khách (rỗng nếu skip hoặc handoff)
 "note": "...",           // một câu cho chủ shop: khách cần gì / vì sao handoff / vì sao skip
 "bot": {bots},
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


async def decide(handle: str, messages: List[DmMessage], folder: str, *, account: str = DEFAULT_ACCOUNT,
                 allowed_bots: Optional[Iterable[str | TargetBot]] = None) -> Optional[Decision]:
    """None = AI lỗi / không trả JSON hợp lệ → để lượt sau (không đánh dấu đã xử lý)."""
    scope = _scope(account, allowed_bots)
    if scope is None:
        return None
    tail = unanswered(messages)
    if not tail:
        return Decision("skip", note="no_unanswered_inbound", bot="none")
    last_theirs = " ".join(m.text for m in tail)
    reason = interaction_handoff_reason(last_theirs)
    if reason:
        return _handoff(reason)
    store_catalog = catalog() if TargetBot.AI_STORE.value in scope.bots else ""
    user_check = cashbot_user(last_theirs) if TargetBot.CASHBOT.value in scope.bots else None
    try:
        prompt = build_prompt(handle, messages, folder, store_catalog, user_check,
                              account=account, allowed_bots=scope.bots)
    except ValueError:
        return None
    try:
        raw, meta = await AIUseCases.generate_text_async(prompt, purpose=AIPurpose.THREADS_REPLY)
    except Exception as exc:
        logger.warning("growth.dm: AI lỗi: %s", exc)
        return None
    decision = parse_decision(raw or "")
    if decision is None:
        logger.info("growth.dm: AI không trả JSON hợp lệ (%s)", (meta or {}).get("fail_reason") or "invalid_json")
    return _validate_decision(decision, scope) if decision is not None else None


# ── một nhịp hộp tin ───────────────────────────────────────────
MAX_PER_DAY = 15         # tin gửi đi / tài khoản / 24 giờ (14/11: giảm sau checkpoint 40 → 15)
MAX_PER_HOUR = 4
MAX_PER_THREAD_DAY = 6   # chặn vòng lặp hai bên nhắn qua lại mãi
MAX_OPEN = 8             # số cuộc mở mỗi nhịp
MAX_AGE_DAYS = 14        # cuộc im quá lâu (Requests 1 năm trước…) → bỏ
HOLD = timedelta(hours=24)


def handle_inbox(dmb: DmBrowser, storage, account: str, now: datetime,
                 run: Callable[[Awaitable], Optional[Decision]], decide_fn=None,
                 *, allowed_bots: Optional[Iterable[str | TargetBot]] = None) -> List[Dict]:
    """Đọc Inbox + Requests của ``account``, trả lời / chuyển chủ bot / bỏ qua. Trả danh sách sự kiện để báo cáo.

    Chỉ mở cuộc có chữ hàng đổi so với lần trước. Tin cuối là của mình → không làm gì. AI lỗi → dừng gọi AI trong
    nhịp này, tiếp tục tìm việc hỗ trợ và giữ câu thường cho lượt sau. Gửi lỗi → đánh dấu đã xử lý để tránh gửi trùng."""
    events: List[Dict] = []
    scope = _scope(account, allowed_bots)
    if scope is None:
        return events

    def budget() -> bool:
        return (storage.count_dm_sent_since(now - timedelta(days=1), account) < MAX_PER_DAY
                and storage.count_dm_sent_since(now - timedelta(hours=1), account) < MAX_PER_HOUR)

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
    ai_available = True
    for row, state in candidates[:MAX_OPEN]:
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
        reason = interaction_handoff_reason(" ".join(msg.text for msg in tail))
        hold = (state or {}).get("hold_until")
        on_hold = status == "handoff" and hold and hold > now.isoformat()
        thread_limit = storage.count_dm_sent_since(now - timedelta(days=1), account, row.thread_id) >= MAX_PER_THREAD_DAY
        # Outbound quotas must not silence support. Ordinary questions remain unhandled until a reply is allowed.
        if (not ai_available or not budget()) and not reason and not on_hold and not thread_limit:
            continue
        for msg in tail:
            storage.log_dm(row.thread_id, account, row.handle, "in", msg.text)
        theirs = " / ".join(m.text for m in tail)[:300]
        if on_hold:
            storage.save_dm_thread(row.thread_id, account, row.handle, row.folder, handled_sig=sig, **keep)
            events.append({"handle": row.handle, "folder": row.folder, "action": "handoff_more", "theirs": theirs,
                           "thread_id": row.thread_id, "sent": False})
            continue
        if thread_limit:
            storage.save_dm_thread(row.thread_id, account, row.handle, row.folder, handled_sig=sig,
                                   **{**keep, "status": "handoff", "hold_until": (now + HOLD).isoformat()})
            events.append({"handle": row.handle, "folder": row.folder, "action": "handoff", "theirs": theirs,
                           "note": f"đã nhắn {MAX_PER_THREAD_DAY} tin hôm nay, chuyển anh xử lý tiếp",
                           "thread_id": row.thread_id, "sent": False})
            continue
        if reason:
            decision = _handoff(reason)
        elif decide_fn is None:
            decision = run(decide(row.handle, messages, row.folder, account=account, allowed_bots=scope.bots))
        else:
            # Compatibility for injected three-positional deciders; never exempt their output from the send gate.
            decision = run(decide_fn(row.handle, messages, row.folder))
        if decision is None:
            ai_available = False
            continue
        current_scope = _scope(account, scope.bots)
        decision = (_validate_decision(decision, current_scope) if current_scope else _handoff("permission_changed"))
        if decision.action == "reply" and not budget():
            continue
        storage.log_dm(row.thread_id, account, row.handle, "note", decision.note or "-", decision.action, decision.hot)
        new_status = {"skip": "ignored" if row.folder == REQUESTS else status, "handoff": "handoff"}.get(
            decision.action, "open")
        hold_until = (now + HOLD).isoformat() if decision.action == "handoff" else None
        event = {"handle": row.handle, "folder": row.folder, "action": decision.action, "theirs": theirs,
                 "reply": decision.reply, "note": decision.note, "hot": decision.hot, "bot": decision.bot,
                 "thread_id": row.thread_id, "sent": False}
        if decision.action != "skip" and decision.reply:
            try:
                dmb.send(row.thread_id, row.folder, decision.reply)
                storage.log_dm(row.thread_id, account, row.handle, "out", decision.reply, decision.action, decision.hot)
                event["sent"] = True
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
