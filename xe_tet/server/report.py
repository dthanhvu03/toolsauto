"""Trang /report (PLAN-143): đọc lại từng buổi live từ `live_log.LiveStore` — phút nào, cảnh nào người xem tặng quà / bình luận /
lên xe nhiều. HTML tự đủ (không thư viện ngoài), biểu đồ vẽ bằng SVG."""

import csv
import io
from collections import Counter
from datetime import datetime
from html import escape

from .game.parser import normalize
from .live_log import PHASE_LABEL, VN, LiveStore, clock

PHASE_COLOR = {"BOARDING": "#b39ddb", "DRIVING": "#7fb2e5", "REST": "#9ccc8a", "DROPOFF": "#f29a76", "FINISH": "#c7b8a6",
               "SPECIAL": "#e57fb0"}

CSS = """
body { margin: 0; font-family: system-ui, "Segoe UI", sans-serif; background: #fff8ec; color: #3b2a1e; }
main { max-width: 1100px; margin: 0 auto; padding: 18px 16px 40px; }
h1 { margin: 0 0 4px; color: #b3261e; font-size: 26px; } h2 { color: #8e1b16; font-size: 20px; margin: 26px 0 8px; }
.muted { color: #8a6f58; font-size: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; background: #fff; border-radius: 10px; overflow: hidden; }
th, td { padding: 7px 9px; text-align: right; border-bottom: 1px solid #f1e3cf; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; } th { background: #fbe7c4; color: #6b3d14; }
tr.on td { background: #fff1d6; font-weight: 600; } a { color: #b3261e; text-decoration: none; } a:hover { text-decoration: underline; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.card { background: #fff; border: 2px solid #f1d8a8; border-radius: 12px; padding: 10px 12px; }
.card b { display: block; font-size: 24px; color: #b3261e; } .card span { font-size: 13px; color: #8a6f58; }
.chart { background: #fff; border-radius: 12px; padding: 10px; border: 2px solid #f1d8a8; overflow-x: auto; }
.legend span { display: inline-block; margin-right: 12px; font-size: 13px; }
.legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }
ul.notes { background: #fff; border-left: 5px solid #b3261e; padding: 10px 14px 10px 30px; border-radius: 8px; }
ul.notes li { margin: 4px 0; } .wrap { overflow-x: auto; }
"""


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".") if abs(n) >= 10 or n == int(n) else f"{n:.1f}".replace(".", ",")


