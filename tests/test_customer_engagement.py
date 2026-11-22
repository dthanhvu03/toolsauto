"""PLAN-178: account permissions and deterministic customer-interaction send boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.features.threads.growth import dm_agent
from app.features.threads.growth.config import AccountRole, TargetBot, channel_url
from app.features.threads.growth.dm import INBOX, REQUESTS, DmMessage, DmRow
from app.features.threads.growth.dm_agent import Decision
from app.features.threads.growth.storage import GrowthStorage

NOW = datetime.now(timezone.utc)


class Inbox:
    def __init__(self, text="Dùng bot như thế nào?", *, mine=False):
        self.rows = [DmRow("test-thread", "test-customer", text, 0, INBOX)]
        self.messages = [DmMessage(mine, text)]
        self.listed = []
        self.opened = []
        self.sent = []

    def list(self, folder):
        self.listed.append(folder)
        return [row for row in self.rows if row.folder == folder]

    def read(self, thread_id, folder):
        self.opened.append(thread_id)
        return list(self.messages)

    def send(self, thread_id, folder, text):
        self.sent.append(text)

    def _pause(self, lo, hi):
        pass


@pytest.fixture
def storage(tmp_path):
    return GrowthStorage(tmp_path / "engagement.sqlite")


@pytest.fixture(autouse=True)
def roles(monkeypatch):
    """Hypothetical roles for tests only; An Linh production DM flag is never changed."""
    current = {
        "us28qt": AccountRole(enabled=True, dm=True, bots=("cashbot",)),
        "anlinh": AccountRole(enabled=True, dm=True, bots=("ai_store",)),
    }
    monkeypatch.setattr(dm_agent, "load_account_roles", lambda: current)
    monkeypatch.setattr(dm_agent, "guidance_block", lambda *a, **k: None)
    return current


def unexpected(*args, **kwargs):
    raise AssertionError("This path must not open a provider or off-role knowledge source")


async def no_decision(*args, **kwargs):
    unexpected()


def run_inbox(inbox, storage, account="us28qt", decider=no_decision, **kwargs):
    return dm_agent.handle_inbox(inbox, storage, account, NOW, asyncio.run, decider, **kwargs)


def test_cashbot_prompt_contains_only_its_own_identity_offer_and_links():
    prompt = dm_agent.build_prompt("test-customer", [DmMessage(False, "Cách dùng bot?")], INBOX,
                                   "DO_NOT_EXPORT_STORE_CATALOG", "checked-cashbot-only")
    assert "@us28qt" in prompt and "@anlinh_08_10" not in prompt
    assert channel_url(TargetBot.CASHBOT, "dm", "us28qt") in prompt
    assert dm_agent.CANVA_URL in prompt and "checked-cashbot-only" in prompt
    assert "DO_NOT_EXPORT_STORE_CATALOG" not in prompt and "aipass_shop_bot" not in prompt
    assert '"ai_store"' not in prompt


def test_store_prompt_uses_hypothetical_account_link_and_no_cashbot_knowledge():
    prompt = dm_agent.build_prompt("test-customer", [DmMessage(False, "CapCut giá bao nhiêu?")], INBOX,
                                   "CapCut: 34.000đ", "DO_NOT_EXPORT_CUSTOMER_CHECK", account="anlinh",
                                   allowed_bots=(TargetBot.AI_STORE,))
    assert "@anlinh_08_10" in prompt and "@us28qt" not in prompt
    assert channel_url(TargetBot.AI_STORE, "dm", "anlinh") in prompt and "CapCut: 34.000đ" in prompt
    assert "zt_shopee_bot" not in prompt and "zalo.me" not in prompt and "Tặng slot Canva" not in prompt
    assert "DO_NOT_EXPORT_CUSTOMER_CHECK" not in prompt and '"cashbot"' not in prompt


@pytest.mark.parametrize("account,role", [
    ("unknown", AccountRole(enabled=True, dm=True)),
    ("us28qt", None),
    ("us28qt", AccountRole(enabled=False, dm=True)),
    ("us28qt", AccountRole(enabled=True, dm=False)),
    ("us28qt", AccountRole(enabled=True, dm=True, bots=())),
])
def test_missing_disabled_or_unknown_permission_never_opens_inbox(account, role, roles, storage):
    roles.clear()
    if role is not None:
        roles[account] = role
    inbox = Inbox()
    assert run_inbox(inbox, storage, account) == []
    assert inbox.listed == inbox.opened == inbox.sent == []
    assert asyncio.run(dm_agent.decide("test-customer", inbox.messages, INBOX, account=account)) is None


@pytest.mark.parametrize("allowed", [(), ("ai_store",), ("unknown",), ("cashbot", "ai_store")])
def test_explicit_scope_cannot_widen_role(allowed, storage):
    inbox = Inbox()
    assert run_inbox(inbox, storage, allowed_bots=allowed) == []
    assert inbox.listed == []
    with pytest.raises(ValueError, match="permission"):
        dm_agent.build_prompt("test-customer", inbox.messages, INBOX, "", None, allowed_bots=allowed)


@pytest.mark.parametrize("text", [
    "Em đã chuyển khoản rồi nhưng chưa nhận hàng", "da ck roi shop oi", "chuyển 100k rồi", "nạp 100k rồi",
    "Tài khoản bị lỗi", "bảo hành sao shop?", "Cho mình hoàn tiền", "Tôi muốn gặp người thật",
    "Kiểm tra đơn giúp em", "don hang cua em bi sai", "da thanh toan", "khieu nai", "mua sỉ có không?",
    "Cho gặp admin", "Hoàn tiền Shopee sao chưa về ví?", "Hoàn tiền Shopee giúp mình",
])
def test_support_is_handoff_without_model_or_outbound(text, storage, monkeypatch):
    monkeypatch.setattr(dm_agent.AIUseCases, "generate_text_async", unexpected)
    monkeypatch.setattr(dm_agent, "catalog", unexpected)
    monkeypatch.setattr(dm_agent, "cashbot_user", unexpected)
    assert dm_agent.interaction_handoff_reason(text)
    inbox = Inbox(text)
    events = run_inbox(inbox, storage)
    assert len(events) == 1 and events[0]["action"] == "handoff" and events[0]["sent"] is False
    assert events[0]["reply"] == "" and inbox.sent == []
    assert storage.dm_thread("test-thread", "us28qt")["status"] == "handoff"
    assert asyncio.run(dm_agent.decide("test-customer", inbox.messages, INBOX)).action == "handoff"


@pytest.mark.parametrize("text", [
    "CapCut giá bao nhiêu?", "Cách thanh toán như thế nào?", "Quét QR như thế nào?", "mua CapCut nhu nao?",
    "Bot hoàn tiền Shopee hoạt động thế nào?", "Cách dùng bot hoàn tiền?", "Cashback là gì?", "Dùng bot hoàn tiền",
    "Admin ơi, giá bao nhiêu?",
])
def test_basic_price_and_how_to_faq_are_not_mistaken_for_support(text):
    assert dm_agent.interaction_handoff_reason(text) is None


def test_actual_account_and_effective_role_reach_production_decide(storage, monkeypatch):
    captured = []

    async def decide(handle, messages, folder, *, account, allowed_bots):
        captured.append((account, allowed_bots))
        return Decision("reply", "Xem thông tin hiện tại: " + channel_url(TargetBot.AI_STORE, "dm", account),
                        bot="ai_store")

    monkeypatch.setattr(dm_agent, "decide", decide)
    inbox = Inbox("CapCut giá bao nhiêu?")
    events = dm_agent.handle_inbox(inbox, storage, "anlinh", NOW, asyncio.run)
    assert captured == [("anlinh", ("ai_store",))]
    assert len(inbox.sent) == 1 and events[0]["sent"] is True


def test_decide_reads_only_in_role_knowledge_and_validates_provider_output(monkeypatch):
    prompts = []
    monkeypatch.setattr(dm_agent, "catalog", unexpected)
    monkeypatch.setattr(dm_agent, "cashbot_user", lambda text: None)

    async def generate(prompt, **kwargs):
        prompts.append(prompt)
        return json.dumps({"action": "reply", "reply": "Cách dùng ở đây: " + channel_url(TargetBot.CASHBOT, "dm"),
                           "bot": "cashbot"}), {}

    monkeypatch.setattr(dm_agent.AIUseCases, "generate_text_async", generate)
    decision = asyncio.run(dm_agent.decide("test-customer", [DmMessage(False, "Cách dùng bot?")], INBOX))
    assert decision.action == "reply" and "aipass_shop_bot" not in prompts[0]


def test_store_decide_does_not_query_cashbot_customer_data(monkeypatch):
    monkeypatch.setattr(dm_agent, "catalog", lambda: "CapCut: 34.000đ")
    monkeypatch.setattr(dm_agent, "cashbot_user", unexpected)

    async def generate(prompt, **kwargs):
        assert "CapCut: 34.000đ" in prompt and "zt_shopee_bot" not in prompt
        return json.dumps({"action": "reply", "reply": "Xem giá: " + channel_url(TargetBot.AI_STORE, "dm", "anlinh"),
                           "bot": "ai_store"}), {}

    monkeypatch.setattr(dm_agent.AIUseCases, "generate_text_async", generate)
    d = asyncio.run(dm_agent.decide("test-customer", [DmMessage(False, "CapCut giá bao nhiêu?")], INBOX,
                                   account="anlinh", allowed_bots=("ai_store",)))
    assert d.action == "reply"


@pytest.mark.parametrize("decision", [
    Decision("reply", "Mở cửa hàng này", bot="ai_store"),
    Decision("reply", "Mình là @anlinh_08_10", bot="cashbot"),
    Decision("reply", "Link " + channel_url(TargetBot.CASHBOT, "dm", "anlinh"), bot="cashbot"),
    Decision("reply", "Link " + channel_url(TargetBot.AI_STORE, "dm"), bot="cashbot"),
    Decision("reply", "Link https://evil.example/path", bot="cashbot"),
    Decision("reply", "Link evil.example/path", bot="cashbot"),
    Decision("reply", "Link evil.example", bot="cashbot"),
    Decision("reply", "Link t.me/zt_shopee_bot?start=threads_cb_dm", bot="cashbot"),
    Decision("reply", channel_url(TargetBot.CASHBOT, "dm") + " " + dm_agent.CANVA_URL, bot="cashbot"),
    Decision("reply", "Shop bán CapCut 34k nhé", bot="cashbot"),
    Decision("reply", "Canva giá 1.100đ nhé", bot="canva"),
    Decision("reply", "Chỉ 1k nhận Canva nhé", bot="canva"),
    Decision("reply", "Shop bán gói AI nhé", bot="cashbot"),
    Decision("reply", "Bạn xem ở đây nhé", bot="unknown"),
    Decision("reply", channel_url(TargetBot.CASHBOT, "dm"), bot="none"),
    Decision("handoff", "Mua ngay " + channel_url(TargetBot.AI_STORE, "dm"), bot="ai_store"),
])
def test_injected_three_arg_decider_does_not_bypass_send_validation(decision, storage):
    calls = []

    async def legacy(handle, messages, folder):
        calls.append((handle, folder))
        return decision

    inbox = Inbox()
    events = run_inbox(inbox, storage, decider=legacy)
    assert len(calls) == 1 and events[0]["action"] == "handoff"
    assert events[0]["reply"] == "" and events[0]["sent"] is False and inbox.sent == []


def test_safe_legacy_decider_remains_supported(storage):
    async def legacy(handle, messages, folder):
        return Decision("reply", "Mở bot rồi dán liên kết sản phẩm để xem hướng dẫn nhé.", bot="cashbot")

    inbox = Inbox()
    events = run_inbox(inbox, storage, decider=legacy)
    assert events[0]["action"] == "reply" and events[0]["sent"] is True and len(inbox.sent) == 1


def test_role_disabled_during_model_call_prevents_send(roles, storage):
    async def legacy(handle, messages, folder):
        roles["us28qt"] = AccountRole(enabled=False, dm=True, bots=("cashbot",))
        return Decision("reply", "Mở bot rồi dán liên kết nhé.", bot="cashbot")

    inbox = Inbox()
    events = run_inbox(inbox, storage, decider=legacy)
    assert inbox.sent == [] and events[0]["action"] == "handoff"
    assert events[0]["note"] == "needs_human:permission_changed"


def test_no_inbound_never_calls_model(storage):
    inbox = Inbox("Mình đã trả lời rồi nhé", mine=True)
    assert run_inbox(inbox, storage) == [] and inbox.sent == []


def test_quota_exhaustion_still_triages_support_without_marking_faq_handled(storage):
    for i in range(dm_agent.MAX_PER_HOUR):
        storage.log_dm(str(i), "us28qt", "test-customer", "out", "test")
    normal = Inbox()
    assert run_inbox(normal, storage) == []
    assert storage.dm_thread("test-thread", "us28qt") is None
    support = Inbox("Đã ck rồi chưa nhận hàng")
    events = run_inbox(support, storage)
    assert events[0]["action"] == "handoff" and events[0]["sent"] is False and support.sent == []


def test_model_outage_still_hands_off_later_candidates(storage):
    texts = {"faq-first": "Cách dùng bot?", "support": "Đã chuyển khoản rồi", "faq-last": "Bot có mất phí không?"}
    inbox = Inbox()
    inbox.rows = [DmRow(key, "test-customer", text, 0, INBOX) for key, text in texts.items()]
    calls = []

    def read(thread_id, folder):
        inbox.opened.append(thread_id)
        return [DmMessage(False, texts[thread_id])]

    async def unavailable(handle, messages, folder):
        calls.append(messages[-1].text)
        return None

    inbox.read = read
    events = run_inbox(inbox, storage, decider=unavailable)
    assert calls == [texts["faq-first"]]
    assert [(ev["thread_id"], ev["action"], ev["sent"]) for ev in events] == [("support", "handoff", False)]
    assert storage.dm_thread("faq-first", "us28qt") is None
    assert storage.dm_thread("faq-last", "us28qt") is None and inbox.sent == []


def test_handoff_hold_preserved_when_customer_adds_message(storage):
    first = Inbox("Cần gặp người thật")
    run_inbox(first, storage)
    later = Inbox("Mình nhắn thêm nhé")
    events = dm_agent.handle_inbox(later, storage, "us28qt", NOW + timedelta(minutes=1), asyncio.run, no_decision)
    assert events[0]["action"] == "handoff_more" and events[0]["sent"] is False and later.sent == []


def test_request_skip_never_accepts_or_sends(storage):
    inbox = Inbox("tin rác")
    inbox.rows[0] = DmRow("test-thread", "test-customer", "tin rác", 0, REQUESTS)

    async def legacy(handle, messages, folder):
        return Decision("skip", "Không gửi chữ này", bot="none")

    events = run_inbox(inbox, storage, decider=legacy)
    assert events[0]["action"] == "skip" and not events[0]["sent"] and inbox.sent == []
    assert storage.dm_thread("test-thread", "us28qt")["status"] == "ignored"
