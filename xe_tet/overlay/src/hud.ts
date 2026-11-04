// Lớp chữ HTML đè lên cảnh 3D, viết cho người xem trên điện thoại (khung 1080 co về ~390 px):
// ít chữ, chữ to, mỗi người tương tác đều thấy mình trên màn hình.

import { BERTHS } from "./art";
import type { Block, GameEvent, Quiz, Route, State, Vendor, Versus, VersusSide } from "./types";

const $ = (id: string) => document.getElementById(id) as HTMLElement;

// State tới 5 lần / giây: chỉ ghi DOM khi nội dung đổi, tránh vẽ lại chữ liên tục (nháy chữ trên vài máy).
function setHTML(id: string, html: string): void {
  const el = $(id);
  if (el.dataset.html !== html) {  // so với bản đã ghi (đọc innerHTML là bắt trình duyệt dựng lại chuỗi HTML mỗi lần)
    el.innerHTML = html;
    el.dataset.html = html;
  }
}
function setText(id: string, text: string): void {
  const el = $(id);
  if (el.textContent !== text) el.textContent = text;
}

const BLOCK_PILL: Record<string, string> = { toll: "Trạm thu phí", police: "Công an", tire: "Xẹp lốp", jam: "Kẹt xe", cattle: "Trâu qua đường" };
const INCIDENT_ICON: Record<string, string> = { tire: "🛞", jam: "🚗", cattle: "🐃" };
const WEATHER_NOTE: Record<string, [string, string]> = {
  drizzle: ["🌦 Mưa phùn", "Đường trơn · xe chạy chậm cho chắc"],
  rain: ["🌧 Trời đổ mưa", "Kéo rèm lại · bác tài bật gạt nước"],
  fog: ["🌫 Sương mù", "Bác tài bật đèn sương mù"],
  clear: ["☀️ Trời tạnh", "Nắng lên rồi · xe chạy bon bon"],
};

const PILL: Record<State["phase"], string> = {
  BOARDING: "Đón khách", DRIVING: "Đang chạy", REST: "Trạm dừng", DROPOFF: "Thả khách",
  FINISH: "Về bến", SPECIAL: "Chúc Tết",
};
const MAX_TOASTS = 2;  // anh 03/11 «che hết rồi»: tối đa 2 thẻ, không phủ xuống nóc xe
const GIFT_BOARD_MS = 12_000;  // vừa có quà: bảng góc phải giữ danh sách quà chừng này
// danh sách quà dọc ở bảng góc phải (anh 04/11 «phải show dạng list thì user mới thấy») — trái: quà làm gì, phải: giá
const GIFT_ROWS: [string, string][] = [
  ["⚡ Lên đầu hàng", "1 xu"],
  ["🚀 Xe x2 · 3 giây", "mỗi xu"],
  ["🎆 Pháo hoa về quê", "10 xu"],
  ["🏮 Băng rôn tên bạn", "100 xu"],
  ["🧧 Cả xe chúc Tết", "1000 xu"],
  ["👑 Chủ nhà xe", "top quà"],
];
const FLASH_MS = 2600;
const FLASH_MINOR_GAP_MS = 8000;  // chữ lớn phụ (bóp còi, trà đá, mốc tim) cách nhau ít nhất 8 giây
const HUD_SCALE = 0.8;  // cỡ chữ mặc định (server chưa gửi thiết lập)
const CTA_ROTATE_MS = 4000;
const GUIDE_MS = 10_000;  // màn «Cách chơi» lớn mỗi lần xe vào bến đón khách
const BOARD_ROTATE_MS = 8000;
const CALLOUT_MS = 1700;
const NAMED_KEEP = 500;  // nhớ lần gọi tên của 500 người gần nhất (có trần, không phình suốt buổi)
const CALLOUT_MERGE = 3; // chờ quá 3 người thì gộp tên vào một thẻ
const MAX_HEARTS = 30;
const SPECIAL_TIER = 4; // bậc quà «cả xe chúc Tết»: hiện băng rôn lớn thay vì thông báo nhỏ
const QUEUE_ROWS = 5;
const MAX_BANNERS = 6;  // băng rôn chờ tối đa; quá thì bỏ (thẻ / thông báo vẫn còn)
// Xe tăng cường ghé nhiều tỉnh liền nhau: gom người về tới trong ~6 giây vào một băng rôn (tên · tỉnh), không mỗi tỉnh một băng
const RELIEF_BATCH_MS = 6000;
const RELIEF_PAGE_SECONDS = 3.5;
const NAMES_PER_PAGE = 4;  // bằng bảng tỉnh dẫn đầu: khung không cao thêm, không lấn vùng nút TikTok

function esc(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}
const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
const seatsOf = (s: State) => s.bus.seats.length;  // số giường do server quyết (engine.SEATS)
const floorName = (seat: number, seats: number) => (seat < seats / 2 ? "tầng dưới" : "tầng trên");
const km = (n: number) => Math.max(0, Math.round(n)).toLocaleString("vi-VN");
/** Giờ xe chạy thật: dưới 1 giờ thì tính phút (tròn 5 phút), từ 1 giờ trở lên tính giờ. */
const drive = (hours: number) => (hours < 1 ? `${Math.max(5, Math.round((hours * 60) / 5) * 5)} phút` : `${Math.round(hours)} giờ`);

interface Ticket {
  name: string; province: string; seat: number | null; next: boolean; eta?: number;
  lane: string; arrow: string; km: number; departure: string; bus: number;
  pickup?: string; pickupIn?: number; passed?: string;  // bắt xe dọc đường / xe đã qua quê (PLAN-136)
  tripNo?: number;
  promoted?: boolean; relief?: boolean;  // người đang giữ chỗ được xếp lên xe / lên xe tăng cường
}

/** Trả lời «xe nào / tới đâu rồi» cho đúng người hỏi (PLAN-134 B). */
function whereText(e: GameEvent): [string, string] {
  const name = esc(e.name ?? "");
  const province = esc(e.province ?? "");
  const eta = e.in_s != null ? ` · ~${clock(e.in_s)}` : "";
  switch (e.status) {
    case "seat": {
      const head = `🎫 ${name} · chuyến ${e.bus_no} · giường ${(e.seat ?? 0) + 1}`;
      if (e.phase === "BOARDING") return [head, `Đang đón khách · xuất bến sau ${clock(e.depart_in ?? 0)} · về ${province}`];
      if (e.phase === "FINISH") return [head, `Xe đang về bến`];
      if (e.pickup) return [head, `Ra điểm đón ${esc(e.pickup)} chờ${e.pickup_in ? ` · ~${clock(e.pickup_in)} xe tới` : ""} · về ${province}`];
      if (!e.stops_before && e.in_s === 0) return [head, `Đang thả khách ở ${province}`];
      return [head, `${e.stops_before ? `Còn ${e.stops_before} điểm nữa tới ${province}` : `Điểm kế là ${province}`}${eta}`];
    }
    case "relief":
      return [`🎫 ${name} · xe tăng cường số ${e.bus_no}`,
        `${e.stops_before ? `Còn ${e.stops_before} điểm nữa tới ${province}` : `Điểm kế là ${province}`}${eta}`];
    case "queue":
      return [`⏳ ${name} giữ chỗ chuyến ${e.bus_no} ${e.arrow ?? ""} ${esc(e.lane ?? "")}`,
        `Thứ ${e.position} trong hàng · lên xe ~${e.eta_min} phút · về ${province}`];
    case "home":
      return [`🏠 ${name} đã về tới quê`, "Chúc cả nhà năm mới an khang"];
    default:
      return [`🎫 ${name} chưa có vé`, "Gõ TÊN TỈNH để lên xe"];
  }
}

