// Âm thanh trong xe (PLAN-127): nhạc riêng từng xe (bài tự sinh hoặc file của anh) + tiếng hiệu ứng tự sinh.
// Tiếng theo xe đang chiếu: server gửi `music` (đài của xe đó) + `music_tracks` (danh sách bài); admin chỉnh âm lượng /
// bật tắt trên /control. Trình duyệt chặn tự phát tiếng tới khi có một cú bấm → báo ra ngoài để hiện 🔇.
//
//   bài nhạc ─► music ─► tunnel (lọc «bịt» khi trong hầm) ─┐
//   còi, pháo hoa, tiếng máy ─► sfx ────────────────────────┴─► master ─► loa

import { PRESETS, Song } from "./music";
import type { GameEvent, State } from "./types";

const FADE = 1.2;  // đổi bài: bài cũ nhỏ dần, bài mới to dần (giây)
const TING_GAP = 0.6;  // vé dồn dập: «ting» cách nhau tối thiểu 0,6 giây
const ENGINE_LEVEL = 0.07;
const OPEN_AIR = 18000;  // tần số cắt bộ lọc ngoài trời / trong hầm
const IN_TUNNEL = 700;

interface Playing { id: string; stop(): void }

export class Sound {
  private ctx = new AudioContext();
  private master = this.ctx.createGain();
  private music = this.ctx.createGain();
  private sfx = this.ctx.createGain();
  private tunnel = this.ctx.createBiquadFilter();
  private engine = this.ctx.createOscillator();
  private engineGain = this.ctx.createGain();
  private playing: Playing | null = null;
  private lastTing = 0;
  /** Gọi khi trình duyệt cho / chưa cho phát tiếng (overlay hiện / ẩn biểu tượng 🔇). */
  onLock?: (locked: boolean) => void;

