// Thời tiết (PLAN-121 V3, anh 03/11): mưa phùn (vệt mảnh, rơi chậm) / mưa rào (vệt dài, rơi nhanh, đậm hơn) trước camera.
// Server bốc thời tiết theo vùng mỗi khi xe vào vùng mới; sương mù do scene chỉnh sương (fog) của cảnh.

import * as THREE from "three";

const COUNT = 420;
const BOX = { x: 44, y: 26, z0: -22, z1: 16 };

export class Weather {
  readonly lines: THREE.LineSegments;
  private pos: Float32Array;
  private fall = new Float32Array(COUNT);
  private pace = 1;  // mưa rào rơi nhanh gấp đôi
  private len = 0.7;

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

  /** «drizzle»: mưa phùn; «rain»: mưa rào; còn lại tắt. */
  set(kind: string): void {
    this.lines.visible = kind === "drizzle" || kind === "rain";
    const heavy = kind === "rain";
    this.pace = heavy ? 2.1 : 1;
    this.len = heavy ? 2.2 : 0.9;
    const m = this.lines.material as THREE.LineBasicMaterial;  // vệt mưa 1 điểm ảnh: sáng + đậm để qua nén TikTok vẫn thấy
    m.opacity = heavy ? 0.9 : 0.7;
    m.color.setHex(heavy ? 0xffffff : 0xe8eef5);
  }

  update(dt: number, wind: number): void {
    if (!this.lines.visible) return;
    for (let i = 0; i < COUNT; i++) {
      const o = i * 6;
      const dy = this.fall[i] * this.pace * dt;
      const dx = -(3 + wind) * dt;
      for (const k of [0, 3]) {
        this.pos[o + k] += dx;
        this.pos[o + k + 1] -= dy;
      }
      if (this.pos[o + 4] < 0) this.place(i, BOX.y);
    }
    (this.lines.geometry.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
  }

  /** Đặt vệt mưa thứ i ở độ cao `y`, vị trí ngẫu nhiên; vệt dài `len` nghiêng theo gió. */
  private place(i: number, y: number): void {
    const x = (Math.random() - 0.5) * BOX.x;
    const z = BOX.z0 + Math.random() * (BOX.z1 - BOX.z0);
    this.pos.set([x, y, z, x + 0.15 * this.len / 0.7, y - this.len, z], i * 6);
  }
}
