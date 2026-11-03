// Thời tiết (PLAN-121 V3): mưa phùn miền Bắc — vệt mưa mảnh rơi xiên trước camera. Nơi khác trời quang.

import * as THREE from "three";

const COUNT = 420;
const BOX = { x: 44, y: 26, z0: -22, z1: 16 };

export class Weather {
  readonly lines: THREE.LineSegments;
  private pos: Float32Array;
  private fall = new Float32Array(COUNT);

  constructor() {
    this.pos = new Float32Array(COUNT * 6);
    for (let i = 0; i < COUNT; i++) {
      this.fall[i] = 16 + Math.random() * 8;
      this.place(i, Math.random() * BOX.y);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    this.lines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xcfd8e3, transparent: true, opacity: 0.45 }));
    this.lines.visible = false;
    this.lines.frustumCulled = false;
  }

  /** Chất lượng thấp: chỉ vẽ một phần số vệt mưa (mỗi vệt 2 đỉnh). */
  setDensity(fraction: number): void {
    this.lines.geometry.setDrawRange(0, Math.floor(COUNT * fraction) * 2);
  }

  /** «drizzle»: mưa phùn; «clear»: tắt. */
  set(kind: "drizzle" | "clear"): void {
    this.lines.visible = kind === "drizzle";
  }

  update(dt: number, wind: number): void {
    if (!this.lines.visible) return;
    for (let i = 0; i < COUNT; i++) {
      const o = i * 6;
      const dy = this.fall[i] * dt;
      const dx = -(3 + wind) * dt;
      for (const k of [0, 3]) {
        this.pos[o + k] += dx;
        this.pos[o + k + 1] -= dy;
      }
      if (this.pos[o + 4] < 0) this.place(i, BOX.y);
    }
    (this.lines.geometry.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
  }

  /** Đặt vệt mưa thứ i ở độ cao `y`, vị trí ngẫu nhiên; vệt dài ~0,7 nghiêng theo gió. */
  private place(i: number, y: number): void {
    const x = (Math.random() - 0.5) * BOX.x;
    const z = BOX.z0 + Math.random() * (BOX.z1 - BOX.z0);
    this.pos.set([x, y, z, x + 0.15, y - 0.7, z], i * 6);
  }
}
