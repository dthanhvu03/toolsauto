// Đồ vật dùng lại giữa các bối cảnh (PLAN-121 V2): cây, chậu quất, đèn lồng, ghế nhựa, bàn, ly trà, vali,
// bảng hiệu, mái ngói, hơi nước. Đồ lặp lại nhiều thì vẽ gộp (InstancedMesh) để nhẹ máy.

import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { at, blob, GEO, mat, rounded, soft } from "./art";
import { strip } from "./bend";

// ---- texture hoa văn vẽ bằng canvas ---------------------------------------------

type Pattern = "tiles" | "bricks" | "roof" | "awning";

/** Gạch lát sân, gạch đỏ lối đi, ngói, bạt sọc — vẽ một lần, lặp lại theo `repeat`. */
export function patternTexture(kind: Pattern, repeatX: number, repeatY: number): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  if (kind === "tiles") {
    g.fillStyle = "#d9d2c4";
    g.fillRect(0, 0, 128, 128);
    g.strokeStyle = "#b9b0a0";
    g.lineWidth = 4;
    g.strokeRect(2, 2, 124, 124);
  } else if (kind === "bricks") {
    g.fillStyle = "#b5583c";
    g.fillRect(0, 0, 128, 128);
    g.strokeStyle = "#e4c9a8";
    g.lineWidth = 5;
    for (let row = 0; row < 4; row++) {
      const y = row * 32;
      g.beginPath();
      g.moveTo(0, y);
      g.lineTo(128, y);
      g.stroke();
      for (let x = row % 2 ? 32 : 0; x < 128; x += 64) {
        g.beginPath();
        g.moveTo(x, y);
        g.lineTo(x, y + 32);
        g.stroke();
      }
    }
  } else if (kind === "roof") {
    for (let i = 0; i < 8; i++) {
      g.fillStyle = i % 2 ? "#a3422b" : "#b9502f";
      g.fillRect(i * 16, 0, 16, 128);
    }
    g.fillStyle = "rgba(0,0,0,0.18)";
    for (let y = 0; y < 128; y += 32) g.fillRect(0, y, 128, 5);
  } else {
    for (let i = 0; i < 8; i++) {
      g.fillStyle = i % 2 ? "#fff4e0" : "#c62828";
      g.fillRect(i * 16, 0, 16, 128);
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeatX, repeatY);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Mặt phẳng nằm (sân, lối đi) phủ hoa văn. */
export function floor(w: number, d: number, kind: Pattern, tileSize = 1.5): THREE.Mesh {
  const m = new THREE.Mesh(strip(w, d),  // đủ đỉnh theo x: sân bến / trạm uốn theo đường lúc xe vào / ra
    new THREE.MeshStandardMaterial({ map: patternTexture(kind, w / tileSize, d / tileSize), roughness: 0.9 }));
  m.rotation.x = -Math.PI / 2;
  m.receiveShadow = true;
  return m;
}

// ---- bảng hiệu ------------------------------------------------------------------

interface SignColors { bg: string; fg: string; rim: string }
/** Bảng đỏ chữ vàng (mặc định: biển bến, quầy vé, làn đang đón) và bảng xanh chữ trắng (làn đang chờ). */
export const SIGN_RED: SignColors = { bg: "#c62828", fg: "#ffe7a8", rim: "#f4c04e" };
export const SIGN_BLUE: SignColors = { bg: "#1e3a5f", fg: "#ffffff", rim: "#f4c04e" };

/** Bảng hiệu chữ vẽ canvas (nằm trong cảnh 3D). `set(text)` chỉ vẽ lại khi chữ / màu đổi. */
export class SignBoard {
  mesh: THREE.Mesh;
  private canvas = document.createElement("canvas");
  private texture: THREE.CanvasTexture;
  private drawn = "";

  constructor(text: string, width: number, height: number, private colors: SignColors = SIGN_RED) {
    this.canvas.width = 1024;
    this.canvas.height = Math.round(1024 * (height / width));
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.anisotropy = 4;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshBasicMaterial({ map: this.texture }));
    this.set(text);
  }

  /** Đổi màu (vẽ lại ở lần `set` kế tiếp). */
  recolor(colors: SignColors): void {
    this.colors = colors;
  }

  set(text: string): void {
    // state tới 5 lần / giây: vẽ lại canvas 1024 px + tải lên GPU mỗi lần là phí — chỉ vẽ khi nội dung đổi
    const key = `${text}|${this.colors.bg}|${this.colors.fg}|${this.colors.rim}`;
    if (key === this.drawn) return;
    this.drawn = key;
    const { width: w, height: h } = this.canvas;
    const g = this.canvas.getContext("2d")!;
    g.fillStyle = this.colors.bg;
    g.fillRect(0, 0, w, h);
    g.strokeStyle = this.colors.rim;
    g.lineWidth = Math.max(8, h * 0.07);
    g.strokeRect(g.lineWidth / 2, g.lineWidth / 2, w - g.lineWidth, h - g.lineWidth);
    g.fillStyle = this.colors.fg;
    g.textAlign = "center";
    g.textBaseline = "middle";
    let size = h * 0.62;
    do {
      g.font = `800 ${size}px 'Be Vietnam Pro', sans-serif`;
      size -= 4;
    } while (g.measureText(text).width > w * 0.9 && size > 12);
    g.fillText(text, w / 2, h / 2 + h * 0.03);
    this.texture.needsUpdate = true;
  }
}

