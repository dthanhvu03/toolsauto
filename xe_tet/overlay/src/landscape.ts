// Cảnh hai bên đường theo vùng (PLAN-121 V3), ba lớp trôi khác tốc độ để có chiều sâu:
//   gần  (z -7…-14): nhà ống, tạp hoá, cây — ẩn khi đang ở bến / trạm / đầu ngõ (trùng chỗ bối cảnh)
//   giữa (z -21…-45 và phía camera z +8…+15): ruộng bậc thang / đồi cà phê / ruộng nước / cát + phi lao, cây
//   xa   (z -60…-150): núi nhiều tầng, biển + thuyền thúng — trôi rất chậm
// Mỗi vùng dựng một lần rồi giữ lại, đổi vùng chỉ gắn / gỡ khỏi cảnh: không dựng lại, không rò bộ nhớ GPU suốt buổi live.
// Vùng chưa tới được dựng sẵn lúc rảnh (`prebuild`, khi xe đang đón khách ở bến) — dựng giữa đường là khựng hình.
// Vùng không hiện thì gỡ hẳn khỏi cây cảnh (không chỉ ẩn): mỗi khung hình three / nhãn chữ khỏi duyệt hàng nghìn vật thừa.
// Ngày Tết (PLAN-129): nhà treo cờ + đèn lồng, chậu mai / đào trước hiên, băng rôn chúc Tết, mai vàng xen cây ven đường.

import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { at, blob, GEO, mat, noiseTexture, post, rounded, slab, soft } from "./art";
import { strip } from "./bend";
import { BLENDER_MODELS } from "./models";
import { blossomTree, kumquatPot, lantern, makeTree, plasticStools, SignBoard, tiledRoof } from "./props";
import { Conveyor, WRAP } from "./road";
import { blossomPot, chrysanthemumPot, DAO, flag, greetingBanner, MAI } from "./tet";
import type { Region } from "./types";

const GROUND: Record<Region, number> = { bac: 0x67944b, trung: 0x9aa65e, taynguyen: 0x9e5936, nam: 0x589847 };
const FAR_SPAN = 220;
const FACADES = [0xf6d36b, 0x8fd3c8, 0xf4a6a0, 0xb5d38a, 0xf7f1e3, 0x9fc3f0];
const REGIONS: Region[] = ["bac", "trung", "taynguyen", "nam"];

function paintGeo(geo: THREE.BufferGeometry, hex: number): THREE.BufferGeometry {
  const g = geo.index ? geo.toNonIndexed() : geo.clone();
  for (const k of Object.keys(g.attributes)) if (k !== "position" && k !== "normal") g.deleteAttribute(k);
  const c = new THREE.Color(hex).convertSRGBToLinear();
  const n = g.attributes.position.count;
  const arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) arr.set([c.r, c.g, c.b], i * 3);
  g.setAttribute("color", new THREE.BufferAttribute(arr, 3));
  return g;
}
const ARCH_MAT = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.78 });

