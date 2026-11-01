"""Đo nhấp nháy: đếm màn đen (#fade), băng rôn / chữ lớn bật tắt, đổi cảnh trong N giây. Chạy: venv/bin/python -I xe_tet/e2e/flicker.py [giây]"""
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

# Máy chủ THỬ riêng (cổng 8811, thiết lập riêng) — không bao giờ bấm vào server anh đang dùng / đang live (8810).
B = os.getenv("XE_TET_URL", "http://127.0.0.1:8811")
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 90


def admin(body):
    urllib.request.urlopen(urllib.request.Request(B + "/api/admin", json.dumps(body).encode(),
                                                  {"Content-Type": "application/json"}))


WATCH = """() => {
  window.__log = [];
  const t0 = performance.now();
  const note = (what) => window.__log.push([Math.round(performance.now() - t0), what]);
  const watch = (id, cls) => new MutationObserver(() => {
    const el = document.getElementById(id);
    note(`${id}:${el.classList.contains(cls) ? (cls === 'hidden' ? 'off' : 'on') : (cls === 'hidden' ? 'on' : 'off')}`);
  }).observe(document.getElementById(id), { attributes: true, attributeFilter: ['class'] });
  watch('fade', 'on');
  watch('banner', 'hidden');
  watch('flash', 'hidden');
  let lastPhase = '';
  setInterval(() => {
    const p = document.getElementById('phase-pill').textContent;
    if (p !== lastPhase) { note('phase:' + p); lastPhase = p; }
  }, 100);
}"""


def _refuse_during_live() -> None:
    """Script này reset game + bật giả lập: chạy lúc đang live thật là xoá vé của khán giả."""
    import json as _json
    import urllib.request as _url
    state = _json.load(_url.urlopen("http://127.0.0.1:8810/api/state"))
    if state.get("tiktok", {}).get("state", "idle") not in ("idle", "error", "ended"):
        raise SystemExit("Đang nối TikTok thật — không chạy test (sẽ xoá vé khán giả). Ngắt kết nối trước.")


_refuse_during_live()

with sync_playwright() as p:
    br = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    pg = br.new_page(viewport={"width": 360, "height": 640})
    pg.set_default_timeout(120000)
    admin({"action": "reset"})
    admin({"action": "settings", "changes": {"board_seconds": 20, "rest_seconds": 20}})
    admin({"action": "sim", "rate": 6})
    pg.goto(B + "/?res=0.5", wait_until="domcontentloaded")
    time.sleep(2)
    pg.evaluate(WATCH)
    time.sleep(SECONDS)
    log = pg.evaluate("window.__log")
    admin({"action": "sim", "rate": 0})
    admin({"action": "settings", "changes": {"board_seconds": 180, "rest_seconds": 90}})
    br.close()

fades = [t for t, w in log if w == "fade:on"]
print(f"{SECONDS}s: màn đen {len(fades)} lần, đổi pha {sum(1 for _, w in log if w.startswith('phase:'))} lần, "
      f"băng rôn bật {sum(1 for _, w in log if w == 'banner:on')}, chữ lớn bật {sum(1 for _, w in log if w == 'flash:on')}")
gaps = [b - a for a, b in zip(fades, fades[1:])]
print("khoảng cách giữa 2 lần màn đen (ms):", gaps)
print("\n".join(f"{t:>6} {w}" for t, w in log[:80]))
