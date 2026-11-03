import "./style.css";
import { Hud } from "./hud";
import { preloadBlenderModels } from "./models";
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

// Chữ vẽ lên canvas (biển bến, bảng LED, cột cây số) chỉ vẽ một lần: chờ font tải xong rồi mới dựng cảnh, không thì biển
// giữ font dự phòng suốt buổi live. Font chia bộ chữ theo unicode-range (latin / latin-ext / vietnamese): phải đưa chữ mẫu
// có dấu thì trình duyệt mới tải bộ tiếng Việt (không đưa thì chỉ tải bộ latin → «Ế Ầ Ừ» vẽ bằng font dự phòng).
// Font nằm sẵn trên máy (public/fonts) nên thường xong ngay; lỗi thì sau 2,5 giây dựng luôn.
const FONT_WAIT_MS = 2500;
// Vẽ tối đa 30 khung / giây — bằng tốc độ phát live, card đồ hoạ đỡ một nửa việc (học từ zane-tv/tiktok-live-temple-rpc).
const FRAME_MS = 1000 / 30;
const CONTEXT_WAIT_MS = 10_000;
const RETRY_MS = 30_000;
const FONT_SAMPLE = "Aa ẾẠỪẦĐĂƠƯỚỘ ếạừầđăơướộ 0123";
const FONT_FACES = ['800 40px "Be Vietnam Pro"', '600 40px "Be Vietnam Pro"', '800 40px "Baloo 2"'];

function fontsReady(): Promise<unknown> {
  return Promise.race([
    Promise.all(FONT_FACES.map((face) => document.fonts.load(face, FONT_SAMPLE))),
    new Promise((ok) => window.setTimeout(ok, FONT_WAIT_MS)),
  ]).catch(() => undefined);
}

async function start(): Promise<void> {
  const canvas = document.getElementById("gl") as HTMLCanvasElement;
  let world: World;
  try {
    world = new World(canvas, document.getElementById("labels") as HTMLElement, document.getElementById("fade") as HTMLElement);
  } catch (err) {  // trình duyệt tạm chặn WebGL (mất ngữ cảnh nhiều lần liền): đợi rồi tải lại, không đứng màn đen cả buổi
    console.error(err);
    window.setTimeout(() => location.reload(), RETRY_MS);
    return;
  }
  // Mất ngữ cảnh WebGL (driver card đồ hoạ khởi động lại, hết bộ nhớ GPU): three tự dựng lại khi trình duyệt trả ngữ cảnh →
  // biên dịch lại shader trước khi vẽ tiếp; CONTEXT_WAIT_MS không trả thì tải lại trang (state lấy từ server, không mất gì).
  let reloadTimer = 0;
  canvas.addEventListener("webglcontextlost", () => {
    reloadTimer = window.setTimeout(() => location.reload(), CONTEXT_WAIT_MS);
  });
  canvas.addEventListener("webglcontextrestored", () => {
    window.clearTimeout(reloadTimer);
    void world.warmUp().catch((err) => console.error(err));
  });
  // biên dịch sẵn shader trước khi nhận state (state đổi ẩn / hiện bối cảnh) và trước vòng vẽ; lỗi thì vẫn chạy như cũ
  await world.warmUp().catch((err) => console.error(err));
  const hud = new Hud();
  const sound = new Sound();
  sound.onLock = (locked) => document.getElementById("sound-lock")!.classList.toggle("hidden", !locked);
  // Trong xe: tên đã nằm trên giường → ẩn thông báo + bảng tỉnh để không che tầng trên.
  world.onView = (view) => document.getElementById("hud")!.classList.toggle("inside", view === "inside");
  world.onVideo = (video) => sound.attachVideo(video);

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
      if (data.kind === "hello") {  // server báo số của màn này (chỉ một màn game phát tiếng)
        sound.setScreen((data as { screen?: number }).screen ?? null);
      } else if (data.kind === "state") {
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
  // Vẽ theo lịch mỗi 33,3 ms (không phải «cách khung trước ≥ 31 ms»): màn 75 Hz theo ngưỡng chỉ ra 25 khung / giây
  // (3 nhịp màn = 40 ms), theo lịch thì xen 2 – 3 nhịp, đủ 30. Trễ hẳn (tab bị treo) thì đặt lại lịch, không vẽ dồn.
  let due = last;
  function loop(now: number): void {
    requestAnimationFrame(loop);
    if (now < due - FRAME_MS / 4) return;  // nới 8 ms: máy chủ tự gọi đúng 30 nhịp / giây hơi sớm thì vẫn vẽ, không bỏ khung
    due += FRAME_MS;
    if (now - due > FRAME_MS) due = now + FRAME_MS;
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

void Promise.all([fontsReady(), preloadBlenderModels()]).then(start).catch((err) => console.error(err));
