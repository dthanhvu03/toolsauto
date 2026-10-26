"""Dashboard khách hàng và dòng tiền cashback (PLAN-089), tìm mã (PLAN-091). Chỉ đọc DB của bot cashback (`mode=ro`).

Số liệu tính ở cashback_bot/insights.py, cùng nguồn với màn /admin Telegram. Trang nằm sau cookie đăng nhập của
dashboard (middleware trong app/main.py). Không hiện số tài khoản đầy đủ, không xuất file.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.main_templates import templates
from cashback_bot import insights
from cashback_bot.money import format_vnd

router = APIRouter(prefix="/cashback", tags=["cashback"])

ROOT = Path(__file__).resolve().parents[3]
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
SORTS = {"margin": "Biên", "orders": "Đơn", "wallet": "Ví", "recent": "Gần đây", "new": "Mới vào"}


def _db_path() -> str:
    raw = (os.getenv("CASHBACK_DB_PATH") or "./data/cashback.sqlite").strip()
    path = Path(raw)
    return str(path if path.is_absolute() else ROOT / path)


def _sync_interval() -> int:
    try:
        return int(os.getenv("SHOPEE_AUTO_SYNC_INTERVAL_MINUTES") or 120)
    except ValueError:
        return 120


def _when(stamp: str | None) -> str:
    moment = insights.parse_stamp(stamp)
    return "-" if moment is None else moment.astimezone(insights.ICT).strftime("%d/%m/%Y %H:%M")


def _pct(part: float, whole: float) -> str:
    return f"{part * 100 / whole:.0f}%" if whole else "–"


def _context(request: Request, **values) -> dict:
    return {"request": request, "vnd": format_vnd, "when": _when, "pct": _pct, "segments": insights.SEGMENTS,
            "periods": insights.PERIODS, **values}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def overview_page(request: Request, period: str = "30d"):
    now = datetime.now(timezone.utc)
    with insights.open_readonly(_db_path()) as conn:
        view = insights.overview(conn, period, now, _sync_interval())
        goals = insights.goals(conn, now, _sync_interval())
    chart = {
        "labels": [p.day[5:] for p in view.days],
        "net": [p.net for p in view.days],
        "margin": [p.margin for p in view.days],
    }
    return templates.TemplateResponse(
        "pages/cashback_overview.html", _context(request, view=view, goals=goals, chart=chart, active_tab="cashback")
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", channel: str = "", segment: str = "", sort: str = "margin"):
    now = datetime.now(timezone.utc)
    with insights.open_readonly(_db_path()) as conn:
        people = insights.customers(conn, now)
    counts = {key: sum(1 for c in people if c.segment == key) for key in insights.SEGMENTS}
    needle = q.strip().lower()
    chosen = [
        c for c in people
        if (not channel or c.channel == channel) and (not segment or c.segment == segment)
        and (not needle or needle in c.label.lower() or needle in str(c.user_id))
    ]
    chosen = insights.sort_customers(chosen, sort if sort in SORTS else "margin")
    return templates.TemplateResponse("pages/cashback_users.html", _context(
        request, people=chosen, total=len(people), counts=counts, q=q, channel=channel, segment=segment, sort=sort,
        sorts=SORTS, active_tab="cashback",
    ))


@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_page(request: Request, user_id: int):
    now = datetime.now(timezone.utc)
    with insights.open_readonly(_db_path()) as conn:
        found = next((c for c in insights.customers(conn, now) if c.user_id == user_id), None)
        if found is None:
            raise HTTPException(status_code=404, detail="Không thấy khách này")
        lifetime = insights.money(conn, EPOCH, max(1, (now - EPOCH).days), user_id)
        recent = insights.money(conn, now - timedelta(days=30), 30, user_id)
        prof = insights.profile(conn, user_id)
        events = insights.timeline(conn, user_id, limit=80)
    return templates.TemplateResponse("pages/cashback_user.html", _context(
        request, c=found, lifetime=lifetime, recent=recent, prof=prof, events=events, active_tab="cashback",
    ))


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = ""):
    with insights.open_readonly(_db_path()) as conn:
        hits = insights.search(conn, q)
    return templates.TemplateResponse("pages/cashback_search.html", _context(
        request, q=q, hits=hits, limit=insights.SEARCH_LIMIT, active_tab="cashback",
    ))


@router.get("/links/{link_id}", response_class=HTMLResponse)
def link_page(request: Request, link_id: int):
    with insights.open_readonly(_db_path()) as conn:
        detail = insights.link_detail(conn, link_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Không thấy link này")
    return templates.TemplateResponse("pages/cashback_link.html", _context(request, d=detail, active_tab="cashback"))
