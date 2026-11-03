// Đồ vật dùng lại giữa các bối cảnh (PLAN-121 V2): cây, chậu quất, đèn lồng, ghế nhựa, bàn, ly trà, vali,
// bảng hiệu, mái ngói, hơi nước. Đồ lặp lại nhiều thì vẽ gộp (InstancedMesh) để nhẹ máy.

import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { at, blob, GEO, rounded, soft } from "./art";
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

const TREE_MAT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.78, flatShading: true });
const TREE_GEOS = new Map<TreeKind, THREE.BufferGeometry>();

function colorizeGeo(geo: THREE.BufferGeometry, hex: number): THREE.BufferGeometry {
  const g = geo.index ? geo.toNonIndexed() : geo.clone();
  for (const k of Object.keys(g.attributes)) if (k !== "position" && k !== "normal") g.deleteAttribute(k);
  const c = new THREE.Color(hex).convertSRGBToLinear();
  const n = g.attributes.position.count;
  const arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) arr.set([c.r, c.g, c.b], i * 3);
  g.setAttribute("color", new THREE.BufferAttribute(arr, 3));
  return g;
}

function getTreeGeo(kind: TreeKind): THREE.BufferGeometry {
  let geo = TREE_GEOS.get(kind);
  if (geo) return geo;
  const parts: THREE.BufferGeometry[] = [];
  if (kind === "pine") {
    // Cây thông / tùng nhiều tầng tán xếp lớp có chiều sâu
    const trunk = new THREE.CylinderGeometry(0.14, 0.24, 1.5, 7);
    trunk.translate(0, 0.75, 0);
    parts.push(colorizeGeo(trunk, 0x6b472a));
    const tiers = [
      { y: 1.9, r: 1.45, h: 1.7, c: 0x285830 },
      { y: 2.95, r: 1.15, h: 1.55, c: 0x326b3a },
      { y: 3.85, r: 0.82, h: 1.35, c: 0x3e7e44 },
    ];
    for (const t of tiers) {
      const cone = new THREE.ConeGeometry(t.r, t.h, 8);
      cone.translate(0, t.y, 0);
      parts.push(colorizeGeo(cone, t.c));
    }
  } else if (kind === "palm") {
    // Cây dừa miền Nam / miền Trung: thân đốt cong tự nhiên, chùm quả dừa + 7 tàu lá uốn cong
    const segs = 5;
    for (let s = 0; s < segs; s++) {
      const f = s / segs;
      const r0 = 0.21 * (1 - f * 0.35);
      const r1 = 0.21 * (1 - (f + 0.2) * 0.35);
      const seg = new THREE.CylinderGeometry(r1, r0, 0.98, 7);
      seg.rotateZ(-0.08 - f * 0.14);
      seg.translate(f * f * 0.52, 0.48 + s * 0.9, 0);
      parts.push(colorizeGeo(seg, s % 2 ? 0x856440 : 0x765636));
    }
    const topX = 0.42;
    const topY = 4.65;
    // Chùm dừa trên ngọn
    for (let c = 0; c < 3; c++) {
      const nut = new THREE.IcosahedronGeometry(0.18, 0);
      const a = (c / 3) * Math.PI * 2;
      nut.translate(topX + Math.cos(a) * 0.18, topY - 0.15, Math.sin(a) * 0.18);
      parts.push(colorizeGeo(nut, 0x6e8c28));
    }
    // 7 tàu lá dừa uốn vòm
    for (let i = 0; i < 7; i++) {
      const a = (i / 7) * Math.PI * 2;
      const mid = new THREE.BoxGeometry(1.45, 0.08, 0.46);
      mid.rotateZ(-0.22);
      mid.translate(0.72, 0.08, 0);
      mid.rotateY(a);
      mid.translate(topX, topY, 0);
      parts.push(colorizeGeo(mid, i % 2 ? 0x3b8538 : 0x499642));

      const tip = new THREE.BoxGeometry(1.25, 0.06, 0.34);
      tip.rotateZ(-0.62);
      tip.translate(1.85, -0.36, 0);
      tip.rotateY(a);
      tip.translate(topX, topY, 0);
      parts.push(colorizeGeo(tip, 0x52a148));
    }
  } else if (kind === "bush") {
    // Khóm cây bụi / rặng tre xanh nhiều cụm tròn
    const clusters: [number, number, number, number, number][] = [
      [0, 0.58, 0, 0.85, 0x2f6c34],
      [-0.55, 0.45, 0.25, 0.62, 0x3d7d3f],
      [0.58, 0.48, -0.2, 0.66, 0x4a8e48],
    ];
    for (const [x, y, z, r, col] of clusters) {
      const b = new THREE.IcosahedronGeometry(r, 1);
      b.scale(1.1, 0.82, 1.1);
      b.translate(x, y, z);
      parts.push(colorizeGeo(b, col));
    }
  } else {
    // Cây thân gỗ làng quê (bàng / đa / xoài): gốc vững, cành chạc chữ Y, 5 vòm lá nhiều sắc độ xanh ấm
    const trunk = new THREE.CylinderGeometry(0.18, 0.3, 1.75, 7);
    trunk.translate(0, 0.85, 0);
    parts.push(colorizeGeo(trunk, 0x68472b));
    for (const side of [-1, 1]) {
      const limb = new THREE.CylinderGeometry(0.09, 0.14, 1.1, 6);
      limb.rotateZ(side * 0.55);
      limb.translate(side * 0.35, 1.8, side * 0.12);
      parts.push(colorizeGeo(limb, 0x68472b));
    }
    const crowns: [number, number, number, number, number][] = [
      [0, 2.75, 0, 1.28, 0x3e7e38],
      [-0.85, 2.32, 0.35, 0.96, 0x4b8f42],
      [0.88, 2.4, -0.3, 1.02, 0x589e4b],
      [0.25, 3.25, 0.28, 0.92, 0x68ad52],
      [-0.3, 2.45, -0.65, 0.88, 0x366f31],
    ];
    for (const [x, y, z, r, col] of crowns) {
      const b = new THREE.IcosahedronGeometry(r, 1);
      b.scale(1.08, 0.86, 1.08);
      b.translate(x, y, z);
      parts.push(colorizeGeo(b, col));
    }
  }
  geo = mergeGeometries(parts)!;
  for (const p of parts) p.dispose();
  TREE_GEOS.set(kind, geo);
  return geo;
}