function rand(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- nhà ven đường -------------------------------------------------------------------------

/** Nhà ống mặt tiền nhiều màu, ban công lan can, mái hiên tôn, bồn nước inox trên nóc — gộp khối kiến trúc để giảm draw calls. */
function tubeHouse(color: number, floors: number, windows: THREE.Material, shop: string | null, pot: THREE.Object3D | null): THREE.Group {
  const g = new THREE.Group();
  const h = floors * 2.2;
  const archParts: THREE.BufferGeometry[] = [
    paintGeo(new THREE.BoxGeometry(3.04, h, 4.0).translate(0, h / 2, 0), color),
    // Phào chỉ mái thượng + chân tường ốp đá
    paintGeo(new THREE.BoxGeometry(3.22, 0.22, 4.16).translate(0, h + 0.1, 0), 0xe9e2d6),
    paintGeo(new THREE.BoxGeometry(3.1, 0.35, 4.06).translate(0, 0.18, 0), 0x7a746c),
    // Cửa cuốn / cửa chính tầng trệt + mái hiên che nắng
    paintGeo(new THREE.BoxGeometry(2.1, 1.85, 0.08).translate(0, 0.95, 2.02), 0x455a64),
    paintGeo(new THREE.BoxGeometry(3.16, 0.08, 1.1).rotateX(0.18).translate(0, 2.12, 2.42), 0xb71c1c),
  ];
  const winParts: THREE.BufferGeometry[] = [];
  for (let f = 1; f < floors; f++) {
    winParts.push(new THREE.BoxGeometry(1.9, 1.15, 0.08).translate(0, 1.2 + f * 2.2, 2.02));
    // Ban công + tường lan can + thanh chắn
    archParts.push(
      paintGeo(new THREE.BoxGeometry(3.2, 0.12, 0.78).translate(0, f * 2.2, 2.34), 0xe9e2d6),
      paintGeo(new THREE.BoxGeometry(3.16, 0.55, 0.08).translate(0, f * 2.2 + 0.3, 2.68), color),
      paintGeo(new THREE.BoxGeometry(3.2, 0.06, 0.1).translate(0, f * 2.2 + 0.62, 2.68), 0xf4f1ea),
    );
  }
  const archMesh = new THREE.Mesh(mergeGeometries(archParts)!, ARCH_MAT);
  archMesh.castShadow = true;
  archMesh.receiveShadow = true;
  g.add(archMesh);
  if (winParts.length) g.add(new THREE.Mesh(mergeGeometries(winParts)!, windows));

  // Bồn nước inox Sơn Hà + chân đế trên sân thượng
  const tank = at(new THREE.Mesh(GEO.cylSmooth, soft(0xdfe4ea, 0.2, 0.92)), 0.6, h + 0.68, -0.8);
  tank.scale.set(0.45, 1.15, 0.45);
  tank.rotation.z = Math.PI / 2;
  g.add(tank);

  if (shop) g.add(at(new SignBoard(shop, 2.8, 0.55, { bg: "#1e6fd9", fg: "#ffffff", rim: "#ffd23f" }).mesh, 0, 2.45, 2.15));
  const pole = at(flag(1.5), 1.35, h - 0.8, 2.08);
  pole.rotation.x = 0.6;
  g.add(pole);
  for (const x of [-1.1, 1.1]) g.add(at(lantern(0.7), x, 2.05, 2.45));
  if (pot) g.add(at(pot, -1.15, 0, 2.75));
  g.add(blob(3.8, 4.6));
  return g;
}

/** Nhà ngói 3 gian truyền thống Việt Nam: ưu tiên nạp model Blender (.glb) mái ngói âm dương võng đầu đao + cột gỗ lim + cây rơm. */
function villageTileHouse(windows: THREE.Material, pot: THREE.Object3D | null): THREE.Group {
  const g = new THREE.Group();
  if (BLENDER_MODELS.villageHouse) {
    const glbHouse = BLENDER_MODELS.villageHouse.clone(true);
    glbHouse.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        m.castShadow = true;
        m.receiveShadow = true;
      }
    });
    g.add(glbHouse);
    const wins = mergeGeometries([
      new THREE.BoxGeometry(0.95, 0.95, 0.08).translate(-1.65, 1.62, 1.24),
      new THREE.BoxGeometry(0.95, 0.95, 0.08).translate(1.65, 1.62, 1.24),
    ])!;
    g.add(new THREE.Mesh(wins, windows));
    const pole = at(flag(1.5), 0.95, 1.38, 3.35);
    pole.rotation.x = 0.45;
    g.add(pole);
    for (const x of [-0.9, 0.9]) g.add(at(lantern(0.65), x, 2.35, 1.75));
    if (pot) g.add(at(pot, -1.6, 0.04, 2.45));
    g.add(at(chrysanthemumPot(), 1.5, 0.04, 2.55));
    g.add(blob(6.5, 5.4));
    return g;
  }
  const parts: THREE.BufferGeometry[] = [
    // Nền tam cấp & thân nhà 3 gian tường vàng ấm
    paintGeo(new THREE.BoxGeometry(5.6, 0.28, 4.2).translate(0, 0.14, 0), 0x8d8478),
    paintGeo(new THREE.BoxGeometry(5.2, 2.45, 3.4).translate(0, 1.36, -0.2), 0xf5d061),
    // Cửa gỗ 3 gian ở giữa + 4 cột hiên gỗ lim
    paintGeo(new THREE.BoxGeometry(1.55, 1.95, 0.1).translate(0, 1.12, 1.52), 0x6d3b22),
    paintGeo(new THREE.BoxGeometry(0.18, 2.35, 0.18).translate(-2.3, 1.3, 1.82), 0x5d341d),
    paintGeo(new THREE.BoxGeometry(0.18, 2.35, 0.18).translate(-0.9, 1.3, 1.82), 0x5d341d),
    paintGeo(new THREE.BoxGeometry(0.18, 2.35, 0.18).translate(0.9, 1.3, 1.82), 0x5d341d),
    paintGeo(new THREE.BoxGeometry(0.18, 2.35, 0.18).translate(2.3, 1.3, 1.82), 0x5d341d),
    // Sân gạch đỏ trước hiên + tường rào gạch thấp hai bên cổng
    paintGeo(new THREE.BoxGeometry(5.4, 0.06, 1.8).translate(0, 0.04, 2.4), 0xb85538),
    paintGeo(new THREE.BoxGeometry(1.9, 0.72, 0.18).translate(-1.85, 0.36, 3.25), 0xc87d4b),
    paintGeo(new THREE.BoxGeometry(1.9, 0.72, 0.18).translate(1.85, 0.36, 3.25), 0xc87d4b),
    paintGeo(new THREE.BoxGeometry(0.34, 1.15, 0.34).translate(-0.82, 0.58, 3.25), 0xd99b52),
    paintGeo(new THREE.BoxGeometry(0.34, 1.15, 0.34).translate(0.82, 0.58, 3.25), 0xd99b52),
  ];
  const mesh = new THREE.Mesh(mergeGeometries(parts)!, ARCH_MAT);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  g.add(mesh);

  // Hai cửa sổ hai gian bên (sáng đèn ban đêm)
  const wins = mergeGeometries([
    new THREE.BoxGeometry(0.95, 0.95, 0.08).translate(-1.65, 1.48, 1.52),
    new THREE.BoxGeometry(0.95, 0.95, 0.08).translate(1.65, 1.48, 1.52),
  ])!;
  g.add(new THREE.Mesh(wins, windows));

  // Mái ngói đỏ truyền thống vươn che hiên
  g.add(at(tiledRoof(5.8, 4.5, 1.35), 0, 2.55, 0.1));
  const pole = at(flag(1.5), 0.85, 1.15, 3.25);
  pole.rotation.x = 0.45;
  g.add(pole);
  for (const x of [-0.9, 0.9]) g.add(at(lantern(0.65), x, 2.25, 1.9));
  if (pot) g.add(at(pot, -1.6, 0.04, 2.45));
  g.add(at(chrysanthemumPot(), 1.5, 0.04, 2.55));
  g.add(blob(6.2, 5.2));
  return g;
}

