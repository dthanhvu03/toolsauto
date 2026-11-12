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
from cashback_bot.messages import BUY_RULE, CART_RULE, ITEM_RULE

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.psych_kb.prompting import guidance_block
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
    url: str = ""  # link món s.shopee.vn trong kho deal — dán cuối bài riêng (chủ bot 12/11)

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
                              int(d.get("cashback") or 0), int(d.get("sold_30d") or 0), str(d.get("url") or "")))
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


def _plain(rule: str) -> str:
    return re.sub(r"<[^>]+>", "", rule).lstrip("• ").strip()


# Lưu ý để đơn được ghi nhận hoàn — lấy NGUYÊN từ Cashbot (trang 🛡️ Lưu ý trước khi mua), sửa ở bot là bài viết theo.
# Chủ bot 06/11: bài đăng phải nhắc «xoá giỏ hàng → bấm link hoàn → thêm lại giỏ».
BUY_NOTES = "\n".join(f"- {_plain(r)}" for r in (CART_RULE, BUY_RULE, ITEM_RULE))
# Threads chỉ nhận bài ≤ 500 ký tự: 11/11 bài riêng 06–12/11 dài 554–918 ký tự đều KHÔNG lên (bài duy nhất lên: 358).
# Chừa chỗ cho link cuối bài và ký tự Threads đếm khác Python (emoji).
POST_LIMIT = 470
_LENGTH_ASK = "Cả bài TỐI ĐA 380 ký tự (Threads chặn bài quá 500 ký tự, link cuối bài đã chiếm ~50). Ngắn gọn."
_LENGTH_ASK_LINKS = "Cả bài TỐI ĐA 280 ký tự (Threads chặn bài quá 500 ký tự; link bot + link món ở cuối đã chiếm ~170). Ngắn gọn."
_NOTES_ASK = f"""BẮT BUỘC có 1 dòng «lưu ý trước khi mua» thật ngắn, giữ đúng ý chính (chọn từ các ý dưới):
{BUY_NOTES}
Ý quan trọng nhất phải nói rõ: món đang nằm sẵn trong giỏ thì XOÁ khỏi giỏ trước, rồi mở lại món đó bằng link bot gửi
(bấm nút Mua của bot) rồi mới thêm vào giỏ / đặt — không thì đơn không được hoàn."""

CART_NOTE = "📌 Lưu ý: món có sẵn trong giỏ thì xoá đi, mở lại bằng link bot gửi rồi mới thêm giỏ / đặt nha, không là ko được hoàn"


def with_buy_note(text: str) -> str:
    """AI quên nhắc chuyện giỏ hàng → chèn câu lưu ý chuẩn (đơn không ghi nhận là khách mất tiền hoàn)."""
    return text if "giỏ" in text.lower() else f"{text.rstrip()}\n{CART_NOTE}"


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
Cuối bài nhắc: link từng món để ở dưới cùng — copy link món dán vào bot Telegram (link bot ở dưới) để được hoàn tiền,
đừng bấm mua thẳng.
KHÔNG viết «{handle}» (trên Threads «@…» là gắn thẻ tài khoản Threads, không mở bot) — link bot tự gắn cuối bài.

Độ dài 4–6 dòng ngắn, mỗi món 1 dòng (tên rút gọn 3–6 chữ + giá). Số hoàn là «dự kiến».
{_LENGTH_ASK if not any(d.url for d in deals) else _LENGTH_ASK_LINKS}
{_NOTES_ASK}
{_STYLE}"""


def _sale_prompt(event: sale_calendar.SaleEvent, today: date, link: str, handle: str) -> str:
    return f"""Viết 1 bài đăng Threads nhắc mọi người chuẩn bị săn sale Shopee {event.label} ({_countdown(event, today)}).

Nội dung: 2–3 mẹo ngắn thật sự hữu ích (gom giỏ trước, lưu mã free ship / mã shop, canh 0h hoặc 12h, so giá trước
khi chốt) và nhắc: trước khi thanh toán thì copy link món dán qua bot Telegram (link dưới) để được hoàn thêm tiền
về tài khoản ngân hàng. KHÔNG viết «{handle}» — link bot tự gắn cuối bài.

