// Đồ Tết (PLAN-129): chậu mai / đào, chậu cúc, cờ đỏ sao vàng, băng rôn chúc Tết, cây nêu, dưa hấu, bánh chưng.
// Rải dọc đường (nhà ống, trụ điện) và ở bến / trạm / nhà. Hình khối + vật liệu dùng chung (art.ts), texture cờ / băng rôn
// vẽ một lần — đồ này lặp lại hàng trăm lần trong cảnh, mỗi cái chỉ thêm vài mesh, không thêm texture.

import * as THREE from "three";
import { at, blob, GEO, mat, post, rounded, soft } from "./art";
import { blossomTree, lantern, SignBoard } from "./props";

export const MAI = 0xffd23f;
export const DAO = 0xff8fb1;

const POT = soft(0xa3301f, 0.6);
const POT_RIM = soft(0xf4c04e, 0.4, 0.3);
const STICK = soft(0x8d6e63, 0.7);

// ---- năm âm lịch -------------------------------------------------------------------------------

const CAN = ["Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ"];
const CHI = ["Thân", "Dậu", "Tuất", "Hợi", "Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi"];

/** Tết sắp tới (hoặc vừa qua, nếu đang tháng 1–2): «Đinh Mùi 2027». */
function lunarYear(now = new Date()): string {
  const y = now.getMonth() >= 2 ? now.getFullYear() + 1 : now.getFullYear();
  return `${CAN[y % 10]} ${CHI[y % 12]} ${y}`;
}

export const GREETING = `CHÚC MỪNG NĂM MỚI · XUÂN ${lunarYear().toUpperCase()}`;

// ---- chậu cây ------------------------------------------------------------------------------------

function pot(radius: number, height: number): THREE.Group {
  const g = new THREE.Group();
  const body = at(new THREE.Mesh(GEO.cylSmooth, POT), 0, height / 2, 0);
  body.scale.set(radius, height, radius);
  body.castShadow = true;
  const rim = at(new THREE.Mesh(GEO.cylSmooth, POT_RIM), 0, height, 0);
  rim.scale.set(radius * 1.1, 0.08, radius * 1.1);
  g.add(body, rim);
  return g;
}

/** Chậu mai (vàng) / đào (hồng) chưng Tết: cây nhỏ trong chậu sành đỏ viền vàng. */
export function blossomPot(color: number): THREE.Group {
  const g = pot(0.6, 0.8);
  const tree = blossomTree(color);
  tree.scale.setScalar(0.62);
  tree.position.y = 0.8;
  g.add(tree);
  return g;
}

/** Chậu cúc vàng: chậu thấp + ụ hoa tròn. */
export function chrysanthemumPot(): THREE.Group {
  const g = pot(0.35, 0.45);
  const leaves = at(new THREE.Mesh(GEO.sphere, soft(0x3e7a35, 0.9)), 0, 0.72, 0);
  leaves.scale.set(0.45, 0.32, 0.45);
  const flowers = new THREE.InstancedMesh(GEO.ball, mat(0xffc400), 12);
  const m4 = new THREE.Matrix4();
  for (let i = 0; i < 12; i++) {
    const a = i * 2.4;
    const r = i < 4 ? 0.12 : 0.36;
    m4.compose(new THREE.Vector3(Math.cos(a) * r, 0.86 + (i < 4 ? 0.1 : 0), Math.sin(a) * r), new THREE.Quaternion(),
      new THREE.Vector3(0.13, 0.11, 0.13));
    flowers.setMatrixAt(i, m4);
  }
  leaves.castShadow = true;
  g.add(leaves, flowers);
  return g;
}

// ---- cờ, băng rôn ----------------------------------------------------------------------------

const FLAG_MAT = (() => {
  const c = document.createElement("canvas");
  c.width = 192;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#da251d";
  g.fillRect(0, 0, 192, 128);
  g.fillStyle = "#ffcd00";
  g.beginPath();
  for (let i = 0; i < 10; i++) {
    const r = i % 2 ? 17 : 42;
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    g.lineTo(96 + Math.cos(a) * r, 66 + Math.sin(a) * r);
  }
  g.fill();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return new THREE.MeshStandardMaterial({ map: tex, side: THREE.DoubleSide, roughness: 0.8 });
})();
const FLAG_GEO = (() => {  // lá cờ gợn sóng nhẹ (đứng yên — rẻ hơn cờ bay)
  const geo = new THREE.PlaneGeometry(1.2, 0.8, 8, 1);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setZ(i, Math.sin((pos.getX(i) + 0.6) * 4) * 0.06 * (pos.getX(i) + 0.6));
  geo.translate(0.6, 0, 0);
  geo.computeVertexNormals();
  return geo;
})();