export class Hud {
  private bannerTimer = 0;
  private boardPending = 0;  // người đã có giường còn đứng hàng ở bến (scene báo) — chưa tính «trên xe»
  private lastState: State | null = null;
  // băng rôn xếp hàng: xe chính và xe tăng cường có thể tới nơi cùng lúc — đọc tên lần lượt, không đè nhau
  private bannerQueue: { pages: string[]; seconds: number; pageSeconds: number }[] = [];
  private bannerBusy = false;
  // thông báo theo khoá (quà của cùng một người): cập nhật thẻ cũ thay vì mỗi lần bấm combo một thẻ mới
  private keyed = new Map<string, { el: HTMLElement; timer: number }>();
  private pageTimer = 0;
  private flashTimer = 0;
  private state: State | null = null;
  private ctaTick = 0;
  private guideShown = false;
  private guideTimer = 0;
  private boardTick = 0;
  private tickets: Ticket[] = [];
  private namedAt = new Map<string, number>();  // lần cuối tên được hiện trên thẻ lớn (chọn tên khi dồn vé)
  private notes: { big: string; small: string }[] = [];
  private reliefArrivals: { name: string; vip: boolean; province: string }[] = [];
  private reliefTimer = 0;
  private calloutBusy = false;
  private lastPass: string | null = null;
  private seats = BERTHS;  // cập nhật theo state; dùng cho thẻ vé (giường thuộc tầng nào)
  private marksKey = "";
  private busDot: HTMLElement | null = null;

  constructor() {
    window.setInterval(() => { this.ctaTick++; this.renderCta(); }, CTA_ROTATE_MS);
    window.setInterval(() => { this.boardTick++; this.renderBoard(); }, BOARD_ROTATE_MS);
    // lơ xe + thông báo bám ngay dưới khung kêu gọi: khung gọn lại thì nhích lên, chừa cảnh xe
    new ResizeObserver(() => this.placeUnderCta()).observe($("cta"));
  }

  private giftBoardUntil = 0;
  private focusName = "";

  /** Đặt lơ xe / cột thông báo ngay dưới đáy khung kêu gọi (đơn vị thiết kế 1080×1920, chia cho cỡ chữ --z). */
  private placeUnderCta(): void {
    const stage = $("hud").getBoundingClientRect();
    const cta = $("cta").getBoundingClientRect();
    if (!stage.width || !cta.height) return;
    const ratio = stage.width / 1080;
    const z = parseFloat(getComputedStyle($("hud")).getPropertyValue("--z")) || HUD_SCALE;
    const bottom = (cta.bottom - stage.top) / ratio + 14;  // px thiết kế
    ($("loxe") as HTMLElement).style.top = `${bottom / z}px`;
    const toasts = $("toasts") as HTMLElement;
    toasts.style.top = `${bottom / z}px`;
    toasts.style.maxHeight = `${Math.max(120, 1270 - bottom) / z}px`;  // không chạm bảng góc phải (1290 px)
  }

  /** Thẻ vé giữa màn: thường đè tạm lên khung «Gõ tên tỉnh»; khung đang là câu đố / trạm / sự cố / cô Ba thì hạ xuống ngay
   *  dưới thanh góp quà — chỉ che tạm bảng quà, không che câu hỏi (anh 03/11 «bị che mất câu đố»). */
  private placeCallout(): void {
    const el = $("callout") as HTMLElement;
    const block = $("cta-block");
    const stage = $("hud").getBoundingClientRect();
    const rect = block.getBoundingClientRect();
    if (block.classList.contains("hidden") || !stage.width || !rect.height) {
      el.style.top = "";
      return;
    }
    const z = parseFloat(getComputedStyle($("hud")).getPropertyValue("--z")) || HUD_SCALE;
    el.style.top = `${((rect.bottom - stage.top) / (stage.width / 1080) + 10) / z}px`;
  }

  /** Scene báo số người còn đứng hàng lên xe: số trên xe tăng theo từng người bước vào cửa. */
  setBoarding(pending: number): void {
    if (pending === this.boardPending) return;
    this.boardPending = pending;
    this.renderSeats();
  }

  private renderSeats(): void {
    const s = this.lastState;
    if (!s) return;
    const on = Math.max(0, s.bus.riders - (s.phase === "BOARDING" ? this.boardPending : 0));
    setText("seats", `🚌 ${on}/${seatsOf(s)}` + (s.waiting ? ` · ⏳${s.waiting}` : ""));
  }

  update(s: State): void {
    const prevPhase = this.state?.phase;
    this.state = s;
    // màn «Cách chơi» lớn 10 giây: lúc mở trang và mỗi lần xe chính vào bến đón khách (PLAN-142)
    if (s.phase === "BOARDING" && prevPhase !== "BOARDING" && (prevPhase !== "SPECIAL" || !this.guideShown)) this.showGuide();
    this.seats = seatsOf(s);
    const c = s.control;
    const hud = $("hud");
    const scale = String(c?.hud_scale ?? HUD_SCALE);
    if (hud.style.getPropertyValue("--z") !== scale) {  // cỡ chữ trên live (admin chỉnh)
      hud.style.setProperty("--z", scale);
      requestAnimationFrame(() => this.placeUnderCta());
    }
    hud.classList.toggle("hide-route", c?.show_route === false);
    hud.classList.toggle("hide-loxe", c?.show_loxe === false);
    hud.classList.toggle("hide-toasts", c?.show_toasts === false);
    hud.classList.toggle("hide-board", c?.show_board === false);
    hud.classList.toggle("showing", !!s.show);  // xem video bảng quảng cáo: ẩn khung kêu gọi / lơ xe / thông báo cho thấy bảng
    // tháng Chạp → mùng 10: ghi ngày âm lịch («26 Chạp · còn 4 ngày nữa là Tết», «Giao thừa», «Mùng 2 Tết») — PLAN-134 C
    const lunar = s.season?.lunar;
    setText("countdown", s.days_to_tet > 1
      ? `${lunar ? `${lunar} · c` : "C"}òn ${s.days_to_tet} ngày nữa là Tết`
      : lunar ?? "Chúc Mừng Năm Mới!");
    const mainAd = c?.ads_on ? c.ads?.[0] : undefined;  // bot chính thường trực cạnh đếm ngày (PLAN-153)
    const titleAd = $("title-ad");
    titleAd.classList.toggle("hidden", !mainAd);
    if (mainAd) {
      const html = `💸 Tele <b>${esc(mainAd.title.replace(/^tele(gram)?\s*:\s*/i, ""))}</b>`;
      if (titleAd.dataset.html !== html) titleAd.innerHTML = titleAd.dataset.html = html;
    }
    setText("phase-pill", s.paused ? "Tạm dừng" : s.show ? "Xem video" : s.block ? (BLOCK_PILL[s.block.kind] ?? "Dừng xe")
      : s.halt ? "Đón dọc đường" : PILL[s.phase]);
    // phần đầu được cắt «…» khi hẹp; phần đuôi (km còn lại, đếm ngược) không bao giờ bị cắt
    const [head, tail] = this.statusText(s);
    setHTML("phase-text", `<span class="head">${esc(head)}</span>${tail ? `<span class="tail">${esc(tail)}</span>` : ""}`);
    ($("bar-fill") as HTMLElement).style.width = `${Math.round(this.progress(s) * 100)}%`;
    this.renderMarks(s);
    this.lastState = s;
    this.renderSeats();
    setHTML("next-stops", this.nextStops(s));
    const pass = s.terrain?.pass ?? null;
    if (pass && pass !== this.lastPass) this.flash(`${s.terrain.tunnel ? "🚇" : "⛰"} ${pass}`);  // vừa vào đèo / hầm
    this.lastPass = pass;
    this.renderCta();
    this.renderBoard();

    const resting = s.phase === "REST";
    $("rest-card").classList.toggle("hidden", !resting);
    $("board").classList.toggle("hidden", resting || !!s.block);  // bị chặn: chừa góc phải cho barie / chú CSGT
    if (resting) {
      setHTML("rest-orders", s.rest.orders.length
        ? s.rest.orders.slice(0, 3).map((o) => `<div>${o.emoji} ${esc(o.item)} × ${o.count}</div>`).join("")
        : `<div>Đặc sản: ${esc(s.specialty)}</div>`);
      setText("rest-wc", s.rest.wc_count ? `🚻 Hàng WC: ${s.rest.wc_count}` : "🚻 WC trống");
    }
    setText("stay", s.staying_count ? `🏠 Ở lại: ${s.staying_count} người` : "");
  }