Độ dài 4–6 dòng ngắn.
{_LENGTH_ASK}
{_NOTES_ASK}
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


_MENTION = re.compile(r"(?:bot\s+(?:telegram|tele)\s+)?@(?:zt_shopee_bot|aipass_shop_bot)(?![\w.])", re.IGNORECASE)


_PRICE = re.compile(r"\d[\d.,]*\s*(?:đ|k\b|vnđ)", re.IGNORECASE)


def _is_item(line: str) -> bool:
    """Dòng món deal: gạch đầu dòng có giá (69.000đ, 59k)."""
    return line.lstrip().startswith(("-", "•")) and bool(_PRICE.search(line)) and "giỏ" not in line.lower()


def fit_post(lines: List[str], link: str, limit: int = POST_LIMIT) -> List[str]:
    """Bài quá 500 ký tự (Threads không đăng): (1) dòng nhắc giỏ dài → câu nhắc chuẩn ngắn; (2) bỏ dòng phụ ở giữa,
    dài nhất trước; (3) bỏ món từ cuối, giữ ít nhất 1 món; (4) còn dài thì cắt dòng đầu. Luôn giữ dòng đầu, dòng cuối
    (kêu gọi dán link vào bot) và lưu ý giỏ hàng."""
    lines = list(lines)

    def size() -> int:
        return len("\n".join(lines + [link]))

    if size() > limit:
        lines = [CART_NOTE if "giỏ" in x.lower() and len(x) > len(CART_NOTE) else x for x in lines]
    while size() > limit:
        middle = range(1, len(lines) - 1)
        extra = [i for i in middle if lines[i] and "giỏ" not in lines[i].lower() and not _is_item(lines[i])]
        items = [i for i in middle if _is_item(lines[i])]
        if extra:
            del lines[max(extra, key=lambda i: len(lines[i]))]
        elif len(items) > 1:
            del lines[items[-1]]
        else:
            break
    lines = [x for i, x in enumerate(lines) if x or (i and lines[i - 1])]
    over = size() - limit
    if over > 0 and lines:
        lines[0] = lines[0][: max(len(lines[0]) - over - 1, 20)].rstrip(" ,.") + "…"
    return lines


ITEM_LINKS_HEAD = "👇 Link món (copy dán vào bot ở trên để đc hoàn):"
_NAME_NOISE = re.compile(r"\b(?:hot|sale|new|freeship|chính hãng|giá rẻ|siêu rẻ|cao cấp|hàng mới)\b", re.IGNORECASE)


def _short_name(name: str, words: int = 5) -> str:
    """Tên món gọn cho dòng link: bỏ ngoặc, emoji / ký hiệu, chữ quảng cáo (HOT, Freeship…), lấy vài chữ đầu."""
    clean = re.sub(r"[\[【(].*?[\]】)]", " ", name)
    clean = _NAME_NOISE.sub(" ", re.sub(r"[^\w\s.,+%/-]", " ", clean))
    return " ".join(clean.split()[:words]) or name[:24]


def item_links(deals: List[Deal]) -> List[str]:
    """Khối link từng món dán cuối bài riêng (chủ bot 12/11: «dán link shopee xuống phía dưới»). Món không có link → bỏ."""
    rows = [f"- {_short_name(d.name)}: {d.url}" for d in deals if d.url]
    return [ITEM_LINKS_HEAD, *rows] if rows else []


