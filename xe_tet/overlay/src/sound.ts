// Âm thanh trong xe (PLAN-127): nhạc riêng từng xe (bài tự sinh hoặc file của anh) + tiếng hiệu ứng tự sinh.
// Tiếng theo xe đang chiếu: server gửi `music` (đài của xe đó) + `music_tracks` (danh sách bài); admin chỉnh âm lượng /
// bật tắt trên /control. Trình duyệt chặn tự phát tiếng tới khi có một cú bấm → báo ra ngoài để hiện 🔇.
//
//   bài nhạc ─► music ─► duck (nhỏ lại khi lơ xe nói) ─► tunnel (lọc «bịt» khi trong hầm) ─┐
//   tiếng máy + lốp / gió (chỉ khi xe chạy, theo tốc độ) ─► vehicleDuck ─► sfx ────────────────────┤
//   còi, pháo hoa, «ting» ─► sfx ─────────────────────────────────────────────────────────────┤
//   giọng Anh Tư lơ xe (file server đọc sẵn, PLAN-128) ─► voice ─────────────────────────────┴─► master ─► nén ─► loa
//
// Trộn (PLAN-130): một bộ nén chung giữ to nhỏ đều (bài anh tải lên to nhỏ khác nhau, pháo hoa không chói); lơ xe nói thì
// nhạc lẫn tiếng xe cùng nhỏ lại; «chế độ trộn» trên /control nhân thêm hệ số cho từng nhóm.

import { PRESETS, Song } from "./music";
import type { GameEvent, State } from "./types";

const FADE = 1.2;  // đổi bài: bài cũ nhỏ dần, bài mới to dần (giây)
const TING_GAP = 0.6;  // vé dồn dập: «ting» cách nhau tối thiểu 0,6 giây
const ENGINE_LEVEL = 0.05;
const OPEN_AIR = 18000;  // tần số cắt bộ lọc ngoài trời / trong hầm
const IN_TUNNEL = 700;
const DUCK = 0.3;  // lơ xe nói: nhạc còn 30 %
const VEHICLE_DUCK = 0.45;  // … tiếng máy / lốp còn 45 %
const ROAD_LEVEL = 0.03;  // tiếng lốp + gió ở tốc độ thường (nhỏ, trầm — chỉ làm nền)
type Mix = "balanced" | "music" | "voice";
/** Hệ số từng nhóm theo chế độ trộn (nhân với âm lượng admin chỉnh) + mức nhạc khi lơ xe nói. */
const MIXES: Record<Mix, { music: number; voice: number; sfx: number; duck: number }> = {
  balanced: { music: 1, voice: 1, sfx: 1, duck: DUCK },
  music: { music: 1.3, voice: 0.85, sfx: 0.8, duck: 0.5 },
  voice: { music: 0.6, voice: 1.15, sfx: 0.75, duck: 0.18 },
};

interface Playing { id: string; stop(): void }

/** Nhả một file đã phát xong: ngắt khỏi đồ thị âm thanh, bỏ nguồn để trình duyệt thu hồi bộ nhớ đã giải mã. */
function release(audio: HTMLAudioElement, source: AudioNode): void {
  audio.pause();
  source.disconnect();
  audio.removeAttribute("src");
  audio.load();
}

export class Sound {
  // bộ đệm lớn (chế độ phát nhạc): live không cần tiếng tức thì, đổi lại ít hụt tiếng (lẹt xẹt) khi máy bận
  private ctx = new AudioContext({ latencyHint: "playback" });
  private master = this.ctx.createGain();
  private music = this.ctx.createGain();
  private sfx = this.ctx.createGain();
  private voice = this.ctx.createGain();
  private duck = this.ctx.createGain();
  private speaking = 0;  // số câu đang phát (server đã giãn cách, phòng hờ chồng nhau)
  private rate = 1;  // tốc độ đọc (admin chỉnh), phát nhanh hơn mà giữ cao độ
  private tunnel = this.ctx.createBiquadFilter();
  private engine = this.ctx.createOscillator();
  private engineGain = this.ctx.createGain();
  private road = this.ctx.createGain();
  private vehicleDuck = this.ctx.createGain();
  private duckLevel = DUCK;
  private playing: Playing | null = null;
  private lastTing = 0;
  /** Gọi khi trình duyệt cho / chưa cho phát tiếng (overlay hiện / ẩn biểu tượng 🔇). */
  onLock?: (locked: boolean) => void;

