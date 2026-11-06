"""Nội dung tự tạo cho Threads Growth (PLAN-159): bài riêng trên tài khoản và câu trả lời người hỏi lại.

- Deal: CHỈ ĐỌC kho deal Cashbot (``bot_state.deals_pool`` trong data/cashback.sqlite, PLAN-100) — món đang ở giá thấp
  nhất 30 ngày, bot đã kiểm lịch sử giá. Không gọi Shopee / AddLiveTag.
- Dịp sale: ``cashback_bot.sale_calendar`` (hàm thuần).
- AI viết bằng ``AIPurpose.THREADS_REPLY``. AI lỗi → trả None: KHÔNG đăng câu mẫu lên tường / trả lời người ta.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from cashback_bot import sale_calendar

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.threads.growth.config import TargetBot, channel_url, load_profiles
from app.features.threads.growth.conversions import cashback_db
from app.features.threads.growth.evaluator import _TME_TOKEN, clean_reply

logger = logging.getLogger(__name__)

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
DEAL_FRESH = timedelta(hours=6)  # deal phải được bot thấy lại gần đây (giá có thể đã đổi)
SALE_LOOKAHEAD_DAYS = 5


@dataclass(frozen=True)
class Deal:
    item_id: int
    name: str
    price: int
    usual: int
    cashback: int
    sold_30d: int

    @property
    def off_pct(self) -> int:
        return round(100 * (1 - self.price / self.usual)) if self.usual else 0


def _vnd(n: int) -> str:
    return f"{n:,}đ".replace(",", ".")


def load_deals(now: datetime, path: Optional[Path] = None) -> List[Deal]:
    """Món còn hời trong kho deal Cashbot, giảm sâu nhất trước. Lỗi đọc DB → [] (không làm hỏng vòng)."""
    path = path or cashback_db()
    if not path.exists():
        return []
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)) as c:
            rows = dict(c.execute(
                "SELECT key, value FROM bot_state WHERE key IN ('deals_pool', 'deals_removed')").fetchall())
    except sqlite3.Error as exc:
        logger.warning("growth.content: đọc kho deal lỗi: %s", exc)
        return []
    try:
        pool: Dict[str, dict] = json.loads(rows.get("deals_pool") or "{}")
        removed = set(json.loads(rows.get("deals_removed") or "[]"))
    except (TypeError, ValueError):
        return []
    since = (now - DEAL_FRESH).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    deals = []
    for d in pool.values():
        try:
            if d.get("seen", "") < since or d["item_id"] in removed or not d.get("lowest_30d"):
                continue
            deals.append(Deal(int(d["item_id"]), str(d["name"]), int(d["price"]), int(d["usual"]),
                              int(d.get("cashback") or 0), int(d.get("sold_30d") or 0)))
        except (KeyError, TypeError, ValueError):
            continue
    deals.sort(key=lambda x: (-x.off_pct, -x.sold_30d))
    return deals


def next_sale(now: datetime, days: int = SALE_LOOKAHEAD_DAYS) -> Optional[sale_calendar.SaleEvent]:
    """Dịp sale lớn (không tính mini) trong ``days`` ngày tới, kể cả hôm nay."""
    today = now.astimezone(ICT).date()
    found = [e for e in sale_calendar.events(today, today + timedelta(days=days)) if e.tier != "mini"]
    return found[0] if found else None


def _countdown(event: sale_calendar.SaleEvent, today: date) -> str:
    left = (event.day - today).days
    if left <= 0:
        return f"HÔM NAY là {event.label}"
    if left == 1:
        return f"đêm nay 0h mở sale {event.label}"
    return f"còn {left} ngày nữa là {event.label}"


_STYLE = """Văn phong — viết y như người thật trên Threads, không như quảng cáo:
- Giọng chia sẻ cá nhân, xưng t / mình, gọi mấy bà / mn. Teencode vừa phải (ko, đc, nha, á, nè). Tối đa 2 emoji.
- KHÔNG «hời phết», «đỉnh chóp», «đừng bỏ lỡ», không dấu chấm than liên tục, không hashtag.
- KHÔNG dùng chữ «VietQR» — tiền hoàn nói «về tài khoản ngân hàng».
- KHÔNG bịa số liệu ngoài những số được cho. KHÔNG lộ là AI viết.
Chỉ xuất đúng nội dung bài, không giải thích, không ngoặc kép."""


def _deal_prompt(deals: List[Deal], link: str, handle: str, sale_line: str) -> str:
    lines = "\n".join(
        f"- {d.name[:90]} · giá {_vnd(d.price)} (thường {_vnd(d.usual)}, thấp nhất 30 ngày)"
        + (f" · dán link qua bot hoàn thêm khoảng {_vnd(d.cashback)}" if d.cashback else "")
        for d in deals
    )
    return f"""Viết 1 bài đăng Threads chia sẻ món Shopee đang rẻ thật (bot đã kiểm lịch sử giá 30 ngày).

Món:
{lines}

{sale_line}
Cuối bài nhắc: muốn mua thì tìm món trên Shopee, copy link dán vào bot Telegram {handle} để được hoàn tiền,
và để nguyên link này: {link}