def clean_post(text: str, link: str, footer: Optional[List[str]] = None) -> str:
    """Giữ xuống dòng (bài nhiều dòng), bỏ mọi link AI tự viết, đặt đúng link tracking sau phần thân, rồi ``footer``
    (link từng món) ở dưới cùng; cả bài vừa 500 ký tự."""
    lines: List[str] = []
    for raw in (text or "").strip().strip('"').splitlines():
        line = " ".join(_MENTION.sub("bot Tele", _TME_TOKEN.sub("", raw)).split()).rstrip(" ,:")
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    tail = list(footer or [])
    reserve = len("\n".join(tail)) + 1 if tail else 0
    return "\n".join(fit_post(lines, link, POST_LIMIT - reserve) + [link] + tail)


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
            return OwnPostDraft("sale", clean_post(with_buy_note(text), link), sale_ref)
    fresh = [d for d in load_deals(now, deal_path) if f"deal:{d.item_id}" not in used_refs][:2]  # 3 món là quá 500 ký tự
    if not fresh:
        return None
    sale_line = f"Có thể mở bài bằng: {_countdown(event, today)}." if event else ""
    text = await _ai(_deal_prompt(fresh, link, profile.handle, sale_line))
    if not text:
        return None
    body = clean_post(with_buy_note(text), link, item_links(fresh))
    return OwnPostDraft("deal", body, ",".join(f"deal:{d.item_id}" for d in fresh))


_NOT_WORTH = re.compile(r"^\W*$")

# Người sợ bấm link lạ (chủ bot 12/11): nói điều bot thật sự KHÔNG làm, để họ tự tìm bot thay vì bấm link.
_SAFE_NOTE = {
    TargetBot.CASHBOT: "chỉ cần dán link món Shopee vào bot, tiền hoàn rút về đúng tài khoản ngân hàng của mình.",
    TargetBot.AI_STORE: "xem giá trước rồi mới nạp, chuyển khoản qua mã QR ngân hàng, bot gửi acc tự động.",
}


async def write_followup(bot: TargetBot, our_reply: str, comment: str) -> tuple[str, Optional[str]]:
    """Trả lời người vừa reply mình → ``("answer", câu)`` · ``("skip", None)`` không cần trả lời (cảm ơn, chê, spam…)
    · ``("error", None)`` AI lỗi — để lần sau thử lại, không đánh dấu đã xử lý."""
    if _NOT_WORTH.match(comment or "") or len((comment or "").strip()) < 2:
        return "skip", None
    profile = load_profiles()[bot]
    link = channel_url(bot, "conv")
    kb = guidance_block(comment, "threads", k=2)  # PLAN-170: gợi ý tâm lý theo đúng câu họ nói
    if kb:
        logger.info("growth.followup kb: %s", ", ".join(kb.ids))
    prompt = f"""Bạn là chủ tài khoản Threads. Bạn đã để lại reply sau dưới bài của người khác:
\"\"\"{our_reply}\"\"\"

Có người trả lời lại bạn:
\"\"\"{comment}\"\"\"

Nếu họ hỏi / tò mò / muốn thử về {profile.name} ({profile.handle}) — vd «bot gì», «có thật ko», «dùng sao», «uy tín ko»,
«link đâu» — thì trả lời ngắn gọn, đúng câu hỏi, thật thà (bot đang chạy thật; tiền hoàn là ước tính, về ví trong bot rồi rút
về tài khoản ngân hàng). Hỏi cách dùng thì nhắc: dán link món vào bot, bấm nút Mua của bot rồi đặt; món có sẵn
trong giỏ thì xoá đi, mở lại bằng link bot rồi mới thêm giỏ. Cần link thì đưa: {link}
Nếu họ ngại / sợ bấm link lạ, sợ lừa đảo — KHÔNG đưa link: đồng cảm («cẩn thận vậy là đúng á»), bảo họ tự mở Telegram,
gõ tìm {profile.handle.lstrip("@")} (viết đúng như vậy, không có @); bot không hỏi mật khẩu / mã OTP / thông tin thẻ, {_SAFE_NOTE[bot]}
Nếu họ chỉ cảm ơn / thả cảm xúc / chê / cãi / spam / bán hàng cạnh tranh / không liên quan thì chỉ xuất đúng chữ: SKIP
{kb.text + chr(10) if kb else ''}
Văn phong: 1–2 câu, tối đa 200 ký tự, như người thật nhắn qua lại, teencode vừa phải, không quảng cáo, không chữ «VietQR».
Chỉ xuất câu trả lời (hoặc SKIP), không giải thích."""
    text = await _ai(prompt, min_len=2)
    if not text:
        return "error", None
    if text.upper().startswith("SKIP"):
        return "skip", None
    return "answer", clean_reply(text, link)
