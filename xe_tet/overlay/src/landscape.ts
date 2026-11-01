// Cảnh hai bên đường theo vùng (PLAN-121 V3), ba lớp trôi khác tốc độ để có chiều sâu:
//   gần  (z -7…-14): nhà ống, tạp hoá, cây — ẩn khi đang ở bến / trạm / đầu ngõ (trùng chỗ bối cảnh)
//   giữa (z -21…-45 và phía camera z +8…+15): ruộng bậc thang / đồi cà phê / ruộng nước / cát + phi lao, cây
//   xa   (z -60…-150): núi nhiều tầng, biển + thuyền thúng — trôi rất chậm
// Mỗi vùng dựng một lần rồi giữ lại, đổi vùng chỉ bật / tắt: không dựng lại, không rò bộ nhớ GPU suốt buổi live.
// Ngày Tết (PLAN-129): nhà treo cờ + đèn lồng, chậu mai / đào trước hiên, băng rôn chúc Tết, mai vàng xen cây ven đường.

import * as THREE from "three";
import { at, GEO, mat, noiseTexture, post, rounded, slab, soft } from "./art";
import { strip } from "./bend";
import { blossomTree, kumquatPot, lantern, makeTree, SignBoard } from "./props";
import { Conveyor, WRAP } from "./road";
import { blossomPot, DAO, flag, greetingBanner, MAI } from "./tet";
import type { Region } from "./types";

const GROUND: Record<Region, number> = { bac: 0x6f9b52, trung: 0xa9b26a, taynguyen: 0xa8603c, nam: 0x5fa04e };
const FAR_SPAN = 220;
const FACADES = [0xf6d36b, 0x8fd3c8, 0xf4a6a0, 0xb5d38a, 0xf7f1e3, 0x9fc3f0];
const REGIONS: Region[] = ["bac", "trung", "taynguyen", "nam"];

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

/** Nhà ống mặt tiền nhiều màu, ban công, bồn nước inox trên nóc; vài căn có biển tạp hoá. Ngày Tết: cờ chĩa ra đường,
 * đôi đèn lồng trước cửa, chậu mai / đào / quất (`pot`) đặt ngoài hiên. */
function tubeHouse(color: number, floors: number, windows: THREE.Material, shop: string | null, pot: THREE.Object3D | null): THREE.Group {
  const g = new THREE.Group();
  const h = floors * 2.2;
  g.add(at(rounded(3, h, 4, 0.08, soft(color, 0.85)), 0, h / 2, 0));
  for (let f = 0; f < floors; f++) {
    g.add(at(slab(2.2, 1.1, 0.06, windows), 0, 1.3 + f * 2.2, 2.02));
    if (f > 0) g.add(at(slab(3.2, 0.1, 0.7, soft(0xe9e2d6, 0.8)), 0, f * 2.2, 2.3));  // ban công
  }
  const tank = at(new THREE.Mesh(GEO.cylSmooth, soft(0xdfe4ea, 0.25, 0.9)), 0.6, h + 0.55, -0.8);
  tank.scale.set(0.45, 1.1, 0.45);
  tank.rotation.z = Math.PI / 2;
  g.add(tank);
  if (shop) g.add(at(new SignBoard(shop, 2.8, 0.55, { bg: "#1e6fd9", fg: "#ffffff", rim: "#ffd23f" }).mesh, 0, 2.35, 2.05));
  const pole = at(flag(1.5), 1.35, h - 0.9, 2.05);
  pole.rotation.x = 0.6;
  g.add(pole);
  for (const x of [-1.1, 1.1]) g.add(at(lantern(0.7), x, 2.15, 2.3));
  if (pot) g.add(at(pot, -1.0, 0, 2.7));
  g.traverse((o) => { o.castShadow = true; });
  return g;
}

function stiltHouse(): THREE.Group {
  const g = new THREE.Group();
  for (const [x, z] of [[-1.3, -1], [1.3, -1], [-1.3, 1], [1.3, 1]]) g.add(at(post(0.1, 1.6, mat(0x6b4a2b)), x, 0.8, z));
  g.add(at(rounded(3.2, 1.8, 2.6, 0.06, soft(0xc9a46a, 0.9)), 0, 2.5, 0));
  const roof = at(new THREE.Mesh(GEO.cone, mat(0x8a6a3c)), 0, 3.9, 0);
  roof.scale.set(2.6, 1.2, 2.2);
  roof.rotation.y = Math.PI / 4;
  g.add(roof);
  return g;
}

// ---- đồng ruộng ----------------------------------------------------------------------------