/** Đống rơm vàng cạnh sân nhà quê Việt Nam (1 draw call). */
let haystackGeo: THREE.BufferGeometry | null = null;
function haystack(): THREE.Mesh {
  if (!haystackGeo) {
    const pole = paintGeo(new THREE.CylinderGeometry(0.07, 0.09, 2.4, 6).translate(0, 1.2, 0), 0x6b4a2b);
    const lower = paintGeo(new THREE.SphereGeometry(1.05, 10, 8).scale(1, 0.85, 1).translate(0, 0.78, 0), 0xd4a843);
    const upper = paintGeo(new THREE.ConeGeometry(0.98, 1.15, 10).translate(0, 1.55, 0), 0xe2b94e);
    haystackGeo = mergeGeometries([pole, lower, upper])!;
  }
  const m = new THREE.Mesh(haystackGeo, ARCH_MAT);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

/** Quán cóc ven quốc lộ (PLAN-140): mái bạt, biển chữ, bàn nhựa thấp + ghế đỏ / xanh (ghế vẽ lặp một lượt). */
function roadStall(name: string, tarp: number): THREE.Group {
  const g = new THREE.Group();
  const awning = at(slab(3.6, 0.08, 2.4, soft(tarp, 0.8)), 0, 2.2, 0);
  awning.rotation.x = 0.12;
  awning.castShadow = true;
  g.add(awning);
  for (const x of [-1.7, 1.7]) g.add(at(post(0.05, 2.2, soft(0x8a8f96, 0.5, 0.5)), x, 1.1, 1.1));
  g.add(at(new SignBoard(name, 3.0, 0.5, { bg: "#d32f2f", fg: "#ffffff", rim: "#ffd23f" }).mesh, 0, 2.62, 1.22));
  g.add(at(rounded(1.3, 0.08, 0.8, 0.04, soft(0x1e6fd9, 0.4)), 0, 0.52, 0.3));
  g.add(at(slab(0.1, 0.5, 0.1, soft(0x1e6fd9, 0.4)), 0, 0.25, 0.3));
  g.add(plasticStools([new THREE.Vector3(-0.9, 0, 0.3), new THREE.Vector3(0.9, 0, 0.3), new THREE.Vector3(-0.3, 0, 1.0),
    new THREE.Vector3(0.4, 0, -0.4)]));
  return g;
}

function stiltHouse(): THREE.Group {
  const g = new THREE.Group();
  const parts: THREE.BufferGeometry[] = [
    paintGeo(new THREE.BoxGeometry(3.4, 1.85, 2.7).translate(0, 2.48, 0), 0xc9a46a),
    paintGeo(new THREE.ConeGeometry(2.65, 1.35, 4).rotateY(Math.PI / 4).translate(0, 4.0, 0), 0x8a5a32),
  ];
  for (const [x, z] of [[-1.35, -1.05], [1.35, -1.05], [-1.35, 1.05], [1.35, 1.05]]) {
    parts.push(paintGeo(new THREE.CylinderGeometry(0.11, 0.13, 1.65, 6).translate(x, 0.82, z), 0x6b4a2b));
  }
  const mesh = new THREE.Mesh(mergeGeometries(parts)!, ARCH_MAT);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  g.add(mesh, blob(3.8, 3.2));
  return g;
}

// ---- đồng ruộng ----------------------------------------------------------------------------

/** Ruộng bậc thang: các bậc xanh xếp chồng lùi dần — gộp thành 1 khối duy nhất (1 draw call thay vì 5). */
function terraces(rnd: () => number): THREE.Group {
  const g = new THREE.Group();
  const greens = [0x8bc34a, 0x9ccc65, 0x7cb342];
  const parts: THREE.BufferGeometry[] = [];
  for (let i = 0; i < 5; i++) {
    const step = new THREE.BoxGeometry(12 - i * 1.4, 0.72, 3.1);
    step.translate((rnd() - 0.5) * 1.5, 0.36 + i * 0.7, -i * 2.6);
    parts.push(paintGeo(step, greens[i % 3]));
  }
  const m = new THREE.Mesh(mergeGeometries(parts)!, ARCH_MAT);
  m.receiveShadow = true;
  g.add(m);
  return g;
}

/** Đồi cà phê: hàng bụi xanh thẫm trên đất đỏ (gộp một lần vẽ). */
function coffeeRows(rnd: () => number): THREE.InstancedMesh {
  const bushes = new THREE.InstancedMesh(GEO.ball, mat(0x2e5d2a), 36);
  const m4 = new THREE.Matrix4();
  let n = 0;
  for (let row = 0; row < 4; row++) {
    for (let k = 0; k < 9; k++) {
      const s = 0.55 + rnd() * 0.2;
      m4.compose(new THREE.Vector3(-7 + k * 1.75, s * 0.8, -row * 2.2), new THREE.Quaternion(), new THREE.Vector3(s, s * 0.9, s));
      bushes.setMatrixAt(n++, m4);
    }
  }
  bushes.castShadow = true;
  return bushes;
}

/** Ruộng nước miền Tây / làng quê: mặt nước loáng phản chiếu bầu trời + bờ đê đất + hàng lúa non gộp 1 khối (2 draw calls thay vì 9). */
let paddyBankGeo: THREE.BufferGeometry | null = null;
function paddy(): THREE.Group {
  const g = new THREE.Group();
  const water = new THREE.Mesh(strip(14.4, 8.4), new THREE.MeshStandardMaterial({ color: 0x7cb6cf, roughness: 0.08, metalness: 0.35 }));
  water.rotation.x = -Math.PI / 2;
  g.add(at(water, 0, 0.04, 0));
  if (!paddyBankGeo) {
    const parts: THREE.BufferGeometry[] = [
      paintGeo(new THREE.BoxGeometry(0.55, 0.28, 8.6).translate(-7.1, 0.14, 0), 0x7a6848),
      paintGeo(new THREE.BoxGeometry(0.55, 0.28, 8.6).translate(7.1, 0.14, 0), 0x7a6848),
      paintGeo(new THREE.BoxGeometry(14.6, 0.26, 0.5).translate(0, 0.13, 4.2), 0x857250),
      paintGeo(new THREE.BoxGeometry(14.6, 0.26, 0.5).translate(0, 0.13, -4.2), 0x857250),
    ];
    for (let i = 0; i < 6; i++) {
      parts.push(paintGeo(new THREE.BoxGeometry(12.6, 0.22, 0.36).translate(0, 0.12, -3.1 + i * 1.24), i % 2 ? 0x9ccc65 : 0x8bc34a));
    }
    paddyBankGeo = mergeGeometries(parts)!;
  }
  const banks = new THREE.Mesh(paddyBankGeo, ARCH_MAT);
  banks.receiveShadow = true;
  g.add(banks);
  return g;
}

let casuarinaGeo: THREE.BufferGeometry | null = null;
function casuarina(): THREE.Group {
  if (!casuarinaGeo) {
    casuarinaGeo = mergeGeometries([
      paintGeo(new THREE.CylinderGeometry(0.08, 0.14, 3.0, 6).translate(0, 1.5, 0), 0x6b4a2b),
      paintGeo(new THREE.ConeGeometry(0.95, 2.6, 7).translate(0, 3.4, 0), 0x356330),
      paintGeo(new THREE.ConeGeometry(0.72, 2.2, 7).translate(0, 4.8, 0), 0x3f753a),
    ])!;
  }
  const g = new THREE.Group();
  const m = new THREE.Mesh(casuarinaGeo, ARCH_MAT);
  m.castShadow = true;
  g.add(m, blob(2.1));
  return g;
}

/** Thuyền thúng: nửa cầu úp ngửa, đáy chạm y = 0 (đặt trên cát; trên biển hạ xuống cho nổi). */
function basketBoat(): THREE.Group {
  const g = new THREE.Group();
  const bowl = at(new THREE.Mesh(GEO.half, soft(0x5b3a24, 0.8)), 0, 0.5, 0);
  bowl.scale.set(1.1, -0.5, 1.1);
  g.add(bowl);
  return g;
}

// ---- núi nền xa ---------------------------------------------------------------------------------

// ---- phông núi vẽ tay bằng canvas (PLAN-140) ---------------------------------------------------------------------
// Mỗi lớp xa là MỘT tấm phẳng dựng đứng, ảnh dáng núi vẽ bằng canvas (nền trong suốt) lặp liền mạch, trôi bằng dời ảnh
// (offset) — thay 26–36 khối nón (26–36 lượt vẽ) bằng 2–3 lượt. Dáng theo vùng cho người xem nhận ra: núi đá vôi miền Bắc,
// dãy Trường Sơn sau biển miền Trung, cao nguyên + núi lửa tắt Tây Nguyên, hàng dừa + núi thấp miền Tây. Sương (fog) của cảnh
// làm lớp xa nhạt dần; vật liệu có ánh sáng nên đêm tự tối theo.
const PAINT_W = 1024;
const PAINT_H = 256;
const PAINT_PERIOD = 110;  // một lần lặp ảnh = 110 đơn vị đường
type Paint = "karst" | "ridge" | "plateau" | "palms" | "hills";

/** Đường sống núi tuần hoàn (khớp hai mép ảnh): tổng vài sóng sin có số chu kỳ nguyên trên bề ngang. */
function ridgeLine(rnd: () => number, waves: number[], rough: number): (x: number) => number {
  const parts = waves.map((k) => ({ k, a: (0.4 + rnd() * 0.6) / k, ph: rnd() * Math.PI * 2 }));
  const norm = parts.reduce((t, w) => t + w.a, 0);
  return (x) => {
    const u = (x / PAINT_W) * Math.PI * 2;
    return 0.5 + (rough * parts.reduce((t, w) => t + w.a * Math.sin(w.k * u + w.ph), 0)) / norm;
  };
}

function paintTexture(kind: Paint, color: number, rnd: () => number): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = PAINT_W;
  c.height = PAINT_H;
  const g = c.getContext("2d")!;
  const base = new THREE.Color(color);
  const grad = g.createLinearGradient(0, 0, 0, PAINT_H);  // đỉnh sáng hơn chân một chút: có khối, không phẳng lì
  grad.addColorStop(0, `#${base.clone().offsetHSL(0, -0.05, 0.08).getHexString()}`);
  grad.addColorStop(1, `#${base.clone().offsetHSL(0, 0, -0.06).getHexString()}`);
  g.fillStyle = grad;
  const H = PAINT_H;
  // vẽ ba lần lệch ±W để hình ở mép ảnh nối liền khi lặp
  const wrap = (draw: (dx: number) => void) => { for (const dx of [-PAINT_W, 0, PAINT_W]) draw(dx); };
  if (kind === "karst") {  // núi đá vôi: khối dựng đứng, đỉnh tròn, chen nhau (Ninh Bình, Hạ Long)
    const towers: [number, number, number][] = [];
    for (let x = 0; x < PAINT_W; x += 34 + rnd() * 40) towers.push([x, 28 + rnd() * 46, 0.35 + rnd() * 0.6]);
    wrap((dx) => {
      for (const [x, w, h] of towers) {
        const top = H - h * H;
        g.beginPath();
        g.moveTo(dx + x - w / 2, H);
        g.bezierCurveTo(dx + x - w * 0.62, top + h * H * 0.35, dx + x - w * 0.45, top, dx + x, top);
        g.bezierCurveTo(dx + x + w * 0.5, top, dx + x + w * 0.6, top + h * H * 0.4, dx + x + w / 2, H);
        g.fill();
      }
    });
  } else if (kind === "palms") {  // chân trời miền Tây: đồi xanh thấp + bóng cây đa dạng (không vẽ rặng dừa thưa đều tăm tắp)
    const line = ridgeLine(rnd, [2, 5, 9, 15], 0.45);
    g.beginPath();
    g.moveTo(0, H);
    for (let x = 0; x <= PAINT_W; x += 6) g.lineTo(x, H - (0.18 + 0.16 * line(x)) * H);
    g.lineTo(PAINT_W, H);
    g.fill();
    // Điểm xuyết các vòm cây làng quê tròn trịa to nhỏ khác nhau dọc đường chân trời
    const groves: [number, number, number][] = [];
    for (let x = 18; x < PAINT_W; x += 28 + rnd() * 55) {
      groves.push([x, 18 + rnd() * 28, 0.24 + rnd() * 0.22]);
    }
    wrap((dx) => {
      for (const [x, r, h] of groves) {
        g.beginPath();
        g.arc(dx + x, H - h * H, r, 0, Math.PI * 2);
        g.fill();
      }
    });
  } else {  // ridge: dãy núi dài; plateau: cao nguyên đỉnh bằng + vài núi lửa tắt; hills: đồi thấp, một ngọn đơn độc
    const shape = {
      ridge: { waves: [2, 3, 5, 9, 17], rough: 0.9, low: 0.3, span: 0.62 },
      plateau: { waves: [2, 4, 11], rough: 0.35, low: 0.42, span: 0.2 },
      hills: { waves: [2, 5, 9], rough: 0.5, low: 0.12, span: 0.25 },
    }[kind];
    const line = ridgeLine(rnd, shape.waves, shape.rough);
    const cones: [number, number, number][] = kind === "plateau" ? [[rnd() * PAINT_W, 120, 0.35], [rnd() * PAINT_W, 90, 0.25]]
      : kind === "hills" ? [[rnd() * PAINT_W, 260, 0.55]] : [];
    const heightAt = (x: number) => {
      let y = shape.low + shape.span * line(x);
      for (const [cx, w, h] of cones) {
        for (const d of [x - cx, x - cx - PAINT_W, x - cx + PAINT_W]) {
          if (Math.abs(d) < w / 2) y = Math.max(y, shape.low + h * (1 - Math.abs(d) / (w / 2)) ** 1.4 + 0.1);
        }
      }
      return Math.min(0.98, y);
    };
    g.beginPath();
    g.moveTo(0, H);
    for (let x = 0; x <= PAINT_W; x += 4) g.lineTo(x, H - heightAt(x) * H);
    g.lineTo(PAINT_W, H);
    g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.repeat.x = (FAR_SPAN * 2) / PAINT_PERIOD;
  return tex;
}

/** Một lớp phông: tấm đứng rộng 2 × FAR_SPAN, cao `height`, chân chìm dưới đất một chút. */
function backdrop(kind: Paint, color: number, height: number, z: number, rnd: () => number): { mesh: THREE.Mesh; tex: THREE.CanvasTexture } {
  const tex = paintTexture(kind, color, rnd);
  const mesh = new THREE.Mesh(strip(FAR_SPAN * 2, height),
    new THREE.MeshStandardMaterial({ map: tex, transparent: true, depthWrite: false, roughness: 1 }));
  return { mesh: at(mesh, 0, height / 2 - 1, z), tex };
}

// ---- chọn theo vùng --------------------------------------------------------------------------------

/** Hoa Tết của vùng: đào miền Bắc, mai vàng từ miền Trung trở vào. */
const blossomOf = (region: Region) => (region === "bac" ? DAO : MAI);

function regionTree(region: Region, rnd: () => number): THREE.Group {
  let g: THREE.Group;
  if (region === "bac") {
    const r = rnd();
    g = r < 0.38 ? blossomTree(DAO) : r < 0.72 ? makeTree("round") : r < 0.9 ? makeTree("pine") : makeTree("bush");
  } else if (region === "trung") {
    const r = rnd();
    g = r < 0.25 ? blossomTree(MAI) : r < 0.65 ? casuarina() : makeTree("round");
  } else if (region === "nam") {
    // Giảm tỷ lệ cây dừa đồng dạng: phối hợp cây thân gỗ làng quê (xoài/mít/bàng), cây mai vàng, khóm tre/bụi và dừa
    const r = rnd();
    g = r < 0.24 ? blossomTree(MAI) : r < 0.56 ? makeTree("round") : r < 0.80 ? makeTree("palm") : makeTree("bush");
  } else {
    const r = rnd();
    g = r < 0.22 ? blossomTree(MAI) : r < 0.62 ? makeTree("pine") : makeTree("round");
  }
  // Xoay ngẫu nhiên góc Y và biến thiên tỷ lệ nhẹ để không có 2 cây nào trông giống hệt nhau
  g.rotation.y = rnd() * Math.PI * 2;
  const s = 0.88 + rnd() * 0.28;
  g.scale.set(s, s * (0.92 + rnd() * 0.16), s);
  return g;
}

/** Khoảnh đặc trưng vùng (16 × 10 đơn vị, toạ độ tương đối): ruộng bậc thang / đồi cà phê / ruộng nước / bãi cát. */
function regionField(region: Region, rnd: () => number): { obj: THREE.Object3D; x: number; z: number }[] {
  if (region === "bac") return [{ obj: terraces(rnd), x: 0, z: -11 }];
  if (region === "taynguyen") return [{ obj: coffeeRows(rnd), x: 0, z: -11 }, { obj: makeTree("round"), x: 6, z: -19 }];
  if (region === "nam") return [{ obj: paddy(), x: 0, z: -14.5 }, { obj: makeTree("round"), x: -6.2, z: -12.5 }];
  const sand = new THREE.Mesh(strip(15, 9), mat(0xe6d3a3));
  sand.rotation.x = -Math.PI / 2;
  sand.receiveShadow = true;
  return [
    { obj: at(sand, 0, 0.04, 0), x: 0, z: -14 },
    { obj: casuarina(), x: -5, z: -12 }, { obj: casuarina(), x: 4, z: -17 },
    { obj: basketBoat(), x: 1, z: -13 },
  ];
}

// ---- cảnh --------------------------------------------------------------------------------------

/** Đồ của một vùng ở ba lớp, mỗi lớp một băng chuyền trôi riêng. */
interface RegionLayer {
  near: THREE.Group;
  mid: THREE.Group;
  far: THREE.Group;
  belts: [Conveyor, Conveyor, Conveyor];
  paints: { tex: THREE.CanvasTexture; parallax: number }[];  // phông vẽ: trôi bằng dời ảnh, lớp xa chậm hơn
}

export class Landscape {
  group = new THREE.Group();
  /** Lớp sát đường — ẩn khi bối cảnh (bến / trạm / đầu ngõ) chiếm chỗ. */
  readonly near = new THREE.Group();
  private mid = new THREE.Group();
  private far = new THREE.Group();
  private layers = new Map<Region, RegionLayer>();
  private current: RegionLayer | null = null;
  private ground: THREE.Mesh;
  private groundTex = noiseTexture(128, 0.78, 90);
  private windows = new THREE.MeshStandardMaterial({ color: 0x2c4a66, roughness: 0.2, metalness: 0.4, emissive: 0xffc46b, emissiveIntensity: 0 });
  private region: Region | null = null;

  constructor() {
    this.ground = new THREE.Mesh(strip(700, 400),
      new THREE.MeshStandardMaterial({ color: GROUND.nam, map: this.groundTex, roughness: 0.95 }));
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.receiveShadow = true;
    this.group.add(this.ground, this.near, this.mid, this.far);
  }

  setRegion(region: Region): void {
    if (region === this.region) return;
    this.region = region;
    (this.ground.material as THREE.MeshStandardMaterial).color.setHex(GROUND[region]);
    if (this.current) this.show(this.current, false);
    const layer = this.prebuild(region);
    this.show(layer, true);
    this.current = layer;
  }

  /** Dựng sẵn cảnh một vùng (chưa gắn vào cảnh); dựng rồi thì thôi. */
  prebuild(region: Region): RegionLayer {
    let layer = this.layers.get(region);
    if (!layer) {
      layer = this.build(region);
      this.layers.set(region, layer);
    }
    return layer;
  }

  /** Các vùng chưa dựng (scene dựng dần lúc rảnh). */
  missing(): Region[] {
    return REGIONS.filter((r) => !this.layers.has(r));
  }

  /** Trong hầm: ẩn cây, núi, ruộng hai bên (lớp sát đường do scene bật / tắt vì còn phụ thuộc bối cảnh). */
  setSides(visible: boolean): void {
    this.mid.visible = this.far.visible = visible;
  }

  setNight(night: boolean): void {
    this.windows.emissiveIntensity = night ? 0.9 : 0;
  }

  advance(dx: number): void {
    for (const belt of this.current?.belts ?? []) belt.advance(dx);
    for (const p of this.current?.paints ?? []) p.tex.offset.x += (dx * p.parallax) / PAINT_PERIOD;
    this.groundTex.offset.x += dx / (700 / 90);
  }

  private show(layer: RegionLayer, on: boolean): void {
    for (const [parent, group] of [[this.near, layer.near], [this.mid, layer.mid], [this.far, layer.far]] as const) {
      if (on) parent.add(group);
      else parent.remove(group);
    }
  }

  private build(region: Region): RegionLayer {
    const layer: RegionLayer = {
      near: new THREE.Group(), mid: new THREE.Group(), far: new THREE.Group(),
      belts: [new Conveyor(1), new Conveyor(1), new Conveyor(0.12, FAR_SPAN)],
      paints: [],
    };
    const rnd = rand(31 + REGIONS.indexOf(region) * 977);  // mỗi vùng một hạt giống riêng, dựng lại vẫn y hệt
    this.buildNear(region, rnd, layer);
    this.buildMid(region, rnd, layer);
    this.buildFar(region, rnd, layer);
    for (const group of [layer.near, layer.mid, layer.far]) {  // cảnh tĩnh: chỉ băng chuyền dời vị trí, không xoay / co
      group.traverse((o) => { if (o !== group && o.parent !== group) { o.matrixAutoUpdate = false; o.updateMatrix(); } });
    }
    return layer;
  }

  /**
   * Dải sát đường (z -10…-20) là phần trung cảnh chính phía sau xe khách:
   * xen kẽ nhà ngói 3 gian truyền thống Việt Nam (villageTileHouse), cụm nhà ống phố huyện và đồng ruộng/đồi theo vùng.
   */
  private buildNear(region: Region, rnd: () => number, { near, belts: [belt] }: RegionLayer): void {
    const shops = ["TẠP HOÁ", "CƠM BÌNH DÂN", "SỬA XE", "BIA HƠI", "NHÀ NGHỈ", "RỬA XE", "BƠM VÁ XE"];
    const stalls = ["TRÀ ĐÁ", "CƠM PHỞ", "BƠM VÁ XE", "NƯỚC MÍA", "BÁNH MÌ"];
    let block = 0;
    for (let x = -WRAP; x < WRAP; x += 16, block++) {
      if (block % 2 === 0) {
        for (const item of regionField(region, rnd)) near.add(belt.add(at(item.obj, x + item.x, 0, item.z)));
        if (block % 4 === 0) near.add(belt.add(at(greetingBanner(), x, 0, -9.2)));  // băng rôn chúc Tết đầu làng
        else near.add(belt.add(at(roadStall(stalls[Math.floor(rnd() * stalls.length)], [0x1e6fd9, 0xd32f2f, 0x2e7d32][block % 3]), x + 3, 0, -9.0)));
        near.add(belt.add(at(haystack(), x - 6.2, 0, -11.2)));
        continue;
      }
      // Tăng tần suất Nhà ngói 3 gian truyền thống Việt Nam để luôn hiện diện rõ trên hành trình qua làng quê
      if (block % 4 === 1 || block % 4 === 3) {
        const pot = blossomPot(blossomOf(region));
        near.add(belt.add(at(villageTileHouse(this.windows, pot), x - 1.8, 0, -11.6)));
        near.add(belt.add(at(blossomTree(blossomOf(region)), x + 3.6, 0, -10.8)));
        if (block % 4 === 3) {
          const sign = shops[Math.floor(rnd() * shops.length)];
          const house = tubeHouse(FACADES[Math.floor(rnd() * FACADES.length)], 2, this.windows, sign, kumquatPot());
          near.add(belt.add(at(house, x + 6.8, 0, -11.2)));
        }
        near.add(belt.add(at(regionTree(region, rnd), x - 6.0, 0, -15.5)));
        continue;
      }
      const houses = 1 + Math.floor(rnd() * 2);
      for (let h = 0; h < houses; h++) {
        const sign = rnd() < 0.5 ? shops[Math.floor(rnd() * shops.length)] : null;
        const roll = rnd();
        const pot = roll < 0.45 ? blossomPot(blossomOf(region)) : roll < 0.75 ? kumquatPot() : null;
        const house = region === "nam" && rnd() < 0.35 ? stiltHouse()
          : tubeHouse(FACADES[Math.floor(rnd() * FACADES.length)], 1 + Math.floor(rnd() * 3), this.windows, sign, pot);
        near.add(belt.add(at(house, x - 4 + h * 4.5, 0, -11.0 - rnd() * 1.5)));
      }
      near.add(belt.add(at(regionTree(region, rnd), x + 5, 0, -16 - rnd() * 3)));
    }
  }

  /** Hàng cây xa (thấy ở góc máy ngang / cận) + bụi cỏ thấp phía camera (KHÔNG đặt cây cao ở z > 0 để tránh che khuất xe chính!). */
  private buildMid(region: Region, rnd: () => number, { mid, belts: [, belt] }: RegionLayer): void {
    for (let x = -WRAP; x < WRAP; x += 6.5 + rnd() * 5.5) {
      const tree = regionTree(region, rnd);
      mid.add(belt.add(at(tree, x, 0, -25 - rnd() * 16)));
      // Phía camera (z dương): chỉ đặt bụi cây thấp (bush) ở xa lề đường để tạo cảm giác tốc độ mà không bao giờ che thân xe
      if (rnd() < 0.35) {
        const lowBush = makeTree("bush");
        lowBush.scale.setScalar(0.65 + rnd() * 0.25);
        mid.add(belt.add(at(lowBush, x + rnd() * 3, 0, 9.5 + rnd() * 5)));
      }
    }
    for (let x = -WRAP; x < WRAP; x += 40) {
      if (region === "taynguyen") mid.add(belt.add(at(coffeeRows(rnd), x + 20, 0, -28)));
      if (region === "nam") {  // mương nước + xuồng phía sau
        const canal = new THREE.Mesh(strip(40, 3), new THREE.MeshStandardMaterial({ color: 0x6aa3b8, roughness: 0.1, metalness: 0.3 }));
        canal.rotation.x = -Math.PI / 2;
        mid.add(belt.add(at(canal, x + 20, 0.035, -23)));
        mid.add(belt.add(at(rounded(2.4, 0.3, 0.7, 0.12, soft(0x6b4226, 0.8)), x + 10 + rnd() * 15, 0.15, -23)));
      }
    }
  }

  private buildFar(region: Region, rnd: () => number, layer: RegionLayer): void {
    const { far, belts: [, , belt] } = layer;
    // [dáng, màu, cao, z, tốc độ trôi]: lớp gần đậm + trôi nhanh hơn, lớp xa nhạt + chậm (sương làm nhạt thêm)
    const plan: [Paint, number, number, number, number][] = {
      bac: [["karst", 0x456e50, 38, -78, 0.16], ["karst", 0x62857b, 48, -110, 0.11], ["ridge", 0x869e9c, 58, -145, 0.07]],
      trung: [["ridge", 0x5c7f76, 42, -135, 0.08], ["ridge", 0x7f9894, 54, -170, 0.05]],
      taynguyen: [["plateau", 0x547342, 28, -82, 0.14], ["ridge", 0x748c66, 38, -120, 0.09]],
      nam: [["palms", 0x3b6636, 22, -72, 0.18], ["hills", 0x6e9474, 30, -118, 0.09], ["ridge", 0x8ca894, 38, -155, 0.05]],
    }[region] as [Paint, number, number, number, number][];
    if (region === "trung") {
      const sea = new THREE.Mesh(strip(FAR_SPAN * 3, 200), new THREE.MeshStandardMaterial({ color: 0x3d8fd1, roughness: 0.15, metalness: 0.2 }));
      sea.rotation.x = -Math.PI / 2;
      far.add(at(sea, 0, 0.05, -150));  // biển đứng yên (trải rộng), thuyền trôi
      for (let i = 0; i < 8; i++) far.add(belt.add(at(basketBoat(), -FAR_SPAN + i * 55 + rnd() * 20, -0.3, -62 - rnd() * 30)));
    }
    for (const [kind, color, height, z, parallax] of plan) {
      const { mesh, tex } = backdrop(kind, color, height, z, rnd);
      far.add(mesh);
      layer.paints.push({ tex, parallax });
    }
  }

}