  /** [phần đầu, phần đuôi] của dòng trạng thái. */
  private statusText(s: State): [string, string] {
    if (s.paused) return ["Xe dừng chờ xíu nha", ""];
    if (s.show) return [`📺 ${s.show.title}`, `còn ${clock(s.show.left)}`];  // dừng xem video bảng quảng cáo
    if (s.block && s.block.left != null) return [`${INCIDENT_ICON[s.block.kind] ?? "⚠"} ${s.block.reason} · ${s.block.place}`,
      `❤ thả tim · ${s.block.left}s`];  // sự cố: tự xong
    if (s.block) return [s.block.kind === "toll" ? `🚧 Trạm thu phí ${s.block.place}` : `👮 ${s.block.reason}`,
      `góp ${s.block.paid}/${s.block.goal} xu`];  // PLAN-148
    if (s.vendor?.stage === "stop") return [`🧺 Tấp vào cho ${s.vendor.name} lên xe`, `${s.vendor.left ?? 0}s`];
    if (s.halt) return [`🚏 Dừng đón ở ${s.halt.place}`, `${s.halt.people.length} người lên`];  // PLAN-145
    const leg = s.legs[s.leg_index];
    const left = s.phase_left ?? 0;
    if (s.name_hold) return ["📢 Đang đọc tên khách lên xe", "xe chạy liền"];
    if (s.rollcall?.length && s.phase === "BOARDING") {  // điểm danh: người im lặng lâu tới lượt lên xe
      const who = s.rollcall.slice(0, 2).map((r) => r.name).join(", ") + (s.rollcall.length > 2 ? ` +${s.rollcall.length - 2}` : "");
      return [`📣 Gọi ${who}`, `❤ giữ giường ${s.rollcall[0].left}s`];
    }
    switch (s.phase) {
      case "BOARDING":  // bến đi đã ghi trên bảng LED và biển bến
        return [s.bus.riders >= seatsOf(s) ? "Đủ khách!" : `Đi ${s.bus.to}`, `chạy sau ${clock(left)}`];
      case "DRIVING": {
        if (!leg) return ["", ""];
        const fast = s.turbo  // quà: xe chạy x2 (anh 03/11)
          ? ` 🚀x${s.speed.toFixed(1)} · ${s.turbo.left}s`
          : s.speed >= 1.15 ? ` ⚡x${s.speed.toFixed(1)}` : "";  // tim của người xem đang đẩy xe
        return [`Tới ${leg.label}`, `còn ${km(Math.max(1, leg.km - s.trip_km))} km${fast}`];
      }
      case "SPECIAL": return ["Cả xe dừng lại chúc Tết", ""];
      case "REST": return [`Nghỉ ở ${s.place}`, `còn ${clock(left)}`];
      case "DROPOFF": return [leg ? `Tới ${leg.label} rồi!` : "", ""];
      case "FINISH": return [`Chuyến ${s.bus.no} xong · xe về bến đón tiếp`, ""];
    }
  }

  /** Ở bến: giường đã kín bao nhiêu; trên đường: cả chuyến đã đi bao nhiêu (chấm điểm dừng nằm trên cùng thanh). */
  private progress(s: State): number {
    if (s.phase === "BOARDING") return s.bus.riders / seatsOf(s);
    const route = this.trip(s);
    return route ? Math.min(1, route.odo / route.total) : 1;
  }

  private trip(s: State): Route | null {
    const route = s.route;
    return route && route.total > 0 && route.stops.length && s.phase !== "BOARDING" ? route : null;
  }

  /** Chấm điểm dừng trên thanh cả chuyến (dựng lại chỉ khi chuyến / điểm đã qua đổi) + chiếc xe: chỉ dời vị trí, để
   * hiệu ứng trượt CSS chạy mượt và không vẽ lại cả dải 5 lần / giây. */
  private renderMarks(s: State): void {
    const route = this.trip(s);
    const at = (k: number) => `${Math.min(100, (k / (route?.total || 1)) * 100).toFixed(1)}%`;
    const key = route ? `${route.total}|${route.stops.map((p) => `${p.kind}${p.km}${p.done ? 1 : 0}`).join(",")}|`
      + (route.via ?? []).filter((v) => v.done).length : "";
    if (key !== this.marksKey) {
      this.marksKey = key;
      const el = $("marks");
      // tỉnh đi qua (không ai xuống): chấm nhỏ, vẽ trước để chấm điểm dừng đè lên
      el.innerHTML = route
        ? (route.via ?? []).map((v) => `<b class="mk via${v.done ? " done" : ""}" style="left:${at(v.km)}"></b>`).join("")
          + route.stops.map((p) => `<b class="mk ${p.kind}${p.done ? " done" : ""}" style="left:${at(p.km)}"></b>`).join("")
          + `<i class="bus-dot">🚌</i>`
        : "";
      this.busDot = el.querySelector(".bus-dot");
    }
    if (route && this.busDot) {
      const left = at(route.odo);
      if (this.busDot.style.left !== left) this.busDot.style.left = left;
    }
  }

  private nextStops(s: State): string {
    // xe tăng cường khác đang chạy: chỉ một huy hiệu nhỏ (chi tiết ở bảng góc phải) — card tuyến không cao thêm
    const others = (s.reliefs ?? []).filter((r) => !r.featured).length;
    const rush = (s.rush ? `<span class="rush">⚡ Cao điểm</span>` : "") + (others ? `<span class="rush">🚌+${others}</span>` : "")
      + (s.bus.parcels ? `<span class="rush">📦 ${s.bus.parcels}</span>` : "");
    if (s.phase === "BOARDING" || !s.legs.length) {
      // bến nhiều làn: làn đang đón + làn có người giữ chỗ (đủ mọi làn đã có trên biển ở bến — BRD-tuyen-xe)
      // xăng / độ sạch: người xem gõ «đổ xăng», «rửa xe» lúc chờ khách (PLAN-137)
      const care = s.care ? `<span class="rush">⛽ ${Math.round(s.care.fuel * 100)}% · 🧽 ${Math.round((1 - s.care.dirt) * 100)}%</span>` : "";
      const lanes = s.lanes.filter((l) => l.current || l.waiting)
        .map((l) => `${l.arrow} ${esc(l.label.replace("Hướng ", ""))} ${l.current ? `${s.bus.riders}/${seatsOf(s)}` : `⏳${l.waiting}`}`);
      return `${rush}${care}${lanes.join(" · ")}`;
    }
    const route = this.trip(s);
    // đang qua địa phận tỉnh không ai xuống: vẫn gọi tên tỉnh đó (bà con quê đó đang xem thấy xe qua quê mình)
    const via = s.phase === "DRIVING" && route?.via?.some((v) => v.name === s.place)
      ? `<span class="rush">🛣 Qua ${esc(s.place)}</span>` : "";
    const pass = s.terrain?.pass ? `<span class="rush">${s.terrain.tunnel ? "🚇" : "⛰"} ${esc(s.terrain.pass)}</span>` : via;
    if (!route) return `${rush}${pass}🏁 Sắp về bến`;
    // đồng hồ trên xe + điểm kế (còn bao lâu thật) + điểm sau nữa, mỗi điểm kèm giờ tới theo đồng hồ xe
    const clockText = `<span class="clock">🕐 ${route.clock.day ? `Ngày ${route.clock.day + 1} · ` : ""}${route.clock.time}</span>`;
    const ahead = route.stops.filter((p) => !p.done).slice(0, 2).map((p, i) => {
      const icon = p.kind === "rest" ? "☕" : "📍";
      const wait = i === 0 && p.in_s ? ` <small>(còn ${clock(p.in_s)})</small>` : "";
      return `${icon} ${esc(p.name)} ${p.at ?? ""}${wait}`;
    });
    return `${rush}${pass}${clockText}${ahead.length ? ahead.join(" → ") : "🏁 Sắp về bến"}`;
  }

  // ---- lời kêu gọi: dòng chính đứng yên, dòng phụ xoay vòng gợi ý ----

  private showGuide(): void {
    this.guideShown = true;
    const g = $("guide");
    g.classList.remove("hidden");
    window.clearTimeout(this.guideTimer);
    this.guideTimer = window.setTimeout(() => g.classList.add("hidden"), GUIDE_MS);
  }

