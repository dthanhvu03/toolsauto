"""Hệ thống Quản trị (Admin System) chuẩn hóa cho Cashback Bot.

Kiến trúc phân tầng (Clean Modular Architecture):
- `base`: Định nghĩa hợp đồng cơ sở (`AdminContext`, `BaseAdminHandler`).
- `router`: Bộ điều phối trung tâm (`AdminRouter`) phân phối sự kiện callback & text.
- `panel`: Lớp điều phối cấp cao (`AdminPanel`) kết nối bot với toàn bộ tính năng quản trị.
- `ui`: Tầng hiển thị giao diện (Keyboards, Views, Glossary).
- `handlers`: Các phân hệ nghiệp vụ quản trị theo domain (Wallet, Support, Policy, TikTok, Sync...).
- `notify`: Hệ thống thông báo cảnh báo Admin (`AdminNotifier`) và gửi tin khách hàng (`CustomerNotifyAdmin`).
"""

from __future__ import annotations

import importlib

from cashback_bot.admin.base import AdminContext, BaseAdminHandler
from cashback_bot.admin.router import AdminRouter

__all__ = [
    "AdminPanel",
    "AdminSafetyError",
    "customer_policy_due",
    "AdminNotifier",
    "CustomerNotifyAdmin",
    "AdminContext",
    "BaseAdminHandler",
    "AdminRouter",
    "WalletAdmin",
    "SupportAdmin",
    "TermsAdmin",
    "AutoSyncAdmin",
    "TikTokAdmin",
    "DealsAdmin",
    "AnnounceAdmin",
    "EngagementAdmin",
    "ValidationAdmin",
    "SettlementAdmin",
    "ReconciliationAdmin",
    "ReadinessAdmin",
    "RetentionAdmin",
    "InsightsAdmin",
]


def __getattr__(name: str):
    if name in ("AdminPanel", "AdminSafetyError", "customer_policy_due"):
        from cashback_bot.admin import panel
        val = getattr(panel, name)
        globals()[name] = val
        return val
    if name == "AdminNotifier":
        from cashback_bot.admin.notify.admin_notify import AdminNotifier
        globals()[name] = AdminNotifier
        return AdminNotifier
    if name == "CustomerNotifyAdmin":
        from cashback_bot.admin.notify.customer_notify import CustomerNotifyAdmin
        globals()[name] = CustomerNotifyAdmin
        return CustomerNotifyAdmin
    # import_module, không dùng «from cashback_bot.admin import handlers»: cách đó gọi lại __getattr__ này.
    handlers = importlib.import_module("cashback_bot.admin.handlers")
    if name in handlers.__all__:
        val = getattr(handlers, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