// ---- mái ngói ------------------------------------------------------------------

/** Mái hai dốc lợp ngói (hai tấm nghiêng + nóc), dài theo trục x. */
export function tiledRoof(length: number, depth: number, rise: number): THREE.Group {
  const g = new THREE.Group();
  const slope = Math.hypot(depth / 2, rise);
  const angle = Math.atan2(rise, depth / 2);
  const roofMat = new THREE.MeshStandardMaterial({ map: patternTexture("roof", length / 1.2, 2), roughness: 0.8 });
  for (const side of [1, -1]) {
    const slab = new THREE.Mesh(new THREE.BoxGeometry(length, 0.16, slope + 0.5), roofMat);
    slab.rotation.x = side * angle;
    slab.position.set(0, rise / 2, side * depth / 4);
    slab.castShadow = true;
    g.add(slab);
  }
  const ridge = at(new THREE.Mesh(GEO.cylSmooth, soft(0x7a2e1e, 0.7)), 0, rise + 0.05, 0);
  ridge.scale.set(0.16, length + 0.3, 0.16);
  ridge.rotation.z = Math.PI / 2;
  g.add(ridge);
  return g;
}

// ---- cây ------------------------------------------------------------------------

type TreeKind = "round" | "pine" | "palm" | "bush";

export function makeTree(kind: TreeKind): THREE.Group {
  const g = new THREE.Group();
  if (kind === "pine") {
    const trunk = new THREE.Mesh(GEO.box, mat(0x6b4a2b));
    trunk.scale.set(0.3, 1.2, 0.3);
    g.add(at(trunk, 0, 0.6, 0));
    const c = new THREE.Mesh(GEO.cone, mat(0x2f5d34));
    c.scale.set(1.4, 3.6, 1.4);
    g.add(at(c, 0, 2.8, 0));
  } else if (kind === "palm") {
    const trunk = new THREE.Mesh(GEO.cyl, mat(0x8a6a44));
    trunk.scale.set(0.18, 4.6, 0.18);
    trunk.rotation.z = 0.12;
    g.add(at(trunk, 0.25, 2.3, 0));
    for (let i = 0; i < 5; i++) {
      const leaf = new THREE.Mesh(GEO.box, mat(0x3d8a3a));
      leaf.scale.set(2.6, 0.12, 0.5);
      leaf.rotation.y = (i / 5) * Math.PI * 2;
      leaf.rotation.z = -0.35;
      g.add(at(leaf, 0.5, 4.6, 0));
    }
  } else if (kind === "bush") {
    const b = new THREE.Mesh(GEO.ball, mat(0x2e6b35));
    b.scale.set(0.9, 0.7, 0.9);
    g.add(at(b, 0, 0.6, 0));
  } else {
    const trunk = new THREE.Mesh(GEO.box, mat(0x6b4a2b));
    trunk.scale.set(0.35, 1.6, 0.35);
    g.add(at(trunk, 0, 0.8, 0));
    for (let i = 0; i < 3; i++) {
      const b = new THREE.Mesh(GEO.ball, mat(0x4c8c3f));
      const s = 1.1 - i * 0.15;
      b.scale.setScalar(s);
      g.add(at(b, (i - 1) * 0.6, 2.2 + (i % 2) * 0.5, (i % 2) * 0.4));
    }
  }
  g.traverse((o) => { if ((o as THREE.Mesh).isMesh) o.castShadow = true; });
  g.add(blob(kind === "bush" ? 1.8 : 2.6));
  return g;
}

