// Đường đi (PLAN-121 V3): quốc lộ nông thôn — nhựa có vá, nứt, ổ gà; lề sỏi; trụ điện bê tông dây võng chằng chịt;
// cột cây số ghi điểm tới. Không biết gì về xe: scene đưa vị trí bánh xe vào, đường trả về bánh nào vừa sập ổ gà.

import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { at, type Bump, GEO, makePerson, post, rounded, slab, soft, type WheelSpot } from "./art";
import { strip } from "./bend";
import { blossomPot, DAO, flag, MAI } from "./tet";

/** Vật cuộn trong dải x ∈ [-WRAP, WRAP) rồi quay vòng — đủ rộng để mép quay vòng nằm ngoài khung hình. */
export const WRAP = 80;
const ROAD_HALF = 4;
const POLE_GAP = 16; // 160 / 16 = 10 trụ, dây trụ cuối nối khớp trụ đầu khi quay vòng
const POLE_Z = -6.8; // Đặt lùi vào lề trong (z = -6.8) để trụ và đường dây điện không cắt ngang mặt xe ở góc chéo/cận

/** Băng chuyền: các vật trôi ngược chiều xe chạy (nhân `parallax`) và quay vòng trong dải [-span, span). */
export class Conveyor {
  readonly items: THREE.Object3D[] = [];

  constructor(private parallax = 1, private span = WRAP) {}

  add<T extends THREE.Object3D>(obj: T): T {
    this.items.push(obj);
    return obj;
  }

  advance(dx: number): void {
    const d = dx * this.parallax;
    for (const o of this.items) {
      o.position.x -= d;
      if (o.position.x < -this.span) o.position.x += this.span * 2;
    }
  }
}

// ---- mặt đường: nhựa + vạch kẻ vẽ chung một texture, trôi bằng offset (không tốn khối vạch riêng) ----

const TILE = 10; // một ô texture = 10 đơn vị dọc đường: vạch giữa 4, khoảng trống 6

function roadTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 512;
  const g = c.getContext("2d")!;
  const img = g.createImageData(512, 512);
  const zToY = (z: number) => ((ROAD_HALF - z) / (ROAD_HALF * 2)) * 512;

  for (let y = 0; y < 512; y++) {
    // Vệt bánh xe mòn bóng nhẹ ở hai làn đường (y quanh 175 và 335)
    const d1 = Math.min(Math.abs(y - 165), Math.abs(y - 215));
    const d2 = Math.min(Math.abs(y - 295), Math.abs(y - 345));
    const track = Math.exp(-(Math.min(d1, d2) ** 2) / 320);
    const edgeDirt = Math.max(0, 1 - Math.min(y, 511 - y) / 42);
    for (let x = 0; x < 512; x++) {
      const i = (y * 512 + x) * 4;
      const grain = (Math.random() - 0.5) * 20;
      const base = 70 - track * 10 + grain;
      const r = Math.round(base + edgeDirt * 28);
      const gr = Math.round(base + edgeDirt * 18);
      const b = Math.round(base + 4 - edgeDirt * 8);
      img.data.set([r, gr, b, 255], i);
    }
  }
  g.putImageData(img, 0, 0);

  // Vạch mép đường trắng phản quang + vạch tim đường vàng đứt nét chuẩn quốc lộ Việt Nam
  g.fillStyle = "#f2efe6";
  for (const z of [3.65, -3.65]) g.fillRect(0, zToY(z) - 6, 512, 12);
  g.fillStyle = "#f5bd33";
  g.fillRect(24, zToY(0) - 6, 512 * 0.44, 12);

  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.repeat.set(700 / TILE, 1);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function gravelTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#9c8466";
  g.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 500; i++) {
    const v = 110 + Math.random() * 90;
    g.fillStyle = `rgb(${v},${v * 0.88},${v * 0.72})`;
    g.fillRect(Math.random() * 128, Math.random() * 128, 2 + Math.random() * 3, 2 + Math.random() * 3);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(700 / 4, 1);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Mép răng cưa: vá nhựa, ổ gà trông «vỡ» thay vì tròn trịa. */
function jagged(radius: number, points = 12, rough = 0.28): THREE.ShapeGeometry {
  const shape = new THREE.Shape();
  for (let i = 0; i <= points; i++) {
    const a = (i / points) * Math.PI * 2;
    const r = radius * (1 - rough / 2 + Math.random() * rough);
    const [x, y] = [Math.cos(a) * r * 1.4, Math.sin(a) * r];
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  const geo = new THREE.ShapeGeometry(shape);
  geo.rotateX(-Math.PI / 2);
  return geo;
}

// ---- cột cây số ----------------------------------------------------------------------------

/** Cột cây số trắng đỉnh đỏ: tên điểm tới + số km (vẽ lại khi đổi). */
class Milestone {
  group = new THREE.Group();
  private canvas = document.createElement("canvas");
  private texture: THREE.CanvasTexture;
  private text = "";

  constructor() {
    this.canvas.width = 256;
    this.canvas.height = 320;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    const body = at(rounded(0.9, 1.1, 0.3, 0.06, soft(0xf4f1ea, 0.7)), 0, 0.55, 0);
    const cap = at(new THREE.Mesh(GEO.cylSmooth, soft(0xc62828, 0.6)), 0, 1.1, 0);
    cap.scale.set(0.45, 0.3, 0.15);
    cap.rotation.x = Math.PI / 2;
    const face = at(new THREE.Mesh(new THREE.PlaneGeometry(0.86, 1.3), new THREE.MeshBasicMaterial({ map: this.texture })), 0, 0.82, 0.16);
    this.group.add(body, cap, face);
    this.set("QL1A", "");
  }

  set(name: string, km: string): void {
    const text = `${name}|${km}`;
    if (text === this.text) return;
    this.text = text;
    const g = this.canvas.getContext("2d")!;
    g.fillStyle = "#c62828";
    g.fillRect(0, 0, 256, 120);
    g.fillStyle = "#f4f1ea";
    g.fillRect(0, 120, 256, 200);
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = "#fff";
    g.font = "800 44px 'Be Vietnam Pro', sans-serif";
    g.fillText(name.toUpperCase(), 128, 64, 236);
    g.fillStyle = "#1b1b1b";
    g.font = "800 96px 'Be Vietnam Pro', sans-serif";
    g.fillText(km, 128, 220, 236);
    this.texture.needsUpdate = true;
  }
}

// ---- biển chỉ dẫn quốc lộ (PLAN-140) -----------------------------------------------------------------
// Biển chỉ dẫn trên quốc lộ VN nền xanh dương, chữ trắng, viền trắng; biển địa giới «TỈNH …» cũng nền xanh dương. Canvas chỉ vẽ
// lại khi chữ đổi (lúc biển quay vòng ra phía trước / lúc xe vào tỉnh mới) — không tải lại ảnh lên GPU mỗi khung.

const SIGN_BLUE = "#1452a6";
const SIGN_FRESH_X = 30;
const SIGN_POST = soft(0x9aa3ad, 0.4, 0.6);
const SIGN_BACK = soft(0x8c939b, 0.5, 0.5);

/** Bảng xanh hai cột: mặt chữ canvas (`draw` vẽ), lưng xám, đặt bên kia đường nhìn về phía camera. */
class BlueBoard {
  group = new THREE.Group();
  readonly canvas = document.createElement("canvas");
  private texture: THREE.CanvasTexture;
  private drawn = "";

  constructor(w: number, h: number, height: number, private draw: (g: CanvasRenderingContext2D, text: string[]) => void) {
    this.canvas.width = 512;
    this.canvas.height = Math.round(512 * (h / w));
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.anisotropy = 4;
    const face = at(new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: this.texture })), 0, height, 0.06);
    const back = at(slab(w + 0.08, h + 0.08, 0.1, SIGN_BACK), 0, height, 0);
    this.group.add(face, back);
    for (const x of [-w * 0.32, w * 0.32]) this.group.add(at(post(0.07, height, SIGN_POST), x, height / 2, -0.08));
  }

  set(text: string[]): void {
    const key = text.join("|");
    if (key === this.drawn) return;
    this.drawn = key;
    const g = this.canvas.getContext("2d")!;
    const { width: w, height: h } = this.canvas;
    g.fillStyle = SIGN_BLUE;
    g.fillRect(0, 0, w, h);
    g.strokeStyle = "#fff";
    g.lineWidth = 10;
    g.strokeRect(14, 14, w - 28, h - 28);
    g.fillStyle = "#fff";
    this.draw(g, text);
    this.texture.needsUpdate = true;
  }
}