export function makeTree(kind: TreeKind): THREE.Group {
  const g = new THREE.Group();
  const mesh = new THREE.Mesh(getTreeGeo(kind), TREE_MAT);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  g.add(mesh, blob(kind === "bush" ? 1.9 : 2.8));
  return g;
}

const BLOSSOM_GEOS = new Map<number, THREE.BufferGeometry>();

/** Cây đào (hồng, miền Bắc) / mai (vàng): gốc + 5 cành uốn + tán hoa rực rỡ gộp 1 khối duy nhất (1 draw call thay vì 7). */
export function blossomTree(color: number): THREE.Group {
  let geo = BLOSSOM_GEOS.get(color);
  if (!geo) {
    const parts: THREE.BufferGeometry[] = [];
    const trunk = new THREE.CylinderGeometry(0.16, 0.28, 2.1, 7);
    trunk.translate(0, 1.05, 0);
    parts.push(colorizeGeo(trunk, 0x563620));
    const budColor = new THREE.Color(color).offsetHSL(0, 0.08, 0.08).getHex();
    for (let b = 0; b < 5; b++) {
      const angle = (b / 5) * Math.PI * 2;
      const branch = new THREE.CylinderGeometry(0.06, 0.11, 1.65, 6);
      branch.rotateX(Math.sin(angle) * 0.68);
      branch.rotateZ(-Math.cos(angle) * 0.68);
      branch.translate(Math.cos(angle) * 0.48, 2.45, Math.sin(angle) * 0.48);
      parts.push(colorizeGeo(branch, 0x563620));
      for (let k = 0; k < 6; k++) {
        const r = 0.55 + k * 0.24;
        const s = 0.34 + ((k * 7 + b) % 3) * 0.07;
        const fl = new THREE.IcosahedronGeometry(s, 1);
        fl.scale(1.12, 0.85, 1.12);
        fl.translate(
          Math.cos(angle + k * 0.38) * r,
          2.45 + k * 0.26,
          Math.sin(angle + k * 0.38) * r,
        );
        parts.push(colorizeGeo(fl, k % 2 === 0 ? color : budColor));
      }
    }
    const topCrown = new THREE.IcosahedronGeometry(0.58, 1);
    topCrown.scale(1.2, 0.8, 1.2);
    topCrown.translate(0, 3.55, 0);
    parts.push(colorizeGeo(topCrown, color));
    geo = mergeGeometries(parts)!;
    for (const p of parts) p.dispose();
    BLOSSOM_GEOS.set(color, geo);
  }
  const g = new THREE.Group();
  const mesh = new THREE.Mesh(geo, TREE_MAT);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  g.add(mesh, blob(3.1));
  return g;
}

