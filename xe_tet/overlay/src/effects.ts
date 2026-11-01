// Hiệu ứng (PLAN-121 V4): pháo hoa có vệt sáng, bụi / khói. Có trần số lượng; chất lượng thấp thì bớt hạt.

import * as THREE from "three";

const TET_COLORS = [0xff3b30, 0xffd23f, 0xffffff, 0xff8fb1, 0xffa726, 0x7fffd4];

const DOT = (() => {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.4, "rgba(255,255,255,0.8)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 32, 32);
  return new THREE.CanvasTexture(c);
})();

const PUFF = (() => {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,0.9)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();

// ---- pháo hoa ---------------------------------------------------------------------------

const GRAVITY = 5;
const SHELL_LIFE = 1.9;
const ROCKET_TIME = 0.85;
const SPARKS = 80;
const SPARKS_LOW = 36;
const MAX_FLYING = 10;  // quả đang bay + chùm đang nổ cùng lúc (chất lượng thấp: 4)
const MAX_FLYING_LOW = 4;

/*
 * Pháo hoa dùng bể đối tượng: quả + chùm cấp sẵn một lần, bắn xong thì ẩn đi chờ lần sau. Trước đây mỗi chùm tạo vật liệu
 * mới rồi dispose() → three xoá luôn chương trình shader (không còn vật liệu nào dùng) → chùm sau biên dịch lại từ đầu,
 * hình khựng đúng lúc có quà (đo 01/11: 30 % luồng chính là biên dịch shader). Cấp sẵn thì shader biên dịch một lần lúc
 * khởi động, được uốn theo đường cùng lượt bendTree đầu tiên.
 */

/**
 * Một chùm tia sau khi nổ. Mỗi tia vẽ thành một nét từ vị trí hiện tại lùi theo vận tốc → có đuôi
 * mà không phải nhớ lịch sử vị trí; đầu tia là chấm sáng.
 */
class Shell {
  readonly lines: THREE.LineSegments;
  readonly heads: THREE.Points;
  private pos = new Float32Array(SPARKS * 3);
  private vel = new Float32Array(SPARKS * 3);
  private segColor = new THREE.BufferAttribute(new Float32Array(SPARKS * 6), 3);
  private headColor = new THREE.BufferAttribute(new Float32Array(SPARKS * 3), 3);
  private life = 0;
  private n = 0;

  constructor() {
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(SPARKS * 6), 3));
    lineGeo.setAttribute("color", this.segColor);
    this.lines = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    const headGeo = new THREE.BufferGeometry();
    headGeo.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    headGeo.setAttribute("color", this.headColor);
    this.heads = new THREE.Points(headGeo, new THREE.PointsMaterial({
      size: 0.7, map: DOT, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    for (const o of [this.lines, this.heads]) {
      o.frustumCulled = false;
      o.visible = false;
    }
  }

  get active(): boolean {
    return this.life > 0;
  }

  /** Nổ `n` tia tại `origin`. */
  fire(origin: THREE.Vector3, colors: number[], n: number): void {
    this.n = n;
    this.life = SHELL_LIFE;
    const seg = this.segColor.array as Float32Array;
    const head = this.headColor.array as Float32Array;
    const c = new THREE.Color();
    const dir = new THREE.Vector3();
    for (let i = 0; i < n; i++) {
      this.pos.set([origin.x, origin.y, origin.z], i * 3);
      dir.randomDirection().multiplyScalar(6.5 + Math.random() * 2.5);
      this.vel.set([dir.x, dir.y, dir.z], i * 3);
      c.setHex(colors[i % colors.length]);
      seg.set([c.r, c.g, c.b, c.r * 0.15, c.g * 0.15, c.b * 0.15], i * 6);  // đầu sáng, đuôi tối dần
      head.set([c.r, c.g, c.b], i * 3);
    }
    this.segColor.needsUpdate = this.headColor.needsUpdate = true;
    this.lines.geometry.setDrawRange(0, n * 2);
    this.heads.geometry.setDrawRange(0, n);
    this.lines.visible = this.heads.visible = true;
    this.update(0);
  }

  update(dt: number): void {
    if (!this.active) return;
    this.life -= dt;
    if (!this.active) {
      this.lines.visible = this.heads.visible = false;
      return;
    }
    const drag = Math.pow(0.35, dt);
    const seg = (this.lines.geometry.getAttribute("position") as THREE.BufferAttribute).array as Float32Array;
    for (let i = 0; i < this.n; i++) {
      const o = i * 3;
      this.vel[o + 1] -= GRAVITY * dt;
      for (let k = 0; k < 3; k++) {
        this.vel[o + k] *= drag;
        this.pos[o + k] += this.vel[o + k] * dt;
        seg[i * 6 + k] = this.pos[o + k];
        seg[i * 6 + 3 + k] = this.pos[o + k] - this.vel[o + k] * 0.14;  // đuôi theo hướng bay
      }
    }
    this.lines.geometry.getAttribute("position").needsUpdate = true;
    this.heads.geometry.getAttribute("position").needsUpdate = true;
    const fade = Math.max(0, this.life / SHELL_LIFE);
    (this.lines.material as THREE.LineBasicMaterial).opacity = fade;
    (this.heads.material as THREE.PointsMaterial).opacity = fade * (0.7 + Math.random() * 0.3);  // lấp lánh
  }
}

const TRAIL_POINTS = 8;
const _p = new THREE.Vector3();

/** Quả pháo bay vụt lên (có vệt sáng) rồi nổ ở độ cao đích. */
class Rocket {
  readonly trail: THREE.Line;
  readonly to = new THREE.Vector3();
  colors: number[] = [];
  private from = new THREE.Vector3();
  private t = 0;
  private count = 0;
  // vệt = cửa sổ trượt 8 điểm gần nhất trên bộ đệm cấp sẵn: điểm mới ghi vào cuối, đầy thì dời cả dải lùi một điểm
  // (copyWithin, không cấp phát gì mỗi khung)
  private positions = new THREE.BufferAttribute(new Float32Array(TRAIL_POINTS * 3), 3);

  constructor() {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", this.positions);
    geometry.setDrawRange(0, 0);
    this.trail = new THREE.Line(geometry, new THREE.LineBasicMaterial({
      color: 0xffe0a0, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }));
    this.trail.frustumCulled = false;
    this.trail.visible = false;
  }

  get active(): boolean {
    return this.trail.visible;
  }

  fire(from: THREE.Vector3, to: THREE.Vector3, colors: number[]): void {
    this.from.copy(from);
    this.to.copy(to);
    this.colors = colors;
    this.t = 0;
    this.count = 0;
    this.trail.geometry.setDrawRange(0, 0);
    this.trail.visible = true;
  }

  /** Trả về true khi tới điểm nổ (quả ẩn đi, trả về bể). */
  update(dt: number): boolean {
    this.t = Math.min(1, this.t + dt / ROCKET_TIME);
    const ease = 1 - Math.pow(1 - this.t, 2);  // chậm dần khi lên cao
    _p.copy(this.from).lerp(this.to, ease);
    const a = this.positions.array as Float32Array;
    if (this.count === TRAIL_POINTS) a.copyWithin(0, 3);
    else this.count++;
    const o = (this.count - 1) * 3;
    a[o] = _p.x;
    a[o + 1] = _p.y;
    a[o + 2] = _p.z;
    this.positions.needsUpdate = true;
    this.trail.geometry.setDrawRange(0, this.count);
    if (this.t < 1) return false;
    this.trail.visible = false;
    return true;
  }
}

export class Fireworks {
  readonly group = new THREE.Group();
  private rockets = Array.from({ length: MAX_FLYING }, () => new Rocket());
  private shells = Array.from({ length: MAX_FLYING }, () => new Shell());
  private low = false;

  constructor() {
    for (const r of this.rockets) this.group.add(r.trail);
    for (const s of this.shells) this.group.add(s.lines, s.heads);
  }

  setQuality(low: boolean): void {
    this.low = low;
  }

  /** Bắn `count` quả từ mặt đất quanh (at.x, at.z) lên nổ ở độ cao at.y (rải ngang ±3). */
  launch(at: THREE.Vector3, count = 1, colors = TET_COLORS): void {
    const max = this.low ? MAX_FLYING_LOW : MAX_FLYING;
    let flying = this.rockets.filter((r) => r.active).length + this.shells.filter((s) => s.active).length;
    for (let i = 0; i < count && flying < max; i++, flying++) {
      const r = this.rockets.find((x) => !x.active);
      if (!r) return;
      const to = at.clone().add(new THREE.Vector3((Math.random() - 0.5) * 6, Math.random() * 2, 0));
      const from = new THREE.Vector3(to.x + (Math.random() - 0.5) * 1.5, 0.5, to.z);
      r.fire(from, to, [colors[Math.floor(Math.random() * colors.length)], colors[Math.floor(Math.random() * colors.length)]]);
    }
  }

  update(dt: number): void {
    for (const r of this.rockets) {
      if (!r.active || !r.update(dt)) continue;
      this.shells.find((s) => !s.active)?.fire(r.to, r.colors, this.low ? SPARKS_LOW : SPARKS);
    }
    for (const s of this.shells) s.update(dt);
  }
}

// ---- bụi / khói ------------------------------------------------------------------------------

interface Puff { sprite: THREE.Sprite; vel: THREE.Vector3; life: number; max: number; opacity: number }

const GROW = 1.8; // làn khói nở thêm 180 % mỗi giây

/** Làn bụi / khói: bốc lên, nở to, tan dần. Dùng chung cho bụi bánh xe (vàng đất) và khói ống xả (xám). */
export class Puffs {
  readonly group = new THREE.Group();
  private free: THREE.Sprite[] = [];
  private live: Puff[] = [];
  private cap: number;

  constructor(private size = 64) {
    this.cap = size;
    for (let i = 0; i < size; i++) {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: PUFF, transparent: true, depthWrite: false, opacity: 0 }));
      s.visible = false;
      this.free.push(s);
      this.group.add(s);
    }
  }

  setQuality(low: boolean): void {
    this.cap = low ? Math.floor(this.size / 3) : this.size;
  }

  emit(at: THREE.Vector3, vel: THREE.Vector3, color: number, opacity = 0.5, life = 1.2, scale = 0.8): void {
    if (this.live.length >= this.cap) return;
    const sprite = this.free.pop();
    if (!sprite) return;
    sprite.position.copy(at);
    sprite.scale.setScalar(scale);
    const m = sprite.material;
    m.color.setHex(color);
    m.opacity = opacity;
    sprite.visible = true;
    this.live.push({ sprite, vel: vel.clone(), life, max: life, opacity });
  }

  update(dt: number): void {
    this.live = this.live.filter((p) => {
      p.life -= dt;
      if (p.life <= 0) {
        p.sprite.visible = false;
        this.free.push(p.sprite);
        return false;
      }
      p.sprite.position.addScaledVector(p.vel, dt);
      p.vel.multiplyScalar(Math.pow(0.4, dt));
      p.sprite.scale.multiplyScalar(1 + GROW * dt);
      p.sprite.material.opacity = p.opacity * (p.life / p.max);  // tan dần theo tuổi
      return true;
    });
  }
}
