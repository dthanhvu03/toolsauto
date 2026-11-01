"""Test UI/UX Xe Tết bằng Chromium thật. Chạy (server đang chạy): venv/bin/python -I xe_tet/e2e/ux_scenarios.py <thư mục ảnh>"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

# Máy chủ THỬ riêng (cổng 8811, thiết lập riêng) — không bao giờ bấm vào server anh đang dùng / đang live (8810).
B = os.getenv("XE_TET_URL", "http://127.0.0.1:8811")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
notes = []


def post(path, body):
    req = urllib.request.Request(B + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def st():
    return json.load(urllib.request.urlopen(B + "/api/state"))


def skip_to(target, limit=60):
    for _ in range(limit):
        if st()["phase"] == target:
            return True
        post("/api/admin", {"action": "skip"})
        time.sleep(0.4)
    return False


def ev(**e):
    post("/api/event", e)


# Vùng TikTok che trên màn người xem (ước lượng, toạ độ khung 1080×1920)
TIKTOK_MASK = """() => {
  const stage = document.getElementById('stage');
  const zones = [
    ['top bar', 0, 0, 1080, 150],
    ['comment feed', 0, 1240, 720, 520],
    ['bottom bar', 0, 1780, 1080, 140],
  ];
  for (const [n, x, y, w, h] of zones) {
    const d = document.createElement('div');
    d.className = 'tt-mask';
    d.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:rgba(0,0,0,.45);z-index:9;color:#fff;font:24px sans-serif;padding:6px;pointer-events:none`;
    d.textContent = 'TikTok: ' + n;
    stage.appendChild(d);
  }
}"""

# Phần tử HUD quan trọng nằm trong vùng TikTok che?
OVERLAP = """() => {
  const zones = [[0,0,1080,150],[0,1240,720,520],[0,1780,1080,140]];
  const stage = document.getElementById('stage').getBoundingClientRect();
  const k = stage.width / 1080;
  const out = [];
  for (const id of ['title','route','cta','loxe','toasts','callout','board','rest-card','banner','flash']) {
    const el = document.getElementById(id);
    if (!el || el.classList.contains('hidden') || !el.offsetParent && id !== 'title') continue;
    const r = el.getBoundingClientRect();
    const x = (r.left - stage.left) / k, y = (r.top - stage.top) / k, w = r.width / k, h = r.height / k;
    for (const [zx, zy, zw, zh] of zones) {
      const ox = Math.max(0, Math.min(x + w, zx + zw) - Math.max(x, zx));
      const oy = Math.max(0, Math.min(y + h, zy + zh) - Math.max(y, zy));
      if (ox * oy > 0.15 * w * h) out.push(`${id} bị che ${Math.round(100 * ox * oy / (w * h))}%`);
    }
  }
  return out;
}"""

# Chữ HUD bị tràn / cắt?
OVERFLOW = """() => {
  const out = [];
  document.querySelectorAll('#hud *').forEach((el) => {
    if (el.offsetParent === null) return;
    const cs = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 2 && cs.overflow !== 'visible' && cs.textOverflow !== 'ellipsis')
      out.push(`${el.id || el.className}: tràn ngang ${el.scrollWidth}>${el.clientWidth}`);
  });
  const stage = document.getElementById('stage').getBoundingClientRect();
  document.querySelectorAll('#hud .card, #hud #banner, #hud #toasts, #hud #loxe').forEach((el) => {
    if (el.offsetParent === null) return;
    const r = el.getBoundingClientRect();
    if (r.right > stage.right + 1 || r.left < stage.left - 1 || r.bottom > stage.bottom + 1)
      out.push(`${el.id}: ra ngoài khung`);
  });
  return out;
}"""


def check(page, name, mask=True):
    issues = page.evaluate(OVERLAP) + page.evaluate(OVERFLOW)
    if mask:
        page.evaluate(TIKTOK_MASK)
    page.screenshot(path=OUT / f"{name}.png")
    if mask:
        page.evaluate("() => document.querySelectorAll('.tt-mask').forEach(e => e.remove())")
    for i in issues:
        notes.append(f"[{name}] {i}")



def _refuse_during_live() -> None:
    """Script này reset game + bật giả lập trên máy chủ B: B đang nối TikTok thật thì dừng (chạy là xoá vé khán giả)."""
    try:
        state = json.load(urllib.request.urlopen(f"{B}/api/state", timeout=5))
    except OSError as exc:
        raise SystemExit(f"Không mở được máy chủ thử {B} ({exc}) — bật máy chủ thử trước (README: Test).") from exc
    if state.get("tiktok", {}).get("state", "idle") not in ("idle", "error", "ended"):
        raise SystemExit(f"{B} đang nối TikTok thật — không chạy test (sẽ xoá vé khán giả). Ngắt kết nối trước.")


_refuse_during_live()

with sync_playwright() as p:
    br = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    try:
        errors = []

        # ---- 1. bảng điều khiển: điện thoại + máy tính, bấm nút có thật sự gửi ----
        post("/api/admin", {"action": "reset"})
        post("/api/admin", {"action": "sim", "rate": 0})
        for label, vp in (("control-mobile", {"width": 390, "height": 844}), ("control-desktop", {"width": 1280, "height": 900})):
            c = br.new_page(viewport=vp)
            c.on("pageerror", lambda e: errors.append(f"control: {e}"))
            c.goto(B + "/control", wait_until="domcontentloaded")
            c.wait_for_timeout(1200)
            sw = c.evaluate("document.documentElement.scrollWidth")
            if sw > vp["width"]:
                notes.append(f"[{label}] cuộn ngang: {sw}px > {vp['width']}px")
            c.screenshot(path=OUT / f"{label}.png", full_page=True)
            c.close()
        c = br.new_page(viewport={"width": 390, "height": 844})
        c.set_default_timeout(120000)
        c.goto(B + "/control", wait_until="domcontentloaded")
        c.fill("#name", "Test Bấm Nút")
        c.click("text=Nghệ An")
        c.wait_for_timeout(500)
        seats = [s for s in st()["bus"]["seats"] if s]
        if not any(s["name"] == "Test Bấm Nút" for s in seats):
            notes.append("[control] bấm «Nghệ An» không lên xe")
        c.fill("#text", "về huế")
        c.press("#text", "Enter")
        c.wait_for_timeout(500)
        c.click("text=❤ 200 tim")
        c.wait_for_timeout(400)
        if st()["trip_likes"] < 200:
            notes.append("[control] nút 200 tim không tính")
        c.click("text=Vắng (2/giây)")
        c.wait_for_timeout(1500)
        if st()["sim_rate"] != 2:
            notes.append("[control] nút giả lập không bật")
        post("/api/admin", {"action": "sim", "rate": 0})
        c.close()

        # ---- 2. overlay ----
        post("/api/admin", {"action": "reset"})
        o = br.new_page(viewport={"width": 540, "height": 960})
        o.set_default_timeout(120000)
        o.on("pageerror", lambda e: errors.append(f"overlay: {e}"))
        o.on("console", lambda m: m.type == "error" and errors.append(f"overlay console: {m.text}"))
        o.goto(B + "/?view=outside&res=0.5", wait_until="domcontentloaded")
        o.wait_for_timeout(3000)
        check(o, "01-empty")

        # tên dài / emoji / mã HTML
        ev(type="comment", name="Nguyễn Thị Phương Thảo Bảo Ngọc Anh", text="Thừa Thiên Huế")
        ev(type="comment", name="🌸Bé Na🌸 ✨", text="37")
        ev(type="comment", name="<b>hack</b><img src=x onerror=alert(1)>", text="sg")
        ev(type="gift", name="🌸Bé Na🌸 ✨", diamonds=1, gift="Hoa hồng")
        ev(type="comment", name="Nguyễn Thị Phương Thảo Bảo Ngọc Anh", text="nhớ nhà quá trời ơi năm nay nhất định phải về ăn Tết với mẹ")
        o.wait_for_timeout(2500)
        check(o, "02-long-names")
        if o.evaluate("document.querySelectorAll('#hud img, #labels img').length"):
            notes.append("[02] tên chứa HTML bị chèn thành thẻ thật")

        # thông báo dồn dập
        post("/api/admin", {"action": "sim", "rate": 15})
        o.wait_for_timeout(6000)
        check(o, "03-flood")
        post("/api/admin", {"action": "sim", "rate": 0})

        # trong xe đầy
        o2 = br.new_page(viewport={"width": 540, "height": 960})
        o2.set_default_timeout(120000)
        o2.goto(B + "/?view=inside&res=0.5", wait_until="domcontentloaded")
        for i in range(24):
            ev(type="comment", name=f"Khách số {i + 1} {'Nguyễn Văn Dài' if i % 5 == 0 else ''}", text="Nghệ An")
        o2.wait_for_timeout(3500)
        check(o2, "04-inside-full")
        o2.close()

        # đang chạy + quà lớn
        skip_to("DRIVING")
        o.wait_for_timeout(2500)
        check(o, "05-driving")
        ev(type="gift", name="Đại Gia Phố Núi", diamonds=1000, gift="Xe Tết")
        o.wait_for_timeout(3000)
        check(o, "06-special")

        # trạm dừng chân: nhiều người gọi món + WC
        post("/api/admin", {"action": "reset"})
        for i, prov in enumerate(["Cà Mau", "Huế", "Hà Nội"]):
            ev(type="comment", name=f"Đi Xe {i}", text=prov)
        skip_to("REST")
        for i in range(14):
            ev(type="comment", name=f"Khách Trạm {i}", text=["phở", "wc", "trà đá", "mua quà", "bánh mì", "wc", "cà phê"][i % 7])
        o.wait_for_timeout(6000)
        check(o, "07-rest")
        o.wait_for_timeout(1000)
        post("/api/admin", {"action": "skip"})  # → còi giục lên xe (hết giờ)

        # thả khách 10 người cùng tỉnh
        post("/api/admin", {"action": "reset"})
        for i in range(10):
            ev(type="comment", name=f"Người Nghệ {i + 1}", text="Nghệ An")
        ev(type="gift", name="Người Nghệ 1", diamonds=20, gift="Đèn lồng")
        skip_to("DROPOFF")
        o.wait_for_timeout(2500)
        check(o, "08-dropoff-10")

        skip_to("FINISH")
        o.wait_for_timeout(1500)
        check(o, "09-finish")

        # KHÔNG VỀ nhiều người
        skip_to("BOARDING")
        for i in range(5):
            ev(type="comment", name=f"Ở Lại {i}", text="không về")
        o.wait_for_timeout(2000)
        check(o, "10-stay")

        # cửa sổ ngang 16:9 (LIVE Studio có thể mở cửa sổ kiểu này)
        w = br.new_page(viewport={"width": 1280, "height": 720})
        w.set_default_timeout(120000)
        w.goto(B + "/?view=outside&res=0.5", wait_until="domcontentloaded")
        w.wait_for_timeout(2500)
        w.screenshot(path=OUT / "11-window-16x9.png")
        w.close()

        print("ERRORS:", errors)
        print("NOTES:")
        print("\n".join(notes) or "(không có)")
    finally:
        br.close()
