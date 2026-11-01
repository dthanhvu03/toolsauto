import "./style.css";
import { Hud } from "./hud";
import { H, W, World } from "./scene";
import { Sound } from "./sound";
import type { GameEvent, State } from "./types";

const stage = document.getElementById("stage") as HTMLElement;

function fit(): void {
  const scale = Math.min(window.innerWidth / W, window.innerHeight / H);
  stage.style.transform = `translate(-50%, -50%) scale(${scale})`;
}
window.addEventListener("resize", fit);
fit();

// Chữ vẽ lên canvas (biển bến, bảng LED, cột cây số) chỉ vẽ một lần: chờ font Be Vietnam Pro tải xong rồi mới dựng cảnh,
// không thì biển giữ font dự phòng suốt buổi live. Mạng chậm / mất mạng thì sau 2,5 giây dựng luôn.
const FONT_WAIT_MS = 2500;
// Vẽ tối đa 30 khung / giây — bằng tốc độ phát live, card đồ hoạ đỡ một nửa việc (học từ zane-tv/tiktok-live-temple-rpc).
const FRAME_MS = 1000 / 30;

function fontsReady(): Promise<unknown> {
  return Promise.race([
    Promise.all(["800 40px", "600 40px"].map((w) => document.fonts.load(`${w} "Be Vietnam Pro"`))),
    new Promise((ok) => window.setTimeout(ok, FONT_WAIT_MS)),
  ]).catch(() => undefined);
}

function start(): void {
  const world = new World(
    document.getElementById("gl") as HTMLCanvasElement,
    document.getElementById("labels") as HTMLElement,
    document.getElementById("fade") as HTMLElement,
  );
  const hud = new Hud();
  const sound = new Sound();
  sound.onLock = (locked) => document.getElementById("sound-lock")!.classList.toggle("hidden", !locked);
  // Trong xe: tên đã nằm trên giường → ẩn thông báo + bảng tỉnh để không che tầng trên.
  world.onView = (view) => document.getElementById("hud")!.classList.toggle("inside", view === "inside");

  function connect(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => hud.setOnline(true);
    ws.onmessage = (msg) => {
      let data: { kind?: string };
      try {
        data = JSON.parse(msg.data);
      } catch {
        return;  // khung hỏng: bỏ, khung sau (5 lần / giây) tới ngay
      }
      // cảnh 3D, chữ, âm thanh chạy độc lập: một phần lỗi không kéo phần khác đứng theo
      const each = (...steps: (() => void)[]) => {
        for (const step of steps) {
          try { step(); } catch (err) { console.error(err); }
        }
      };
      if (data.kind === "state") {
        each(() => world.update(data as State), () => hud.update(data as State), () => sound.update(data as State));
      } else if (data.kind === "event") {
        each(() => world.onEvent(data as GameEvent), () => hud.onEvent(data as GameEvent),
          () => sound.onEvent(data as GameEvent));
      }
    };
    ws.onclose = () => {
      hud.setOnline(false);
      window.setTimeout(connect, 1500);
    };
  }
  connect();

  // ?fps=1: đồng hồ khung hình + số lần vẽ để anh đo trên GPU thật (không bật khi đang live).
  const meter = new URLSearchParams(location.search).has("fps") ? document.createElement("div") : null;
  if (meter) {
    meter.style.cssText = "position:fixed;left:8px;top:8px;z-index:9;background:#000c;color:#7f7;font:14px monospace;padding:6px 10px;border-radius:6px";
    document.body.append(meter);
  }
  let frames = 0;
  let meterAt = performance.now();
  let last = performance.now();
  function loop(now: number): void {
    requestAnimationFrame(loop);
    if (now - last < FRAME_MS - 2) return;
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    world.frame(dt);
    frames++;
    if (meter && now - meterAt >= 1000) {
      const { calls, triangles, geometries, textures } = world.stats();  // hình / ảnh tăng mãi = rò bộ nhớ GPU
      meter.textContent = `${Math.round((frames * 1000) / (now - meterAt))} khung/s · ${calls} lần vẽ · ` +
        `${(triangles / 1000).toFixed(0)}k tam giác · ${geometries} hình · ${textures} ảnh`;
      frames = 0;
      meterAt = now;
    }
  }
  requestAnimationFrame(loop);
}

void fontsReady().then(start);