/** Co chữ cho vừa bề ngang. */
function fit(g: CanvasRenderingContext2D, text: string, size: number, max: number, weight = 800): void {
  do {
    g.font = `${weight} ${size}px 'Be Vietnam Pro', sans-serif`;
    size -= 2;
  } while (g.measureText(text).width > max && size > 10);
}

/** Biển chỉ đường: tối đa 3 dòng «Nghệ An ··· 120 km» — các điểm xe sắp tới, km thật trên bảng chặng. */
function directionSign(): BlueBoard {
  return new BlueBoard(4.8, 2.7, 3.3, (g, rows) => {
    const { width: w, height: h } = g.canvas;
    const lines = rows.length ? rows : ["QL1A|"];
    const step = (h - 60) / 3;
    lines.slice(0, 3).forEach((row, i) => {
      const [name, km] = row.split("|");
      const y = 30 + step * (i + 0.5);
      g.textBaseline = "middle";
      g.textAlign = "right";
      fit(g, km, 52, 150, 700);
      g.fillText(km, w - 40, y);
      g.textAlign = "left";
      fit(g, name, 58, w - 230);
      g.fillText(name, 40, y);
    });
  });
}

/** Biển địa giới: «TỈNH NGHỆ AN» / «THÀNH PHỐ ĐÀ NẴNG» + «Kính chào quý khách». */
function borderSign(): BlueBoard {
  return new BlueBoard(6.2, 2.3, 3.4, (g, [title]) => {
    const { width: w, height: h } = g.canvas;
    g.textAlign = "center";
    g.textBaseline = "middle";
    fit(g, title, 84, w - 70);
    g.fillText(title, w / 2, h * 0.42);
    fit(g, "Kính chào quý khách", 40, w - 120, 600);
    g.fillText("Kính chào quý khách", w / 2, h * 0.75);
  });
}

const CITIES = new Set(["Hà Nội", "Hải Phòng", "Đà Nẵng", "Cần Thơ", "Huế"]);

/** Tên trên biển địa giới (tên 63 tỉnh cũ như cả game). */
export function borderTitle(place: string): string {
  if (place === "TP.HCM") return "TP. HỒ CHÍ MINH";
  return `${CITIES.has(place) ? "THÀNH PHỐ" : "TỈNH"} ${place.toUpperCase()}`;
}

// ---- cọc tiêu, biển tốc độ, xe máy chở mai / đào (PLAN-140) -------------------------------------------------------

/** Một hàng cọc tiêu trắng đầu đỏ dọc mép đường (khúc cua, đầu cầu): cả hàng một lượt vẽ (vẽ lặp + màu theo đỉnh). */
const STAKE_GEO = (() => {
  const paint = (g: THREE.BufferGeometry, hex: number) => {
    const c = new THREE.Color(hex);
    const n = g.attributes.position.count;
    const colors = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) colors.set([c.r, c.g, c.b], i * 3);
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return g;
  };
  const body = new THREE.BoxGeometry(0.16, 0.7, 0.16).translate(0, 0.35, 0);
  const band = new THREE.BoxGeometry(0.17, 0.18, 0.17).translate(0, 0.62, 0);
  for (const g of [body, band]) g.deleteAttribute("uv");
  return mergeGeometries([paint(body, 0xf4f1ea), paint(band, 0xc62828)])!;
})();
const STAKE_MAT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6 });

function stakeRow(count: number, gap: number): THREE.InstancedMesh {
  const row = new THREE.InstancedMesh(STAKE_GEO, STAKE_MAT, count);
  const m4 = new THREE.Matrix4();
  for (let i = 0; i < count; i++) row.setMatrixAt(i, m4.makeTranslation((i - (count - 1) / 2) * gap, 0, 0));
  row.computeBoundingSphere();
  return row;
}

