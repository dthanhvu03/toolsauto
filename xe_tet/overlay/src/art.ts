// Hình 3D (PLAN-121): low-poly bo tròn, ấm áp — xe khách, người chibi, trời, cánh hoa, texture chữ.
// Đồ đặc trưng Việt Nam dựng bằng code; chỉ dùng hình khối + texture vẽ bằng canvas, không tải mô hình ngoài.

import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { bendShader } from "./bend";
import { BLENDER_MODELS } from "./models";

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

/** Nhiễu organic 2D value-noise mượt (không dùng sóng sin/cos tuần hoàn để triệt tiêu hoàn toàn vệt sọc lặp trên mặt đất). */
export function noiseTexture(size = 256, low = 0.80, repeat = 28): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  const img = g.createImageData(size, size);
  // Tạo lưới hạt thô tuần hoàn 16x16 rồi nội suy bilinear + nhiễu hạt mịn để tạo mảng cỏ tự nhiên
  const grid = 16;
  const cells = new Float32Array(grid * grid);
  let seed = 1337;
  const nextRand = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let i = 0; i < cells.length; i++) cells[i] = nextRand();
  const sampleGrid = (gx: number, gy: number) => {
    const x0 = Math.floor(gx) % grid;
    const y0 = Math.floor(gy) % grid;
    const x1 = (x0 + 1) % grid;
    const y1 = (y0 + 1) % grid;
    const fx = gx - Math.floor(gx);
    const fy = gy - Math.floor(gy);
    const sx = fx * fx * (3 - 2 * fx);
    const sy = fy * fy * (3 - 2 * fy);
    const top = cells[y0 * grid + x0] * (1 - sx) + cells[y0 * grid + x1] * sx;
    const bot = cells[y1 * grid + x0] * (1 - sx) + cells[y1 * grid + x1] * sx;
    return top * (1 - sy) + bot * sy;
  };
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const n1 = sampleGrid((x / size) * grid, (y / size) * grid);
      const n2 = sampleGrid((x / size) * (grid * 2), (y / size) * (grid * 2)) * 0.5;
      const fine = (nextRand() - 0.5) * 0.08;
      const val = low + ((n1 + n2) / 1.5) * (1 - low) + fine;
      const v = Math.min(255, Math.max(150, Math.round(255 * val)));
      const warm = n1 > 0.58 ? 5 : 0;
      img.data.set([Math.min(255, v + warm), v, Math.max(0, v - warm)], (y * size + x) * 4);
    }
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeat, repeat);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
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

/** Vòm trời chuyển màu từ đỉnh xuống chân trời + vầng hào quang mặt trời chiều + dải mây ấm áp. */
export class SkyDome {
  mesh: THREE.Mesh;
  private uniforms = {
    top: { value: new THREE.Color() },
    bottom: { value: new THREE.Color() },
    sunDir: { value: new THREE.Vector3(0.45, 0.24, -0.86).normalize() },
  };

