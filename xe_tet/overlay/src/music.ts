// Nhạc Tết tự sinh (PLAN-127): giai điệu ngũ cung chơi bằng tiếng đàn tranh / sáo / trống / mõ dựng từ Web Audio — nhạc
// của mình, không vướng bản quyền khi phát trên TikTok LIVE. Mỗi bài một hạt giống + nhịp + điệu; cùng hạt giống thì bài
// y hệt (nghe lại vẫn là «bài đó»). Thứ tự PRESETS khớp server/music.py GENERATED.

interface Preset {
  seed: number;
  bpm: number;
  root: number;  // nốt gốc (MIDI)
  scale: number[];  // ngũ cung: bậc tính bằng nửa cung
  lead: "tranh" | "sao";
  drums: number;  // 0 → 1: trống / mõ thưa → dày
}

const BAC = [0, 2, 5, 7, 9];  // ngũ cung Bắc (vui, sáng)
const OAN = [0, 3, 5, 7, 10];  // điệu oán (man mác, nhớ quê)

export const PRESETS: Preset[] = [
  { seed: 11, bpm: 104, root: 62, scale: BAC, lead: "tranh", drums: 0.6 },  // Xuân về trên phố
  { seed: 23, bpm: 84, root: 64, scale: BAC, lead: "tranh", drums: 0.25 },  // Đàn tranh mùa xuân
  { seed: 37, bpm: 76, root: 67, scale: BAC, lead: "sao", drums: 0.15 },  // Sáo trúc đồng quê
  { seed: 41, bpm: 120, root: 60, scale: BAC, lead: "tranh", drums: 1 },  // Trống hội làng
  { seed: 53, bpm: 88, root: 65, scale: OAN, lead: "sao", drums: 0.35 },  // Đường xa về nhà
  { seed: 67, bpm: 70, root: 62, scale: BAC, lead: "tranh", drums: 0.1 },  // Giao thừa bên bếp lửa
];

const STEPS_PER_PHRASE = 16;  // 2 ô nhịp 4/4, mỗi bước một móc đơn
const PHRASES = 8;  // A A' B A'' × 2 đoạn (đoạn sau lên quãng tám) ≈ 30–55 giây rồi lặp lại
const LOOKAHEAD = 0.35;  // giây lên lịch trước (đồng hồ JS không đều, đồng hồ âm thanh thì đều)

function rand(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const hz = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12);

interface Note { step: number; midi: number; len: number }

/** Một câu nhạc: đi từng bậc trên thang ngũ cung, thỉnh thoảng nhảy quãng, kết câu về nốt gốc / quãng năm, ngân dài. */
function phrase(rnd: () => number, p: Preset, start: number, lift: number): Note[] {
  const ladder = [...p.scale, ...p.scale.map((n) => n + 12), 24];  // hai quãng tám
  const RHYTHMS = p.lead === "sao"
    ? [[4, 2, 2, 4, 4], [2, 2, 4, 2, 2, 4], [6, 2, 4, 4]]  // sáo: nốt dài, thở
    : [[2, 1, 1, 2, 2, 2, 2, 4], [1, 1, 2, 1, 1, 2, 4, 4], [2, 2, 1, 1, 2, 4, 4]];  // đàn tranh: rải, láy
  const lens = RHYTHMS[Math.floor(rnd() * RHYTHMS.length)];
  let deg = start;
  let step = 0;
  const notes: Note[] = [];
  lens.forEach((len, i) => {
    const last = i === lens.length - 1;
    if (last) deg = rnd() < 0.6 ? 0 : 3;  // kết về gốc hoặc quãng năm
    else deg = Math.max(0, Math.min(ladder.length - 1, deg + (rnd() < 0.8 ? (rnd() < 0.5 ? -1 : 1) : (rnd() < 0.5 ? -2 : 2))));
    notes.push({ step, midi: p.root + lift + ladder[deg], len });
    step += len;
  });
  return notes;
}

/** Cả bài: câu A, A' (đổi đuôi), B (lên cao), A''; đoạn hai lên quãng tám cho «cao trào». */
function compose(p: Preset): Note[][] {
  const rnd = rand(p.seed);
  const a = phrase(rnd, p, 2, 0);
  const tail = phrase(rnd, p, 4, 0);
  const aVar = [...a.filter((n) => n.step < 8), ...tail.filter((n) => n.step >= 8)];
  const b = phrase(rnd, p, 6, 0);
  const section = [a, aVar, b, a];
  return [...section, ...section.map((ph) => ph.map((n) => ({ ...n, midi: n.midi + (ph === b ? 0 : 12) })))].slice(0, PHRASES);
}

/** Một bài đang chơi: lên lịch nốt trước LOOKAHEAD giây, lặp vô hạn tới khi stop(). */
export class Song {
  private timer = 0;
  private next = 0;  // thời điểm (đồng hồ âm thanh) của bước kế tiếp
  private index = 0;  // bước thứ mấy trong cả bài
  private notes: Map<number, Note[]>;
  private total: number;
  private stepSec: number;