/** Cây đào (hồng, miền Bắc) / mai (vàng): thân + cành + chùm hoa. */
export function blossomTree(color: number): THREE.Group {
  const g = new THREE.Group();
  const bark = mat(0x5b3a24);
  const trunk = new THREE.Mesh(GEO.cyl, bark);
  trunk.scale.set(0.22, 2.2, 0.22);
  g.add(at(trunk, 0, 1.1, 0));
  const flowers = new THREE.InstancedMesh(GEO.ball, mat(color), 26);
  const m4 = new THREE.Matrix4();
  let n = 0;
  for (let b = 0; b < 5; b++) {
    const angle = (b / 5) * Math.PI * 2;
    const branch = new THREE.Mesh(GEO.cyl, bark);
    branch.scale.set(0.08, 1.6, 0.08);
    branch.position.set(Math.cos(angle) * 0.5, 2.6, Math.sin(angle) * 0.5);
    branch.rotation.set(Math.sin(angle) * 0.7, 0, -Math.cos(angle) * 0.7);
    g.add(branch);
    for (let k = 0; k < 5; k++) {
      const r = 0.6 + k * 0.25;
      const s = 0.32 + ((k * 7 + b) % 3) * 0.06;
      m4.compose(new THREE.Vector3(Math.cos(angle + k * 0.4) * r, 2.6 + k * 0.28, Math.sin(angle + k * 0.4) * r),
        new THREE.Quaternion(), new THREE.Vector3(s, s, s));
      flowers.setMatrixAt(n++, m4);
    }
  }
  flowers.count = n;
  flowers.castShadow = true;
  g.add(flowers, blob(3));
  return g;
}

/** Chậu quất ngày Tết: chậu đỏ viền vàng + tán tròn + quả cam lấm tấm. */
export function kumquatPot(): THREE.Group {
  const g = new THREE.Group();
  const pot = at(new THREE.Mesh(GEO.cylSmooth, soft(0xa3301f, 0.6)), 0, 0.4, 0);
  pot.scale.set(0.55, 0.8, 0.55);
  const rim = at(new THREE.Mesh(GEO.cylSmooth, soft(0xf4c04e, 0.4, 0.3)), 0, 0.8, 0);
  rim.scale.set(0.6, 0.08, 0.6);
  const bush = at(new THREE.Mesh(GEO.sphere, soft(0x2f6b2f, 0.9)), 0, 1.55, 0);
  bush.scale.set(0.85, 0.8, 0.85);
  const fruit = new THREE.InstancedMesh(GEO.sphere, soft(0xff9a1f, 0.5), 14);
  const m4 = new THREE.Matrix4();
  for (let i = 0; i < 14; i++) {
    const a = i * 2.4;
    const y = 1.2 + (i % 5) * 0.16;
    m4.compose(new THREE.Vector3(Math.cos(a) * 0.82, y, Math.sin(a) * 0.82), new THREE.Quaternion(), new THREE.Vector3(0.09, 0.09, 0.09));
    fruit.setMatrixAt(i, m4);
  }
  for (const m of [pot, bush]) m.castShadow = true;
  g.add(pot, rim, bush, fruit, blob(1.6));
  return g;
}