  constructor() {
    const material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: `varying vec3 vPos; void main() { vPos = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `uniform vec3 top; uniform vec3 bottom; uniform vec3 sunDir; varying vec3 vPos;
        void main() {
          float h = clamp(vPos.y * 1.55 + 0.06, 0.0, 1.0);
          vec3 col = mix(bottom, top, pow(h, 0.65));
          float horizonBand = exp(-abs(vPos.y - 0.03) * 14.0);
          col = mix(col, bottom * 1.12, horizonBand * 0.45);
          float s = max(0.0, dot(normalize(vPos), sunDir));
          col += bottom * pow(s, 6.0) * 0.35 + vec3(1.0, 0.94, 0.78) * pow(s, 48.0) * 0.55;
          gl_FragColor = vec4(col, 1.0);
        }`,
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
    });
    this.mesh = new THREE.Mesh(new THREE.SphereGeometry(450, 24, 16), material);
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

// ---- đám đông: mọi người đi bộ / đứng vẽ chung MỘT lượt (PLAN-139) -----------------------------------------------------
// Trước đây mỗi người = khối thân + 4 tay chân + vệt bóng = 6 lượt vẽ; trạm dừng 40 người ~240 lượt, tụt 22 khung/s. Giờ một
// khối người mẫu đủ mọi phần (cả nón lá, mũ len, ba lô), vẽ lặp (instancing) cho tất cả: màu áo / quần / mũ / ba lô và độ vung
// tay chân là số riêng từng người, shader tô màu, xoay tay chân quanh vai / hông, co phần người đó không có về 0. Vẫn là
// người 3D thật (camera nhìn từ trên cao vẫn đúng), cả đám đông 1 lượt vẽ + vệt bóng 1 lượt. `makePerson` trả về một nhóm
// rỗng làm «mỏ neo» (vị trí, nhãn tên, thùng quà đội đầu vẫn gắn vào nhóm như cũ); vào cảnh thì có mặt trong đám đông.
const CROWD_MAX = 160;  // tối đa 60 người đi bộ + người cảnh nền ở bến / cổng nhà
// aPart: 0 màu cố định (da, tóc, mắt, má, nón lá, quả bông), 1 thân áo, 2 mũ len, 3 ba lô, 4 / 5 chân trái / phải,
// 6 / 7 tay trái / phải. aOpt: 1 nón lá, 2 mũ len, 3 ba lô — người không có thì co về 0.
function tagged(g: THREE.BufferGeometry, part: number, opt = 0): THREE.BufferGeometry {
  const n = g.attributes.position.count;
  g.setAttribute("aPart", new THREE.BufferAttribute(new Float32Array(n).fill(part), 1));
  g.setAttribute("aOpt", new THREE.BufferAttribute(new Float32Array(n).fill(opt), 1));
  return g;
}

/** Tay / chân ở tư thế đứng thẳng (khớp ở vai / hông, shader xoay quanh khớp). */
function limbPiece(radius: number, length: number, pivotY: number, x: number, part: number): THREE.BufferGeometry {
  return tagged(piece(GEO.capsule, 0xffffff, [x, pivotY - length / 2 - radius * 0.3, 0], [radius, length / 2, radius]), part);
}

function crowdGeometry(): THREE.BufferGeometry {
  const parts = [
    tagged(piece(GEO.sphere, SKIN, [0, 1.36, 0], [0.38, 0.38, 0.38]), 0),
    tagged(piece(GEO.half, HAIR, [0, 1.4, -0.02], [0.4, 0.36, 0.4]), 0),
    tagged(piece(GEO.cone, STRAW, [0, 1.78, 0], [0.62, 0.3, 0.62]), 0, 1),
    tagged(piece(GEO.half, 0xffffff, [0, 1.5, 0], [0.41, 0.34, 0.41]), 2, 2),
    tagged(piece(GEO.ball, 0xffffff, [0, 1.86, 0], [0.09, 0.09, 0.09]), 0, 2),
    tagged(piece(GEO.capsule, 0xffffff, [0, 0.72, 0], [0.27, 0.17, 0.22]), 1),
    tagged(piece(GEO.backpack, 0xffffff, [0, 0.78, -0.27], [1, 1, 1]), 3, 3),
    limbPiece(0.1, 0.32, 0.5, -0.12, 4), limbPiece(0.1, 0.32, 0.5, 0.12, 5),
    limbPiece(0.08, 0.32, 0.92, -0.33, 6), limbPiece(0.08, 0.32, 0.92, 0.33, 7),
  ];
  for (const x of [-0.13, 0.13]) {
    parts.push(tagged(piece(GEO.ball, EYE, [x, 1.37, 0.34], [0.045, 0.045, 0.045]), 0),
      tagged(piece(GEO.ball, CHEEK, [x * 1.5, 1.27, 0.3], [0.06, 0.035, 0.03]), 0));
  }
  const geo = mergeGeometries(parts)!;
  for (const part of parts) part.dispose();
  return geo;
}

const CROWD_HEAD = /* glsl */ `
attribute float aPart;
attribute float aOpt;
attribute vec3 iShirt;
attribute vec3 iPants;
attribute vec3 iHat;
attribute vec3 iPack;
attribute vec4 iPose;  // x: độ vung tay chân, y: tay phải giơ lên vẫy, z: kiểu mũ (1 nón lá, 2 mũ len), w: có ba lô
`;
const CROWD_POSE = /* glsl */ `
int crowdPart = int(aPart + 0.5);
int crowdOpt = int(aOpt + 0.5);
float crowdKeep = 1.0;
if ((crowdOpt == 1 && iPose.z != 1.0) || (crowdOpt == 2 && iPose.z != 2.0) || (crowdOpt == 3 && iPose.w < 0.5)) crowdKeep = 0.0;
vec3 crowdTint = vec3(1.0);
if (crowdPart == 1 || crowdPart >= 6) crowdTint = iShirt;
else if (crowdPart == 2) crowdTint = iHat;
else if (crowdPart == 3) crowdTint = iPack;
else if (crowdPart >= 4) crowdTint = iPants;
mat3 crowdRot = mat3(1.0);
vec3 crowdPivot = vec3(0.0);
if (crowdPart >= 4) {
  float swing = crowdPart == 4 ? iPose.x : crowdPart == 5 ? -iPose.x : crowdPart == 6 ? -0.8 * iPose.x : 0.8 * iPose.x;
  float c = cos(swing), s = sin(swing);
  crowdRot = mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c);
  if (crowdPart == 7) {
    float cz = cos(iPose.y), sz = sin(iPose.y);
    crowdRot = crowdRot * mat3(cz, sz, 0.0, -sz, cz, 0.0, 0.0, 0.0, 1.0);
  }
  crowdPivot = crowdPart <= 5 ? vec3(crowdPart == 4 ? -0.12 : 0.12, 0.5, 0.0) : vec3(crowdPart == 6 ? -0.33 : 0.33, 0.92, 0.0);
}
#include <color_vertex>
vColor.rgb *= crowdTint;
`;

const CROWD_MAT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.72 });
CROWD_MAT.userData.bent = true;  // tự uốn trong onBeforeCompile; lượt quét bendTree bỏ qua
CROWD_MAT.onBeforeCompile = (shader) => {
  shader.vertexShader = CROWD_HEAD + shader.vertexShader
    .replace("#include <color_vertex>", CROWD_POSE)
    .replace("#include <beginnormal_vertex>", "#include <beginnormal_vertex>\nobjectNormal = crowdRot * objectNormal;")
    .replace("#include <begin_vertex>",
      "#include <begin_vertex>\ntransformed = crowdKeep * (crowdRot * (transformed - crowdPivot) + crowdPivot);");
  bendShader(shader);
};

interface Look { shirt: THREE.Color; pants: THREE.Color; hat: THREE.Color; pack: THREE.Color; hatType: number; backpack: number }
interface Pose { swing: number; wave: number }
const looks = new Map<number, Look>();

/** Màu / mũ / ba lô theo màu áo (như khối gộp cũ): tối đa 360 kiểu, dùng chung. */
function lookOf(hue: number): Look {
  let look = looks.get(hue);
  if (!look) {
    const tone = Math.round(hue / HUE_STEP) * HUE_STEP;
    look = {
      shirt: new THREE.Color(hueColor(tone, 0.52)), pants: new THREE.Color(PANTS[hue % PANTS.length]),
      hat: new THREE.Color(hueColor((tone + 180) % 360, 0.45)), pack: new THREE.Color(hueColor((tone + 90) % 360, 0.4)),
      hatType: hue % 4, backpack: hue % 3 === 0 ? 1 : 0,
    };
    looks.set(hue, look);
  }
  return look;
}

const BLOB_LOCAL = new THREE.Matrix4().compose(new THREE.Vector3(0, 0.04, 0),
  new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2), new THREE.Vector3(0.9, 0.9, 1));
const _blobM = new THREE.Matrix4();

/** Còn trong cảnh và không bị ẩn (bối cảnh khác đang tắt, người đã rời đi). */
function shown(o: THREE.Object3D, scene: THREE.Scene): boolean {
  for (let x: THREE.Object3D | null = o; x; x = x.parent) {
    if (!x.visible) return false;
    if (x === scene) return true;
  }
  return false;
}

class Crowd {
  readonly mesh: THREE.InstancedMesh;
  readonly blobs: THREE.InstancedMesh;
  readonly people = new Set<THREE.Object3D>();
  private shirt = new THREE.InstancedBufferAttribute(new Float32Array(CROWD_MAX * 3), 3);
  private pants = new THREE.InstancedBufferAttribute(new Float32Array(CROWD_MAX * 3), 3);
  private hat = new THREE.InstancedBufferAttribute(new Float32Array(CROWD_MAX * 3), 3);
  private pack = new THREE.InstancedBufferAttribute(new Float32Array(CROWD_MAX * 3), 3);
  private pose = new THREE.InstancedBufferAttribute(new Float32Array(CROWD_MAX * 4), 4);

  constructor() {
    const geo = crowdGeometry();
    geo.setAttribute("iShirt", this.shirt);
    geo.setAttribute("iPants", this.pants);
    geo.setAttribute("iHat", this.hat);
    geo.setAttribute("iPack", this.pack);
    geo.setAttribute("iPose", this.pose);
    this.mesh = new THREE.InstancedMesh(geo, CROWD_MAT, CROWD_MAX);
    this.blobs = new THREE.InstancedMesh(BLOB_GEO, BLOB_MAT, CROWD_MAX);
    this.blobs.renderOrder = -1;
    for (const m of [this.mesh, this.blobs]) {
      m.count = 0;
      m.frustumCulled = false;  // vị trí đổi mỗi khung, khỏi tính lại khối bao
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    }
  }

  /** Chép vị trí / màu / tư thế của mọi người đang hiện vào bản vẽ lặp (gọi sau updateMatrixWorld, trước khi vẽ). */
  sync(scene: THREE.Scene): void {
    let n = 0;
    for (const p of this.people) {
      if (n >= CROWD_MAX) break;
      if (!shown(p, scene)) continue;
      const look = p.userData.look as Look;
      const pose = p.userData.pose as Pose;
      this.mesh.setMatrixAt(n, p.matrixWorld);
      this.blobs.setMatrixAt(n, _blobM.multiplyMatrices(p.matrixWorld, BLOB_LOCAL));
      look.shirt.toArray(this.shirt.array, n * 3);
      look.pants.toArray(this.pants.array, n * 3);
      look.hat.toArray(this.hat.array, n * 3);
      look.pack.toArray(this.pack.array, n * 3);
      this.pose.setXYZW(n, pose.swing, pose.wave, look.hatType, look.backpack);
      n++;
    }
    this.mesh.count = this.blobs.count = n;
    for (const a of [this.mesh.instanceMatrix, this.blobs.instanceMatrix, this.shirt, this.pants, this.hat, this.pack, this.pose]) {
      a.clearUpdateRanges();
      a.addUpdateRange(0, n * a.itemSize);
      a.needsUpdate = true;
    }
  }
}

export const CROWD = new Crowd();

/** Người chibi: đầu to, tay chân đung đưa khi đi; `headOnly` cho đầu trên gối trong xe. */
export function makePerson(hue: number, name?: string, vip = false, size = PERSON_SCALE, headOnly = false): THREE.Group {
  const g = new THREE.Group();
  g.scale.setScalar(size);
  if (headOnly) {
    g.add(new THREE.Mesh(personBody(hue, headOnly), PERSON_MAT));
    return noShadow(g);
  }
  g.userData.look = lookOf(hue);
  g.userData.pose = { swing: 0, wave: 0 } satisfies Pose;
  g.addEventListener("added", () => CROWD.people.add(g));
  g.addEventListener("removed", () => CROWD.people.delete(g));
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
  const pose = g.userData.pose as Pose | undefined;
  if (!pose) return;
  pose.swing = mode === "walk" ? Math.sin(phase) * 0.7 : 0;
  pose.wave = mode === "wave" ? 2.6 + Math.sin(phase * 1.6) * 0.35 : 0;
}

// ---- xe khách giường nằm --------------------------------------------------------

function ledTexture(text: string): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#0a0706";
  g.fillRect(0, 0, 512, 128);
  // Nền ma trận điểm LED tối
  g.fillStyle = "#1d140e";
  for (let y = 8; y < 120; y += 8) {
    for (let x = 8; x < 504; x += 8) {
      g.fillRect(x, y, 4, 4);
    }
  }
  g.strokeStyle = "#3a322d";
  g.lineWidth = 6;
  g.strokeRect(3, 3, 506, 122);
  g.font = "800 64px 'Be Vietnam Pro', sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.shadowColor = "#ff7b00";
  g.shadowBlur = 16;
  g.fillStyle = "#ffc43d";
  g.fillText(text, 256, 66, 480);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Texture tem xe cao cấp + chữ XE TẾT SUM VẦY + hoa văn lượn sóng vàng kim. */
function sideLiveryTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 1024;
  c.height = 256;
  const g = c.getContext("2d")!;
  g.clearRect(0, 0, 1024, 256);

  // Dải lụa vàng kim chạy dọc hông xe
  const ribbonGrad = g.createLinearGradient(0, 0, 1024, 0);
  ribbonGrad.addColorStop(0, "rgba(255, 210, 63, 0.0)");
  ribbonGrad.addColorStop(0.12, "rgba(255, 215, 80, 0.95)");
  ribbonGrad.addColorStop(0.88, "rgba(255, 190, 45, 0.95)");
  ribbonGrad.addColorStop(1, "rgba(255, 210, 63, 0.0)");
  g.fillStyle = ribbonGrad;
  g.beginPath();
  g.moveTo(20, 36);
  g.bezierCurveTo(320, 10, 680, 56, 1004, 22);
  g.lineTo(1004, 44);
  g.bezierCurveTo(680, 78, 320, 32, 20, 58);
  g.closePath();
  g.fill();

  // Đường chỉ mảnh phía dưới
  g.fillStyle = "rgba(255, 232, 150, 0.75)";
  g.fillRect(60, 218, 904, 8);

  // Chữ chính XE TẾT SUM VẦY có viền nổi và bóng đổ
  g.font = "800 104px 'Be Vietnam Pro', sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.shadowColor = "rgba(60, 8, 8, 0.85)";
  g.shadowBlur = 10;
  g.shadowOffsetY = 5;
  g.strokeStyle = "#7a1111";
  g.lineWidth = 10;
  g.strokeText("XE TẾT SUM VẦY", 512, 128, 920);
  const textGrad = g.createLinearGradient(0, 75, 0, 180);
  textGrad.addColorStop(0, "#fffdf5");
  textGrad.addColorStop(0.55, "#ffe9a6");
  textGrad.addColorStop(1, "#f7c143");
  g.fillStyle = textGrad;
  g.fillText("XE TẾT SUM VẦY", 512, 128, 920);

  // Dòng chữ phụ nhỏ
  g.shadowBlur = 4;
  g.font = "700 30px 'Be Vietnam Pro', sans-serif";
  g.fillStyle = "#ffd97d";
  g.fillText("CHUYẾN XE ĐOÀN VIÊN · XUÂN ĐINH MÙI 2027", 512, 194, 860);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Kính cửa sổ giường nằm: có chiều sâu khoang giường ấm áp, thanh chắn an toàn, ánh phản chiếu chéo trên mặt kính. */
function sleeperGlassTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 128;
  const g = c.getContext("2d")!;
  const bg = g.createLinearGradient(0, 0, 0, 128);
  bg.addColorStop(0, "#0d1b2c");
  bg.addColorStop(0.55, "#19304a");
  bg.addColorStop(1, "#2a2422");
  g.fillStyle = bg;
  g.fillRect(0, 0, 512, 128);

  // Ánh đèn ngủ vàng ấm hắt nhẹ từ từng khoang giường
  for (let i = 0; i < 6; i++) {
    const cx = (i + 0.5) * (512 / 6);
    const glow = g.createRadialGradient(cx, 88, 4, cx, 88, 42);
    glow.addColorStop(0, "rgba(255, 198, 105, 0.42)");
    glow.addColorStop(1, "rgba(255, 198, 105, 0)");
    g.fillStyle = glow;
    g.fillRect(cx - 42, 20, 84, 96);
    // Nệm & gối mờ bên trong kính
    g.fillStyle = "rgba(215, 185, 150, 0.28)";
    g.fillRect(cx - 32, 92, 64, 18);
  }

  // Thanh inox bảo vệ ngang khoang giường nằm
  g.fillStyle = "rgba(210, 222, 235, 0.55)";
  g.fillRect(0, 82, 512, 5);
  g.fillRect(0, 96, 512, 3);

  // Vệt phản quang bầu trời chéo qua kính
  g.fillStyle = "rgba(255, 255, 255, 0.14)";
  for (let x = -60; x < 520; x += 110) {
    g.beginPath();
    g.moveTo(x, 128);
    g.lineTo(x + 48, 0);
    g.lineTo(x + 76, 0);
    g.lineTo(x + 28, 128);
    g.closePath();
    g.fill();
  }

  // Viền cao su đen bao quanh mép trên/dưới dải kính
  g.fillStyle = "#11151c";
  g.fillRect(0, 0, 512, 8);
  g.fillRect(0, 120, 512, 8);

  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.repeat.set(2, 1);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Xe giường nằm 2 tầng: 24 giường = engine.SEATS (server), mỗi tầng 12 — một khung cửa sổ một giường. */
export const BERTHS = 24;
export const BERTHS_PER_FLOOR = BERTHS / 2;
const RED = new THREE.MeshPhysicalMaterial({
  color: 0xc82323,
  roughness: 0.28,
  metalness: 0.08,
  clearcoat: 0.85,
  clearcoatRoughness: 0.14,
});
const MUD = new THREE.Color(0x7a6448);
const CREAM = new THREE.MeshPhysicalMaterial({
  color: 0xfff5e4,
  roughness: 0.32,
  metalness: 0.04,
  clearcoat: 0.65,
  clearcoatRoughness: 0.18,
});
const GOLD_TRIM = new THREE.MeshStandardMaterial({ color: 0xf5c249, roughness: 0.28, metalness: 0.65 });
const GLASS = new THREE.MeshPhysicalMaterial({
  color: 0x162b42,
  roughness: 0.08,
  metalness: 0.25,
  clearcoat: 1.0,
  clearcoatRoughness: 0.06,
  reflectivity: 0.9,
});
const RUBBER = soft(0x1b1c1f, 0.82);
const CHROME = soft(0xe2e7ec, 0.18, 0.92);
const DARK = soft(0x23252a, 0.52);

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
  // sơn riêng của xe (RED / CREAM dùng chung với biển hiệu…): xe bẩn ngả màu bùn mà không làm bẩn lây cả bến (PLAN-137)
  private red = RED.clone();
  private cream = CREAM.clone();
  private dirt = -1;

  constructor() {
    const b = this.body;
    const shade = (m: THREE.Mesh) => { m.castShadow = true; m.receiveShadow = true; return m; };

    if (BLENDER_MODELS.busCoach) {
      // Nạp khung thân xe khí động học dựng bằng Blender 4.0 (.glb) có hốc bánh xe khoét lõm thật, kính chắn gió 2 tầng, cửa lên xuống...
      const glbCoach = BLENDER_MODELS.busCoach.clone(true);
      glbCoach.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        m.castShadow = true;
        m.receiveShadow = true;
        const mname = (m.material as THREE.Material)?.name ?? "";
        if (mname.includes("BusRed")) m.material = this.red;
        else if (mname.includes("BusCream")) m.material = this.cream;
        else if (mname.includes("BusGold")) m.material = GOLD_TRIM;
        else if (mname.includes("BusChrome")) m.material = CHROME;
        else if (mname.includes("BusGlass")) m.material = GLASS;
        else if (mname.includes("BusDark")) m.material = DARK;
      });
      b.add(glbCoach);
    } else {
      // Bản Three.js Procedural đầy đủ chi tiết khi chạy ?glb=0 để so sánh công bằng với bản Blender GLB
      b.add(shade(at(rounded(12.04, 1.82, 2.56, 0.34, this.red), 0, 1.5, 0)));
      b.add(shade(at(rounded(11.92, 2.02, 2.54, 0.44, this.cream), 0, 3.32, 0)));
      const goldParts: THREE.BufferGeometry[] = [
        new THREE.BoxGeometry(12.08, 0.15, 2.60).translate(0, 2.38, 0),
        new THREE.BoxGeometry(9.2, 0.06, 2.58).translate(0.05, 0.68, 0),
        new THREE.BoxGeometry(0.14, 0.08, 2.48).translate(6.04, 1.05, 0),
      ];
      b.add(new THREE.Mesh(mergeGeometries(goldParts)!, GOLD_TRIM));
      const darkParts: THREE.BufferGeometry[] = [
        new THREE.BoxGeometry(11.5, 0.24, 2.44).translate(0, 0.56, 0),
        new THREE.BoxGeometry(0.28, 0.42, 2.58).translate(5.96, 0.76, 0),
        new THREE.BoxGeometry(0.26, 0.44, 2.56).translate(-5.96, 0.78, 0),
        new THREE.BoxGeometry(0.12, 0.52, 1.66).translate(6.02, 1.24, 0),
        new THREE.BoxGeometry(5.6, 0.035, 2.58).translate(0.08, 1.74, 0),
        new THREE.BoxGeometry(0.035, 1.02, 2.58).translate(-2.7, 1.22, 0),
        new THREE.BoxGeometry(0.035, 1.02, 2.58).translate(-0.85, 1.22, 0),
        new THREE.BoxGeometry(0.035, 1.02, 2.58).translate(1.0, 1.22, 0),
        new THREE.BoxGeometry(0.035, 1.02, 2.58).translate(2.85, 1.22, 0),
        new THREE.BoxGeometry(0.96, 0.045, 2.57).translate(-5.05, 1.54, 0),
        new THREE.BoxGeometry(0.96, 0.045, 2.57).translate(-5.05, 1.38, 0),
        new THREE.BoxGeometry(0.96, 0.045, 2.57).translate(-5.05, 1.22, 0),
        new THREE.BoxGeometry(0.06, 0.05, 0.94).rotateX(0.18).translate(6.06, 2.40, 0.48),
        new THREE.BoxGeometry(0.06, 0.05, 0.94).rotateX(0.18).translate(6.06, 2.40, -0.48),
        new THREE.BoxGeometry(0.68, 0.07, 0.07).translate(5.90, 3.74, 1.34),
        new THREE.BoxGeometry(0.68, 0.07, 0.07).translate(5.90, 3.74, -1.34),
        new THREE.BoxGeometry(0.10, 0.58, 0.28).translate(6.22, 3.44, 1.44),
        new THREE.BoxGeometry(0.10, 0.58, 0.28).translate(6.22, 3.44, -1.44),
      ];
      for (const x of [-3.9, 4.0]) {
        for (const z of [1.18, -1.18]) {
          const ag = new THREE.CylinderGeometry(0.76, 0.76, 0.48, 20, 1, false, -Math.PI / 2, Math.PI);
          ag.rotateX(Math.PI / 2);
          ag.translate(x, 0.64, z * 1.01);
          darkParts.push(ag);
        }
      }
      b.add(shade(new THREE.Mesh(mergeGeometries(darkParts)!, DARK)));
      const chromeParts: THREE.BufferGeometry[] = [
        new THREE.BoxGeometry(0.14, 0.04, 1.54).translate(6.04, 1.38, 0),
        new THREE.BoxGeometry(0.14, 0.04, 1.54).translate(6.04, 1.24, 0),
        new THREE.BoxGeometry(0.14, 0.04, 1.54).translate(6.04, 1.10, 0),
        new THREE.BoxGeometry(0.24, 0.06, 2.60).translate(-1.78, 1.58, 0),
        new THREE.BoxGeometry(0.24, 0.06, 2.60).translate(0.08, 1.58, 0),
        new THREE.BoxGeometry(0.24, 0.06, 2.60).translate(1.92, 1.58, 0),
      ];
      b.add(new THREE.Mesh(mergeGeometries(chromeParts)!, CHROME));
      b.add(shade(at(rounded(10.8, 0.34, 2.22, 0.14, soft(0xf2eadc, 0.45)), -0.2, 4.38, 0)));
      b.add(shade(at(rounded(1.5, 0.24, 2.1, 0.1, this.red), 5.05, 4.32, 0)));
      b.add(shade(at(rounded(0.65, 0.28, 2.34, 0.08, this.red), -5.55, 4.36, 0)));
      b.add(shade(at(rounded(2.6, 0.38, 1.55, 0.12, soft(0xd8dfe6, 0.38, 0.15)), -1.8, 4.64, 0)));
      const windShield = at(rounded(0.16, 1.94, 2.32, 0.06, GLASS), 5.99, 3.26, 0);
      windShield.rotation.z = 0.04;
      b.add(windShield);
      for (const side of [1, -1]) {
        b.add(at(rounded(0.92, 1.88, 0.06, 0.04, this.cream), 2.92, 1.68, side * 1.28));
        b.add(at(box(0.72, 1.12, 0.07, 0x162b42), 2.92, 1.92, side * 1.285));
      }
    }

    // Kính 2 tầng giường nằm có chiều sâu nội thất + phản quang + khung cửa sổ (instanced)
    const sleeperTex = sleeperGlassTexture();
    this.cabin = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      map: sleeperTex,
      roughness: 0.1,
      metalness: 0.35,
      emissive: 0xffb85c,
      emissiveMap: sleeperTex,
      emissiveIntensity: 0.28,
    });
    for (const y of [2.92, 3.86]) b.add(at(rounded(10.45, 0.74, 2.61, 0.1, this.cabin), -0.48, y, 0));
    const pillars = new THREE.InstancedMesh(GEO.box, this.cream, 13 * 2 * 2);
    const curtains = new THREE.InstancedMesh(GEO.box, soft(0xf2cf88, 0.75), 12 * 2 * 2);  // rèm lụa vàng kem
    const m4 = new THREE.Matrix4();
    let p = 0;
    let c = 0;
    for (const y of [2.92, 3.86]) {
      for (const z of [1.31, -1.31]) {
        for (let i = 0; i <= BERTHS_PER_FLOOR; i++) {
          m4.compose(new THREE.Vector3(-5.7 + i * 0.86, y, z), new THREE.Quaternion(), new THREE.Vector3(0.11, 0.76, 0.04));
          pillars.setMatrixAt(p++, m4);
          if (i < BERTHS_PER_FLOOR && (i + (y > 3 ? 1 : 0)) % 2 === 0) {
            m4.compose(new THREE.Vector3(-5.27 + i * 0.86, y + 0.08, z * 0.996), new THREE.Quaternion(), new THREE.Vector3(0.28, 0.58, 0.025));
            curtains.setMatrixAt(c++, m4);
          }
        }
      }
    }
    curtains.count = c;
    b.add(pillars, curtains);

    // Mặt trước: bảng LED điện tử, đèn pha kép, đèn sương mù, biển số
    this.led = new THREE.MeshBasicMaterial({ map: ledTexture("VỀ QUÊ ĂN TẾT") });
    const led = new THREE.Mesh(new THREE.PlaneGeometry(2.22, 0.42), this.led);
    led.rotation.y = Math.PI / 2;
    b.add(at(led, 6.12, 4.05, 0));

    this.lights = new THREE.MeshStandardMaterial({ color: 0xfff8e0, emissive: 0xffe89e, emissiveIntensity: 0.65, roughness: 0.15 });
    for (const z of [0.95, -0.95]) {
      b.add(at(rounded(0.12, 0.3, 0.48, 0.06, this.lights), 6.14, 1.35, z));
      b.add(at(rounded(0.1, 0.14, 0.26, 0.04, this.lights), 6.12, 0.82, z)); // đèn sương mù
    }
    const plate = new THREE.Mesh(new THREE.PlaneGeometry(0.92, 0.25), new THREE.MeshBasicMaterial({
      map: textTexture("29B-TẾT.27", { w: 256, h: 72, bg: "#f5f5f5", fg: "#111", font: "800 44px sans-serif", border: "#111" }) }));
    plate.rotation.y = Math.PI / 2;
    b.add(at(plate, 6.18, 0.82, 0));

    // Câu đối đỏ hai góc đầu xe
    for (const [z, text] of [[1.0, "PHÚC"], [-1.0, "LỘC"]] as const) {
      const p2 = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.7), new THREE.MeshBasicMaterial({
        map: textTexture(text, { w: 96, h: 200, bg: "#c62828", fg: "#ffd23f", font: "800 34px sans-serif", border: "#ffd23f" }) }));
      p2.rotation.y = Math.PI / 2;
      b.add(at(p2, 6.12, 2.55, z));
    }

    // Tem hông xe cao cấp + chữ XE TẾT SUM VẦY sơn 2 bên (đặt ở x = -0.35, z = ±1.312 tránh cửa lên xuống ở x = 2.92)
    const side = sideLiveryTexture();
    for (const z of [1.312, -1.312]) {
      const s = new THREE.Mesh(new THREE.PlaneGeometry(5.8, 1.15), new THREE.MeshBasicMaterial({ map: side, transparent: true, depthWrite: false }));
      if (z < 0) s.rotation.y = Math.PI;
      b.add(at(s, -0.45, 1.52, z));
    }

    // Cành đào / mai Tết rực rỡ trên nóc đầu xe — gộp thành 2 mesh (cành + hoa) thay vì 20 mesh rời để giảm 18 draw calls!
    const twig = soft(0x5c361e, 0.85);
    const petal = soft(0xff7aa8, 0.55);
    const branchGeos: THREE.BufferGeometry[] = [];
    const flowerGeos: THREE.BufferGeometry[] = [];
    for (let i = 0; i < 5; i++) {
      const bx = 5.05 + (i % 2) * 0.28;
      const bz = -0.68 + i * 0.34;
      const stickGeo = new THREE.CylinderGeometry(0.025, 0.045, 0.72, 6);
      stickGeo.rotateZ(-0.42 + i * 0.2);
      stickGeo.translate(bx, 4.78, bz);
      branchGeos.push(stickGeo);
      for (let k = 0; k < 6; k++) {
        const fg = new THREE.IcosahedronGeometry(0.095, 1);
        fg.translate(
          bx + Math.sin(k * 1.9 + i) * 0.24,
          4.86 + k * 0.11,
          bz + Math.cos(k * 2.5 + i) * 0.22,
        );
        flowerGeos.push(fg);
      }
    }
    b.add(new THREE.Mesh(mergeGeometries(branchGeos)!, twig));
    b.add(new THREE.Mesh(mergeGeometries(flowerGeos)!, petal));

    // băng rôn quà ≥ 100 xu: chữ HTML + thêm hoa
    this.banner = label("", "lbl banner");
    this.banner.position.set(-1, 0.75, 1.5);
    this.banner.visible = false;
    b.add(this.banner);
    const sponsorBlossoms: THREE.BufferGeometry[] = [];
    for (let i = 0; i < 9; i++) {
      const bl = new THREE.IcosahedronGeometry(0.18, 1);
      bl.translate(-5 + i * 1.2, 4.62, (i % 2 ? 1 : -1) * 0.9);
      sponsorBlossoms.push(bl);
    }
    this.blossoms.add(new THREE.Mesh(mergeGeometries(sponsorBlossoms)!, petal));
    this.blossoms.visible = false;
    b.add(this.blossoms);
    this.group.add(b);

    // Bánh xe khách đường dài: nạp model .glb từ Blender (mâm đúc 6 chấu + lốp Bevel, trục bánh xe đã nằm dọc trục Z của Three.js)
    const wheelRimGeo = (() => {
      const parts: THREE.BufferGeometry[] = [
        new THREE.CylinderGeometry(0.38, 0.38, 0.40, 16).rotateX(Math.PI / 2),
        new THREE.CylinderGeometry(0.14, 0.14, 0.46, 12).rotateX(Math.PI / 2),
      ];
      for (let k = 0; k < 6; k++) {
        const spoke = new THREE.BoxGeometry(0.64, 0.08, 0.42);
        spoke.rotateZ((k * Math.PI) / 3);
        parts.push(spoke);
      }
      return mergeGeometries(parts)!;
    })();
    const tireGeoZ = new THREE.CylinderGeometry(0.60, 0.60, 0.38, 24).rotateX(Math.PI / 2);
    for (const x of [-3.9, 4.0]) {
      for (const z of [1.18, -1.18]) {
        const wheel = new THREE.Group();
        if (BLENDER_MODELS.busWheel) {
          const glbW = BLENDER_MODELS.busWheel.clone(true);
          glbW.traverse((o) => {
            const m = o as THREE.Mesh;
            if (!m.isMesh) return;
            m.castShadow = true;
            const mname = (m.material as THREE.Material)?.name ?? "";
            if (mname.includes("TireRubber")) m.material = RUBBER;
            else if (mname.includes("AlloyRim")) m.material = CHROME;
            else if (mname.includes("HubDark")) m.material = DARK;
          });
          wheel.add(glbW);
        } else {
          const tire = new THREE.Mesh(tireGeoZ, RUBBER);
          tire.castShadow = true;
          const rim = new THREE.Mesh(wheelRimGeo, CHROME);
          wheel.add(tire, rim);
        }
        // Đặt z * 1.08 (= ±1.274) để mặt ngoài bánh xe (rộng 0.38 -> mặt ngoài ở ±1.464) nằm ngang mép vòm chắn bùn, lộ rõ mâm đúc 3D
        this.wheels.push(at(wheel, x, 0.62, z * 1.08));
        b.add(wheel);
      }
    }
    // Vệt bóng tiếp xúc dưới gầm xe (đặt ở y = 0.016 thấp hơn mặt đường y = 0.02 hoặc dùng polygonOffset để không cắt ngang đáy lốp xe!)
    const underShadow = blob(14.6, 4.2);
    underShadow.position.y = 0.022;
    (underShadow.material as THREE.Material).polygonOffset = true;
    (underShadow.material as THREE.Material).polygonOffsetFactor = -1;
    this.group.add(underShadow);

    // vị trí cửa sổ cho bong bóng chat ở góc nhìn ngoài xe: mỗi tầng một hàng giường
    for (let i = 0; i < BERTHS; i++) {
      const col = i % BERTHS_PER_FLOOR;
      this.windowSpots.push(new THREE.Vector3(-5.27 + col * 0.86, i < BERTHS_PER_FLOOR ? 3.05 : 4.3, 1.4));
    }
  }

  /** Độ bẩn 0 (sạch) → 1: thân xe ngả màu bùn (chạy mưa / đèo bẩn dần, người xem «rửa xe» ở bến cho sạch). */
  setDirt(dirt: number): void {
    const d = Math.round(Math.min(1, Math.max(0, dirt)) * 20) / 20;  // bước 5 %: khỏi đổi màu mỗi khung
    if (d === this.dirt) return;
    this.dirt = d;
    this.red.color.setHex(0xc62828).lerp(MUD, d * 0.7);
    this.cream.color.setHex(0xfff3e0).lerp(MUD, d * 0.75);
    this.red.roughness = this.cream.roughness = 0.45 + d * 0.45;
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
    for (const w of this.wheels) w.rotation.z -= (speed * dt) / 0.60;
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
    this.lights.emissiveIntensity = night ? 2.4 : 0.65;
    this.cabin.emissiveIntensity = night ? 0.55 : 0.22;  // khoang giường luôn có ánh đèn ấm dịu, đêm rực hơn
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