  constructor(private ctx: AudioContext, private out: AudioNode, private p: Preset) {
    this.stepSec = 60 / p.bpm / 2;
    const phrases = compose(p);
    this.total = phrases.length * STEPS_PER_PHRASE;
    this.notes = new Map();
    phrases.forEach((ph, i) => ph.forEach((n) => {
      const at = i * STEPS_PER_PHRASE + n.step;
      this.notes.set(at, [...(this.notes.get(at) ?? []), n]);
    }));
  }

  start(): void {
    this.next = this.ctx.currentTime + 0.1;
    this.timer = window.setInterval(() => this.schedule(), 100);
    this.schedule();
  }

  stop(): void {
    window.clearInterval(this.timer);
  }

  /** Lên lịch nốt tới `ahead` giây phía trước (dựng offline để kiểm tra thì truyền cả độ dài bài). */
  schedule(ahead = LOOKAHEAD): void {
    while (this.next < this.ctx.currentTime + ahead) {
      const step = this.index % this.total;
      const t = this.next;
      for (const n of this.notes.get(step) ?? []) {
        if (this.p.lead === "sao") sao(this.ctx, this.out, t, hz(n.midi), n.len * this.stepSec, 0.13);  // sáo ngân dài: nhỏ hơn đàn cho đều tai
        else tranh(this.ctx, this.out, t, hz(n.midi), 0.28);
      }
      const beat = step % 4 === 0;
      if (step % 8 === 0) bass(this.ctx, this.out, t, hz(this.p.root - 12 + (step % 32 === 16 ? 7 : 0)), this.stepSec * 8);
      const roll = rand(this.p.seed * 1000 + step)();
      if (beat && roll < this.p.drums) trong(this.ctx, this.out, t, step % 16 === 0 ? 0.5 : 0.3);
      if (!beat && step % 2 === 1 && roll < this.p.drums * 0.7) mo(this.ctx, this.out, t, 0.12);
      this.next += this.stepSec;
      this.index++;
    }
  }
}

// ---- nhạc cụ ------------------------------------------------------------------------------------

function env(ctx: AudioContext, t: number, attack: number, peak: number, decay: number): GainNode {
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
  return g;
}

/** Đàn tranh: gảy dây — tắt nhanh, nhấn nhá (cao lên chút rồi trả về). */
function tranh(ctx: AudioContext, out: AudioNode, t: number, freq: number, vel: number): void {
  const g = env(ctx, t, 0.005, vel, 1.3);
  for (const [mult, type, level] of [[1, "triangle", 1], [2, "sine", 0.35], [3, "sine", 0.12]] as const) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq * mult * 1.012, t);
    osc.frequency.exponentialRampToValueAtTime(freq * mult, t + 0.07);
    const lvl = ctx.createGain();
    lvl.gain.value = level;
    osc.connect(lvl).connect(g);
    osc.start(t);
    osc.stop(t + 1.4);
  }
  g.connect(out);
}

/** Sáo trúc: vào hơi chậm, ngân, rung (vibrato) sau một nhịp thở. */
function sao(ctx: AudioContext, out: AudioNode, t: number, freq: number, dur: number, vel: number): void {
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(vel, t + 0.08);
  g.gain.setValueAtTime(vel, t + Math.max(0.1, dur - 0.12));
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.15);
  const osc = ctx.createOscillator();
  osc.type = "sine";
  osc.frequency.value = freq;
  const lfo = ctx.createOscillator();
  lfo.frequency.value = 5.5;
  const depth = ctx.createGain();
  depth.gain.setValueAtTime(0, t);
  depth.gain.linearRampToValueAtTime(freq * 0.006, t + 0.25);
  lfo.connect(depth).connect(osc.frequency);
  osc.connect(g).connect(out);
  for (const o of [osc, lfo]) {
    o.start(t);
    o.stop(t + dur + 0.2);
  }
}

/** Nền trầm: một nốt gốc / quãng năm ngân dài (như dây đàn bầu nền). */
function bass(ctx: AudioContext, out: AudioNode, t: number, freq: number, dur: number): void {
  const g = env(ctx, t, 0.04, 0.12, dur);
  const osc = ctx.createOscillator();
  osc.type = "sine";
  osc.frequency.value = freq;
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + dur + 0.1);
}

/** Trống: tiếng «thùng» trầm, cao độ tụt nhanh. */
function trong(ctx: AudioContext, out: AudioNode, t: number, vel: number): void {
  const g = env(ctx, t, 0.003, vel, 0.35);
  const osc = ctx.createOscillator();
  osc.frequency.setValueAtTime(110, t);
  osc.frequency.exponentialRampToValueAtTime(48, t + 0.25);
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + 0.4);
}

/** Mõ: tiếng «cốc» gỗ ngắn. */
function mo(ctx: AudioContext, out: AudioNode, t: number, vel: number): void {
  const g = env(ctx, t, 0.002, vel, 0.06);
  const osc = ctx.createOscillator();
  osc.frequency.value = 1150;
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + 0.1);
}
