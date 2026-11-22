"""Pure opportunity gate for the two existing Threads Growth offers (PLAN-178).

This is a conservative demand filter, not evidence that an author became a customer.
It does not read storage, call a model, or authorize a message.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.features.threads.growth.config import TargetBot


@dataclass(frozen=True)
class OpportunityDecision:
    eligible: bool
    reason: str
    lane: str = "buyer"


def _plain(content: str) -> str:
    text = unicodedata.normalize("NFKD", (content or "").lower().replace("đ", "d"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"https?://\S+", " ", text)
    return " ".join(re.sub(r"[^a-z0-9?%]+", " ", text).split())


_JOBS = re.compile(
    r"\b(?:tuyen dung|tuyen (?:nhan vien|ctv|cong tac vien|editor|content|thanh vien|tts)|"
    r"tim (?:viec|job|cong viec|dong doi)|viec lam|ung tuyen|thuc tap sinh|"
    r"part time|full time|gui cv|nhan jd|xin jd|co job|co jod|luong cung)\b"
)
_SELLER = re.compile(
    r"\b(?:nhan order|nhan don|gia si|gia chi|mua ngay|san ngay|chot don|"
    r"link (?:o |trong )?bio|len don|lien he zalo|ib shop|ib ngay)\b|"
    r"^(?:ban (?:cap\s?cut|shopee|acc|tai khoan|goi|hang)|cung cap\b|phan phoi\b)|"
    r"\b(?:shop|minh|em|toi|tui|ben minh|ben em|chung minh)\s+"
    r"(?:co\s+)?(?:ban|cung cap|phan phoi|nhan order)\b|"
    r"\b(?:san hang|con hang)\b(?!\s+(?:khong|ko|k)\b)(?!\s*\?)"
)
_SUPPORT = re.compile(
    r"\b(?:refund|tra hang|hoan tra|huy don|khieu nai|boc phot|lua dao|bao hanh|"
    r"doi tra|chua nhan (?:duoc )?(?:hang|acc|tai khoan|tien)|"
    r"da (?:chuyen khoan|thanh toan)|mat tien|bi tru tien|giao (?:sai|thieu)|"
    r"acc loi|tai khoan loi|quen mat khau|bi khoa (?:acc|tai khoan))\b"
)
_REFUSAL = re.compile(
    r"\b(?:khong|ko|k|chang|chua)\s+(?:muon|can|dinh)\s+"
    r"(?:mua|dung|xai|nang cap|gia han)\b|"
    r"\b(?:dung|khong|ko) mua\b|\b(?:khong|ko) co nhu cau\b"
)
_CAPCUT = re.compile(r"\bcap\s?cut\b")
_FREE = re.compile(r"\b(?:mien phi|free|crack|mod|khong mat phi|khong ton tien)\b")
_PAID_ACCEPTED = re.compile(
    r"\b(?:khong can (?:mien phi|free)|(?:tra|co|mat) phi (?:cung )?duoc|"
    r"chap nhan tra phi|san sang tra phi)\b|"
    r"\b(?:dang dung|dang xai)\b.{0,35}\b(?:free|mien phi)\b.{0,35}"
    r"\b(?:muon|can|dinh)\b.{0,15}\b(?:mua|nang cap)\b"
)
_OFFER_MISMATCH = re.compile(
    r"\b(?:vinh vien|lifetime|chinh chu|tai khoan ca nhan|acc ca nhan|"
    r"(?:[2-9]|1[0-2]|hai|ba|sau|muoi hai) thang|(?:1|mot) nam|"
    r"(?:[3-9]|ba|bon|nam) thiet bi)\b"
)
_HAS_ACCESS = re.compile(
    r"\b(?:da co|dang co|dang dung|da mua|vua mua|co san)\s+"
    r"(?:(?:goi|tai khoan|acc|ban|cai|mot)\s+){0,3}cap\s?cut\s+pro\b|"
    r"\bcap\s?cut\s+pro\b.{0,25}\b(?:mua roi|con han|dang co)\b"
)
_EXPIRED = re.compile(r"\b(?:het han|het goi|sap het han|can gia han|muon gia han)\b")
_ACCESS_NEED = re.compile(
    r"\b(?:can|muon|dinh|dang tim|tim cho|tim noi|tim nguoi|tim shop)\b.{0,50}"
    r"\b(?:mua|thue|nang cap|gia han|tai khoan|acc|goi|pro)\b|"
    r"\b(?:mua o dau|mua cho nao|(?:cho|ban|shop) nao ban|ai ban|ai co ban|co ai ban|"
    r"xin (?:link|cho|noi) mua|cho (?:minh|em|toi) (?:xin )?(?:link|cho|noi) mua|"
    r"nang cap|gia han|het han)\b"
)
_QUESTION = re.compile(
    r"\?|\b(?:khong a|k a|o dau|cho nao|lam sao|the nao|bao nhieu|"
    r"cach nao|ai co|co ai|ai ban|co ban|nen mua)\b"
)
_AVAILABILITY_QUESTION = re.compile(r"\b(?:con hang|co san)\s*(?:khong|ko|k\b|\?)")
_HELP_TOPIC = re.compile(
    r"\b(?:(?:xuat|luu) (?:duoc )?(?:video|clip)|export|phu de|subtitle|"
    r"tai nguyen pro|hieu ung pro|asset pro|"
    r"bao (?:can |yeu cau )?pro|template (?:(?:yeu cau|can|doi) )?pro|"
    r"watermark|font|tach nen|am thanh|nhac pro)\b"
)
_HELP_QUESTION = re.compile(
    r"\?|\b(?:lam sao|the nao|cach nao|tai sao|vi sao|ai biet|hoi cach|"
    r"khong (?:xuat|luu|export|them|hien|tao|tach|tim)|bi loi|bao loi|"
    r"khong duoc|can giup|giup (?:minh|em|toi))\b"
)
_GENERAL_EDITING = re.compile(r"\b(?:len xu huong|viral|trieu view|edit dep|tang view|tang follow)\b")
_DIRECT_PURCHASE = re.compile(
    r"\b(?:mua|thue|gia han|gia bao nhieu|con hang)\b|"
    r"\b(?:muon|dinh|dang tim)\b.{0,25}\bnang cap\b"
)
_HELP_URL = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|mailto:|tel:|tg:|www\.|t\.me/|zalo\.me/)|"
    r"(?<![\w.])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b",
    re.IGNORECASE,
)
_HELP_OFFER = re.compile(
    r"\b(?:shop|bot|inbox|lien he|ib|mua|thue|nang cap|dang ky|goi 30 ngay|"
    r"cap san|gia re|gia hien tai|gia chi|xem gia|t\.me|telegram|zalo)\b"
)
_ECOM = re.compile(r"\b(?:shopee|tiktok(?: shop)?)\b")
_SHOPPING_NEED = re.compile(
    r"\b(?:can|muon|dinh|sap|chuan bi|dang tim|tim|xin|san|"
    r"ai co|co ai|lam sao|cach nao|the nao|ma nao|cho nao)\b"
)
_SHOPPING_SUBJECT = re.compile(
    r"\b(?:mua|dat|chot|order|sale|deal|voucher|ma|giam gia|phi ship|"
    r"freeship|hoan tien|hoan xu|cashback|gio hang|tiet kiem)\b"
)
_OTHER_AI_PRODUCT = re.compile(
    r"\b(?:chat\s?gpt|gpt|claude|canva|gemini|midjourney|perplexity|elsa)\b"
)
_TESTIMONIAL = re.compile(
    r"\b(?:minh|toi|tui|tao|em|t)\s+(?:(?:da|vua|tung|dang|thuong|hay)\s+)?"
    r"(?:mua|dung|xai|test|lay|su dung|nhan hoan|nhan tien hoan)\b|"
    r"\b(?:mua|dung|xai|test|nhan hoan) roi\b"
)
_UNSUPPORTED_CLAIM = re.compile(
    r"\b(?:bao hanh|bao dam|cam ket|dam bao|con hang|san hang|het hang|"
    r"giao ngay|nhan ngay|tuc thi|re nhat|tot nhat|giam gia|uu dai)\b|"
    r"\b\d+\s*%"
)
_CASHBOT_GUARANTEE = re.compile(r"\b(?:bao hanh|bao dam|cam ket|dam bao)\b|\b100\s*%")
_SPECIFIC_PRICE = re.compile(
    r"\b\d[\d.,]*\s*(?:k\b|dong\b|vnd\b|usd\b|dola\b|nghin\b|ngan\b|trieu\b)|"
    r"\bgia\s+(?:chi\s+)?\d"
)
_CURRENCY_PRICE = re.compile(r"\d[\d.,]*\s*[đ₫]|\b\d[\d.,]{2,}\s*d\b", re.IGNORECASE)


def is_seller_offer(content: str) -> bool:
    """Specific supply-side language; a buyer saying inbox/freeship is not a seller."""
    return bool(_SELLER.search(_plain(content)))


def qualify_opportunity(content: str, bot_type: TargetBot | str) -> OpportunityDecision:
    """Require an explicit, compatible need before the existing model/sender path."""
    try:
        target = TargetBot(bot_type)
    except (TypeError, ValueError):
        return OpportunityDecision(False, "unknown_target")
    text = _plain(content)
    if not text:
        return OpportunityDecision(False, "empty_content")
    if _JOBS.search(text):
        return OpportunityDecision(False, "recruitment_or_job")
    if _SELLER.search(text):
        return OpportunityDecision(False, "seller_or_promotion")
    if _SUPPORT.search(text):
        return OpportunityDecision(False, "support_or_dispute")
    if _REFUSAL.search(text):
        return OpportunityDecision(False, "purchase_refusal")
    if target == TargetBot.AI_STORE:
        if not _CAPCUT.search(text):
            return OpportunityDecision(False, "no_matching_product")
        if _FREE.search(text) and not _PAID_ACCEPTED.search(text):
            return OpportunityDecision(False, "free_only")
        if _OFFER_MISMATCH.search(text):
            return OpportunityDecision(False, "offer_mismatch")
        if (_HELP_TOPIC.search(text) and _HELP_QUESTION.search(text)
                and not _GENERAL_EDITING.search(text)
                and not _DIRECT_PURCHASE.search(text)):
            return OpportunityDecision(True, "qualified_capcut_help", "help_first")
        if _HAS_ACCESS.search(text) and not _EXPIRED.search(text):
            return OpportunityDecision(False, "already_has_access")
        if _ACCESS_NEED.search(text) or _AVAILABILITY_QUESTION.search(text) or (
            _QUESTION.search(text)
            and ("mua" in text.split() or ("pro" in text.split() and "gia" in text.split()))
        ):
            return OpportunityDecision(True, "qualified_capcut_need")
        return OpportunityDecision(False, "no_purchase_need")
    if not _ECOM.search(text):
        return OpportunityDecision(False, "no_matching_platform")
    if _SHOPPING_SUBJECT.search(text) and (
        _SHOPPING_NEED.search(text) or _QUESTION.search(text)
    ):
        return OpportunityDecision(True, "qualified_shopping_need")
    return OpportunityDecision(False, "no_shopping_need")


def qualify_reply(content: str, bot_type: TargetBot | str, reply: str) -> OpportunityDecision:
    """Check the opportunity and the copy without rewriting a persisted queue row."""
    opportunity = qualify_opportunity(content, bot_type)
    if not opportunity.eligible:
        return opportunity
    if opportunity.lane == "help_first":
        return qualify_help_reply_copy(TargetBot(bot_type), reply)
    return qualify_reply_copy(TargetBot(bot_type), reply)


def qualify_help_reply_copy(target: TargetBot, reply: str) -> OpportunityDecision:
    """A help-only reply cannot turn a technical question into an offer or URL."""
    if _HELP_URL.search(unicodedata.normalize("NFKC", reply or "")):
        return OpportunityDecision(False, "help_link_not_allowed", "help_first")
    if _HELP_OFFER.search(_plain(reply)):
        return OpportunityDecision(False, "help_offer_not_allowed", "help_first")
    copy = qualify_reply_copy(target, reply)
    return OpportunityDecision(copy.eligible, copy.reason, "help_first")


def qualify_reply_copy(target: TargetBot, reply: str) -> OpportunityDecision:
    """Reject ungrounded claims, including specific Store prices lacking a live catalog."""
    text = _plain(reply)
    if not text:
        return OpportunityDecision(False, "empty_reply")
    if target == TargetBot.AI_STORE and _OTHER_AI_PRODUCT.search(text):
        return OpportunityDecision(False, "cross_product_reply")
    if _TESTIMONIAL.search(text):
        return OpportunityDecision(False, "personal_testimonial")
    claim_text = re.sub(r"\bkhong\s+(?:bao dam|cam ket|dam bao)\b", "", text)
    claims = _UNSUPPORTED_CLAIM if target == TargetBot.AI_STORE else _CASHBOT_GUARANTEE
    if claims.search(claim_text):
        return OpportunityDecision(False, "unsupported_claim")
    if target == TargetBot.AI_STORE and (
        _SPECIFIC_PRICE.search(text)
        or _CURRENCY_PRICE.search(re.sub(r"https?://\S+", "", reply or ""))
    ):
        return OpportunityDecision(False, "ungrounded_price_claim")
    return OpportunityDecision(True, "qualified_reply")