  constructor() {
    this.tunnel.type = "lowpass";
    this.tunnel.frequency.value = OPEN_AIR;
    this.music.connect(this.tunnel).connect(this.master);
    this.sfx.connect(this.master);
    this.master.connect(this.ctx.destination);
    // tiếng máy: răng cưa trầm qua lọc thấp, to nhỏ / cao thấp theo tốc độ
    const engineFilter = this.ctx.createBiquadFilter();
    engineFilter.type = "lowpass";
    engineFilter.frequency.value = 260;
    this.engine.type = "sawtooth";
    this.engine.frequency.value = 42;
    this.engineGain.gain.value = 0;
    this.engine.connect(engineFilter).connect(this.engineGain).connect(this.sfx);
    this.engine.start();
    const unlock = () => void this.ctx.resume().then(() => this.onLock?.(false));
    for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, unlock);
    window.setTimeout(() => this.onLock?.(this.ctx.state !== "running"), 500);
  }

  update(s: State): void {
    const c = s.control;
    const now = this.ctx.currentTime;
    this.music.gain.setTargetAtTime(c?.music_volume ?? 0.5, now, 0.2);
    this.sfx.gain.setTargetAtTime(c?.sfx_volume ?? 0.6, now, 0.2);
    const moving = s.phase === "DRIVING" && !s.paused;
    this.engineGain.gain.setTargetAtTime(moving ? ENGINE_LEVEL : 0, now, 0.6);
    this.engine.frequency.setTargetAtTime(38 + 10 * (s.speed ?? 1), now, 0.5);
    this.tunnel.frequency.setTargetAtTime(moving && s.terrain?.tunnel ? IN_TUNNEL : OPEN_AIR, now, 0.4);
    // bài của xe đang chiếu; tắt nhạc (chung hoặc riêng xe) thì im
    const tracks = s.music_tracks ?? [];
    const on = c?.music_on !== false && s.music?.on !== false && tracks.length > 0;
    const track = on ? tracks[((s.music.index % tracks.length) + tracks.length) % tracks.length] : null;
    if ((track?.id ?? null) === (this.playing?.id ?? null)) return;
    this.playing?.stop();
    this.playing = track ? this.play(track.id, track.url) : null;
  }

  onEvent(e: GameEvent): void {
    switch (e.type) {
      case "depart":
      case "honk":
      case "relief_depart":
        this.horn();
        break;
      case "special":
        for (let i = 0; i < 4; i++) this.firework(this.ctx.currentTime + i * 0.6);
        break;
      case "dropoff":
      case "relief_dropoff":
        if (e.fireworks) this.firework(this.ctx.currentTime);
        break;
      case "gift":
        if (e.tier_up && (e.tier ?? 0) >= 2) this.firework(this.ctx.currentTime);
        break;
      case "ticket":
        this.ting();
        break;
    }
  }

  // ---- nhạc ------------------------------------------------------------------------------------

  private play(id: string, url?: string): Playing {
    const g = this.ctx.createGain();
    const now = this.ctx.currentTime;
    g.gain.setValueAtTime(0.0001, now);
    g.gain.exponentialRampToValueAtTime(1, now + FADE);
    g.connect(this.music);
    const fadeOut = () => {
      const t = this.ctx.currentTime;
      g.gain.cancelScheduledValues(t);
      g.gain.setValueAtTime(Math.max(0.0001, g.gain.value), t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + FADE);
      window.setTimeout(() => g.disconnect(), FADE * 1000 + 100);
    };
    if (url) {  // file của anh: phát lặp
      const audio = new Audio(url);
      audio.loop = true;
      this.ctx.createMediaElementSource(audio).connect(g);
      void audio.play().catch(() => undefined);  // chưa được phép phát: tự phát khi bấm mở khoá (ctx.resume)
      return { id, stop: () => { fadeOut(); window.setTimeout(() => audio.pause(), FADE * 1000); } };
    }
    const preset = PRESETS[Number(id.split(":")[1]) % PRESETS.length];
    const song = new Song(this.ctx, g, preset);
    song.start();
    return { id, stop: () => { fadeOut(); window.setTimeout(() => song.stop(), FADE * 1000); } };
  }

  // ---- tiếng hiệu ứng ----------------------------------------------------------------------------

  /** Còi xe khách: hai nốt vuông chồng nhau, «bíp bíp». */
  private horn(): void {
    const t0 = this.ctx.currentTime;
    for (const start of [t0, t0 + 0.32]) {
      const g = this.ctx.createGain();
      g.gain.setValueAtTime(0.0001, start);
      g.gain.exponentialRampToValueAtTime(0.18, start + 0.02);
      g.gain.setValueAtTime(0.18, start + 0.2);
      g.gain.exponentialRampToValueAtTime(0.0001, start + 0.26);
      const lp = this.ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = 1800;
      for (const f of [370, 466]) {
        const osc = this.ctx.createOscillator();
        osc.type = "square";
        osc.frequency.value = f;
        osc.connect(lp);
        osc.start(start);
        osc.stop(start + 0.28);
      }
      lp.connect(g).connect(this.sfx);
    }
  }

  /** Pháo hoa: tiếng rít bay lên rồi «đùng» (tiếng ồn qua lọc, tắt dần). */
  private firework(t: number): void {
    const whistle = this.ctx.createOscillator();
    const wg = this.ctx.createGain();
    whistle.frequency.setValueAtTime(900, t);
    whistle.frequency.exponentialRampToValueAtTime(2400, t + 0.7);
    wg.gain.setValueAtTime(0.0001, t);
    wg.gain.exponentialRampToValueAtTime(0.04, t + 0.1);
    wg.gain.exponentialRampToValueAtTime(0.0001, t + 0.75);
    whistle.connect(wg).connect(this.sfx);
    whistle.start(t);
    whistle.stop(t + 0.8);
    const boom = t + 0.8;
    const noise = this.ctx.createBufferSource();
    noise.buffer = this.noise();
    const bp = this.ctx.createBiquadFilter();
    bp.type = "lowpass";
    bp.frequency.setValueAtTime(2500, boom);
    bp.frequency.exponentialRampToValueAtTime(200, boom + 1.2);
    const ng = this.ctx.createGain();
    ng.gain.setValueAtTime(0.0001, boom);
    ng.gain.exponentialRampToValueAtTime(0.35, boom + 0.01);
    ng.gain.exponentialRampToValueAtTime(0.0001, boom + 1.3);
    noise.connect(bp).connect(ng).connect(this.sfx);
    noise.start(boom);
    noise.stop(boom + 1.4);
  }

  /** «Ting» khi có vé (giới hạn tần suất — phòng đông vé tới liên tục). */
  private ting(): void {
    const t = this.ctx.currentTime;
    if (t - this.lastTing < TING_GAP) return;
    this.lastTing = t;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.08, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
    const osc = this.ctx.createOscillator();
    osc.frequency.value = 1760;
    osc.connect(g).connect(this.sfx);
    osc.start(t);
    osc.stop(t + 0.55);
  }

  private noiseBuffer: AudioBuffer | null = null;

  private noise(): AudioBuffer {
    if (!this.noiseBuffer) {
      const buf = this.ctx.createBuffer(1, this.ctx.sampleRate * 1.5, this.ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      this.noiseBuffer = buf;
    }
    return this.noiseBuffer;
  }
}
