// Hình 3D (PLAN-121): low-poly bo tròn, ấm áp — xe khách, người chibi, trời, cánh hoa, texture chữ.
// Đồ đặc trưng Việt Nam dựng bằng code; chỉ dùng hình khối + texture vẽ bằng canvas, không tải mô hình ngoài.

import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// ---- vật liệu --------------------------------------------------------------

const flatCache = new Map<string, THREE.MeshStandardMaterial>();
const softCache = new Map<string, THREE.MeshStandardMaterial>();

/** Vật liệu mặt phẳng (cây, nhà, đồ ven đường) — kiểu low-poly. */
export function mat(color: number, emissive = 0): THREE.MeshStandardMaterial {
  const key = `${color}:${emissive}`;
  let m = flatCache.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({ color, roughness: 0.85, flatShading: true, emissive, emissiveIntensity: emissive ? 1 : 0 });
    flatCache.set(key, m);
  }
  return m;
}

/** Vật liệu mịn (xe, người) — bề mặt bo tròn trông «đồ chơi» thay vì khối thô. */
export function soft(color: number, roughness = 0.55, metalness = 0): THREE.MeshStandardMaterial {
  const key = `${color}:${roughness}:${metalness}`;
  let m = softCache.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({ color, roughness, metalness });
    softCache.set(key, m);
  }
  return m;
}

export const hueColor = (hue: number, l = 0.5) => new THREE.Color().setHSL(hue / 360, 0.6, l).getHex();

export const GEO = {
  box: new THREE.BoxGeometry(1, 1, 1),
  cone: new THREE.ConeGeometry(1, 1, 7),
  cyl: new THREE.CylinderGeometry(1, 1, 1, 8),
  cylSmooth: new THREE.CylinderGeometry(1, 1, 1, 20),
  ball: new THREE.IcosahedronGeometry(1, 0),
  sphere: new THREE.SphereGeometry(1, 16, 12),
  half: new THREE.SphereGeometry(1, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2),
  capsule: new THREE.CapsuleGeometry(1, 1, 4, 10),
  /** ba lô người đi Tết — dùng chung: người đi bộ tạo / xoá liên tục suốt buổi live */
  backpack: new RoundedBoxGeometry(0.36, 0.42, 0.18, 3, 0.06),
};

export function box(w: number, h: number, d: number, color: number, emissive = 0): THREE.Mesh {
  const m = new THREE.Mesh(GEO.box, mat(color, emissive));
  m.scale.set(w, h, d);
  return m;
}

/** Khối hộp kích thước w×h×d với vật liệu tuỳ ý (thanh, nẹp, xà). */
export function slab(w: number, h: number, d: number, material: THREE.Material): THREE.Mesh {
  const m = new THREE.Mesh(GEO.box, material);
  m.scale.set(w, h, d);
  return m;
}

/** Cột / cọc tròn bán kính r, cao h. */
export function post(r: number, h: number, material: THREE.Material): THREE.Mesh {
  const m = new THREE.Mesh(GEO.cyl, material);
  m.scale.set(r, h, r);
  return m;
}

export function rounded(w: number, h: number, d: number, radius: number, material: THREE.Material): THREE.Mesh {
  return new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, radius), material);
}

export function at<T extends THREE.Object3D>(obj: T, x: number, y: number, z: number): T {
  obj.position.set(x, y, z);
  return obj;
}

export function label(text: string, cls = "lbl"): CSS2DObject {
  const el = document.createElement("div");
  el.className = cls;
  el.textContent = text;
  return new CSS2DObject(el);
}

// ---- texture vẽ bằng canvas ---------------------------------------------------

/** Chữ vẽ lên texture (bảng LED, biển số, chữ trên thân xe) — nằm trong cảnh 3D, không phải nhãn HTML. */
function textTexture(text: string, opts: { w?: number; h?: number; bg?: string; fg?: string; font?: string;
  glow?: string; border?: string } = {}): THREE.CanvasTexture {
  const { w = 512, h = 128, bg = "transparent", fg = "#ffd23f", font = "800 72px 'Be Vietnam Pro', sans-serif",
    glow = "", border = "" } = opts;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d")!;
  if (bg !== "transparent") {
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);
  }
  if (border) {
    g.strokeStyle = border;
    g.lineWidth = 8;
    g.strokeRect(4, 4, w - 8, h - 8);
  }
  g.font = font;
  g.textAlign = "center";
  g.textBaseline = "middle";
  if (glow) {
    g.shadowColor = glow;
    g.shadowBlur = 18;
  }
  g.fillStyle = fg;
  g.fillText(text, w / 2, h / 2 + 4, w - 24);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Nhiễu nhẹ cho cỏ / nhựa đường — mặt đất bớt «phẳng lì». Nhân với màu vật liệu. */