def _duration(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m // 60} giờ {m % 60:02d} phút" if m >= 60 else f"{m} phút"


def _chart(minutes: list[dict], started: float) -> str:
    """Cột vàng = xu mỗi phút, đường đỏ = bình luận mỗi phút, dải màu dưới = cảnh đang chiếu."""
    if not minutes:
        return "<p class='muted'>Chưa có phút nào.</p>"
    n = minutes[-1]["minute"] + 1
    w, h, strip = max(600, n * 12), 220, 14
    top_xu = max(1, max(m["xu"] for m in minutes))
    top_cm = max(1, max(m["comments"] for m in minutes))
    bw = w / n
    parts = [f"<svg viewBox='0 0 {w} {h + strip + 22}' width='100%' role='img' "
             f"aria-label='Quà và bình luận theo phút'>"]
    for m in minutes:
        x = m["minute"] * bw
        bh = (h - 10) * m["xu"] / top_xu
        tip = (f"Phút {m['minute'] + 1} ({clock(started + m['minute'] * 60)[-5:]}) · {PHASE_LABEL.get(m['phase'], m['phase'])} · "
               f"{m['xu']} xu · {m['comments']} bình luận · {m['seats'] + m['pickups']} lên xe")
        parts.append(f"<rect x='{x:.1f}' y='{h - bh:.1f}' width='{max(1, bw - 2):.1f}' height='{bh:.1f}' fill='#e8a317'>"
                     f"<title>{escape(tip)}</title></rect>")
        parts.append(f"<rect x='{x:.1f}' y='{h + 2}' width='{bw:.1f}' height='{strip}' fill='{PHASE_COLOR.get(m['phase'], '#ccc')}'>"
                     f"<title>{escape(tip)}</title></rect>")
    pts = " ".join(f"{m['minute'] * bw + bw / 2:.1f},{h - (h - 10) * m['comments'] / top_cm:.1f}" for m in minutes)
    parts.append(f"<polyline points='{pts}' fill='none' stroke='#c62828' stroke-width='2'/>")
    step = max(1, n // 10)
    for i in range(0, n, step):
        parts.append(f"<text x='{i * bw:.1f}' y='{h + strip + 18}' font-size='11' fill='#8a6f58'>"
                     f"{clock(started + i * 60)[-5:]}</text>")
    parts.append("</svg>")
    legend = ("<div class='legend'><span><i style='background:#e8a317'></i>xu / phút (cao nhất "
              f"{_fmt(top_xu)})</span><span><i style='background:#c62828'></i>bình luận / phút (cao nhất {_fmt(top_cm)})</span>"
              + "".join(f"<span><i style='background:{c}'></i>{PHASE_LABEL[p]}</span>" for p, c in PHASE_COLOR.items()) + "</div>")
    return f"<div class='chart'>{''.join(parts)}{legend}</div>"


def _by_phase(phase_rows: list[dict], minutes: list[dict]) -> list[dict]:
    """Trung bình mỗi phút của từng cảnh, tính trên số giây thật của cảnh (sự kiện gán đúng cảnh lúc xảy ra). Buổi ghi trước
    khi có bảng cảnh thì tính theo phút."""
    if phase_rows:
        out = []
        for phase, label in PHASE_LABEL.items():
            r = next((x for x in phase_rows if x["phase"] == phase), None)
            if not r or r["seconds"] < 1:
                continue
            per = 60 / r["seconds"]
            out.append({"phase": phase, "label": label, "minutes": r["seconds"] / 60, "xu": r["xu"] * per,
                        "comments": r["comments"] * per, "likes": r["likes"] * per, "board": r["seats"] * per,
                        "joins": r["joins"] * per})
        return out
    out = []
    for phase, label in PHASE_LABEL.items():
        ms = [m for m in minutes if m["phase"] == phase]
        if not ms:
            continue
        k = len(ms)
        out.append({"phase": phase, "label": label, "minutes": k,
                    "xu": sum(m["xu"] for m in ms) / k, "comments": sum(m["comments"] for m in ms) / k,
                    "likes": sum(m["likes"] for m in ms) / k, "board": sum(m["seats"] + m["pickups"] for m in ms) / k,
                    "joins": sum(m["joins"] for m in ms) / k})
    return out


def _notes(s: dict, minutes: list[dict], phases: list[dict]) -> list[str]:
    """Vài nhận xét tự động — chỉ nói điều số liệu cho thấy, không đoán."""
    notes = []
    total_min = max(1, len(minutes))
    phases = [p for p in phases if p["minutes"] >= 1] or phases  # cảnh quá ngắn (< 1 phút cả buổi): số / phút không đáng tin
    if s["xu"]:
        avg = s["xu"] / total_min
        best = max(phases, key=lambda p: p["xu"])
        notes.append(f"Quà nhiều nhất lúc <b>{best['label']}</b>: {_fmt(best['xu'])} xu / phút "
                     f"(trung bình cả buổi {_fmt(avg)} xu / phút).")
        peak = max(minutes, key=lambda m: m["xu"])
        notes.append(f"Phút nhiều quà nhất: <b>{clock(s['started'] + peak['minute'] * 60)[-5:]}</b> ({_fmt(peak['xu'])} xu, "
                     f"{PHASE_LABEL.get(peak['phase'], peak['phase'])}).")
    else:
        notes.append("Buổi này chưa có quà.")
    if phases:
        talk = max(phases, key=lambda p: p["comments"])
        notes.append(f"Bình luận sôi nhất lúc <b>{talk['label']}</b>: {_fmt(talk['comments'])} bình luận / phút.")
    if s["uniq_commenters"]:
        rate = 100 * s["uniq_boarded"] / s["uniq_commenters"]
        notes.append(f"{_fmt(s['uniq_commenters'])} người bình luận, {_fmt(s['uniq_boarded'])} người có vé "
                     f"(<b>{rate:.0f} %</b>), {_fmt(s['delivered'])} lượt về tới quê.")
    seen = s["regulars"] + s["newcomers"]
    if seen:
        notes.append(f"Khách quen quay lại: <b>{_fmt(s['regulars'])}</b> / {_fmt(seen)} người tương tác "
                     f"({100 * s['regulars'] / seen:.0f} %).")
    return notes


KIND_LABEL = {"province": "Gõ tỉnh (đặt vé)", "board": "Muốn lên xe (chưa ghi tỉnh)", "stay": "Không về", "food": "Gọi món ở trạm",
              "wc": "WC", "gift_shop": "Mua quà", "where": "Hỏi vé / xe nào", "station": "Gọi xe ra bến khác",
              "fuel": "Đổ xăng", "wash": "Rửa xe", "question": "Câu hỏi", "chat": "Trò chuyện (game không làm gì)"}


def _comments_html(live: LiveStore, sid: int, q: str) -> str:
    """Bình luận thật của buổi (anh 03/11): game hiểu được bao nhiêu, câu nào game chưa làm gì — gom câu giống nhau."""
    rows = live.comments(sid)
    if not rows:
        return ("<h2>💬 Bình luận</h2><p class='muted'>Buổi này chưa lưu nội dung bình luận (lưu từ bản 03/11 trở đi).</p>")
    kinds = Counter(r["kind"] for r in rows)
    kind_rows = "".join(f"<tr><td>{KIND_LABEL.get(k, k)}</td><td>{_fmt(n)}</td><td>{round(100 * n / len(rows))} %</td></tr>"
                        for k, n in kinds.most_common())

    def grouped(pick, limit: int) -> str:
        groups: dict[str, list[dict]] = {}
        for r in rows:
            if pick(r):
                groups.setdefault(normalize(r["text"]), []).append(r)
        top = sorted(groups.values(), key=lambda g: -len(g))[:limit]
        return "".join(f"<tr><td>{escape(g[0]['text'])}</td><td>{len(g)}</td><td>{len({x['uid'] for x in g})}</td>"
                       f"<td>{PHASE_LABEL.get(g[0]['phase'], g[0]['phase'])}</td></tr>" for g in top) \
            or "<tr><td colspan='4'>Không có.</td></tr>"
    head = "<tr><th>Câu (gom câu giống nhau)</th><th>Số lần</th><th>Số người</th><th>Cảnh</th></tr>"
    return (f"<h2>💬 Bình luận · {_fmt(len(rows))} câu</h2>"
            f"<p><a href='/report/comments.csv?id={sid}{q}'>⬇ Tải toàn bộ bình luận (CSV, mở bằng Excel)</a></p>"
            f"<div class='wrap'><table><tr><th>Game hiểu là</th><th>Số câu</th><th>Tỉ lệ</th></tr>{kind_rows}</table></div>"
            "<h2>Câu game chưa làm gì (nên xử lý thêm?)</h2>"
            f"<div class='wrap'><table>{head}{grouped(lambda r: r['kind'] == 'chat', 40)}</table></div>"
            "<h2>Câu hỏi chưa có trả lời sẵn (đang phải hỏi AI)</h2>"
            f"<div class='wrap'><table>{head}{grouped(lambda r: r['kind'] == 'question' and r['detail'] == 'ai', 25)}</table></div>")


def _cell(text: str) -> str:
    """Bình luận bắt đầu bằng = + - @ thì Excel coi là công thức: thêm dấu ' để luôn hiện là chữ."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def comments_csv(live: LiveStore, session_id: int) -> str:
    """Toàn bộ bình luận một buổi — CSV có BOM để Excel đọc đúng tiếng Việt."""
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out)
    w.writerow(["giờ", "phút thứ", "cảnh", "tên", "bình luận", "game hiểu là", "chi tiết"])
    for r in live.comments(session_id):
        w.writerow([datetime.fromtimestamp(r["ts"], VN).strftime("%H:%M:%S"), r["minute"], PHASE_LABEL.get(r["phase"], r["phase"]),
                    _cell(r["name"]), _cell(r["text"]), KIND_LABEL.get(r["kind"], r["kind"]), r["detail"]])
    return out.getvalue()


def render(live: LiveStore, session_id: int | None, token: str = "") -> str:
    sessions = live.sessions()
    q = f"&token={escape(token)}" if token else ""
    head = (f"<!doctype html><html lang='vi'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>Báo cáo live</title><style>{CSS}</style></head><body><main>"
            "<h1>📊 Báo cáo buổi live — Xe Tết Sum Vầy</h1>"
            "<p class='muted'>Chỉ tính sự kiện thật từ TikTok khi đã kết nối (không tính giả lập / bấm thử). Giờ Việt Nam.</p>")
    if not sessions:
        return head + ("<p>Chưa có buổi live nào được ghi. Báo cáo bắt đầu ghi từ lần kết nối TikTok kế tiếp.</p>"
                       "</main></body></html>")
    current = next((s for s in sessions if s["id"] == session_id), sessions[0])
    rows = "".join(
        f"<tr class='{'on' if s['id'] == current['id'] else ''}'><td><a href='?id={s['id']}{q}'>{clock(s['started'])}</a></td>"
        f"<td>@{escape(s['username'])}</td><td>{_duration(s['ended'] - s['started'])}</td><td>{_fmt(s['peak_viewers'])}</td>"
        f"<td>{_fmt(s['comments'])}</td><td>{_fmt(s['xu'])}</td><td>{_fmt(s['uniq_boarded'])}</td><td>{_fmt(s['delivered'])}</td>"
        f"<td>{_fmt(s['regulars'])}</td></tr>" for s in sessions)
    table = ("<h2>Các buổi live</h2><div class='wrap'><table><tr><th>Bắt đầu</th><th>Kênh</th><th>Thời lượng</th>"
             "<th>Xem đông nhất</th><th>Bình luận</th><th>Xu</th><th>Người có vé</th><th>Về tới quê</th><th>Khách quen</th></tr>"
             f"{rows}</table></div>")
    minutes = live.minutes(current["id"])
    phases = _by_phase(live.phases(current["id"]), minutes)
    s = current
    cards = "".join(f"<div class='card'><b>{v}</b><span>{k}</span></div>" for k, v in (
        ("thời lượng", _duration(s["ended"] - s["started"])), ("người xem đông nhất", _fmt(s["peak_viewers"])),
        ("xu", _fmt(s["xu"])), ("lượt quà", _fmt(s["gifts"])), ("người tặng", _fmt(s["uniq_gifters"])),
        ("bình luận", _fmt(s["comments"])), ("người bình luận", _fmt(s["uniq_commenters"])), ("tim", _fmt(s["likes"])),
        ("người có vé", _fmt(s["uniq_boarded"])), ("lượt về tới quê", _fmt(s["delivered"])),
        ("khách quen", _fmt(s["regulars"])), ("khách mới", _fmt(s["newcomers"]))))
    phase_rows = "".join(
        f"<tr><td><i style='display:inline-block;width:10px;height:10px;border-radius:3px;background:{PHASE_COLOR[p['phase']]}'>"
        f"</i> {p['label']}</td><td>{_fmt(p['minutes'])}</td><td>{_fmt(p['xu'])}</td><td>{_fmt(p['comments'])}</td>"
        f"<td>{_fmt(p['likes'])}</td><td>{_fmt(p['board'])}</td><td>{_fmt(p['joins'])}</td></tr>" for p in phases)
    top = sorted((m for m in minutes if m["xu"]), key=lambda m: -m["xu"])[:5]
    top_rows = "".join(
        f"<tr><td>{clock(s['started'] + m['minute'] * 60)[-5:]}</td><td>{PHASE_LABEL.get(m['phase'], m['phase'])}</td>"
        f"<td>{_fmt(m['xu'])}</td><td>{_fmt(m['gifts'])}</td><td>{_fmt(m['comments'])}</td><td>{_fmt(m['viewers'])}</td></tr>"
        for m in top) or "<tr><td colspan='6'>Chưa có quà.</td></tr>"
    notes = "".join(f"<li>{n}</li>" for n in _notes(s, minutes, phases))
    body = (f"<h2>Buổi {clock(s['started'])} · @{escape(s['username'])}</h2><div class='cards'>{cards}</div>"
            f"<h2>Nhận xét</h2><ul class='notes'>{notes}</ul>"
            f"<h2>Theo từng phút</h2>{_chart(minutes, s['started'])}"
            "<h2>Theo cảnh (trung bình mỗi phút)</h2><div class='wrap'><table><tr><th>Cảnh</th><th>Số phút</th><th>Xu</th>"
            f"<th>Bình luận</th><th>Tim</th><th>Lên xe</th><th>Vào phòng</th></tr>{phase_rows}</table></div>"
            "<h2>5 phút nhiều quà nhất</h2><div class='wrap'><table><tr><th>Giờ</th><th>Cảnh</th><th>Xu</th><th>Lượt quà</th>"
            f"<th>Bình luận</th><th>Người xem</th></tr>{top_rows}</table></div>"
            + _comments_html(live, s["id"], q))
    return head + body + table + "</main></body></html>"
