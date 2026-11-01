"""Bấm bảng điều khiển → kiểm overlay đổi theo. Chạy (server đang chạy): venv/bin/python -I xe_tet/e2e/control_panel.py <thư mục ảnh>"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

B = "http://127.0.0.1:8810"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
fails, passes = [], []


def st():
    return json.load(urllib.request.urlopen(B + "/api/state"))


def ok(cond, what):
    (passes if cond else fails).append(what)


def until(page, js: str, timeout_s: float = 20) -> bool:
    """Chờ tới khi biểu thức JS đúng (overlay 3D trên máy không GPU cập nhật chậm, chờ cố định thì chập chờn)."""
    try:
        page.wait_for_function(js, timeout=timeout_s * 1000)
        return True
    except Exception:
        return False



def _refuse_during_live() -> None:
    """Script này reset game + bật giả lập: chạy lúc đang live thật là xoá vé của khán giả."""
    import json as _json
    import urllib.request as _url
    state = _json.load(_url.urlopen("http://127.0.0.1:8810/api/state"))
    if state.get("tiktok", {}).get("state", "idle") not in ("idle", "error", "ended"):
        raise SystemExit("Đang nối TikTok thật — không chạy test (sẽ xoá vé khán giả). Ngắt kết nối trước.")


_refuse_during_live()

DEFAULTS = {"view": "outside", "cam": "wide", "zoom": 1, "fade": False, "quality": "high", "auto_loxe": True, "show_route": True,
            "show_loxe": True, "show_toasts": True, "show_board": True, "board_seconds": 180, "rest_seconds": 90}


def admin(body):
    urllib.request.urlopen(urllib.request.Request(B + "/api/admin", json.dumps(body).encode(), {"Content-Type": "application/json"}))


# đón khách 15 phút: script chạy chậm trên máy không GPU, xe không được xuất bến giữa chừng
admin({"action": "settings", "changes": {**DEFAULTS, "board_seconds": 900}})
try:
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctl = br.new_page(viewport={"width": 390, "height": 900})
        ctl.set_default_timeout(120000)
        live = br.new_page(viewport={"width": 360, "height": 640})
        live.set_default_timeout(120000)
        errors = []
        for pg in (ctl, live):
            pg.on("pageerror", lambda e: errors.append(str(e)))
        ctl.goto(B + "/control", wait_until="domcontentloaded")
        urllib.request.urlopen(urllib.request.Request(B + "/api/admin", b'{"action":"reset"}', {"Content-Type": "application/json"}))
        live.goto(B + "/?res=0.5", wait_until="domcontentloaded")
        ctl.fill("#name", "Minh Anh")
        ctl.click("#quick >> text=Nghệ An")
        time.sleep(3)

        # camera: 4 góc ngoài xe + khoảng cách
        for key, label in (("wide", "Toàn cảnh"), ("high", "Từ trên cao"), ("side", "Ngang xe"), ("close", "Cận xe")):
            ctl.click(f"text={label}")
            time.sleep(3.5)
            ok(st()["control"]["cam"] == key, f"góc {label} lưu ở server")
            live.screenshot(path=OUT / f"cam-{key}.png")
        ok("on" in ctl.get_attribute("[data-val=close]", "class"), "nút góc đang chọn được tô sáng")
        ctl.click("#zoom-out")
        ctl.click("#zoom-out")
        time.sleep(0.8)
        ok(st()["control"]["zoom"] == 1.2, "khoảng cách +0,2")
        time.sleep(3)
        live.screenshot(path=OUT / "cam-close-zoom12.png")
        ctl.click("#zoom-reset")
        ctl.click("text=Toàn cảnh")

        # trong / ngoài xe — không còn tự đổi
        ctl.click("text=Trong xe (24 giường)")
        ok(until(live, "document.getElementById('hud').classList.contains('inside')"), "overlay vào trong xe")
        live.screenshot(path=OUT / "view-inside.png")
        time.sleep(8)
        still = live.evaluate("document.getElementById('hud').classList.contains('inside')")
        ok(still, f"trong xe giữ nguyên, không tự quay ra (server view={st()['control']['view']})")
        ctl.click("text=Ngoài xe")
        ok(until(live, "!document.getElementById('hud').classList.contains('inside')"), "overlay ra ngoài xe")

        # tạm dừng
        left0 = st()["phase_left"]
        ctl.click("#pause")
        time.sleep(3)
        s = st()
        ok(s["paused"] and abs(s["phase_left"] - left0) < 2.5, "tạm dừng: đồng hồ đứng")
        ok(until(live, "document.getElementById('phase-pill').textContent === 'Tạm dừng'"), "overlay hiện «Tạm dừng»")
        ok("Chạy tiếp" in ctl.inner_text("#pause"), "nút đổi thành «Chạy tiếp»")
        live.screenshot(path=OUT / "paused.png")
        ctl.click("#pause")
        time.sleep(1)
        ok(not st()["paused"], "chạy tiếp")
        before = st()["phase_left"]
        ctl.click("[data-extend='30']")
        time.sleep(0.6)
        ok(st()["phase_left"] > before + 25, "+30 giây")

        # thời gian
        ctl.fill("#board-seconds", "120")
        ctl.fill("#rest-seconds", "60")
        ctl.click("#save-times")
        time.sleep(0.6)
        c = st()["control"]
        ok(c["board_seconds"] == 120 and c["rest_seconds"] == 60, "lưu thời gian đón / nghỉ")

        # bật tắt từng phần
        for key, sel in (("show_board", "#board"), ("show_loxe", "#loxe"), ("show_route", "#route"), ("show_toasts", "#toasts")):
            ctl.uncheck(f"[data-show={key}]")
            ok(until(live, f"getComputedStyle(document.querySelector('{sel}')).display === 'none'"), f"tắt {sel}")
        live.screenshot(path=OUT / "all-hidden.png")
        for key in ("show_board", "show_loxe", "show_route", "show_toasts"):
            ctl.check(f"[data-show={key}]")
        ok(until(live, "getComputedStyle(document.querySelector('#board')).display !== 'none'"), "bật lại bảng tỉnh")

        # lơ xe nói + băng rôn
        ctl.fill("#say", "Chào bà con tối nay nha!")
        ctl.click("#say-send")
        ok(until(live, "document.getElementById('loxe-text').textContent === 'Chào bà con tối nay nha!'"), "lơ xe nói câu admin gõ")
        ctl.fill("#ann-title", "🎉 Giờ vàng 21h")
        ctl.fill("#ann-text", "Thả tim x2 tốc độ xe!")
        ctl.click("#ann-send")
        ok(until(live, "document.getElementById('banner').textContent.includes('Giờ vàng 21h') && !document.getElementById('banner').classList.contains('hidden')"),
           "băng rôn admin hiện")
        live.screenshot(path=OUT / "announce.png")

        # chất lượng hình: thấp → overlay đổi (ghi lên khung #stage), cao → trở lại
        ctl.click("text=Thấp (máy nóng / LIVE Studio giật)")
        ok(until(live, "document.getElementById('stage').dataset.quality === 'low'"), "chất lượng thấp áp dụng")
        ctl.click("[data-set=quality][data-val=high]")
        ok(until(live, "document.getElementById('stage').dataset.quality === 'high'"), "chất lượng cao trở lại")

        # lơ xe tự nói tắt: chờ server nhận + câu lơ xe đứng yên (overlay vẽ chậm còn đang hiện dở câu cũ) rồi mới ghi mốc
        ctl.uncheck("[data-show=auto_loxe]")
        for _ in range(40):
            if st()["control"]["auto_loxe"] is False:
                break
            time.sleep(0.25)
        marker = live.inner_text("#loxe-text")
        for _ in range(20):
            time.sleep(1)
            now_text = live.inner_text("#loxe-text")
            if now_text == marker:
                break
            marker = now_text
        phase_before = st()["phase"]
        ctl.click("#skip")  # qua pha (đang đón khách → xuất bến): bình thường lơ xe sẽ nói
        for _ in range(40):
            if st()["phase"] != phase_before:
                break
            time.sleep(0.25)
        time.sleep(4)
        after = live.inner_text("#loxe-text")
        ok(after == marker, f"tắt lơ xe tự nói: không nói khi qua pha ({phase_before} → {st()['phase']}; «{marker}» → «{after}»)")
        ctl.check("[data-show=auto_loxe]")

        # tải lại overlay → thiết lập vẫn giữ
        ctl.click("text=Từ trên cao")
        time.sleep(0.6)
        live.reload()
        time.sleep(3)
        ok(st()["control"]["cam"] == "high", "thiết lập còn sau khi tải lại")
        ok((Path(__file__).resolve().parents[2] / "storage" / "db" / "config" / "xe_tet.json").exists(), "file thiết lập ở storage/db/config")

        # trả về mặc định
        ctl.click("text=Toàn cảnh")
        ctl.fill("#board-seconds", "180")
        ctl.fill("#rest-seconds", "90")
        ctl.click("#save-times")
        ctl.screenshot(path=OUT / "control.png", full_page=True)
        ok(ctl.evaluate("document.documentElement.scrollWidth") <= 390, "bảng điều khiển không cuộn ngang ở 390 px")

        print("JS errors:", errors)
        print(f"PASS {len(passes)}")
        print("FAIL:", fails or "(không)")
        br.close()
finally:
    admin({"action": "settings", "changes": DEFAULTS})  # lỗi giữa chừng cũng không để lại thiết lập bẩn