// ---- đèn lồng --------------------------------------------------------------------

const LANTERN_BODY = soft(0xd32f2f, 0.5);
const LANTERN_CAP = soft(0xf4c04e, 0.4, 0.4);

/** Một đèn lồng đỏ (gốc ở móc treo) — dây đèn lồng, hiên nhà ống, cây nêu. */
export function lantern(scale = 1): THREE.Group {
  const l = new THREE.Group();
  const shell = at(new THREE.Mesh(GEO.sphere, LANTERN_BODY), 0, -0.42, 0);
  shell.scale.set(0.3, 0.36, 0.3);
  const top = at(new THREE.Mesh(GEO.cylSmooth, LANTERN_CAP), 0, -0.08, 0);
  top.scale.set(0.16, 0.08, 0.16);
  const tassel = at(new THREE.Mesh(GEO.cyl, LANTERN_CAP), 0, -0.88, 0);
  tassel.scale.set(0.03, 0.22, 0.03);
  l.add(shell, top, tassel);
  l.scale.setScalar(scale);
  return l;
}

/** Dây đèn lồng đỏ võng giữa hai điểm; `update(t)` cho đèn đung đưa nhẹ. */
export class LanternString {
  group = new THREE.Group();
  private lanterns: THREE.Group[] = [];

  constructor(from: THREE.Vector3, to: THREE.Vector3, count: number, sag = 0.6) {
    const curve = new THREE.QuadraticBezierCurve3(from, from.clone().lerp(to, 0.5).add(new THREE.Vector3(0, -sag * 2, 0)), to);
    this.group.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.025, 4), soft(0x3a2a20, 0.9)));
    for (let i = 1; i <= count; i++) {
      const l = lantern();
      l.position.copy(curve.getPoint(i / (count + 1)));
      this.lanterns.push(l);
      this.group.add(l);
    }
  }

  update(t: number): void {
    this.lanterns.forEach((l, i) => { l.rotation.z = Math.sin(t * 1.4 + i * 0.9) * 0.08; });
  }
}

// ---- bàn ghế quán ven đường -----------------------------------------------------------

const STOOL_GEO = new RoundedBoxGeometry(0.42, 0.44, 0.42, 3, 0.08);

/** Ghế nhựa thấp đỏ / xanh (đặc trưng quán Việt) — vẽ gộp một lần cho cả dãy. */
export function plasticStools(spots: THREE.Vector3[]): THREE.InstancedMesh {
  const stools = new THREE.InstancedMesh(STOOL_GEO, new THREE.MeshStandardMaterial({ roughness: 0.4 }), spots.length);
  const m4 = new THREE.Matrix4();
  const red = new THREE.Color(0xd32f2f);
  const blue = new THREE.Color(0x1e6fd9);
  spots.forEach((p, i) => {
    m4.compose(p.clone().setY(0.22), new THREE.Quaternion(), new THREE.Vector3(1, 1, 1));
    stools.setMatrixAt(i, m4);
    stools.setColorAt(i, i % 3 === 1 ? blue : red);
  });
  stools.castShadow = true;
  return stools;
}

/** Bàn nhựa thấp: mặt bàn + 4 chân. */
export function plasticTable(color: number): THREE.Group {
  const g = new THREE.Group();
  const top = at(rounded(1.3, 0.08, 1.3, 0.04, soft(color, 0.4)), 0, 0.62, 0);
  top.castShadow = true;
  g.add(top);
  for (const [x, z] of [[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5], [0.5, 0.5]]) {
    const leg = at(new THREE.Mesh(GEO.cyl, soft(color, 0.4)), x, 0.3, z);
    leg.scale.set(0.05, 0.6, 0.05);
    g.add(leg);
  }
  g.add(blob(1.8));
  return g;
}