/** Chậu quất ngày Tết: chậu đỏ viền vàng + tán tròn + quả cam lấm tấm — gộp thành 1 khối duy nhất (1 draw call). */
let kumquatGeo: THREE.BufferGeometry | null = null;
export function kumquatPot(): THREE.Group {
  if (!kumquatGeo) {
    const parts: THREE.BufferGeometry[] = [
      colorizeGeo(new THREE.CylinderGeometry(0.55, 0.42, 0.8, 12).translate(0, 0.4, 0), 0xa3301f),
      colorizeGeo(new THREE.CylinderGeometry(0.6, 0.6, 0.08, 12).translate(0, 0.8, 0), 0xf4c04e),
      colorizeGeo(new THREE.IcosahedronGeometry(0.85, 1).scale(1, 0.95, 1).translate(0, 1.55, 0), 0x2f6b2f),
    ];
    for (let i = 0; i < 16; i++) {
      const a = i * 2.4;
      const y = 1.18 + (i % 5) * 0.16;
      const fr = new THREE.IcosahedronGeometry(0.095, 0);
      fr.translate(Math.cos(a) * 0.82, y, Math.sin(a) * 0.82);
      parts.push(colorizeGeo(fr, 0xff9a1f));
    }
    kumquatGeo = mergeGeometries(parts)!;
    for (const p of parts) p.dispose();
  }
  const g = new THREE.Group();
  const mesh = new THREE.Mesh(kumquatGeo, TREE_MAT);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  g.add(mesh, blob(1.6));
  return g;
}

// ---- đèn lồng --------------------------------------------------------------------

let lanternGeo: THREE.BufferGeometry | null = null;
const LANTERN_MAT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.45, emissive: 0x3a0808 });

/** Một đèn lồng đỏ (gốc ở móc treo) — gộp vỏ đỏ + nắp vàng + tua rua thành 1 khối duy nhất (1 draw call thay vì 3). */
export function lantern(scale = 1): THREE.Group {
  if (!lanternGeo) {
    const shell = new THREE.SphereGeometry(0.3, 12, 8);
    shell.scale(1, 1.2, 1);
    shell.translate(0, -0.42, 0);
    const top = new THREE.CylinderGeometry(0.16, 0.16, 0.08, 10);
    top.translate(0, -0.08, 0);
    const bot = new THREE.CylinderGeometry(0.14, 0.14, 0.06, 10);
    bot.translate(0, -0.76, 0);
    const tassel = new THREE.CylinderGeometry(0.03, 0.04, 0.24, 6);
    tassel.translate(0, -0.9, 0);
    const parts = [
      colorizeGeo(shell, 0xd82828),
      colorizeGeo(top, 0xf4c04e),
      colorizeGeo(bot, 0xf4c04e),
      colorizeGeo(tassel, 0xf4c04e),
    ];
    lanternGeo = mergeGeometries(parts)!;
    for (const p of parts) p.dispose();
  }
  const l = new THREE.Group();
  l.add(new THREE.Mesh(lanternGeo, LANTERN_MAT));
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