  private renderCta(): void {
    const s = this.state;
    if (!s) return;
    let main: string;
    let tips: string[];
    if (s.phase === "REST") {
      main = "💬 Gõ <b>PHỞ</b> · <b>TRÀ ĐÁ</b> · <b>WC</b>";
      tips = [`🎁 Gõ MUA QUÀ: ${esc(s.specialty)}`, "🧊 Tặng quà = bao cả xe trà đá · chỉ dành cho người từ 18 tuổi",
        "🍜 Còn có BÁNH MÌ · CƠM · CÀ PHÊ", "⛽ Trạm có cây xăng: gõ ĐỔ XĂNG · 🧽 RỬA XE"];
    } else {
      main = "💬 Gõ <b>TÊN TỈNH</b> để lên xe";
      tips = ["Ví dụ: Nghệ An · 37 · Sài Gòn", "Năm nay ở lại? Gõ KHÔNG VỀ", "❤ Thả tim cho xe chạy nhanh hơn",
        "🚏 Muốn xe ra bến khác? Gõ «từ Hà Nội»",
        "⏳ Ai đặt vé trước lên xe trước · tặng quà được lên đầu hàng", "🎁 Tặng quà: từ 18 tuổi"];
      if (s.phase === "BOARDING") {  // anh dặn 02/11: nói rõ chuyến này đi đâu, hướng khác đợi chuyến sau
        const vs = s.versus;  // đối kháng ở bến (PLAN-152): chưa biết xe nào chạy — nói hai xe đang đấu
        tips.unshift(vs && !vs.done
          ? `⚔️ Xe ${esc(vs.sides[0].dest)} đấu xe ${esc(vs.sides[1].dest)} · gõ tên tỉnh để vào phe`
          : `🚌 Chuyến này đi ${esc(s.bus.lane)} · hướng khác đợi chuyến sau`);
        tips.push("⛽ Gõ ĐỔ XĂNG · 🧽 Gõ RỬA XE · xe đầy xăng, sạch chạy nhanh hơn");
      }
      const c = s.control;
      if (c?.ads_on) for (const ad of c.ads ?? []) tips.push(`📣 <b>${esc(ad.title)}</b> · ${esc(ad.desc)}`);  // bot của anh
      if (s.next_lane) {  // ai chờ trước đi trước — nói rõ xe kế tiếp đi đâu để người chờ yên tâm
        tips.unshift(`⏳ Chuyến sau: ${s.next_lane.arrow} ${esc(s.next_lane.label)} · ~${s.next_lane.eta_min} phút`);
      }
      if (s.rush) tips.push("⚡ Cao điểm: xe chạy nhanh, lên lẹ!");
      const hungry = s.bus.seats.filter((x) => x && x.full != null && x.full < 30).length;
      if (s.vendor?.stage === "sell") {  // cô Ba đang bán: cách mua luôn đứng đầu, kèm số người sắp đói
        tips.unshift(`🧺 ${esc(s.vendor.name)} đang bán · gõ NEM · BÌ · BÁNH MÌ${hungry ? ` · 😋 ${hungry} người sắp đói` : ""} · 🎁 quà = bao cả xe`);
      } else if (hungry && s.vendor?.stage === "pool") {
        tips.unshift(`😋 ${hungry} người sắp đói · góp quà ${s.vendor.paid ?? 0}/${s.vendor.goal ?? 10} xu gọi ${esc(s.vendor.name)} lên bán đồ ăn`);
      }
      if (s.vendor?.stage === "pool" && !hungry) {  // góp quà gọi cô bán hàng: gợi ý luôn đứng đầu lúc xe đang chạy
        tips.unshift(`🧺 Góp quà ${s.vendor.paid ?? 0}/${s.vendor.goal ?? 10} xu gọi ${esc(s.vendor.name)} lên xe bán nem, bì, bánh mì`);
      }
    }
    // chân bảng quà (anh 04/11 «cái nào thừa»): chỉ cảm ơn người góp lúc bị chặn + Chủ nhà xe / Phó nhà xe. Số người chờ đã có
    // ở bảng tuyến + bảng «Chờ chuyến sau», xe x2 đã có ở bảng tuyến, «từ 18 tuổi» nằm trong dòng gợi ý + màn «Cách chơi»
    const [owner, deputy] = s.patrons ?? [];
    const crown = owner ? `👑 Chủ nhà xe <b>${esc(owner.name)}</b> ${owner.xu} xu` + (deputy ? ` · Phó ${esc(deputy.name)} ${deputy.xu}` : "") : "";
    const thanks = s.block?.top.length  // đang bị chặn: chân bảng cảm ơn người góp
      ? `🙏 Cảm ơn ${s.block.top.map((t) => `<b>${esc(t.name)}</b> ${t.xu}`).join(" · ")}` : "";
    const foot = [thanks, crown].filter(Boolean).join(" · ");
    setHTML("cta-foot", foot);
    $("cta-foot").classList.toggle("hidden", !foot);
    setHTML("cta-main", main);
    setHTML("cta-sub", tips[this.ctaTick % tips.length]);
    this.renderBlock(s.block ?? null, s.vendor ?? null, s.quiz ?? null);
    const f = s.focus;
    if (f && f.name !== this.focusName) {  // anh bấm vào khách trên /control: thẻ giới thiệu người đó
      const where = f.stops_before ? `còn ${f.stops_before} điểm nữa tới ${esc(f.province)}` : `điểm kế là ${esc(f.province)}`;
      const eta = f.in_s != null ? ` · ~${clock(f.in_s)}` : "";
      this.note(`🔍 ${f.vip ? "⭐ " : ""}${esc(f.name)} · giường ${f.seat + 1} ${floorName(f.seat, this.seats)}`,
        s.phase === "BOARDING" ? `Về ${esc(f.province)} · xe sắp xuất bến` : `${where}${eta}${f.trips ? ` · lần về quê thứ ${f.trips + 1}` : ""}`);
    }
    this.focusName = f?.name ?? "";
    const g = s.goal;
    if (g) {
      const pct = Math.min(100, Math.round((g.xu / Math.max(1, g.goal)) * 100));
      setHTML("goal-bar", `<i style="width:${pct}%"></i><span>🎯 Mục tiêu buổi live ${g.xu}/${g.goal} xu · tới ${g.next_xu} xu: ${esc(g.next)}</span>`);
    }
    this.renderVersus(s.versus ?? null);
  }

  /** Thanh đối kháng: hai màu, phần mỗi bên theo tỉ lệ điểm (0 – 0 thì chia đôi); bên dẫn có vương miện. */
  private renderVersus(vs: Versus | null): void {
    const bar = $("vs-bar");
    bar.classList.toggle("hidden", !vs);
    if (!vs) return;
    const [a, b] = vs.sides;
    const total = a.points + b.points;
    const pct = total ? Math.round((a.points / total) * 100) : 50;
    const side = (x: VersusSide) => `${x.lead && total ? "👑 " : ""}${x.arrow} ${esc(x.dest)} <b>${x.points}</b>`;
    // dòng dưới (PLAN-151): giờ vàng → đếm ngược; có người góp → tên người góp nhiều nhất mỗi bên; chưa ai → cách chơi
    const tops = vs.sides.map((x) => x.top ? `${x.arrow} ${esc(x.top)}` : "").filter(Boolean);
    const foot = vs.done
      ? `🏁 Xe ${esc(a.dest)} xuất bến trước · xe ${esc(b.dest)} giữ khách, chạy chuyến sau`
      : vs.golden
        ? `⏱ GIỜ VÀNG ${clock(vs.left ?? 0)} · quà x2 điểm · 1 xu = ${(vs.xu ?? 20) * 2} điểm`
        : tops.length ? `🔥 Góp nhiều nhất: ${tops.join(" · ")} · 1 xu = ${vs.xu ?? 20} điểm`
          : `Quê bên nào góp cho xe bên đó · 1 xu = ${vs.xu ?? 20} điểm · xe nhiều điểm xuất bến trước`;
    bar.classList.toggle("golden", !!vs.golden);
    setHTML("vs-bar", `<i style="width:${Math.min(92, Math.max(8, pct))}%"></i>`
      + `<span class="a">${side(a)}</span><em>⚔️</em><span class="b">${side(b)}</span><small>${foot}</small>`);
  }