/** Ly trà đá (thuỷ tinh hổ phách) gộp một lần vẽ. */
export function teaGlasses(spots: THREE.Vector3[]): THREE.InstancedMesh {
  const glass = new THREE.MeshStandardMaterial({ color: 0xd9a441, roughness: 0.15, metalness: 0.1, transparent: true, opacity: 0.85 });
  const cups = new THREE.InstancedMesh(GEO.cylSmooth, glass, spots.length);
  const m4 = new THREE.Matrix4();
  spots.forEach((p, i) => {
    m4.compose(p, new THREE.Quaternion(), new THREE.Vector3(0.09, 0.2, 0.09));
    cups.setMatrixAt(i, m4);
  });
  return cups;
}

// ---- hành lý ---------------------------------------------------------------------

/** Vali kéo / thùng quà buộc dây — người đi Tết. */
export function luggage(color: number, kind: "case" | "box" = "case"): THREE.Group {
  const g = new THREE.Group();
  if (kind === "case") {
    const body = at(rounded(0.55, 0.75, 0.3, 0.06, soft(color, 0.5)), 0, 0.42, 0);
    const handle = at(new THREE.Mesh(GEO.box, soft(0x2a2a2e, 0.5)), 0, 0.9, 0);
    handle.scale.set(0.3, 0.04, 0.04);
    body.castShadow = true;
    g.add(body, handle);
  } else {
    const body = at(rounded(0.7, 0.5, 0.5, 0.03, soft(color, 0.8)), 0, 0.25, 0);
    const rope = at(new THREE.Mesh(GEO.box, soft(0xe9d8a6, 0.9)), 0, 0.25, 0);
    rope.scale.set(0.72, 0.52, 0.06);
    body.castShadow = true;
    g.add(body, rope);
  }
  return g;
}

/** Ghế chờ dài (bến xe). */
export function bench(): THREE.Group {
  const g = new THREE.Group();
  const seat = at(rounded(2.4, 0.1, 0.55, 0.04, soft(0x1e6fd9, 0.4)), 0, 0.5, 0);
  const back = at(rounded(2.4, 0.5, 0.08, 0.04, soft(0x1e6fd9, 0.4)), 0, 0.8, -0.25);
  seat.castShadow = true;
  g.add(seat, back);
  for (const x of [-1, 1]) {
    const leg = at(new THREE.Mesh(GEO.box, soft(0x7d8590, 0.4, 0.6)), x, 0.25, 0);
    leg.scale.set(0.06, 0.5, 0.5);
    g.add(leg);
  }
  return g;
}

// ---- hơi nước / khói --------------------------------------------------------------------

const PUFF = (() => {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,0.7)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();

/** Hơi bốc lên từ nồi phở / nồi bánh chưng: các hạt mờ dâng lên rồi tan. */
export class Steam {
  points: THREE.Points;
  private age: Float32Array;

  constructor(private origin: THREE.Vector3, private n = 18, private height = 2.4) {
    const pos = new Float32Array(n * 3);
    this.age = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      this.age[i] = i / n;
      pos.set([origin.x, origin.y, origin.z], i * 3);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.points = new THREE.Points(geo, new THREE.PointsMaterial({ size: 1.1, map: PUFF, transparent: true,
      depthWrite: false, opacity: 0.55 }));
  }

  update(dt: number, t: number): void {
    const attr = this.points.geometry.getAttribute("position") as THREE.BufferAttribute;
    const a = attr.array as Float32Array;
    for (let i = 0; i < this.n; i++) {
      this.age[i] = (this.age[i] + dt * 0.35) % 1;
      const k = this.age[i];
      a[i * 3] = this.origin.x + Math.sin(t * 1.5 + i) * 0.25 * k;
      a[i * 3 + 1] = this.origin.y + k * this.height;
      a[i * 3 + 2] = this.origin.z + Math.cos(t + i) * 0.15 * k;
    }
    attr.needsUpdate = true;
  }
}