/** Cờ đỏ sao vàng trên cán (gốc ở chân cán); nơi cắm tự xoay cho cán chĩa ra đường. */
export function flag(height = 1.6): THREE.Group {
  const g = new THREE.Group();
  g.add(at(post(0.025, height, STICK), 0, height / 2, 0));
  const cloth = new THREE.Mesh(FLAG_GEO, FLAG_MAT);
  cloth.position.set(0.03, height - 0.42, 0);
  cloth.castShadow = true;
  g.add(cloth);
  return g;
}

let greetingBoard: SignBoard | null = null;

/** Băng rôn «CHÚC MỪNG NĂM MỚI · XUÂN …» trên hai cột tre — texture dùng chung cho mọi băng rôn. */
export function greetingBanner(width = 6, height = 0.7, poles = 2.6): THREE.Group {
  greetingBoard ??= new SignBoard(GREETING, 6, 0.7);
  const g = new THREE.Group();
  const cloth = new THREE.Mesh(greetingBoard.mesh.geometry, greetingBoard.mesh.material);
  cloth.scale.set(width / 6, height / 0.7, 1);
  g.add(at(cloth, 0, poles - height / 2, 0));
  if (poles > 0) for (const x of [-width / 2 - 0.08, width / 2 + 0.08]) g.add(at(post(0.05, poles + 0.2, STICK), x, (poles + 0.2) / 2, 0));
  return g;
}

// ---- sân nhà ngày Tết ---------------------------------------------------------------------------

/** Cây nêu: cây tre cao, ngọn còn lá, treo chùm khánh + dải giấy đỏ vàng. */
export function cayNeu(height = 7): THREE.Group {
  const g = new THREE.Group();
  g.add(at(post(0.07, height, soft(0x9bb35a, 0.7)), 0, height / 2, 0));
  for (let i = 0; i < 5; i++) {  // tán lá ngọn
    const leaf = at(new THREE.Mesh(GEO.box, mat(0x5f8f3a)), 0, height + 0.1, 0);
    leaf.scale.set(1.3, 0.05, 0.22);
    leaf.rotation.set(0, (i / 5) * Math.PI * 2, -0.5);
    leaf.translateX(0.55);
    g.add(leaf);
  }
  g.add(at(post(0.012, 1.4, STICK), 0.35, height - 0.9, 0));  // dây treo
  g.add(at(lantern(0.7), 0.35, height - 1.5, 0));
  const ribbons = [0xd32f2f, 0xf4c04e, 0xd32f2f];
  ribbons.forEach((c, i) => {
    const r = at(rounded(0.12, 0.7, 0.02, 0.02, soft(c, 0.6)), -0.18 - i * 0.14, height - 0.7 - i * 0.12, 0);
    g.add(r);
  });
  g.add(blob(0.8));
  return g;
}

/** Dưa hấu bổ đôi: vỏ xanh, ruột đỏ. */
export function watermelon(): THREE.Group {
  const g = new THREE.Group();
  const rind = at(new THREE.Mesh(GEO.half, soft(0x2e7d32, 0.5)), 0, 0.02, 0);
  rind.scale.set(0.32, 0.26, 0.32);
  rind.rotation.x = Math.PI;
  rind.position.y = 0.28;
  const flesh = at(new THREE.Mesh(GEO.cylSmooth, soft(0xe53935, 0.6)), 0, 0.29, 0);
  flesh.scale.set(0.3, 0.02, 0.3);
  g.add(rind, flesh);
  return g;
}

/** Chồng bánh chưng gói lá xanh, buộc lạt. */
export function banhChungStack(count = 4): THREE.Group {
  const g = new THREE.Group();
  const leaf = soft(0x3f7d3a, 0.8);
  const tie = soft(0xd9c38a, 0.8);
  for (let i = 0; i < count; i++) {
    const y = i < 3 ? 0.17 : 0.51;
    const x = i < 3 ? (i - 1) * 0.66 : 0;
    const cake = at(rounded(0.6, 0.32, 0.6, 0.04, leaf), x, y, 0);
    cake.rotation.y = i * 0.2;
    const band = at(rounded(0.62, 0.34, 0.08, 0.02, tie), x, y, 0);
    band.rotation.y = i * 0.2;
    g.add(cake, band);
  }
  return g;
}