/** Biển hạn chế tốc độ tròn viền đỏ (xe khách trên quốc lộ). */
function speedSign(limit: number): THREE.Group {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#c62828";
  g.beginPath();
  g.arc(64, 64, 62, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#fff";
  g.beginPath();
  g.arc(64, 64, 46, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#1b1b1b";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = "800 52px 'Be Vietnam Pro', sans-serif";
  g.fillText(String(limit), 64, 68);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sign = new THREE.Group();
  sign.add(at(new THREE.Mesh(new THREE.CircleGeometry(0.55, 24), new THREE.MeshBasicMaterial({ map: tex })), 0, 2.3, 0.05),
    at(post(0.05, 2.3, SIGN_POST), 0, 1.15, 0));
  return sign;
}

/** Xe máy chở chậu mai / đào về quê ăn Tết, chạy cùng chiều sát lề phía camera — xe khách vượt qua (làn ngược chiều nằm
 * sau thân xe khách, góc cận không thấy). Người lái nằm trong đám đông vẽ lặp. */
class Motorbike {
  group = new THREE.Group();
  readonly blossom: number;

  constructor(blossom: number, hue: number) {
    this.blossom = blossom;
    const red = soft(0xb71c1c, 0.4, 0.2);
    const tire = soft(0x1c1c1c, 0.9);
    this.group.add(at(rounded(1.5, 0.42, 0.34, 0.12, red), 0, 0.62, 0));  // thân xe (dài theo trục x)
    for (const x of [-0.62, 0.62]) {
      const wheel = at(new THREE.Mesh(GEO.cyl, tire), x, 0.32, 0);
      wheel.scale.set(0.32, 0.14, 0.32);
      wheel.rotation.x = Math.PI / 2;
      this.group.add(wheel);
    }
    const rider = makePerson(hue, undefined, false, 1.05);
    rider.rotation.y = Math.PI / 2;  // nhìn về hướng xe chạy (+x)
    this.group.add(at(rider, 0.05, 0.42, 0));
    const pot = blossomPot(blossom);  // chậu buộc sau yên
    pot.scale.setScalar(0.62);
    this.group.add(at(pot, -0.78, 0.82, 0));
    this.group.visible = false;
  }
}

// ---- trụ điện ------------------------------------------------------------------------------

const WIRE = soft(0x1f1f22, 0.6);

let poleStaticGeo: THREE.BufferGeometry | null = null;
let poleWireGeo: THREE.BufferGeometry | null = null;

/** Trụ bê tông + xà + sứ + đèn đường; gộp thân + xà + sứ + tay đèn thành 1 khối, dây điện thành 1 khối -> giảm 50 draw calls cho 10 trụ! */
function utilityPole(lampMat: THREE.Material): THREE.Group {
  if (!poleStaticGeo || !poleWireGeo) {
    const paint = (geo: THREE.BufferGeometry, hex: number) => {
      const g = geo.index ? geo.toNonIndexed() : geo.clone();
      for (const k of Object.keys(g.attributes)) if (k !== "position" && k !== "normal") g.deleteAttribute(k);
      const c = new THREE.Color(hex).convertSRGBToLinear();
      const n = g.attributes.position.count;
      const arr = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) arr.set([c.r, c.g, c.b], i * 3);
      g.setAttribute("color", new THREE.BufferAttribute(arr, 3));
      return g;
    };
    const statics: THREE.BufferGeometry[] = [
      paint(new THREE.CylinderGeometry(0.11, 0.21, 9.2, 8).translate(0, 4.6, 0), 0xb9b5ad),
      paint(new THREE.BoxGeometry(0.16, 0.16, 2.45).translate(0, 8.7, 0), 0x9e9a92),
      paint(new THREE.BoxGeometry(0.08, 0.08, 1.65).rotateX(-0.25).translate(0, 7.6, 0.8), 0x9e9a92),
    ];
    const tips: THREE.Vector3[] = [];
    for (const z of [-1.05, 0, 1.05]) {
      statics.push(paint(new THREE.CylinderGeometry(0.06, 0.06, 0.24, 8).translate(0, 8.9, z), 0xf2f2f2));
      tips.push(new THREE.Vector3(0, 9.0, z));
    }
    poleStaticGeo = mergeGeometries(statics)!;

    const wires: THREE.BufferGeometry[] = [];
    const span = (from: THREE.Vector3, sag: number, radius: number) => {
      const to = from.clone().add(new THREE.Vector3(POLE_GAP, 0, 0));
      const mid = from.clone().lerp(to, 0.5).add(new THREE.Vector3(0, -sag * 2, 0));
      wires.push(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(from, mid, to), 18, radius, 4));
    };
    for (const tip of tips) span(tip, 0.42, 0.022);
    span(new THREE.Vector3(0, 7.1, -0.25), 0.72, 0.045);
    span(new THREE.Vector3(0, 6.8, 0.2), 0.85, 0.038);
    const coil = new THREE.TorusGeometry(0.32, 0.045, 6, 14);
    coil.translate(0, 6.5, 0.25);
    wires.push(coil);
    poleWireGeo = mergeGeometries(wires)!;
  }

  const g = new THREE.Group();
  const bodyMesh = new THREE.Mesh(poleStaticGeo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.82 }));
  bodyMesh.castShadow = true;
  const wireMesh = new THREE.Mesh(poleWireGeo, WIRE);
  wireMesh.castShadow = true;
  const lamp = at(rounded(0.32, 0.12, 0.55, 0.05, lampMat), 0, 7.75, 1.6);
  const banner = at(flag(1.6), 0, 5.2, 0.12);
  banner.rotation.x = 0.55;
  g.add(bodyMesh, wireMesh, lamp, banner);
  return g;
}