  /** Xe bị chặn (PLAN-148): thanh góp quà thay dòng «Gõ tên tỉnh» — ai cũng thấy còn thiếu bao nhiêu xu. */
  private renderBlock(b: Block | null, v: Vendor | null = null, q: Quiz | null = null): void {
    // cô Ba bán suốt chuyến: thẻ lớn chỉ lúc cô lên + 20 giây đầu, sau đó nhường chỗ «Gõ tên tỉnh», cách mua nằm ở dòng gợi ý
    if (v?.stage === "stop") this.vendorSince = 0;
    else if (v?.stage === "sell" && !this.vendorSince) this.vendorSince = Date.now();
    else if (!v || v.stage === "pool") this.vendorSince = 0;
    const quiz = !b && !!q;
    const selling = !b && !quiz && (v?.stage === "stop" || (v?.stage === "sell" && Date.now() - this.vendorSince < 20000));
    const card = !!b || quiz || selling;
    $("cta-block").classList.toggle("hidden", !card);
    $("cta-block").classList.toggle("quiz", quiz);
    $("cta-main").classList.toggle("hidden", card);
    $("cta-sub").classList.toggle("hidden", card);
    if (this.calloutBusy) this.placeCallout();  // câu đố / trạm hiện ra giữa lúc thẻ vé đang đứng
    if (quiz) {  // đố vui: câu hỏi + ba đáp án; hết giờ thì đáp án đúng + người trả lời nhanh nhất
      const opts = q!.options.map((o, i) => q!.done && i !== q!.answer ? "" : `<b>${"ABC"[i]}</b> ${esc(o)}`).filter(Boolean).join(" · ");
      const tail = q!.done
        ? (q!.winners?.length ? ` · 🏆 ${q!.winners.map((n) => esc(n)).join(", ")}` : " · chưa ai đúng")
        : ` · gõ <b>A</b> <b>B</b> <b>C</b> · ${q!.left}s`;
      setHTML("cta-block", `<div class="blk-title">🧠 ${q!.done ? "ĐÁP ÁN · " : ""}${esc(q!.question)}?</div>`
        + `<div class="blk-bar">${q!.done ? "" : `<i style="width:${Math.round(q!.left / 25 * 100)}%"></i>`}`
        + `<span>${q!.done ? "✅ " : ""}${opts}${tail}</span></div>`);
      return;
    }
    if (selling) {  // cô bán hàng trên xe: hai dòng như thẻ bị chặn — cách mua + giờ còn lại
      const treat = v!.treats?.length ? ` · 🎉 ${v!.treats.slice(-2).map((n) => esc(n)).join(", ")} bao cả xe` : "";
      setHTML("cta-block", `<div class="blk-title">🧺 ${esc(v!.name).toUpperCase()} LÊN XE · BÁN SUỐT CHUYẾN</div>`
        + `<div class="blk-bar"><span>Gõ <b>NEM</b> · <b>BÌ</b> · <b>BÁNH MÌ</b> để mua · 🎁 tặng quà bao cả xe${treat}</span></div>`);
      return;
    }
    if (!b) return;
    if (b.left != null) {  // sự cố dọc đường: tự xong, tim làm nhanh hơn, quà xong ngay
      const total = Math.max(1, b.total ?? 30);
      const done = Math.min(100, Math.round(((total - b.left) / total) * 100));
      setHTML("cta-block", `<div class="blk-title">${INCIDENT_ICON[b.kind] ?? "⚠"} ${esc(b.reason).toUpperCase()} · ${esc(b.place)}</div>`
        + `<div class="blk-bar"><i style="width:${done}%"></i><span>❤ Thả tim cho nhanh · 🎁 ${b.goal} xu xong ngay · ${b.left}s</span></div>`);
      return;
    }
    // hai dòng (cao bằng «Gõ tên tỉnh» + dòng gợi ý): không đẩy bảng quà xuống đè lơ xe
    const title = b.kind === "toll" ? `🚧 TRẠM THU PHÍ ${esc(b.place).toUpperCase()}`
      : b.speeding ? "👮 QUÁ TỐC ĐỘ · CÔNG AN PHẠT" : `👮 CÔNG AN · ${esc(b.reason)}`;
    const pct = Math.min(100, Math.round((b.paid / Math.max(1, b.goal)) * 100));
    setHTML("cta-block", `<div class="blk-title">${title}</div>`
      + `<div class="blk-bar"><i style="width:${pct}%"></i><span>${b.paid} / ${b.goal} xu · 🎁 tặng quà góp để xe đi tiếp</span></div>`);
  }

  // ---- bảng góc phải: luân phiên «người đang chờ xe sau», «ai đang trên xe», «tỉnh về đông» ----
  // Người chờ được ưu tiên: phải thấy tên mình + thứ tự thì mới chịu ở lại tới lúc lên xe.

  private renderBoard(): void {
    const s = this.state;
    if (!s) return;
    // bảng góc phải luân phiên: người chờ (có tên + thứ tự), quà, tỉnh đông nhất; khách trên xe đã có ở dải tên dưới thân xe
    const modes = [
      ...(s.queue?.length ? ["queue", "queue"] : []),
      "gifts",
      "top",
    ];
    const mode = Date.now() < this.giftBoardUntil ? "gifts" : modes[this.boardTick % modes.length];
    $("board").classList.toggle("gifts", mode === "gifts");
    if (mode === "gifts") {
      setText("board-title", "🎁 Tặng quà");
      setHTML("board-list", GIFT_ROWS.map(([what, price]) => `<li><span>${price}</span>${what}</li>`).join(""));
    } else if (mode === "queue") {
      setText("board-title", "⏳ Chờ chuyến sau");
      setHTML("board-list", s.queue.slice(0, QUEUE_ROWS).map((w) =>
        // số thứ tự đặt trước (float phải) để nằm cùng dòng; tên dài bị cắt «…», dòng không xuống hàng
        `<li><span>#${w.pos}</span>${w.arrow} ${esc(w.name)} <small>· ${esc(w.province)}</small></li>`).join(""));
    } else {
      setText("board-title", "🏆 Tỉnh đông nhất");
      setHTML("board-list", s.board.length
        ? s.board.slice(0, 5).map((b) => `<li>${esc(b.province)} <span>${b.count}</span></li>`).join("")
        : "<li>Chưa ai lên xe</li>");
    }
  }

