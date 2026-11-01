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

/**
 * Một chùm tia sau khi nổ. Mỗi tia vẽ thành một nét từ vị trí hiện tại lùi theo vận tốc → có đuôi
 * mà không phải nhớ lịch sử vị trí; đầu tia là chấm sáng.
 */
class Shell {
  readonly lines: THREE.LineSegments;
  readonly heads: THREE.Points;
  private pos: Float32Array;
  private vel: Float32Array;
  private life = SHELL_LIFE;

  constructor(origin: THREE.Vector3, colors: number[], private n: number) {
    this.pos = new Float32Array(n * 3);
    this.vel = new Float32Array(n * 3);
    const segColor = new Float32Array(n * 6);
    const headColor = new Float32Array(n * 3);
    const c = new THREE.Color();
    const dir = new THREE.Vector3();
    for (let i = 0; i < n; i++) {
      this.pos.set([origin.x, origin.y, origin.z], i * 3);
      dir.randomDirection().multiplyScalar(6.5 + Math.random() * 2.5);
      this.vel.set([dir.x, dir.y, dir.z], i * 3);
      c.setHex(colors[i % colors.length]);
      segColor.set([c.r, c.g, c.b, c.r * 0.15, c.g * 0.15, c.b * 0.15], i * 6);  // đầu sáng, đuôi tối dần
      headColor.set([c.r, c.g, c.b], i * 3);
    }
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 6), 3));
    lineGeo.setAttribute("color", new THREE.BufferAttribute(segColor, 3));
    this.lines = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    const headGeo = new THREE.BufferGeometry();
    headGeo.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    headGeo.setAttribute("color", new THREE.BufferAttribute(headColor, 3));
    this.heads = new THREE.Points(headGeo, new THREE.PointsMaterial({
      size: 0.7, map: DOT, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    for (const o of [this.lines, this.heads]) o.frustumCulled = false;
  }

  update(dt: number): boolean {
    this.life -= dt;
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
    return this.life > 0;
  }

  dispose(): void {
    for (const o of [this.lines, this.heads]) {
      o.removeFromParent();
      o.geometry.dispose();
      (o.material as THREE.Material).dispose();
    }
  }
}

const TRAIL_POINTS = 8;

/** Quả pháo bay vụt lên (có vệt sáng) rồi nổ ở độ cao đích. */
class Rocket {
  readonly trail: THREE.Line;
  private t = 0;
  private points: THREE.Vector3[] = [];
  // vệt dài cố định 8 điểm: cấp sẵn bộ đệm, mỗi khung chỉ chép toạ độ + đổi số điểm vẽ
  // (setFromPoints lên hình đã có sẵn bộ đệm 1 điểm sẽ không nới ra được → vệt không hiện)
  private positions = new THREE.BufferAttribute(new Float32Array(TRAIL_POINTS * 3), 3);

  constructor(private from: THREE.Vector3, readonly to: THREE.Vector3, readonly colors: number[]) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", this.positions);
    geometry.setDrawRange(0, 0);
    this.trail = new THREE.Line(geometry, new THREE.LineBasicMaterial({
      color: 0xffe0a0, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }));
    this.trail.frustumCulled = false;
  }

  /** Trả về true khi tới điểm nổ. */
  update(dt: number): boolean {
    this.t = Math.min(1, this.t + dt / ROCKET_TIME);
    const ease = 1 - Math.pow(1 - this.t, 2);  // chậm dần khi lên cao
    this.points.push(this.from.clone().lerp(this.to, ease));
    if (this.points.length > TRAIL_POINTS) this.points.shift();
    this.points.forEach((p, i) => this.positions.setXYZ(i, p.x, p.y, p.z));
    this.positions.needsUpdate = true;
    this.trail.geometry.setDrawRange(0, this.points.length);
    return this.t >= 1;
  }

  dispose(): void {
    this.trail.removeFromParent();
    this.trail.geometry.dispose();
    (this.trail.material as THREE.Material).dispose();
  }
}

export class Fireworks {
  readonly group = new THREE.Group();
  private rockets: Rocket[] = [];
  private shells: Shell[] = [];
  private low = false;

  setQuality(low: boolean): void {
    this.low = low;
  }

  /** Bắn `count` quả từ mặt đất quanh (at.x, at.z) lên nổ ở độ cao at.y (rải ngang ±3). */
  launch(at: THREE.Vector3, count = 1, colors = TET_COLORS): void {
    const max = this.low ? 4 : 10;
    for (let i = 0; i < count && this.rockets.length + this.shells.length < max; i++) {
      const to = at.clone().add(new THREE.Vector3((Math.random() - 0.5) * 6, Math.random() * 2, 0));
      const from = new THREE.Vector3(to.x + (Math.random() - 0.5) * 1.5, 0.5, to.z);
      const pair = [colors[Math.floor(Math.random() * colors.length)], colors[Math.floor(Math.random() * colors.length)]];
      const r = new Rocket(from, to, pair);
      this.rockets.push(r);
      this.group.add(r.trail);
    }
  }

  update(dt: number): void {
    this.rockets = this.rockets.filter((r) => {
      if (!r.update(dt)) return true;
      const shell = new Shell(r.to, r.colors, this.low ? 36 : 80);
      this.shells.push(shell);
      this.group.add(shell.lines, shell.heads);
      r.dispose();
      return false;
    });
    this.shells = this.shells.filter((s) => {
      if (s.update(dt)) return true;
      s.dispose();
      return false;
    });
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