  constructor() {
    this.tunnel.type = "lowpass";
    this.tunnel.frequency.value = OPEN_AIR;
    const glue = this.ctx.createDynamicsCompressor();  // nén chung: to nhỏ đều, đỉnh pháo hoa không chói
    glue.threshold.value = -18;
    glue.knee.value = 12;
    glue.ratio.value = 3;
    glue.attack.value = 0.01;
    glue.release.value = 0.25;
    this.music.connect(this.duck).connect(this.tunnel).connect(this.master);
    this.vehicleDuck.connect(this.sfx);
    this.sfx.connect(this.master);
    this.voice.connect(this.master);
    this.master.connect(glue).connect(this.ctx.destination);
    // lốp + gió: tiếng ồn nâu lặp vòng qua lọc thấp, to theo tốc độ
    const rumble = this.ctx.createBufferSource();
    rumble.buffer = this.brownNoise();
    rumble.loop = true;
    const roadFilter = this.ctx.createBiquadFilter();
    roadFilter.type = "lowpass";
    roadFilter.frequency.value = 320;
    this.road.gain.value = 0;
    rumble.connect(roadFilter).connect(this.road).connect(this.vehicleDuck);
    rumble.start();
    // tiếng máy: sóng tam giác trầm qua lọc thấp (răng cưa nghe rè rè), to nhỏ / cao thấp theo tốc độ
    const engineFilter = this.ctx.createBiquadFilter();
    engineFilter.type = "lowpass";
    engineFilter.frequency.value = 160;
    this.engine.type = "triangle";
    this.engine.frequency.value = 42;
    this.engineGain.gain.value = 0;
    this.engine.connect(engineFilter).connect(this.engineGain).connect(this.vehicleDuck);
    this.engine.start();
    const unlock = () => void this.ctx.resume().then(() => this.onLock?.(false));
    for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, unlock);
    window.setTimeout(() => this.onLock?.(this.ctx.state !== "running"), 500);
  }

  update(s: State): void {
    const c = s.control;
    const now = this.ctx.currentTime;
    const mix = MIXES[c?.mix ?? "balanced"] ?? MIXES.balanced;
    this.duckLevel = mix.duck;
    this.music.gain.setTargetAtTime((c?.music_volume ?? 0.5) * mix.music, now, 0.2);
    this.sfx.gain.setTargetAtTime((c?.sfx_volume ?? 0.6) * mix.sfx, now, 0.2);
    this.voice.gain.setTargetAtTime(c?.voice_on === false ? 0 : (c?.voice_volume ?? 0.9) * mix.voice, now, 0.2);
    this.rate = c?.voice_rate ?? 1;
    const moving = s.phase === "DRIVING" && !s.paused;
    const speed = s.speed ?? 1;
    this.engineGain.gain.setTargetAtTime(moving ? ENGINE_LEVEL : 0, now, 0.6);  // đứng ở bến / trạm: tắt máy, im hẳn
    this.engine.frequency.setTargetAtTime(38 + 10 * speed, now, 0.5);
    this.road.gain.setTargetAtTime(moving ? ROAD_LEVEL * Math.min(1.6, speed) * (s.terrain?.tunnel ? 1.6 : 1) : 0, now, 0.5);
    this.tunnel.frequency.setTargetAtTime(moving && s.terrain?.tunnel ? IN_TUNNEL : OPEN_AIR, now, 0.4);
    // bài của xe đang chiếu; tắt nhạc (chung hoặc riêng xe) thì im
    const tracks = s.music_tracks ?? [];
    const on = c?.music_on !== false && s.music?.on !== false && tracks.length > 0;
    const track = on ? tracks[((s.music.index % tracks.length) + tracks.length) % tracks.length] : null;
    // khoá = bài + lúc bắt đầu: server tự qua bài (kể cả quay lại đúng bài cũ) hay đổi xe chiếu đều nhận ra
    const key = track ? `${track.id}|${s.music.since}` : null;
    if (key === (this.playing?.id ?? null)) return;
    this.playing?.stop();
    this.playing = track && key ? this.play(key, s.music.pos ?? 0, c?.music_auto !== false, track.url) : null;
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
      case "speak":
        if (e.url) this.speak(e.url);
        break;
    }
  }

  // ---- nhạc ------------------------------------------------------------------------------------

  /** Phát bài từ giây `offset`; auto = server tự qua bài nên file không lặp (tắt tự qua bài thì lặp). */
  private play(id: string, offset: number, auto: boolean, url?: string): Playing {
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
    if (url) {  // file của anh
      const audio = new Audio(url);
      audio.loop = !auto;
      audio.addEventListener("loadedmetadata", () => {
        if (offset > 0 && offset < audio.duration) audio.currentTime = offset;
      }, { once: true });
      const source = this.ctx.createMediaElementSource(audio);
      source.connect(g);
      void audio.play().catch(() => undefined);  // chưa được phép phát: tự phát khi bấm mở khoá (ctx.resume)
      return { id, stop: () => { fadeOut(); window.setTimeout(() => release(audio, source), FADE * 1000); } };
    }
    const preset = PRESETS[Number(id.split(":")[1].split("|")[0]) % PRESETS.length];
    const song = new Song(this.ctx, g, preset);
    song.start(offset);
    return { id, stop: () => { fadeOut(); window.setTimeout(() => song.stop(), FADE * 1000); } };
  }

  /** Anh Tư lơ xe nói: phát file giọng đã đọc sẵn, nhạc nhỏ lại tới khi nói xong. */
  private speak(url: string): void {
    const audio = new Audio(url);
    audio.preservesPitch = true;  // nhanh lên mà không thành giọng «chuột chũi»
    audio.playbackRate = this.rate;
    const source = this.ctx.createMediaElementSource(audio);
    source.connect(this.voice);
    const now = this.ctx.currentTime;
    this.speaking++;
    this.duck.gain.setTargetAtTime(this.duckLevel, now, 0.15);
    this.vehicleDuck.gain.setTargetAtTime(VEHICLE_DUCK, now, 0.15);
    let finished = false;
    const done = () => {
      if (finished) return;
      finished = true;
      release(audio, source);  // buổi live đọc cả nghìn câu: không nhả thì mỗi câu giữ lại một nút âm thanh + file đã giải mã
      this.speaking = Math.max(0, this.speaking - 1);
      if (this.speaking) return;
      this.duck.gain.setTargetAtTime(1, this.ctx.currentTime, 0.4);
      this.vehicleDuck.gain.setTargetAtTime(1, this.ctx.currentTime, 0.4);
    };
    audio.onended = done;
    audio.onerror = done;
    void audio.play().catch(done);  // chưa được phép phát (chưa bấm mở tiếng) thì thôi, nhạc trả lại như cũ
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

  /** Tiếng ồn nâu 4 giây (trầm, như lốp lăn trên nhựa + gió), lặp vòng liền mạch: kéo cuối đoạn về khớp đầu đoạn
   * (lệch là nghe «tách» mỗi lần lặp) và bỏ độ lệch trung bình. */
  private brownNoise(): AudioBuffer {
    const buf = this.ctx.createBuffer(1, this.ctx.sampleRate * 4, this.ctx.sampleRate);
    const data = buf.getChannelData(0);
    let last = 0;
    for (let i = 0; i < data.length; i++) {
      last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
      data[i] = last * 3.5;
    }
    const n = data.length;
    const gap = data[n - 1] - data[0];
    let mean = 0;
    for (let i = 0; i < n; i++) {
      data[i] -= (gap * i) / (n - 1);
      mean += data[i] / n;
    }
    for (let i = 0; i < n; i++) data[i] -= mean;
    return buf;
  }

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