  onEvent(e: GameEvent): void {
    const name = esc(e.name ?? "");
    this.eventAvatar = e.avatar ?? "";  // thông báo của sự kiện này có ảnh đại diện người đó (anh 03/11)
    switch (e.type) {
      case "loxe":
        this.loxe(e.text ?? "");
        break;
      case "ticket":
        if (e.changed) {
          this.toast(`🔁 ${name} đổi vé → ${esc(e.province ?? "")}`);
        } else {
          this.tickets.push({ name: `${e.badge ? `${e.badge} ` : ""}${e.name ?? ""}`, province: e.province ?? "", seat: e.seat ?? null,
            next: !!e.next, eta: e.eta_min, lane: e.lane ?? "", arrow: e.arrow ?? "",
            km: e.km ?? 0, departure: e.departure ?? "", bus: e.bus_no ?? 0,
            pickup: e.pickup, pickupIn: e.pickup_in, passed: e.passed, tripNo: e.trip_no,
            promoted: !!e.promoted, relief: !!e.relief });
          this.pumpCallout();
        }
        break;
      case "likes":
        this.hearts(e.count ?? 1);
        break;
      case "where":
        this.note(...whereText(e));
        break;
      case "fuel":  // đổ xăng / rửa xe lúc chờ khách (PLAN-137)
        this.toast(`⛽ ${name} đổ xăng`, `Bình ${Math.round((e.level ?? 0) * 100)}% · đầy bình xe chạy nhanh hơn`);
        break;
      case "wash":
        this.toast(`🧽 ${name} rửa xe`, `Sạch ${Math.round((e.level ?? 0) * 100)}% · xe sạch chạy nhanh hơn`);
        break;
      case "station_vote":  // gọi xe ra bến khác (PLAN-136)
        this.toast(`🚏 ${name} gọi xe ra ${esc(e.station ?? "")}`, `${e.votes}/${e.need} người · gõ «từ Hà Nội», «bến Đà Nẵng»…`);
        break;
      case "station_switch":
        this.flash(`🚏 Xe ra ${esc(e.station ?? "")}`);
        break;
      case "versus_start":  // đối kháng: vòng mới
        if (e.sides?.length === 2) this.note(`⚔️ Đối kháng: ${esc(e.sides[0])} đấu ${esc(e.sides[1])}`,
          "Hai xe đậu sẵn · quê bên nào thì bình luận, thả tim, tặng quà cho xe bên đó · xe nhiều điểm xuất bến trước");
        break;
      case "versus_win":  // đối kháng: hướng thắng chạy chuyến này
        this.note(`⚔️ ${esc(e.dest ?? "")} thắng ${esc(e.rival ?? "")} · ${e.points} – ${e.rival_points ?? 0}`,
          e.mvp ? `👑 Góp nhiều nhất: ${esc(e.mvp)} ${e.mvp_points ?? 0} điểm · tên lên băng rôn xe`
            : `Xe ${esc(e.dest ?? "")} xuất bến trước · xe ${esc(e.rival ?? "")} chạy chuyến sau`);
        break;
      case "versus_golden":  // PLAN-151: một phút cuối, quà x2 điểm
        this.flash("⏱ GIỜ VÀNG · QUÀ X2");
        break;
      case "versus_assist":  // người không thuộc bên nào tặng quà → tiếp sức bên đang thua
        this.toast(`🎁 ${name} tiếp sức ${esc(e.dest ?? "")}`, `+${e.points ?? 0} điểm đối kháng`, "gift", `assist:${e.name}`);
        break;
      case "goal_step":  // mục tiêu buổi live qua mốc: cả phòng được cảnh vui
        this.note(`🎯 Cả phòng đạt ${e.xu} xu · ${esc(e.label ?? "")}`, `Cảm ơn ${esc(e.name ?? "")} và mọi người đã tặng quà`);
        break;
      case "block":  // trạm thu phí / công an chặn xe (PLAN-148)
        this.flash(e.block === "toll" ? "🚧 TRẠM THU PHÍ" : e.block === "police" ? (e.speeding ? "👮 QUÁ TỐC ĐỘ!" : "👮 CÔNG AN KIỂM TRA")
          : `${INCIDENT_ICON[e.block ?? ""] ?? "⚠"} ${(e.reason ?? "").toUpperCase()}`);
        $("cta-block").classList.remove("alarm");
        void ($("cta-block") as HTMLElement).offsetWidth;
        $("cta-block").classList.add("alarm");
        break;
      case "ad":  // lơ xe vừa đọc quảng cáo bot
        this.toast(`📣 ${e.name ? `${esc(e.name)} · ` : ""}${esc(e.title ?? "")}`, esc(e.desc ?? ""));  // có name: khán giả hỏi
        break;
      case "quiz":  // đố vui
        this.flash("🧠 ĐỐ VUI!");
        break;
      case "quiz_end":
        this.note(`✅ Đáp án ${e.answer}: ${esc(e.option ?? "")}`, e.winners?.length
          ? `🏆 ${e.winners.map((n) => esc(n)).join(", ")} · ${e.right}/${e.total} người đúng` : `Chưa ai đúng · ${e.total} người trả lời`);
        break;
      case "weather": {
        const w = WEATHER_NOTE[e.sky ?? ""];
        if (w) this.toast(...w);
        break;
      }
      case "block_end":
        if (e.by === "time" || (e.block && INCIDENT_ICON[e.block])) {
          this.note(`✅ ${INCIDENT_ICON[e.block ?? ""] ?? ""} Xong rồi · xe chạy tiếp`, e.by === "gifts" ? `Cảm ơn ${esc(e.name ?? "")} góp quà` : "Cảm ơn bà con thả tim");
        } else if (e.by === "cover") {
          this.note(`💸 Anh Tư bù lỗ ${(e.goal ?? 0) - (e.paid ?? 0)} xu`, `${e.block === "toll" ? "Qua trạm" : "Nộp phạt xong"} · xe đi tiếp`);
        } else {
          this.note(`✅ Góp đủ ${e.goal} xu · cảm ơn ${esc(e.name ?? "")}`, `${e.block === "toll" ? "Barie mở" : "Nộp phạt xong"} · xe đi tiếp`);
        }
        break;
      case "pickup_stop": {  // xe dừng hẳn bên lề đón người hẹn (PLAN-145): đọc tên ai lên
        const who = (e.people ?? []).slice(0, 4).map((p) => esc(p.name)).join(", ");
        const more = (e.people?.length ?? 0) > 4 ? ` +${(e.people?.length ?? 0) - 4} người` : "";
        this.note(`🚏 Xe dừng ở ${esc(e.place ?? "")} đón ${who}${more}`, "Đứng chờ sẵn bên đường · lên xe từng người");
        break;
      }
      case "rollcall":
        this.toast(`📣 Gọi ${(e.names ?? [e.name ?? ""]).slice(0, 3).map((n) => esc(n)).join(", ")}${(e.names?.length ?? 1) > 3 ? ` +${(e.names?.length ?? 1) - 3}` : ""}`, `Còn xem thì thả tim / bình luận trong ${e.seconds ?? 45}s để giữ giường`);
        break;
      case "rollcall_ok":
        this.toast(`🙋 ${name} có mặt`, "Lên giường");
        break;
      case "rollcall_skip":
        this.toast(`⏭ ${name} lùi chuyến sau`, "Vé vẫn giữ");
        break;
      case "rollcall_drop":
        this.toast(`👋 ${name} nhường vé`, "Quay lại gõ tỉnh để đặt lại");
        break;
      case "vendor":
        if (e.stage === "stop") {
          this.note(`🧺 ${name} lên xe bán nem, bì, bánh mì`, e.by ? `Nhờ ${esc(e.by)} góp quà · gõ tên món để mua` : "Gõ tên món để mua");
        }
        break;
      case "snack":
        this.toast(`${e.emoji ?? "🥖"} ${name} mua ${esc((e.item ?? "").toLowerCase())}`, "");
        break;
      case "vendor_treat":
        this.toast(`🎉 ${name} bao cả xe ${esc((e.item ?? "").toLowerCase())} ${e.emoji ?? ""}`, `${e.riders ?? 0} người trên xe`, "gift");
        break;
      case "vendor_end":
        this.toast(`👋 ${name} xuống xe`, `Bán được ${e.sold ?? 0} phần`);
        break;
      case "pickup":  // xe tấp vô điểm đón rước người bắt xe dọc đường (PLAN-136)
        this.toast(`🚏 Xe đón ${name} ở ${esc(e.place ?? "")}`, e.province ? `Về ${esc(e.province)}` : "");
        break;
      case "on_air": {  // xe tăng cường lên sóng theo điểm quà / bình luận / tim của khách trên xe (PLAN-141)
        const owner = e.sponsor ? ` của ${esc(e.sponsor)}` : "";
        const who = (e.names ?? []).map(esc).join(", ");
        this.toast(`📺 Xe số ${e.bus_no}${owner} đang lên sóng`, who ? `Cảm ơn ${who} · ${esc(e.lane ?? "")}` : esc(e.lane ?? ""));
        break;
      }
      case "patron":
        this.toast(`👑 ${name} lên làm Chủ nhà xe`, `${e.xu ?? 0} xu trong buổi`, "gift");
        break;
      case "welcome":  // khách buổi trước quay lại (PLAN-134 D)
        this.toast(`🎉 ${name} quay lại`, [(e.streak ?? 0) >= 2 ? `🔥 ${e.streak} ngày liên tiếp` : "",
          e.trips && e.home ? `Đã về ${esc(e.home)} ${e.trips} chuyến` : `Ghé bến ngày thứ ${e.days ?? 2}`].filter(Boolean).join(" · "));
        break;
      case "level_up":  // cấp khách (anh 04/11 «chơi quài không chán»)
        this.toast(`${esc(e.badge ?? "")} ${name} lên cấp`, esc(e.title ?? ""), "gift", `level:${e.name}`);
        break;
      case "streak":  // mốc chuỗi ngày: thưởng lên đầu hàng
        this.toast(`🔥 ${name} ghé ${e.n ?? 0} ngày liền`, "Thưởng lên đầu hàng chờ · gõ tên tỉnh", "gift", `streak:${e.name}`);
        break;
      case "via":  // xe chạy qua tỉnh không ai xuống: gọi bà con tỉnh đó (PLAN-134)
        this.toast(`🛣 Xe đang qua ${esc(e.province ?? "")}`, `Bà con ${esc(e.province ?? "")} thả tim chào xe ❤`);
        break;
      case "stay":
        this.toast(`🏠 ${name} ở lại`, esc(e.text ?? ""), "stay");
        break;
      case "home":  // comment đúng tỉnh của bến đi
        this.toast(`🏠 ${name} ở ngay ${esc(e.province ?? "")}`, "Đi bộ về nhà nha!", "stay");
        break;
      case "gift":
        this.giftBoardUntil = Date.now() + GIFT_BOARD_MS;  // vừa có quà: bảng góc phải hiện danh sách quà cho người khác thấy
        this.renderBoard();
        if (e.fx === "hearts") this.hearts(Math.min(40, 8 * (e.fx_n ?? 1)));
        if (e.fx === "honk") this.flash(`📢 ${name} bóp còi xe!`, true);
        if ((e.tier ?? 0) < SPECIAL_TIER) {
          // gọn 2 dòng (anh báo 03/11: thẻ quà 4 dòng đè nhau, tràn xuống bảng góc phải): việc quà làm được + mốc kế tiếp;
          // thùng quà gầm xe đã hiện trên xe, không ghi lại
          const perk = (e.perk ?? "").split(" · ").slice(0, 2).join(" · ");
          const hint = e.next_tier ? ` · 🎯 ${esc(e.next_tier)}` : "";
          this.toast(`🎁 ${name} · ${e.total ?? e.diamonds} xu`, `${esc(perk)}${hint}`, "gift", `gift:${e.name}`);
        }
        break;
      case "follow":
        this.toast(`➕ ${name} có vé khứ hồi`, "Cảm ơn đã theo dõi!");
        break;
      case "share":
        this.toast(`↗ ${name} gọi người ${esc(e.province ?? "cùng quê")} về`);
        break;
      case "join": {
        if ($("toasts").children.length >= 2) break;  // người vào phòng ít quan trọng nhất: không chen thông báo khác
        const names = (e.names ?? []).slice(-2).map(esc).join(", ");
        const more = (e.count ?? 0) - Math.min(2, e.names?.length ?? 0);
        this.toast(`👋 ${names}${more > 0 ? ` +${more}` : ""} vừa ra bến`);
        break;
      }
      case "depart":
        this.flash(`🚌 Chuyến ${e.bus_no} xuất bến!`);
        break;
      case "rest":
        this.flash(`☕ Trạm dừng chân ${e.place ?? ""}`);
        break;
      case "honk":
        this.flash("📢 Bíp bíp! Lên xe nào!", true);
        break;
      case "like_milestone":
        this.flash(`❤ ${(e.total ?? 0).toLocaleString("vi-VN")} tim! Nhấn ga!`, true);
        break;
      case "treat":
        this.flash(`🧊 ${name} bao cả xe trà đá!`, true);
        break;
      case "relief_depart": {
        const sponsor = e.sponsor ? ` của ${esc(e.sponsor)}` : "";
        this.flash(`🚌 Xe tăng cường${sponsor} ${e.arrow ?? ""} xuất bến!`);
        const names = (e.names ?? []).map(esc).join(", ");
        const more = (e.count ?? 0) - (e.names?.length ?? 0);
        this.note(`🎫 ${names}${more > 0 ? ` +${more} người` : ""} lên xe tăng cường!`,
          `${esc(e.lane ?? "")} · ${km(e.km ?? 0)} km${e.sponsor ? ` · ${esc(e.sponsor)} bao nguyên xe` : ""}`);
        break;
      }
      case "relief_dropoff":
        for (const p of e.people ?? []) this.reliefArrivals.push({ name: p.name, vip: p.vip, province: e.province ?? "" });
        if (!this.reliefTimer) this.reliefTimer = window.setTimeout(() => this.flushRelief(), RELIEF_BATCH_MS);
        break;
      case "dropoff": {
        // Ai xuống xe cũng được gọi tên: chia trang, mỗi trang page_size người.
        const people = e.people ?? [];
        const title = `🏡 Về tới ${esc(e.province ?? "")} rồi!`;
        const size = e.page_size ?? 4;
        const secs = e.page_seconds ?? 3.5;
        const total = Math.max(1, Math.ceil(people.length / size));
        const pages = Array.from({ length: total }, (_, i) => {
          const rows = people.slice(i * size, (i + 1) * size).map((p) =>
            `<li class="${p.vip ? "vip" : ""}"><b>${esc(p.name)}</b><br>${esc(p.wish)}</li>`).join("");
          const foot = total > 1 ? `<p>${people.length} người con ${esc(e.province ?? "")} · ${i + 1}/${total}</p>` : "";
          const trip = e.km ? `<p>${km(e.km)} km từ ${esc(e.departure ?? "")} · ~${drive(e.hours ?? 0)} xe</p>` : "";
          return `<h2>${title}</h2>${trip}<ul>${rows}</ul>${foot}`;
        });
        this.banner(pages, 3 + secs * total, secs);
        break;
      }
      case "announce":
        this.banner(`<h2>${esc(e.title ?? "")}</h2>${e.text ? `<p>${esc(e.text)}</p>` : ""}`, e.seconds ?? 8);
        break;
      case "special":
        this.banner(`<h2>🧧 Cả xe chúc Tết<br>${name}!</h2><p>Cảm ơn đã tiếp lửa cho chuyến xe.<br>Năm mới an khang, vạn sự như ý!</p>`, 18);
        break;
      case "finish": {
        const board = (e.board ?? []).slice(0, 3).map((b, i) => `<li><b>${i + 1}. ${esc(b.province)}</b> — ${b.count} người</li>`).join("");
        const top = e.top_liker ? `<p>❤ Phụ xe danh dự: <b>${esc(e.top_liker)}</b></p>` : "";
        const total = e.delivered_km ? ` · ${km(e.delivered_km)} km` : "";
        this.banner(`<h2>Chuyến ${e.bus_no} xong, xe về bến!</h2><p>Đã đưa ${e.delivered} người về quê${total}</p><ul>${board}</ul>${top}`, 10);
        break;
      }
    }
  }

