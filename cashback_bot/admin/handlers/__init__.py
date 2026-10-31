"""Tập hợp các phân hệ nghiệp vụ quản trị (Domain Handlers) cho Admin Bot."""

from __future__ import annotations

import importlib

__all__ = [
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
    "Stats",
    "InsightsAdmin",
    "ShopeeAdmin",
    "SimulationAdmin",
    "PolicyAdmin",
]

_MAP = {
    "WalletAdmin": "wallet",
    "SupportAdmin": "support",
    "TermsAdmin": "terms",
    "AutoSyncAdmin": "sync",
    "TikTokAdmin": "tiktok",
    "DealsAdmin": "deals",
    "AnnounceAdmin": "announce",
    "EngagementAdmin": "engagement",
    "ValidationAdmin": "validation",
    "SettlementAdmin": "settlement",
    "ReconciliationAdmin": "reconciliation",
    "ReadinessAdmin": "readiness",
    "RetentionAdmin": "retention",
    "Stats": "stats",
    "InsightsAdmin": "insights",
    "ShopeeAdmin": "shopee",
    "SimulationAdmin": "simulation",
    "PolicyAdmin": "policy",
}


def __getattr__(name: str):
    if name in _MAP:
        mod = importlib.import_module(f"cashback_bot.admin.handlers.{_MAP[name]}")
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