export function noiseTexture(size = 128, low = 0.82, repeat = 40): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  const img = g.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const v = Math.round(255 * (low + Math.random() * (1 - low)));
    img.data.set([v, v, v, 255], i * 4);
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeat, repeat);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

const BLOB = (() => {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(0,0,0,0.45)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();
const BLOB_MAT = new THREE.MeshBasicMaterial({ map: BLOB, transparent: true, depthWrite: false });
const BLOB_GEO = new THREE.PlaneGeometry(1, 1);

/** Vệt tối dưới chân / bánh xe: vật «đứng» trên đất thay vì lơ lửng (rẻ hơn bóng đổ thật). */
export function blob(sx: number, sz = sx): THREE.Mesh {
  const m = new THREE.Mesh(BLOB_GEO, BLOB_MAT);
  m.rotation.x = -Math.PI / 2;
  m.scale.set(sx, sz, 1);
  m.position.y = 0.04;
  m.renderOrder = -1;
  return m;
}

// ---- bầu trời ---------------------------------------------------------------

/** Vòm trời chuyển màu từ đỉnh xuống chân trời; luôn đặt quanh camera đang dùng. */
export class SkyDome {
  mesh: THREE.Mesh;
  private uniforms = { top: { value: new THREE.Color() }, bottom: { value: new THREE.Color() } };

  constructor() {
    const material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: `varying vec3 vPos; void main() { vPos = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `uniform vec3 top; uniform vec3 bottom; varying vec3 vPos;
        void main() { float h = clamp(vPos.y * 1.6 + 0.05, 0.0, 1.0);
          gl_FragColor = vec4(mix(bottom, top, pow(h, 0.7)), 1.0); }`,
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
    });
    this.mesh = new THREE.Mesh(new THREE.SphereGeometry(450, 24, 12), material);
    this.mesh.renderOrder = -10;
  }

  set(top: number, bottom: number): void {
    this.uniforms.top.value.setHex(top);
    this.uniforms.bottom.value.setHex(bottom);
  }
}

// ---- người chibi ------------------------------------------------------------

/** Ngoài trời nhân vật to hơn để còn thấy rõ trên màn điện thoại; trong xe (đầu trên gối) giữ cỡ gốc. */
export const PERSON_SCALE = 1.35;
const PANTS = [0x3b4a6b, 0x4a3b32, 0x2f3b2f, 0x5a5a66];
// Phần đứng yên của một người (đầu, tóc, mắt, má, mũ, thân, ba lô) gộp thành MỘT khối tô màu theo đỉnh: trước đây 13–15 khối
// riêng = 13–15 lần vẽ (+ ~9 lần vẽ bóng) mỗi người, lúc thả 24 khách / bến đông là thêm vài trăm lần vẽ. Tay chân giữ riêng
// (đung đưa khi đi). Khối gộp dùng chung theo «kiểu người» (màu áo làm tròn 15°, mũ, ba lô) — có trần, không rò bộ nhớ dù
// người đi bộ tạo / xoá liên tục suốt buổi live.
const PERSON_MAT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.72 });
const SKIN = 0xf3c9a2;
const HAIR = 0x2b1d14;
const EYE = 0x1a1210;
const CHEEK = 0xf29a9a;
const STRAW = 0xe8cf8a;
const HUE_STEP = 15;
const personGeo = new Map<string, THREE.BufferGeometry>();
const _m4 = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _c = new THREE.Color();

/** Một mảnh của khối gộp: hình gốc dời / co tới chỗ, tô một màu. */
function piece(geo: THREE.BufferGeometry, color: number, pos: [number, number, number],
  scale: [number, number, number]): THREE.BufferGeometry {
  const g = (geo.index ? geo.toNonIndexed() : geo.clone());
  for (const name of Object.keys(g.attributes)) if (name !== "position" && name !== "normal") g.deleteAttribute(name);
  g.applyMatrix4(_m4.compose(new THREE.Vector3(...pos), _q, new THREE.Vector3(...scale)));
  _c.setHex(color).convertSRGBToLinear();
  const colors = new Float32Array(g.attributes.position.count * 3);
  for (let i = 0; i < colors.length; i += 3) colors.set([_c.r, _c.g, _c.b], i);
  g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return g;
}

/** Khối gộp phần đứng yên theo kiểu người (dựng một lần, dùng chung). */
function personBody(hue: number, headOnly: boolean): THREE.BufferGeometry {
  const tone = Math.round(hue / HUE_STEP) * HUE_STEP;
  const hat = hue % 4;  // mũ theo người (cố định theo màu áo): nón lá, mũ len, hoặc không
  const pack = !headOnly && hue % 3 === 0;  // người đi Tết: ba lô
  const key = `${tone}|${hat}|${pack}|${headOnly}`;
  let geo = personGeo.get(key);
  if (geo) return geo;
  const parts = [
    piece(GEO.sphere, SKIN, [0, 1.36, 0], [0.38, 0.38, 0.38]),
    piece(GEO.half, HAIR, [0, 1.4, -0.02], [0.4, 0.36, 0.4]),
  ];
  for (const x of [-0.13, 0.13]) {
    parts.push(piece(GEO.ball, EYE, [x, 1.37, 0.34], [0.045, 0.045, 0.045]),
      piece(GEO.ball, CHEEK, [x * 1.5, 1.27, 0.3], [0.06, 0.035, 0.03]));
  }
  if (hat === 1) parts.push(piece(GEO.cone, STRAW, [0, 1.78, 0], [0.62, 0.3, 0.62]));
  if (hat === 2) {
    parts.push(piece(GEO.half, hueColor((tone + 180) % 360, 0.45), [0, 1.5, 0], [0.41, 0.34, 0.41]),
      piece(GEO.ball, 0xffffff, [0, 1.86, 0], [0.09, 0.09, 0.09]));
  }
  if (!headOnly) {
    parts.push(piece(GEO.capsule, hueColor(tone, 0.52), [0, 0.72, 0], [0.27, 0.17, 0.22]));
    if (pack) parts.push(piece(GEO.backpack, hueColor((tone + 90) % 360, 0.4), [0, 0.78, -0.27], [1, 1, 1]));
  }
  geo = mergeGeometries(parts)!;
  for (const part of parts) part.dispose();
  personGeo.set(key, geo);
  return geo;
}

function limb(radius: number, length: number, material: THREE.Material, pivotY: number, x: number): THREE.Group {
  const pivot = new THREE.Group();
  const m = new THREE.Mesh(GEO.capsule, material);
  m.scale.set(radius, length / 2, radius);
  m.position.y = -length / 2 - radius * 0.3;
  pivot.add(m);
  pivot.position.set(x, pivotY, 0);
  return pivot;
}

interface Limbs { legL: THREE.Group; legR: THREE.Group; armL: THREE.Group; armR: THREE.Group }

/** Người chibi: đầu to, tay chân đung đưa khi đi; `headOnly` cho đầu trên gối trong xe. */
export function makePerson(hue: number, name?: string, vip = false, size = PERSON_SCALE, headOnly = false): THREE.Group {
  const g = new THREE.Group();
  g.scale.setScalar(size);
  const body = new THREE.Mesh(personBody(hue, headOnly), PERSON_MAT);
  g.add(body);
  if (headOnly) return noShadow(g);
  const shirt = soft(hueColor(Math.round(hue / HUE_STEP) * HUE_STEP, 0.52), 0.7);
  const pants = soft(PANTS[hue % PANTS.length], 0.8);
  const legL = limb(0.1, 0.32, pants, 0.5, -0.12);
  const legR = limb(0.1, 0.32, pants, 0.5, 0.12);
  const armL = limb(0.08, 0.32, shirt, 0.92, -0.33);
  const armR = limb(0.08, 0.32, shirt, 0.92, 0.33);
  g.add(legL, legR, armL, armR, blob(0.9));
  g.userData.limbs = { legL, legR, armL, armR } satisfies Limbs;
  if (name) g.add(at(label(name, vip ? "lbl vip" : "lbl"), 0, 2.3, 0));
  return noShadow(g);
}

/**
 * Người không đổ bóng thật (PLAN-133): đã có vệt bóng giả dưới chân (`blob`), bóng thật thêm 5 lần vẽ / người — trạm dừng
 * 40 người là 200 lần vẽ, tụt còn 22 khung/s trên máy anh. Đánh dấu để `shadowed()` của bối cảnh cũng bỏ qua.
 */
function noShadow(g: THREE.Group): THREE.Group {
  g.traverse((o) => { o.userData.noShadow = true; });
  return g;
}

/** Đi: chân tay vung ngược nhau; đứng: thả lỏng; vẫy: tay phải giơ lên lắc. */
export function animatePerson(g: THREE.Object3D, mode: "walk" | "idle" | "wave", phase: number): void {
  const l = g.userData.limbs as Limbs | undefined;
  if (!l) return;
  const swing = mode === "walk" ? Math.sin(phase) * 0.7 : 0;
  l.legL.rotation.x = swing;
  l.legR.rotation.x = -swing;
  l.armL.rotation.x = -swing * 0.8;
  l.armR.rotation.x = swing * 0.8;
  if (mode === "wave") {
    l.armR.rotation.x = 0;
    l.armR.rotation.z = 2.6 + Math.sin(phase * 1.6) * 0.35;
  } else {
    l.armR.rotation.z = 0;
  }
}

// ---- xe khách giường nằm --------------------------------------------------------

function ledTexture(text: string): THREE.CanvasTexture {
  return textTexture(text, { bg: "#120a06", fg: "#ffb02e", glow: "#ff8a00" });
}

/** Xe giường nằm 2 tầng: 24 giường = engine.SEATS (server), mỗi tầng 12 — một khung cửa sổ một giường. */
export const BERTHS = 24;
export const BERTHS_PER_FLOOR = BERTHS / 2;
const RED = soft(0xc62828, 0.45);
const CREAM = soft(0xfff3e0, 0.5);
const GLASS = soft(0x1d3048, 0.12, 0.6);
const RUBBER = soft(0x1c1c1e, 0.85);
const CHROME = soft(0xd8dde3, 0.25, 0.9);
const DARK = soft(0x2a2a2e, 0.6);

/** Ổ gà dưới bánh nào (đường trả về) — xem road.ts. */
/** Bánh xe (toạ độ trong xe) và cú xóc khi một bánh sập ổ gà — road.ts dò ổ gà theo bánh, xe nhận cú xóc. */
export interface WheelSpot { x: number; z: number; axle: "front" | "rear" }
export interface Bump { axle: "front" | "rear"; side: number; depth: number }

// Giảm xóc: lò xo + giảm chấn cho nảy (lên xuống), chúi (đầu xe lên xuống), lắc (nghiêng trái phải).
const SPRING = 70;
const DAMPING = 9;

export class Bus {
  group = new THREE.Group();
  body = new THREE.Group();
  /** Chỗ bánh chạm đất (x dọc xe, z ngang xe) — đưa cho đường để biết bánh nào sập ổ gà. */
  readonly wheelSpots = [
    { x: 4.0, z: 1.18, axle: "front" as const }, { x: 4.0, z: -1.18, axle: "front" as const },
    { x: -3.9, z: 1.18, axle: "rear" as const }, { x: -3.9, z: -1.18, axle: "rear" as const },
  ];
  private ride = { heave: 0, heaveV: 0, pitch: 0, pitchV: 0, roll: 0, rollV: 0 };
  private led: THREE.MeshBasicMaterial;
  private route = "";
  private leanRoll = 0;  // theo đường: nghiêng ra ngoài khi vào cua (dốc thì shader uốn đã nghiêng cả thân xe)
  /** Chỗ đứng ngay trước cửa lên xuống (phía bến) — người đi bộ ra / vào xe ở đây. */
  readonly doorSpot = new THREE.Vector3(4.6, 0, -1.7);
  wheels: THREE.Group[] = [];
  lights: THREE.MeshStandardMaterial;
  cabin: THREE.MeshStandardMaterial;
  banner: CSS2DObject;
  blossoms = new THREE.Group();
  windowSpots: THREE.Vector3[] = [];

  constructor() {
    const b = this.body;
    const shade = (m: THREE.Mesh) => { m.castShadow = true; m.receiveShadow = true; return m; };
    b.add(shade(at(rounded(12, 1.8, 2.6, 0.32, RED), 0, 1.5, 0)));  // thân dưới đỏ
    b.add(shade(at(rounded(11.9, 2.0, 2.56, 0.45, CREAM), 0, 3.3, 0)));  // thân trên kem
    b.add(at(box(12.06, 0.16, 2.64, 0xf4c04e), 0, 2.38, 0));  // chỉ vàng
    b.add(shade(at(rounded(10.6, 0.34, 2.2, 0.12, soft(0xe9e1d4, 0.6)), -0.3, 4.38, 0)));  // mui
    b.add(at(rounded(2.2, 0.36, 1.4, 0.1, soft(0xcfd6dd, 0.5)), -2.5, 4.68, 0));  // máy lạnh trên mui

    // kính 2 tầng + khung cửa sổ (instanced: 1 lần vẽ cho cả dãy)
    this.cabin = new THREE.MeshStandardMaterial({ color: 0x1d3048, roughness: 0.12, metalness: 0.6, emissive: 0xffc46b, emissiveIntensity: 0 });
    for (const y of [2.92, 3.86]) b.add(at(rounded(10.4, 0.72, 2.62, 0.12, this.cabin), -0.5, y, 0));
    const pillars = new THREE.InstancedMesh(GEO.box, CREAM, 13 * 2 * 2);
    const curtains = new THREE.InstancedMesh(GEO.box, soft(0xe8c88a, 0.9), 12 * 2 * 2);  // rèm kem, kéo xen kẽ
    const m4 = new THREE.Matrix4();
    let p = 0;
    let c = 0;
    for (const y of [2.92, 3.86]) {
      for (const z of [1.33, -1.33]) {
        for (let i = 0; i <= BERTHS_PER_FLOOR; i++) {
          m4.compose(new THREE.Vector3(-5.7 + i * 0.86, y, z), new THREE.Quaternion(), new THREE.Vector3(0.1, 0.76, 0.04));
          pillars.setMatrixAt(p++, m4);
          if (i < BERTHS_PER_FLOOR && (i + (y > 3 ? 1 : 0)) % 2 === 0) {
            m4.compose(new THREE.Vector3(-5.27 + i * 0.86, y + 0.1, z * 0.995), new THREE.Quaternion(), new THREE.Vector3(0.3, 0.6, 0.03));
            curtains.setMatrixAt(c++, m4);
          }
        }
      }
    }
    curtains.count = c;
    b.add(pillars, curtains);

    // mặt trước: kính lái, bảng LED, lưới tản nhiệt, đèn, biển số, gương
    b.add(at(rounded(0.12, 1.9, 2.3, 0.05, GLASS), 6.0, 3.25, 0));
    this.led = new THREE.MeshBasicMaterial({ map: ledTexture("VỀ QUÊ ĂN TẾT") });
    const led = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 0.42), this.led);
    led.rotation.y = Math.PI / 2;
    b.add(at(led, 6.08, 4.05, 0));
    b.add(at(rounded(0.1, 0.55, 1.6, 0.05, DARK), 6.02, 1.25, 0));
    this.lights = new THREE.MeshStandardMaterial({ color: 0xfff5d6, emissive: 0xfff2b0, emissiveIntensity: 0.4, roughness: 0.2 });
    for (const z of [0.95, -0.95]) b.add(at(rounded(0.12, 0.28, 0.45, 0.06, this.lights), 6.03, 1.35, z));
    const tail = soft(0xff2a2a, 0.3);
    for (const z of [1.05, -1.05]) b.add(at(rounded(0.1, 0.5, 0.22, 0.05, tail), -6.02, 1.5, z));
    const plate = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.24), new THREE.MeshBasicMaterial({
      map: textTexture("29B-TẾT.27", { w: 256, h: 72, bg: "#f5f5f5", fg: "#111", font: "800 44px sans-serif", border: "#111" }) }));
    plate.rotation.y = Math.PI / 2;
    b.add(at(plate, 6.08, 0.82, 0));
    for (const z of [1.45, -1.45]) {
      b.add(at(box(0.5, 0.06, 0.06, 0x2a2a2e), 5.9, 3.7, z));
      b.add(at(rounded(0.12, 0.5, 0.26, 0.05, DARK), 6.1, 3.45, z * 1.06));
    }
    // câu đối đỏ hai góc đầu xe
    for (const [z, text] of [[1.0, "PHÚC"], [-1.0, "LỘC"]] as const) {
      const p2 = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.7), new THREE.MeshBasicMaterial({
        map: textTexture(text, { w: 96, h: 200, bg: "#c62828", fg: "#ffd23f", font: "800 34px sans-serif", border: "#ffd23f" }) }));
      p2.rotation.y = Math.PI / 2;
      b.add(at(p2, 6.08, 2.55, z));
    }

    // chữ nhà xe sơn trên thân (cả 2 bên)
    const side = textTexture("XE TẾT SUM VẦY", { w: 1024, h: 160, fg: "#ffe7a8", font: "800 110px 'Be Vietnam Pro', sans-serif" });
    for (const z of [1.315, -1.315]) {
      const s = new THREE.Mesh(new THREE.PlaneGeometry(6.4, 1.0), new THREE.MeshBasicMaterial({ map: side, transparent: true }));
      if (z < 0) s.rotation.y = Math.PI;
      b.add(at(s, 0.3, 1.55, z));
    }
    b.add(at(box(0.9, 1.9, 0.05, 0x29486b), 4.6, 1.95, -1.33));  // cửa lên xuống (phía bến)

    // cành đào trên đầu xe
    const twig = soft(0x6b4226, 0.9);
    const petal = soft(0xff8fb1, 0.8);
    for (let i = 0; i < 4; i++) {
      const stick = at(new THREE.Mesh(GEO.cyl, twig), 5.0 + (i % 2) * 0.3, 4.75, -0.6 + i * 0.4);
      stick.scale.set(0.035, 0.6, 0.035);
      stick.rotation.z = -0.4 + i * 0.25;
      b.add(stick);
      for (let k = 0; k < 4; k++) {
        const f = at(new THREE.Mesh(GEO.sphere, petal), 5.0 + (i % 2) * 0.3 + Math.sin(k * 2 + i) * 0.25,
          4.9 + k * 0.12, -0.6 + i * 0.4 + Math.cos(k * 3) * 0.2);
        f.scale.setScalar(0.09);
        b.add(f);
      }
    }

    // băng rôn quà ≥ 100 xu: chữ HTML + thêm hoa
    this.banner = label("", "lbl banner");
    this.banner.position.set(-1, 0.75, 1.5);
    this.banner.visible = false;
    b.add(this.banner);
    for (let i = 0; i < 9; i++) {
      const bl = at(new THREE.Mesh(GEO.sphere, petal), -5 + i * 1.2, 4.62, (i % 2 ? 1 : -1) * 0.9);
      bl.scale.setScalar(0.18);
      this.blossoms.add(bl);
    }
    this.blossoms.visible = false;
    b.add(this.blossoms);
    this.group.add(b);

    // bánh xe: lốp + mâm + vòm; trục theo trục z
    for (const x of [-3.9, 4.0]) {
      for (const z of [1.18, -1.18]) {
        const arch = at(new THREE.Mesh(GEO.cylSmooth, DARK), x, 0.72, z * 1.03);
        arch.scale.set(0.78, 0.5, 0.78);
        arch.rotation.x = Math.PI / 2;
        b.add(arch);
        const wheel = new THREE.Group();
        const tire = new THREE.Mesh(GEO.cylSmooth, RUBBER);
        tire.scale.set(0.62, 0.42, 0.62);
        tire.castShadow = true;
        const rim = at(new THREE.Mesh(GEO.cyl, CHROME), 0, Math.sign(z) * 0.06, 0);
        rim.scale.set(0.36, 0.34, 0.36);
        const hub = at(new THREE.Mesh(GEO.box, DARK), 0, Math.sign(z) * 0.24, 0);
        hub.scale.set(0.5, 0.02, 0.08);  // nan mâm: thấy bánh đang quay
        wheel.add(tire, rim, hub);
        wheel.rotation.x = Math.PI / 2;
        this.wheels.push(at(wheel, x, 0.62, z));
        this.group.add(wheel);
      }
    }
    this.group.add(blob(14.5, 4.2));

    // vị trí cửa sổ cho bong bóng chat ở góc nhìn ngoài xe: mỗi tầng một hàng giường
    for (let i = 0; i < BERTHS; i++) {
      const col = i % BERTHS_PER_FLOOR;
      this.windowSpots.push(new THREE.Vector3(-5.27 + col * 0.86, i < BERTHS_PER_FLOOR ? 3.05 : 4.3, 1.4));
    }
  }

  /** Nghiêng theo cua (cộng thêm vào giảm xóc). */
  setLean(roll: number): void {
    this.leanRoll = roll;
  }

  /** Bảng LED đầu xe: tuyến thật, ví dụ «TP.HCM → HÀ NỘI». */
  setRoute(text: string): void {
    if (text === this.route) return;
    this.route = text;
    this.led.map?.dispose();
    this.led.map = ledTexture(text.toUpperCase());
  }

  setBanner(name: string | null): void {
    this.banner.visible = !!name;
    this.blossoms.visible = !!name;
    if (name) this.banner.element.textContent = `🧧 Xe Tết của ${name}`;
  }

  /** Sập ổ gà: bánh trước → đầu xe chúi xuống; bánh sau → đầu xe ngóc lên; bên nào sập thì nghiêng bên đó. */
  bump(b: Bump): void {
    const r = this.ride;
    r.heaveV -= b.depth * 2.6;
    r.pitchV += (b.axle === "front" ? -1 : 1) * b.depth * 0.75;
    r.rollV += b.side * b.depth * 0.55;
  }

  update(dt: number, speed: number, night: boolean): void {
    for (const w of this.wheels) w.rotation.y -= (speed * dt) / 0.62;
    const r = this.ride;
    if (speed > 0.5) {  // mặt đường gồ ghề: rung nhẹ liên tục, chạy càng nhanh càng rung
      const k = Math.min(1, speed / 30) * dt * 4;
      r.heaveV += (Math.random() - 0.5) * k;
      r.pitchV += (Math.random() - 0.5) * k * 0.12;
      r.rollV += (Math.random() - 0.5) * k * 0.1;
    }
    const h = Math.min(dt, 1 / 30);
    r.heaveV += (-SPRING * r.heave - DAMPING * r.heaveV) * h;
    r.pitchV += (-SPRING * r.pitch - DAMPING * r.pitchV) * h;
    r.rollV += (-SPRING * r.roll - DAMPING * r.rollV) * h;
    r.heave += r.heaveV * h;
    r.pitch += r.pitchV * h;
    r.roll += r.rollV * h;
    this.body.position.y = r.heave;
    this.body.rotation.z = r.pitch;
    this.body.rotation.x = r.roll + this.leanRoll;
    this.lights.emissiveIntensity = night ? 2.2 : 0.4;
    this.cabin.emissiveIntensity = night ? 0.35 : 0;  // đèn trong xe hắt ra cửa kính ban đêm
  }
}

// ---- cánh hoa đào / mai bay --------------------------------------------------

const PETAL_TEX = (() => {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  g.fillStyle = "#fff";
  g.beginPath();
  g.ellipse(16, 16, 13, 7, 0.6, 0, Math.PI * 2);
  g.fill();
  return new THREE.CanvasTexture(c);
})();

/** Cánh hoa rơi chậm, đung đưa theo gió — đào hồng miền Bắc, mai vàng nơi khác. */
export class Petals {
  points: THREE.Points;
  private speed: Float32Array;
  private n: number;
  private material: THREE.PointsMaterial;

  constructor(n = 220) {
    this.n = n;
    const pos = new Float32Array(n * 3);
    this.speed = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      pos.set([(Math.random() - 0.5) * 50, Math.random() * 30, -24 + Math.random() * 38], i * 3);
      this.speed[i] = 0.6 + Math.random() * 0.8;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.material = new THREE.PointsMaterial({ size: 1.0, map: PETAL_TEX, transparent: true, depthWrite: false,
      color: 0xff9fc0, alphaTest: 0.2 });
    this.points = new THREE.Points(geo, this.material);
  }

  setColor(hex: number): void {
    this.material.color.setHex(hex);
  }

  /** Chất lượng thấp: chỉ vẽ một phần số cánh hoa. */
  setDensity(fraction: number): void {
    this.points.geometry.setDrawRange(0, Math.floor(this.n * fraction));
  }

  update(dt: number, t: number, wind: number): void {
    const attr = this.points.geometry.getAttribute("position") as THREE.BufferAttribute;
    const a = attr.array as Float32Array;
    for (let i = 0; i < this.n; i++) {
      a[i * 3] += (Math.sin(t * 1.3 + i) * 0.6 - wind) * dt;
      a[i * 3 + 1] -= this.speed[i] * dt;
      a[i * 3 + 2] += Math.cos(t * 0.9 + i * 0.7) * 0.3 * dt;
      if (a[i * 3 + 1] < 0) {
        a[i * 3 + 1] = 28 + Math.random() * 4;
        a[i * 3] = (Math.random() - 0.5) * 50;
      }
      if (a[i * 3] < -25) a[i * 3] += 50;
    }
    attr.needsUpdate = true;
  }
}