  setOnline(online: boolean): void {
    $("offline").classList.toggle("hidden", online);
  }

  // ---- thẻ lớn «X lên xe về Y»: lần lượt từng người, đông thì gộp tên ----

  /** Một băng rôn cho mọi người xe tăng cường vừa thả trong lượt gom: «Tên · Tỉnh», 4 người một trang. */
  private flushRelief(): void {
    this.reliefTimer = 0;
    const people = this.reliefArrivals.splice(0);
    if (!people.length) return;
    const total = Math.ceil(people.length / NAMES_PER_PAGE);
    const pages = Array.from({ length: total }, (_, i) => {
      const rows = people.slice(i * NAMES_PER_PAGE, (i + 1) * NAMES_PER_PAGE).map((p) =>
        `<li class="${p.vip ? "vip" : ""}"><b>${esc(p.name)}</b><br>về tới ${esc(p.province)}</li>`).join("");
      const foot = total > 1 ? `<p>${people.length} người · ${i + 1}/${total}</p>` : "";
      return `<h2>🏡 Xe tăng cường về tới quê!</h2><ul>${rows}</ul>${foot}`;
    });
    this.banner(pages, 2 + RELIEF_PAGE_SECONDS * total, RELIEF_PAGE_SECONDS);
  }

  /** Thẻ lớn tự soạn (xe tăng cường xuất bến): chen trước vé lẻ. */
  private note(big: string, small: string): void {
    this.notes.push({ big, small });
    this.pumpCallout();
  }

