// Lớp chữ HTML đè lên cảnh 3D, viết cho người xem trên điện thoại (khung 1080 co về ~390 px):
// ít chữ, chữ to, mỗi người tương tác đều thấy mình trên màn hình.

import { BERTHS } from "./art";
import type { FleetBus, GameEvent, Route, State } from "./types";

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

const PILL: Record<State["phase"], string> = {
  BOARDING: "Đón khách", DRIVING: "Đang chạy", REST: "Trạm dừng", DROPOFF: "Thả khách",
  FINISH: "Về bến", SPECIAL: "Chúc Tết",
};
const MAX_TOASTS = 3;
const HUD_SCALE = 0.8;  // cỡ chữ mặc định (server chưa gửi thiết lập)
const CTA_ROTATE_MS = 4000;
const BOARD_ROTATE_MS = 8000;
const CALLOUT_MS = 1700;
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
  lane: string; arrow: string; km: number; departure: string;
}

export class Hud {
  private bannerTimer = 0;
  // băng rôn xếp hàng: xe chính và xe tăng cường có thể tới nơi cùng lúc — đọc tên lần lượt, không đè nhau
  private bannerQueue: { pages: string[]; seconds: number; pageSeconds: number }[] = [];
  private bannerBusy = false;
  // thông báo theo khoá (quà của cùng một người): cập nhật thẻ cũ thay vì mỗi lần bấm combo một thẻ mới
  private keyed = new Map<string, { el: HTMLElement; timer: number }>();
  private pageTimer = 0;
  private flashTimer = 0;
  private state: State | null = null;
  private ctaTick = 0;
  private boardTick = 0;
  private tickets: Ticket[] = [];
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
  }

  update(s: State): void {
    this.state = s;
    this.seats = seatsOf(s);
    const c = s.control;
    const hud = $("hud");
    const scale = String(c?.hud_scale ?? HUD_SCALE);
    if (hud.style.getPropertyValue("--z") !== scale) hud.style.setProperty("--z", scale);  // cỡ chữ trên live (admin chỉnh)
    hud.classList.toggle("hide-route", c?.show_route === false);
    hud.classList.toggle("hide-loxe", c?.show_loxe === false);
    hud.classList.toggle("hide-toasts", c?.show_toasts === false);
    hud.classList.toggle("hide-board", c?.show_board === false);
    setText("countdown", s.days_to_tet > 0 ? `Còn ${s.days_to_tet} ngày nữa là Tết` : "Chúc Mừng Năm Mới!");
    setText("phase-pill", s.paused ? "Tạm dừng" : PILL[s.phase]);
    // phần đầu được cắt «…» khi hẹp; phần đuôi (km còn lại, đếm ngược) không bao giờ bị cắt
    const [head, tail] = this.statusText(s);
    setHTML("phase-text", `<span class="head">${esc(head)}</span>${tail ? `<span class="tail">${esc(tail)}</span>` : ""}`);
    ($("bar-fill") as HTMLElement).style.width = `${Math.round(this.progress(s) * 100)}%`;
    this.renderMarks(s);
    setText("seats", `🚌 ${s.bus.riders}/${seatsOf(s)}` + (s.waiting ? ` · ⏳${s.waiting}` : ""));
    setHTML("next-stops", this.nextStops(s));
    const pass = s.terrain?.pass ?? null;
    if (pass && pass !== this.lastPass) this.flash(`${s.terrain.tunnel ? "🚇" : "⛰"} ${pass}`);  // vừa vào đèo / hầm
    this.lastPass = pass;
    this.renderCta();
    this.renderBoard();

    const resting = s.phase === "REST";
    $("rest-card").classList.toggle("hidden", !resting);
    $("board").classList.toggle("hidden", resting);
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
    const leg = s.legs[s.leg_index];
    const left = s.phase_left ?? 0;
    switch (s.phase) {
      case "BOARDING":  // bến đi đã ghi trên bảng LED và biển bến
        return [s.bus.riders >= seatsOf(s) ? "Đủ khách!" : `Đi ${s.bus.to}`, `chạy sau ${clock(left)}`];
      case "DRIVING": {
        if (!leg) return ["", ""];
        const fast = s.speed >= 1.15 ? ` ⚡x${s.speed.toFixed(1)}` : "";  // tim của người xem đang đẩy xe
        return [`Tới ${leg.label}`, `còn ${km(Math.max(1, leg.km - s.trip_km))} km${fast}`];
      }
      case "SPECIAL": return ["Cả xe dừng lại chúc Tết", ""];
      case "REST": return [`Nghỉ ở ${s.place}`, `còn ${clock(left)}`];
      case "DROPOFF": return [leg ? `Tới ${leg.label} rồi!` : "", ""];
      case "FINISH": return [`Xe số ${s.bus.no} về bến`, ""];
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
    const key = route ? `${route.total}|${route.stops.map((p) => `${p.kind}${p.km}${p.done ? 1 : 0}`).join(",")}` : "";
    if (key !== this.marksKey) {
      this.marksKey = key;
      const el = $("marks");
      el.innerHTML = route
        ? route.stops.map((p) => `<b class="mk ${p.kind}${p.done ? " done" : ""}" style="left:${at(p.km)}"></b>`).join("")
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
    const rush = (s.rush ? `<span class="rush">⚡ Cao điểm</span>` : "") + (others ? `<span class="rush">🚌+${others}</span>` : "");
    if (s.phase === "BOARDING" || !s.legs.length) {
      // bến nhiều làn: làn đang đón + làn có người giữ chỗ (đủ mọi làn đã có trên biển ở bến — BRD-tuyen-xe)
      const lanes = s.lanes.filter((l) => l.current || l.waiting)
        .map((l) => `${l.arrow} ${esc(l.label.replace("Hướng ", ""))} ${l.current ? `${s.bus.riders}/${seatsOf(s)}` : `⏳${l.waiting}`}`);
      return `${rush}${lanes.join(" · ")}`;
    }
    const pass = s.terrain?.pass ? `<span class="rush">${s.terrain.tunnel ? "🚇" : "⛰"} ${esc(s.terrain.pass)}</span>` : "";
    const route = this.trip(s);
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

  private renderCta(): void {
    const s = this.state;
    if (!s) return;
    let main: string;
    let tips: string[];
    if (s.phase === "REST") {
      main = "💬 Gõ <b>PHỞ</b> · <b>TRÀ ĐÁ</b> · <b>WC</b>";
      tips = [`🎁 Gõ MUA QUÀ: ${esc(s.specialty)}`, "🧊 Tặng quà = bao cả xe trà đá", "🍜 Còn có BÁNH MÌ · CƠM · CÀ PHÊ"];
    } else {
      main = "💬 Gõ <b>TÊN TỈNH</b> để lên xe";
      tips = ["Ví dụ: Nghệ An · 37 · Sài Gòn", "Năm nay ở lại? Gõ KHÔNG VỀ", "❤ Thả tim cho xe chạy nhanh hơn"];
      if (s.next_lane) {  // ai chờ trước đi trước — nói rõ xe kế tiếp đi đâu để người chờ yên tâm
        tips.unshift(`⏳ Xe kế tiếp: ${s.next_lane.arrow} ${esc(s.next_lane.label)} · ~${s.next_lane.eta_min} phút`);
      }
      if (s.rush) tips.push("⚡ Cao điểm: xe chạy nhanh, lên lẹ!");
    }
    setHTML("cta-main", main);
    setHTML("cta-sub", tips[this.ctaTick % tips.length]);
  }

  // ---- bảng góc phải: luân phiên «người đang chờ xe sau», «ai đang trên xe», «tỉnh về đông» ----
  // Người chờ được ưu tiên: phải thấy tên mình + thứ tự thì mới chịu ở lại tới lúc lên xe.

  private renderBoard(): void {
    const s = this.state;
    if (!s) return;
    const riders = s.bus.seats.filter((x): x is NonNullable<typeof x> => !!x);
    const others: FleetBus[] = (s.fleet ?? []).filter((b) => !b.featured);
    const modes = [
      ...(s.queue?.length ? ["queue", "queue"] : []),
      ...((s.fleet?.length ?? 0) > 1 ? ["fleet"] : []),
      ...(riders.length ? ["riders"] : []),
      "top",
    ];
    const mode = modes[this.boardTick % modes.length];
    if (mode === "queue") {
      setText("board-title", "⏳ Chờ xe sau");
      setHTML("board-list", s.queue.slice(0, QUEUE_ROWS).map((w) =>
        // số thứ tự đặt trước (float phải) để nằm cùng dòng; tên dài bị cắt «…», dòng không xuống hàng
        `<li><span>#${w.pos}</span>${w.arrow} ${esc(w.name)} <small>· ${esc(w.province)}</small></li>`).join(""));
    } else if (mode === "fleet") {  // các xe khác đang ở đâu, bao lâu nữa tới điểm kế (PLAN-130)
      setText("board-title", "🚌 Xe khác");
      setHTML("board-list", others.slice(0, QUEUE_ROWS).map((b) => {
        const where = b.next ? `→ ${esc(b.next)}` : b.phase === "BOARDING" ? "đang đón" : "về bến";
        return `<li><span>${b.in_s ? clock(b.in_s) : ""}</span>${b.arrow} số ${b.no} <small>${where}</small></li>`;
      }).join(""));
    } else if (mode === "riders") {
      setText("board-title", `🚌 Trên xe số ${s.bus.no}`);
      setHTML("board-list", riders.slice(-6).reverse()
        .map((r) => `<li>${r.vip ? "⭐ " : ""}${esc(r.name)} <small>· ${esc(r.province)}</small></li>`).join(""));
    } else {
      setText("board-title", "🏆 Tỉnh dẫn đầu");
      setHTML("board-list", s.board.length
        ? s.board.slice(0, 5).map((b) => `<li>${esc(b.province)} <span>${b.count}</span></li>`).join("")
        : "<li>Chưa ai lên xe</li>");
    }
  }

  onEvent(e: GameEvent): void {
    const name = esc(e.name ?? "");
    switch (e.type) {
      case "loxe":
        this.loxe(e.text ?? "");
        break;
      case "ticket":
        if (e.changed) {
          this.toast(`🔁 ${name} đổi vé → ${esc(e.province ?? "")}`);
        } else {
          this.tickets.push({ name: e.name ?? "", province: e.province ?? "", seat: e.seat ?? null,
            next: !!e.next, eta: e.eta_min, lane: e.lane ?? "", arrow: e.arrow ?? "",
            km: e.km ?? 0, departure: e.departure ?? "" });
          this.pumpCallout();
        }
        break;
      case "likes":
        this.hearts(e.count ?? 1);
        break;
      case "stay":
        this.toast(`🏠 ${name} ở lại`, esc(e.text ?? ""), "stay");
        break;
      case "home":  // comment đúng tỉnh của bến đi
        this.toast(`🏠 ${name} ở ngay ${esc(e.province ?? "")}`, "Đi bộ về nhà nha!", "stay");
        break;
      case "gift":
        if ((e.tier ?? 0) < SPECIAL_TIER) {
          const hint = e.next_tier ? `<br>🎯 ${esc(e.next_tier)}` : "";
          this.toast(`🎁 ${name} · ${e.total ?? e.diamonds} xu`, `${esc(e.perk ?? "")}${hint}`, "gift", `gift:${e.name}`);
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
        this.flash(`🚌 Xe số ${e.bus_no} xuất bến!`);
        break;
      case "rest":
        this.flash(`☕ Trạm dừng chân ${e.place ?? ""}`);
        break;
      case "honk":
        this.flash("📢 Bíp bíp! Lên xe nào!");
        break;
      case "like_milestone":
        this.flash(`❤ ${(e.total ?? 0).toLocaleString("vi-VN")} tim! Nhấn ga!`);
        break;
      case "treat":
        this.flash(`🧊 ${name} bao cả xe trà đá!`);
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
        this.banner(`<h2>Xe số ${e.bus_no} về bến!</h2><p>Đã đưa ${e.delivered} người về quê${total}</p><ul>${board}</ul>${top}`, 10);
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
      const names = batch.slice(0, 3).map((t) => esc(t.name)).join(", ");
      big = `🎫 ${names} +${batch.length - 3} người lên xe!`;
      small = [...new Set(batch.map((t) => t.province))].slice(0, 4).map(esc).join(" · ");
    } else {
      const t = this.tickets.shift()!;
      const route = `${esc(t.departure)} → ${esc(t.province)} · ${km(t.km)} km`;
      if (t.next) {
        big = `🎫 ${esc(t.name)} giữ chỗ xe ${t.arrow} ${esc(t.lane)}`;
        small = `${route}${t.eta ? ` · lên xe sau ~${t.eta} phút` : ""}`;
      } else {
        big = `🎫 ${esc(t.name)} lên xe về ${esc(t.province)}!`;
        small = `${route} · giường ${(t.seat ?? 0) + 1} ${floorName(t.seat ?? 0, this.seats)}`;
      }
    }
    el.innerHTML = `<div class="big">${big}</div><div class="small">${small}</div>`;
    el.classList.remove("hidden", "show");
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

  private toast(title: string, sub = "", kind = "", key = ""): void {
    const list = $("toasts");
    const html = sub ? `${title}<small>${sub}</small>` : title;
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

  private flash(text: string): void {
    const el = $("flash");
    el.textContent = text;
    el.classList.remove("hidden");
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "";
    window.clearTimeout(this.flashTimer);
    this.flashTimer = window.setTimeout(() => el.classList.add("hidden"), 2600);
  }
}