Độ dài 3–6 dòng ngắn, mỗi món 1 dòng (tên rút gọn dễ hiểu + giá). Số hoàn là «dự kiến».
{_STYLE}"""


def _sale_prompt(event: sale_calendar.SaleEvent, today: date, link: str, handle: str) -> str:
    return f"""Viết 1 bài đăng Threads nhắc mọi người chuẩn bị săn sale Shopee {event.label} ({_countdown(event, today)}).

Nội dung: 2–3 mẹo ngắn thật sự hữu ích (gom giỏ trước, lưu mã free ship / mã shop, canh 0h hoặc 12h, so giá trước
khi chốt) và nhắc: trước khi thanh toán thì copy link món dán qua bot Telegram {handle} để được hoàn thêm tiền
về tài khoản ngân hàng. Để nguyên link: {link}

Độ dài 3–6 dòng ngắn.
{_STYLE}"""


async def _ai(prompt: str, min_len: int = 20) -> Optional[str]:
    try:
        text, meta = await AIUseCases.generate_text_async(prompt, purpose=AIPurpose.THREADS_REPLY)
    except Exception as exc:
        logger.warning("growth.content: AI lỗi: %s", exc)
        return None
    text = (text or "").strip().strip('"').strip()
    if len(text) < min_len:
        logger.info("growth.content: AI không viết được (%s)", (meta or {}).get("fail_reason") or "rỗng")
        return None
    return text


def clean_post(text: str, link: str) -> str:
    """Giữ xuống dòng (bài nhiều dòng), bỏ mọi link AI tự viết, đặt đúng link tracking ở dòng cuối."""
    lines: List[str] = []
    for raw in (text or "").strip().strip('"').splitlines():
        line = " ".join(_TME_TOKEN.sub("", raw).split()).rstrip(" ,:")
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines + [link])


@dataclass(frozen=True)
class OwnPostDraft:
    kind: str  # deal · sale
    text: str
    ref: str  # item id các món / mã dịp sale — tránh đăng lặp


async def write_own_post(now: datetime, used_refs: set[str], deal_path: Optional[Path] = None) -> Optional[OwnPostDraft]:
    """Bài riêng cho vòng này: có dịp sale lớn sắp tới thì xen bài nhắc sale (1 bài / ngày), còn lại là bài deal."""
    profile = load_profiles()[TargetBot.CASHBOT]
    link = channel_url(TargetBot.CASHBOT, "post")
    today = now.astimezone(ICT).date()
    event = next_sale(now)
    sale_ref = f"sale:{event.day.isoformat()}:{today.isoformat()}" if event else ""
    if event and sale_ref not in used_refs:
        text = await _ai(_sale_prompt(event, today, link, profile.handle))
        if text:
            return OwnPostDraft("sale", clean_post(text, link), sale_ref)
    fresh = [d for d in load_deals(now, deal_path) if f"deal:{d.item_id}" not in used_refs][:3]
    if not fresh:
        return None
    sale_line = f"Có thể mở bài bằng: {_countdown(event, today)}." if event else ""
    text = await _ai(_deal_prompt(fresh, link, profile.handle, sale_line))
    if not text:
        return None
    return OwnPostDraft("deal", clean_post(text, link), ",".join(f"deal:{d.item_id}" for d in fresh))


_NOT_WORTH = re.compile(r"^\W*$")


async def write_followup(bot: TargetBot, our_reply: str, comment: str) -> tuple[str, Optional[str]]:
    """Trả lời người vừa reply mình → ``("answer", câu)`` · ``("skip", None)`` không cần trả lời (cảm ơn, chê, spam…)
    · ``("error", None)`` AI lỗi — để lần sau thử lại, không đánh dấu đã xử lý."""
    if _NOT_WORTH.match(comment or "") or len((comment or "").strip()) < 2:
        return "skip", None
    profile = load_profiles()[bot]
    link = channel_url(bot, "conv")
    prompt = f"""Bạn là chủ tài khoản Threads. Bạn đã để lại reply sau dưới bài của người khác:
\"\"\"{our_reply}\"\"\"

Có người trả lời lại bạn:
\"\"\"{comment}\"\"\"

Nếu họ hỏi / tò mò / muốn thử về {profile.name} ({profile.handle}) — vd «bot gì», «có thật ko», «dùng sao», «uy tín ko»,
«link đâu» — thì trả lời ngắn gọn, đúng câu hỏi, thật thà (bot đang chạy thật; tiền hoàn là ước tính, về ví trong bot rồi rút
về tài khoản ngân hàng). Cần link thì đưa: {link}
Nếu họ chỉ cảm ơn / thả cảm xúc / chê / cãi / spam / bán hàng cạnh tranh / không liên quan thì chỉ xuất đúng chữ: SKIP

Văn phong: 1–2 câu, tối đa 200 ký tự, như người thật nhắn qua lại, teencode vừa phải, không quảng cáo, không chữ «VietQR».
Chỉ xuất câu trả lời (hoặc SKIP), không giải thích."""
    text = await _ai(prompt, min_len=2)
    if not text:
        return "error", None
    if text.upper().startswith("SKIP"):
        return "skip", None
    return "answer", clean_reply(text, link)