  private pumpCallout(): void {
    if (this.calloutBusy) return;
    const el = $("callout");
    if (!this.tickets.length && !this.notes.length) {
      el.classList.add("hidden");
      $("hud").classList.remove("calling");
      return;
    }
    this.calloutBusy = true;
    let big: string;
    let small: string;
    const note = this.notes.shift();
    if (note) {
      ({ big, small } = note);
    } else if (this.tickets.length > CALLOUT_MERGE) {
      const batch = this.tickets.splice(0, this.tickets.length);
      // dồn nhiều vé một thẻ: hiện tên người lâu chưa được gọi nhất trước, không phải luôn 3 người đầu (PLAN-134 D)
      const shown = [...batch].sort((a, b) => (this.namedAt.get(a.name) ?? 0) - (this.namedAt.get(b.name) ?? 0)).slice(0, 3);
      const now = performance.now();
      for (const t of shown) this.namedAt.set(t.name, now);
      if (this.namedAt.size > NAMED_KEEP) this.namedAt.delete(this.namedAt.keys().next().value!);
      const names = shown.map((t) => esc(t.name)).join(", ");
      // thẻ gộp: người giữ chỗ chuyến sau không được ghi «lên xe» (rà soát 02/11 — vừa «đợi chuyến sau» lại «lên xe»)
      const held = batch.filter((t) => t.next).length;
      big = `🎫 ${names} +${batch.length - 3} người ${held ? "có vé" : "lên xe"}!`;
      small = held
        ? `${batch.length - held} lên xe · ${held} giữ chỗ chuyến sau · gõ XE NÀO xem vé của mình`
        : [...new Set(batch.map((t) => t.province))].slice(0, 4).map(esc).join(" · ");
    } else {
      const t = this.tickets.shift()!;
      const route = `${esc(t.departure)} → ${esc(t.province)} · ${km(t.km)} km`;
      if (t.next) {
        big = `🎫 ${esc(t.name)} giữ chỗ chuyến ${t.bus} ${t.arrow} ${esc(t.lane)}`;
        small = t.passed
          ? `Xe vừa qua ${esc(t.passed)} rồi · lên chuyến sau${t.eta ? ` ~${t.eta} phút` : ""}`
          : `${route}${t.eta ? ` · lên xe sau ~${t.eta} phút` : ""} · 🎁 tặng 1 xu lên đầu hàng`;
      } else if (t.pickup) {  // bắt xe dọc đường: ra điểm đón chờ (PLAN-136)
        big = `🚏 ${esc(t.name)} bắt xe dọc đường!`;
        small = `Ra điểm đón ${esc(t.pickup)} chờ${t.pickupIn ? ` · ~${clock(t.pickupIn)} xe tới` : ""} · về ${esc(t.province)}`;
      } else if (t.relief) {  // từ hàng chờ lên xe tăng cường (rà soát live 02/11: trước chỉ đọc 3 tên đầu)
        big = `🎫 ${esc(t.name)} lên xe tăng cường số ${t.bus} về ${esc(t.province)}!`;
        small = `${route} · xe chạy ngay, hết chờ`;
      } else {
        // thẻ gọn một dòng (anh 04/11 «to quá»): ai + về đâu; chuyến / giường / km ở dòng phụ
        big = t.promoted  // người đang giữ chỗ được xếp lên xe: phải báo, không thì thẻ cũ vẫn ghi «chuyến sau»
          ? `🎫 ${esc(t.name)} hết chờ · về ${esc(t.province)}`
          : `🎫 ${esc(t.name)} lên xe về ${esc(t.province)}`;
        small = `Chuyến ${t.bus} · giường ${(t.seat ?? 0) + 1} ${floorName(t.seat ?? 0, this.seats)} · ${km(t.km)} km`
          + ((t.tripNo ?? 1) > 1 ? ` · lần về quê thứ ${t.tripNo}` : "");
      }
    }
    el.innerHTML = `<div class="big">${big}</div><div class="small">${small}</div>`;
    this.placeCallout();
    el.classList.remove("hidden", "show");
    $("hud").classList.toggle("calling", $("cta-block").classList.contains("hidden"));  // câu đố / trạm: thẻ nằm dưới, khỏi ẩn
    void el.offsetWidth;
    el.classList.add("show");
    window.setTimeout(() => {
      this.calloutBusy = false;
      this.pumpCallout();
    }, CALLOUT_MS);
  }

  // ---- tim bay từ góc nút tim của TikTok lên thanh tốc độ ----

  private hearts(count: number): void {
    const layer = $("hearts");
    const n = Math.min(6, Math.max(1, Math.round(count / 5)));
    for (let i = 0; i < n && layer.childElementCount < MAX_HEARTS; i++) {
      const h = document.createElement("div");
      h.className = "heart";
      h.textContent = ["❤️", "💖", "💗"][Math.floor(Math.random() * 3)];
      const x = 880 + Math.random() * 100;  // tim rộng ~60 px: giữ trong khung 1080
      const y = 1600 + Math.random() * 120;
      h.style.left = `${x}px`;
      h.style.top = `${y}px`;
      h.style.setProperty("--dx", `${540 + (Math.random() - 0.5) * 500 - x}px`);
      h.style.setProperty("--dy", `${400 - y}px`);
      h.style.animationDelay = `${i * 90}ms`;
      layer.append(h);
      window.setTimeout(() => h.remove(), 1500 + i * 90);
    }
  }

  private loxe(text: string): void {
    $("loxe-text").textContent = text;
    const box = $("loxe");
    box.classList.remove("pop");
    void box.offsetWidth;
    box.classList.add("pop");
  }

  private eventAvatar = "";
  private vendorSince = 0;

  private toast(title: string, sub = "", kind = "", key = ""): void {
    const list = $("toasts");
    const face = this.eventAvatar ? avatarImg(this.eventAvatar) : "";
    const html = `<span class="t">${face}${title}</span>${sub ? `<small>${sub}</small>` : ""}`;
    const old = key ? this.keyed.get(key) : undefined;
    if (old && old.el.isConnected && !old.el.classList.contains("out")) {
      old.el.innerHTML = html;
      list.prepend(old.el);
      window.clearTimeout(old.timer);
      old.timer = this.expire(old.el, key);
      return;
    }
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.innerHTML = html;
    list.prepend(el);
    while (list.children.length > MAX_TOASTS) list.lastElementChild?.remove();
    const timer = this.expire(el, key);
    if (key) this.keyed.set(key, { el, timer });
  }

  private expire(el: HTMLElement, key: string): number {
    return window.setTimeout(() => {
      el.classList.add("out");
      if (key && this.keyed.get(key)?.el === el) this.keyed.delete(key);  // khoá đã trỏ sang thẻ mới thì để yên
      window.setTimeout(() => el.remove(), 400);
    }, 5000);
  }

  private banner(html: string | string[], seconds: number, pageSeconds = 0): void {
    const pages = Array.isArray(html) ? html : [html];
    if (this.bannerBusy) {
      if (this.bannerQueue.length < MAX_BANNERS) this.bannerQueue.push({ pages, seconds, pageSeconds });
      return;
    }
    this.showBanner(pages, seconds, pageSeconds);
  }

  private showBanner(pages: string[], seconds: number, pageSeconds: number): void {
    this.bannerBusy = true;
    const el = $("banner");
    el.innerHTML = pages[0];
    window.clearInterval(this.pageTimer);
    if (pages.length > 1 && pageSeconds > 0) {
      let i = 0;
      this.pageTimer = window.setInterval(() => {
        i = Math.min(i + 1, pages.length - 1);
        el.innerHTML = pages[i];
        if (i === pages.length - 1) window.clearInterval(this.pageTimer);
      }, pageSeconds * 1000);
    }
    el.classList.remove("hidden");
    $("hud").classList.add("bannering");
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "";
    window.clearTimeout(this.bannerTimer);
    this.bannerTimer = window.setTimeout(() => {
      el.classList.add("hidden");
      $("hud").classList.remove("bannering");
      this.bannerBusy = false;
      const next = this.bannerQueue.shift();
      if (next) this.showBanner(next.pages, next.seconds, next.pageSeconds);
    }, seconds * 1000);
  }

  private flashShownAt = -Infinity;
  private minorAt = -Infinity;

  /** Chữ lớn giữa màn. Lúc chữ hiện, lơ xe + thông báo mờ đi để không chồng chữ (anh 04/11 «đỡ rối»).
   *  Chữ phụ (minor) không đè chữ chính đang hiện và cách nhau ít nhất FLASH_MINOR_GAP_MS. */
  private flash(text: string, minor = false): void {
    const now = performance.now();
    if (minor && (now - this.flashShownAt < FLASH_MS || now - this.minorAt < FLASH_MINOR_GAP_MS)) return;
    if (minor) this.minorAt = now;
    this.flashShownAt = now;
    $("hud").classList.add("flashing");
    const el = $("flash");
    el.textContent = text;
    el.classList.remove("hidden");
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "";
    window.clearTimeout(this.flashTimer);
    this.flashTimer = window.setTimeout(() => {
      el.classList.add("hidden");
      $("hud").classList.remove("flashing");
    }, FLASH_MS);
  }
}

/** Ảnh đại diện TikTok tròn nhỏ trước tên; ảnh hỏng / hết hạn thì tự ẩn. */
export function avatarImg(url: string | undefined, cls = "av"): string {
  if (!url || !/^https:\/\/[^"'<>\s\\]+$/.test(url)) return "";
  return `<img class="${cls}" src="${url.replace(/&/g, "&amp;")}" alt="" referrerpolicy="no-referrer" loading="lazy" onerror="this.remove()">`;
}