// ---- đường -----------------------------------------------------------------------------------


interface Pothole { mesh: THREE.Object3D; z: number; radius: number }

export class Roadway {
  group = new THREE.Group();
  /** Đồ ven đường (trụ điện, cột cây số) — ẩn khi đang ở bến / trạm / đầu ngõ. */
  readonly roadside = new THREE.Group();
  private belt = new Conveyor();
  private roadTex = roadTexture();
  private gravelTex = gravelTexture();
  private roadMat: THREE.MeshStandardMaterial;
  private holeMat = soft(0x1c1a19, 0.95);
  private puddleMat = new THREE.MeshStandardMaterial({ color: 0x4a5a6a, roughness: 0.05, metalness: 0.4 });
  private lampMat = new THREE.MeshStandardMaterial({ color: 0xfff5d6, emissive: 0xffe08a, emissiveIntensity: 0, roughness: 0.3 });
  private potholes: Pothole[] = [];
  private holeInners: THREE.Mesh[] = [];
  private milestones: Milestone[] = [];
  private target = { name: "QL1A", km: "" };
  private directions: BlueBoard[] = [];
  private ahead: { name: string; km: number }[] = [];
  private kmPerUnit = 0;  // km xe chạy ứng với một đơn vị đường trôi (chuyến bị nén nên lớn) — đo từ odo thật
  private odo: number | null = null;
  private rolled = 0;
  private borders: BlueBoard[] = [borderSign(), borderSign()];  // hai tấm: tỉnh ngắn qua liền hai ranh vẫn không giật biển
  private bikes = [new Motorbike(MAI, 30), new Motorbike(DAO, 210)];
  private blossom = MAI;
  private bikeGap = 40;

  constructor() {
    this.roadMat = new THREE.MeshStandardMaterial({ map: this.roadTex, roughness: 0.92 });
    const road = new THREE.Mesh(strip(700, ROAD_HALF * 2), this.roadMat);
    road.rotation.x = -Math.PI / 2;
    road.position.y = 0.02;
    road.receiveShadow = true;
    this.group.add(road);
    const gravelMat = new THREE.MeshStandardMaterial({ map: this.gravelTex, roughness: 1 });
    for (const z of [ROAD_HALF + 0.8, -ROAD_HALF - 0.8]) {  // lề đất sỏi
      const shoulder = new THREE.Mesh(strip(700, 1.6), gravelMat);
      shoulder.rotation.x = -Math.PI / 2;
      shoulder.position.set(0, 0.015, z);
      shoulder.receiveShadow = true;
      this.group.add(shoulder);
    }
    this.buildSurfaceDamage();
    for (let x = -WRAP; x < WRAP; x += POLE_GAP) this.roadside.add(this.belt.add(at(utilityPole(this.lampMat), x, 0, POLE_Z)));
    for (let x = -WRAP + 6; x < WRAP; x += 40) {
      const m = new Milestone();
      this.milestones.push(m);
      this.roadside.add(this.belt.add(at(m.group, x, 0, -ROAD_HALF - 1.1)));
    }
    for (const x of [-WRAP + 28, 28]) {  // biển chỉ đường: hai tấm trên dải 160 đơn vị, lệch cột cây số
      const sign = directionSign();
      sign.set([]);
      this.directions.push(sign);
      this.roadside.add(this.belt.add(at(sign.group, x, 0, -ROAD_HALF - 2.4)));
    }
    // cọc tiêu hai bên mép đường + biển tốc độ, trôi theo băng chuyền
    for (const [x, z] of [[-60, -ROAD_HALF - 0.35], [-20, ROAD_HALF + 0.35], [52, -ROAD_HALF - 0.35]] as const) {
      this.roadside.add(this.belt.add(at(stakeRow(7, 1.6), x, 0, z)));
    }
    this.roadside.add(this.belt.add(at(speedSign(60), -10, 0, -ROAD_HALF - 0.9)));
    for (const bike of this.bikes) this.roadside.add(at(bike.group, -WRAP, 0, ROAD_HALF - 0.8));
    for (const sign of this.borders) {
      sign.group.visible = false;
      this.roadside.add(at(sign.group, -WRAP, 0, -ROAD_HALF - 2.8));
    }
    this.group.add(this.roadside);
  }