/** Ruộng bậc thang: các bậc xanh xếp chồng lùi dần. */
function terraces(rnd: () => number): THREE.Group {
  const g = new THREE.Group();
  const greens = [0x8bc34a, 0x9ccc65, 0x7cb342];
  for (let i = 0; i < 5; i++) {
    const step = at(rounded(12 - i * 1.4, 0.7, 3, 0.2, mat(greens[i % 3])), (rnd() - 0.5) * 1.5, 0.35 + i * 0.7, -i * 2.6);
    g.add(step);
  }
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

/** Ruộng nước miền Tây: mặt nước loáng + bờ ruộng + mạ xanh. */
function paddy(): THREE.Group {
  const g = new THREE.Group();
  const water = new THREE.Mesh(strip(14, 8), new THREE.MeshStandardMaterial({ color: 0x7fb3c8, roughness: 0.08, metalness: 0.3 }));
  water.rotation.x = -Math.PI / 2;
  g.add(at(water, 0, 0.04, 0));
  for (const x of [-7, 7]) g.add(at(slab(0.5, 0.25, 8, mat(0x7a6a4a)), x, 0.12, 0));
  for (let i = 0; i < 6; i++) g.add(at(slab(12, 0.18, 0.35, mat(0x9ccc65)), 0, 0.1, -3 + i * 1.2));
  return g;
}

function casuarina(): THREE.Group {
  const g = new THREE.Group();
  g.add(at(post(0.1, 3, mat(0x6b4a2b)), 0, 1.5, 0));
  const crown = at(new THREE.Mesh(GEO.cone, mat(0x3f6e3a)), 0, 4.2, 0);
  crown.scale.set(0.9, 4, 0.9);
  g.add(crown);
  g.traverse((o) => { o.castShadow = true; });
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

/** Một dãy núi: các đỉnh rải đều dải [-FAR_SPAN, FAR_SPAN); mỗi đỉnh là một vật riêng để tự quay vòng trên băng chuyền. */
function ridge(rnd: () => number, color: number, count: number, height: number, z: number): THREE.Mesh[] {
  return Array.from({ length: count }, (_, i) => {
    const peak = new THREE.Mesh(GEO.cone, mat(color));
    const s = height * (0.6 + rnd() * 0.7);
    peak.scale.set(s * (1.2 + rnd() * 0.8), s, s);
    return at(peak, -FAR_SPAN + (i / count) * FAR_SPAN * 2 + rnd() * 12, s * 0.42, z - rnd() * 12);
  });
}

// ---- chọn theo vùng --------------------------------------------------------------------------------

/** Hoa Tết của vùng: đào miền Bắc, mai vàng từ miền Trung trở vào. */
const blossomOf = (region: Region) => (region === "bac" ? DAO : MAI);

function regionTree(region: Region, rnd: () => number): THREE.Group {
  if (region === "bac") return rnd() < 0.45 ? blossomTree(DAO) : makeTree(rnd() < 0.6 ? "pine" : "round");
  if (rnd() < 0.25) return blossomTree(MAI);
  if (region === "trung") return casuarina();
  if (region === "nam") return makeTree(rnd() < 0.7 ? "palm" : "bush");
  return makeTree(rnd() < 0.6 ? "round" : "pine");
}

/** Khoảnh đặc trưng vùng (16 × 10 đơn vị, toạ độ tương đối): ruộng bậc thang / đồi cà phê / ruộng nước / bãi cát. */
function regionField(region: Region, rnd: () => number): { obj: THREE.Object3D; x: number; z: number }[] {
  if (region === "bac") return [{ obj: terraces(rnd), x: 0, z: -11 }];
  if (region === "taynguyen") return [{ obj: coffeeRows(rnd), x: 0, z: -11 }, { obj: makeTree("round"), x: 6, z: -19 }];
  if (region === "nam") return [{ obj: paddy(), x: 0, z: -14 }, { obj: makeTree("palm"), x: -6, z: -10 }];
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
    let layer = this.layers.get(region);
    if (!layer) {
      layer = this.build(region);
      this.layers.set(region, layer);
    }
    this.show(layer, true);
    this.current = layer;
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
    this.groundTex.offset.x += dx / (700 / 90);
  }

  private show(layer: RegionLayer, on: boolean): void {
    layer.near.visible = layer.mid.visible = layer.far.visible = on;
  }

  private build(region: Region): RegionLayer {
    const layer: RegionLayer = {
      near: new THREE.Group(), mid: new THREE.Group(), far: new THREE.Group(),
      belts: [new Conveyor(1), new Conveyor(1), new Conveyor(0.12, FAR_SPAN)],
    };
    const rnd = rand(31 + REGIONS.indexOf(region) * 977);  // mỗi vùng một hạt giống riêng, dựng lại vẫn y hệt
    this.buildNear(region, rnd, layer);
    this.buildMid(region, rnd, layer);
    this.buildFar(region, rnd, layer);
    this.near.add(layer.near);
    this.mid.add(layer.mid);
    this.far.add(layer.far);
    return layer;
  }

  /**
   * Dải sát đường (z -9…-20) là phần duy nhất camera rộng nhìn thấy dưới khung chữ, nên đặc trưng vùng phải nằm ở đây:
   * xen kẽ một khoảnh ruộng / đồi theo vùng và một cụm nhà ống.
   */
  private buildNear(region: Region, rnd: () => number, { near, belts: [belt] }: RegionLayer): void {
    const shops = ["TẠP HOÁ", "CƠM BÌNH DÂN", "SỬA XE", "BIA HƠI"];
    let block = 0;
    for (let x = -WRAP; x < WRAP; x += 16, block++) {
      if (block % 2 === 0) {
        for (const item of regionField(region, rnd)) near.add(belt.add(at(item.obj, x + item.x, 0, item.z)));
        if (block % 4 === 0) near.add(belt.add(at(greetingBanner(), x, 0, -8.6)));  // băng rôn chúc Tết đầu làng
        continue;
      }
      const houses = 1 + Math.floor(rnd() * 2);
      for (let h = 0; h < houses; h++) {
        const sign = rnd() < 0.5 ? shops[Math.floor(rnd() * shops.length)] : null;
        const roll = rnd();
        const pot = roll < 0.4 ? blossomPot(blossomOf(region)) : roll < 0.65 ? kumquatPot() : null;
        const house = region === "nam" && rnd() < 0.4 ? stiltHouse()
          : tubeHouse(FACADES[Math.floor(rnd() * FACADES.length)], 1 + Math.floor(rnd() * 3), this.windows, sign, pot);
        near.add(belt.add(at(house, x - 4 + h * 4.5, 0, -10.5 - rnd() * 1.5)));
      }
      near.add(belt.add(at(regionTree(region, rnd), x + 5, 0, -16 - rnd() * 3)));
    }
  }

  /** Hàng cây xa (thấy ở góc máy ngang / cận) + cây và ruộng phía camera làm tiền cảnh. */
  private buildMid(region: Region, rnd: () => number, { mid, belts: [, belt] }: RegionLayer): void {
    for (let x = -WRAP; x < WRAP; x += 5 + rnd() * 4) {
      const tree = regionTree(region, rnd);
      tree.scale.setScalar(1 + rnd() * 0.5);
      mid.add(belt.add(at(tree, x, 0, -26 - rnd() * 16)));
      if (rnd() < 0.6) mid.add(belt.add(at(regionTree(region, rnd), x + rnd() * 3, 0, 8 + rnd() * 7)));
    }
    for (let x = -WRAP; x < WRAP; x += 40) {
      if (region === "taynguyen") mid.add(belt.add(at(coffeeRows(rnd), x + 20, 0, 11)));
      if (region === "nam") {  // mương nước + xuồng phía sau
        const canal = new THREE.Mesh(strip(40, 3), new THREE.MeshStandardMaterial({ color: 0x6aa3b8, roughness: 0.1, metalness: 0.3 }));
        canal.rotation.x = -Math.PI / 2;
        mid.add(belt.add(at(canal, x + 20, 0.035, -23)));
        mid.add(belt.add(at(rounded(2.4, 0.3, 0.7, 0.12, soft(0x6b4226, 0.8)), x + 10 + rnd() * 15, 0.15, -23)));
      }
    }
  }

  private buildFar(region: Region, rnd: () => number, { far, belts: [, , belt] }: RegionLayer): void {
    const ridges = (items: THREE.Object3D[]) => { for (const o of items) far.add(belt.add(o)); };
    if (region === "trung") {
      const sea = new THREE.Mesh(strip(FAR_SPAN * 3, 200), new THREE.MeshStandardMaterial({ color: 0x3d8fd1, roughness: 0.15, metalness: 0.2 }));
      sea.rotation.x = -Math.PI / 2;
      far.add(at(sea, 0, 0.05, -150));  // biển đứng yên (trải rộng), thuyền + núi trôi
      for (let i = 0; i < 8; i++) far.add(belt.add(at(basketBoat(), -FAR_SPAN + i * 55 + rnd() * 20, -0.3, -62 - rnd() * 30)));
      ridges(ridge(rnd, 0x6f8f86, 6, 14, -175));
      return;
    }
    if (region === "nam") {
      ridges(ridge(rnd, 0x86a88a, 5, 8, -160));
      return;
    }
    // núi nhiều tầng: gần đậm, xa nhạt; Tây Bắc cao và dày hơn
    const layers = region === "bac" ? [[0x4f7a5a, 14, 26, -95], [0x6f8f86, 12, 34, -125], [0x93a9a6, 10, 40, -155]]
      : [[0x5e7d4a, 10, 16, -100], [0x7e9670, 8, 22, -135]];
    for (const [color, count, height, z] of layers) ridges(ridge(rnd, color, count, height, z));
  }
}