  /** Vá nhựa, vết nứt, ổ gà — gộp vá nhựa + vết nứt thành 2 khối tĩnh trên băng chuyền để giảm 21 draw calls. */
  private buildSurfaceDamage(): void {
    const patchesA: THREE.BufferGeometry[] = [];
    const patchesB: THREE.BufferGeometry[] = [];
    const patchXs = [-70, -52, -34, -18, 14, 28, 42, 56, 70];
    for (let i = 0; i < 9; i++) {
      const g = jagged(0.9 + (i % 3) * 0.35, 8, 0.15);
      g.scale(1.5, 1, 1);
      g.translate(patchXs[i], 0.023, ((i * 2.3) % 5) - 2.5);
      (i % 2 ? patchesA : patchesB).push(g);
    }
    const cracks: THREE.BufferGeometry[] = [];
    for (let i = 0; i < 14; i++) {
      const c = new THREE.BoxGeometry(1.2 + Math.random() * 2.2, 0.005, 0.05);
      c.rotateY((Math.random() - 0.5) * 1.6);
      c.translate(-WRAP + i * 11.4 + Math.random() * 4, 0.024, (Math.random() - 0.5) * 6.5);
      cracks.push(c);
    }
    const damageChunk = new THREE.Group();
    damageChunk.add(
      new THREE.Mesh(mergeGeometries(patchesA)!, soft(0x3f3f43, 0.95)),
      new THREE.Mesh(mergeGeometries(patchesB)!, soft(0x6a6863, 0.95)),
      new THREE.Mesh(mergeGeometries(cracks)!, soft(0x1e1e20, 1)),
    );
    this.group.add(this.belt.add(damageChunk));

    // ổ gà: nửa số nằm ngay vệt bánh xe (z ≈ ±1.18) để xe sập thật, còn lại rải khắp mặt đường.
    // Chừa trống đoạn x ∈ [-8, 12] ở mốc khởi hành để khi chụp ảnh tĩnh xe ở x = 0 không có ổ gà nằm đè ngay dưới bánh xe!
    const rimMat = soft(0x76716a, 0.95);
    const holeXs = [-72, -56, -41, -26, -13, 15, 29, 44, 58, 71];
    for (let i = 0; i < 10; i++) {
      const radius = 0.30 + (i % 3) * 0.10;
      const z = i % 2 ? (i % 4 === 1 ? 1.18 : -1.18) : ((i * 1.7) % 5) - 2.5;
      const hole = new THREE.Group();
      const inner = new THREE.Mesh(jagged(radius), this.holeMat);
      hole.add(at(new THREE.Mesh(jagged(radius * 1.25), rimMat), 0, 0.024, 0), at(inner, 0, 0.026, 0));
      this.holeInners.push(inner);
      this.potholes.push({ mesh: hole, z, radius });
      this.group.add(this.belt.add(at(hole, holeXs[i], 0, z)));
    }
  }

  /** Điểm tới hiện ra trên cột cây số (vẽ lại khi cột quay vòng ra sau để khỏi thấy chữ đổi giữa chừng). */
  setTarget(name: string, km: number): void {
    this.target = { name, km: `${Math.max(1, Math.round(km))}` };
  }

  /** Các điểm sắp tới (km còn lại tính từ xe) + odo xe lúc này; biển ghi km tính từ CHỖ BIỂN ĐỨNG như biển thật. */
  setAhead(rows: { name: string; km: number }[], odo: number): void {
    this.ahead = rows;
    if (this.odo !== null && odo >= this.odo && this.rolled > 1) {
      const ratio = (odo - this.odo) / this.rolled;
      this.kmPerUnit = this.kmPerUnit ? this.kmPerUnit * 0.7 + ratio * 0.3 : ratio;
    } else if (this.odo !== null && odo < this.odo) {
      this.kmPerUnit = 0;  // chuyến mới / đổi xe đang chiếu
    }
    if (this.odo === null || odo !== this.odo) {
      this.odo = odo;
      this.rolled = 0;
    }
  }

  private signRows(x: number): string[] {
    const rows: string[] = [];
    for (const { name, km } of this.ahead) {
      const left = Math.round(km - x * this.kmPerUnit);
      if (left >= 1) rows.push(`${name}|${left.toLocaleString("vi-VN")} km`);
      if (rows.length === 3) break;
    }
    return rows;
  }

  /** Xe vừa vào tỉnh mới: dựng biển địa giới ở phía trước (ngoài khung hình), trôi lại như mọi vật ven đường. */
  welcome(place: string): void {
    const sign = this.borders.find((b) => !b.group.visible)
      ?? this.borders.reduce((a, b) => (a.group.position.x < b.group.position.x ? a : b));
    sign.set([borderTitle(place)]);
    sign.group.position.x = WRAP - 4;
    sign.group.visible = true;
  }

  /** Hoa trên xe máy chở về quê: đào miền Bắc, mai nơi khác. */
  setBlossom(color: number): void {
    this.blossom = color;
  }

  /** Mưa: mặt đường sẫm + bóng, ổ gà đọng nước. */
  setWet(wet: boolean): void {
    this.roadMat.roughness = wet ? 0.35 : 0.92;
    this.roadMat.color.setHex(wet ? 0xb4b4bc : 0xffffff);
    for (const m of this.holeInners) m.material = wet ? this.puddleMat : this.holeMat;
  }

  setNight(night: boolean): void {
    this.lampMat.emissiveIntensity = night ? 2.4 : 0;
  }

  /**
   * Trôi quãng `dx`. Trả về các cú xóc: ổ gà vừa lọt qua dưới bánh xe nào (bánh trước / sau, bên nào, sâu cỡ nào).
   */
  advance(dx: number, wheels: WheelSpot[]): Bump[] {
    const before = this.potholes.map((p) => p.mesh.position.x);
    this.belt.advance(dx);
    this.rolled += dx;
    this.roadTex.offset.x += dx / TILE;
    this.gravelTex.offset.x += dx / 4;
    const bumps: Bump[] = [];
    this.potholes.forEach((p, i) => {
      const now = p.mesh.position.x;
      for (const w of wheels) {
        const crossed = before[i] >= w.x && now < w.x;
        if (crossed && Math.abs(p.z - w.z) < p.radius + 0.25) bumps.push({ axle: w.axle, side: Math.sign(w.z), depth: p.radius });
      }
    });
    for (const m of this.milestones) {
      if (m.group.position.x > WRAP - 10) m.set(this.target.name, this.target.km);  // vừa quay vòng ra cuối dải
    }
    // biển chỉ đường vẽ lại ngay trước khi lọt vào khung hình (x < SIGN_FRESH_X): chuyến dài bị nén, vẽ lúc quay vòng thì
    // tới lúc thấy xe đã qua tỉnh dòng đầu rồi; khung dọc 9:16 mọi góc máy chỉ thấy |x| < ~20
    for (const d of this.directions) {
      if (d.group.position.x > SIGN_FRESH_X) d.group.userData.fresh = false;
      else if (!d.group.userData.fresh) {
        d.group.userData.fresh = true;
        d.set(this.signRows(d.group.position.x));
      }
    }
    for (const b of this.borders) {
      if (!b.group.visible) continue;
      b.group.position.x -= dx;
      if (b.group.position.x < -WRAP) b.group.visible = false;
    }
    // xe máy cùng chiều, chậm hơn xe khách: cứ 120–220 đơn vị đường một chiếc, hiện phía trước rồi bị vượt, lùi dần ra sau
    for (const bike of this.bikes) {
      if (!bike.group.visible) continue;
      bike.group.position.x -= dx * 0.3;  // ~4 đơn vị / giây so với xe khách: trong khung ~7 giây
      if (bike.group.position.x < -WRAP) bike.group.visible = false;
    }
    this.bikeGap -= dx;
    if (this.bikeGap <= 0) {
      this.bikeGap = 120 + Math.random() * 100;
      const bike = this.bikes.find((b) => b.blossom === this.blossom && !b.group.visible);
      if (bike) {
        bike.group.position.x = SIGN_FRESH_X + 10;  // ngay ngoài khung phía trước: hiện sau vài giây
        bike.group.visible = true;
      }
    }
    return bumps;
  }
}
