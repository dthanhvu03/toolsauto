// Ba bối cảnh (PLAN-121 V2): bến xe, trạm dừng chân, đầu ngõ quê nhà.
// Mỗi bối cảnh tự dựng hình và khai báo điểm mốc (chỗ đứng chờ, quầy, ghế, hàng WC, cổng, cửa nhà…) —
// scene.ts chỉ hỏi điểm mốc, không tự đặt toạ độ.
//
// Hệ toạ độ chung: xe đậu dọc trục x ở z = 0, cửa xe ở phía z âm (về phía bối cảnh); bối cảnh trải từ z ≈ -5 tới -19,
// camera nhìn từ z dương nên đồ cao (nhà, bảng hiệu) đặt phía sau (z nhỏ) để không che người.

import * as THREE from "three";
import { at, GEO, makePerson, mat, PERSON_SCALE, post, rounded, slab, soft } from "./art";
import { strip } from "./bend";
import {
  bench, blossomTree, floor, kumquatPot, LanternString, luggage, patternTexture, plasticStools, plasticTable, SIGN_BLUE,
  SIGN_RED, SignBoard, Steam, teaGlasses, tiledRoof,
} from "./props";
import { banhChungStack, blossomPot, cayNeu, chrysanthemumPot, DAO, flag, greetingBanner, MAI, watermelon } from "./tet";
import type { Region } from "./types";

export interface StageSet {
  group: THREE.Group;
  update(dt: number, t: number): void;
}

interface Rect { x0: number; x1: number; z0: number; z1: number }

const WALK_Y = 0.1;
const v = (x: number, z: number) => new THREE.Vector3(x, WALK_Y, z);

function shadowed(g: THREE.Object3D): void {
  g.traverse((o) => { if ((o as THREE.Mesh).isMesh && !o.userData.noShadow) { o.castShadow = true; o.receiveShadow = true; } });
}

// ---- bến xe -----------------------------------------------------------------------

const LUGGAGE_PILE: [number, "case" | "box"][] = [
  [0xc62828, "case"], [0x1e6fd9, "case"], [0xd9a441, "box"], [0x2e7d32, "case"], [0xc62828, "box"],
];

export class BenSet implements StageSet {
  group = new THREE.Group();
  /** Chỗ người vừa có vé đứng chờ trước khi ra xe. */
  readonly waiting: Rect = { x0: -9, x1: 7, z0: -12, z1: -9 };
  private lanterns: LanternString;
  private station = new SignBoard("BẾN XE", 9, 1.1);
  private laneBoards: SignBoard[] = [];
  private lanesKey = "";

  constructor() {
    const g = this.group;
    g.add(at(floor(30, 14, "tiles", 1.6), 0, 0.05, -11.5));

    // nhà chờ: tường sau + cột + mái
    g.add(at(rounded(24, 3.6, 0.6, 0.1, soft(0xf3e6cf, 0.8)), 0, 1.8, -18));
    const windows = at(rounded(20, 1.1, 0.1, 0.05, soft(0x2c4a66, 0.2, 0.4)), 0, 2.2, -17.65);
    g.add(windows);
    for (const x of [-10, -3.5, 3.5, 10]) g.add(at(rounded(0.4, 4.4, 0.4, 0.08, soft(0x8d6e63, 0.6)), x, 2.2, -13.8));
    g.add(at(rounded(23, 0.4, 4.8, 0.15, soft(0x9c2a1e, 0.6)), 0, 4.5, -15.8));
    g.add(at(slab(23, 0.14, 0.06, soft(0xf4c04e, 0.4, 0.3)), 0, 4.32, -13.4));  // nẹp vàng mép mái

    // biển gắn mép mái trước, lệch phải: đặt cao hơn thì nằm dưới khung lời kêu gọi, giữa thì sau bong bóng lơ xe
    g.add(at(this.station.mesh, 5, 4.55, -13.3));
    // bảng làn treo dưới mái (bến nhiều làn theo hướng — BRD-tuyen-xe): làn đang đón đỏ, làn đang chờ xanh
    for (const x of [1.4, 7.6, -4.8]) {
      const board = new SignBoard("", 5.6, 0.75, SIGN_BLUE);
      board.mesh.visible = false;
      this.laneBoards.push(board);
      g.add(at(board.mesh, x, 3.0, -13.25));
    }

    // ghế chờ, quầy vé, hành lý, chậu quất
    for (const x of [-7, -2, 2, 7]) g.add(at(bench(), x, 0, -16.2));
    const booth = at(rounded(2.4, 2.8, 2, 0.15, soft(0xc62828, 0.6)), -12.5, 1.4, -10);
    g.add(booth);
    g.add(at(rounded(1.6, 0.9, 0.06, 0.04, soft(0x2c4a66, 0.2, 0.4)), -12.5, 1.8, -8.97));
    const ticket = new SignBoard("BÁN VÉ", 2.2, 0.6);
    g.add(at(ticket.mesh, -12.5, 3.1, -8.98));
    LUGGAGE_PILE.forEach(([color, kind], i) => {
      g.add(at(luggage(color, kind), -10.4 + (i % 3) * 0.7, 0.05, -11.6 + Math.floor(i / 3) * 0.6));
    });
    for (const x of [-13.5, 12.5]) g.add(at(kumquatPot(), x, 0.05, -14));
    // đồ Tết (PLAN-129): băng rôn trên tường nhà chờ, chậu đào / mai hai đầu, cúc vàng chân cột, cờ hai góc mái
    g.add(at(greetingBanner(12, 0.65, 0), 0, 3.2, -17.62));
    g.add(at(blossomPot(DAO), -14.2, 0.05, -12.4), at(blossomPot(MAI), 13.8, 0.05, -11.6));
    for (const x of [-10.6, -9.4, 9.4, 10.6]) g.add(at(chrysanthemumPot(), x, 0.05, -13.2));
    for (const side of [-1, 1]) {
      const pole = at(flag(1.8), side * 11.3, 4.6, -13.5);
      pole.rotation.set(0.35, side < 0 ? Math.PI : 0, -0.45);
      g.add(pole);
    }

    this.lanterns = new LanternString(new THREE.Vector3(-10, 3.9, -13.6), new THREE.Vector3(10, 3.9, -13.6), 9, 0.3);
    g.add(this.lanterns.group);

    // vài người đứng chờ có vali (cảnh nền)
    for (let i = 0; i < 5; i++) {
      const p = at(makePerson((i * 67 + 20) % 360), -8 + i * 3.6, WALK_Y, -14.6 + (i % 2) * 0.8);
      g.add(p, at(luggage([0xc62828, 0x1e6fd9, 0x6a1b9a][i % 3]), -7.3 + i * 3.6, 0.05, -14.4 + (i % 2) * 0.8));
    }
    shadowed(g);
  }

  setStation(name: string): void {
    this.station.set(name.toUpperCase());
  }

  /** Bảng làn: «⬆ HƯỚNG HÀ NỘI · ĐANG ĐÓN» / «⬇ HƯỚNG CÀ MAU · 7 CHỜ». Bến có tới 6 làn mà chỉ 3 bảng: làn đang đón
   * luôn có bảng, rồi tới làn đông người chờ. */
  setLanes(lanes: { label: string; arrow: string; waiting: number; current: boolean }[]): void {
    const key = JSON.stringify(lanes);
    if (key === this.lanesKey) return;
    this.lanesKey = key;
    const shown = [...lanes].sort((a, b) => Number(b.current) - Number(a.current) || b.waiting - a.waiting);
    this.laneBoards.forEach((board, i) => {
      const lane = shown[i];
      board.mesh.visible = !!lane;
      if (!lane) return;
      board.recolor(lane.current ? SIGN_RED : SIGN_BLUE);
      board.set(`${lane.arrow} ${lane.label.toUpperCase()} · ${lane.current ? "ĐANG ĐÓN" : `${lane.waiting} CHỜ`}`);
    });
  }

  update(_dt: number, t: number): void {
    this.lanterns.update(t);
  }
}

// ---- trạm dừng chân ------------------------------------------------------------------

const TABLES: [number, number][] = [[-9.2, -9.4], [-6.2, -9.4], [-9.2, -6.6], [-6.2, -6.6]];
const STAND_COLS = 5;  // hết ghế: đứng ăn 5 người / hàng ở sân trống cạnh bàn (x −4,2 → 0,6, chừa chỗ hàng WC)
const WC_ROW = 9;  // hàng chờ WC: 9 người / hàng

export class RestSet implements StageSet {
  group = new THREE.Group();
  /** Chỗ người ngồi ăn (ghế nhựa quanh bàn) — người gọi món đi tới quầy rồi ngồi một ghế. */
  readonly seats: THREE.Vector3[] = [];
  readonly shop = v(5, -13.4);
  // Chỗ ăn đang có người (PLAN-133). Trước đây xếp xoay vòng theo lượt (`lượt % 16`): người thứ 17 ngồi đè lên người đang
  // ngồi, tên chồng khít lên nhau; hàng WC từ người thứ 10 cũng đứng chung một điểm.
  private taken = new Set<number>();
  private shopSign = new SignBoard("ĐẶC SẢN", 4.4, 0.75);
  private steam: Steam;
  private lanterns: LanternString;

  constructor() {
    const g = this.group;
    g.add(at(floor(30, 15, "tiles", 2), 0, 0.05, -12));

    // quán: tường, cửa, mái ngói, mái bạt sọc che quầy
    g.add(at(rounded(12, 3.2, 3.6, 0.1, soft(0xf6e3bf, 0.85)), -3, 1.6, -17.2));
    g.add(at(rounded(2.2, 2.2, 0.08, 0.04, soft(0x6d4c41, 0.7)), -3, 1.1, -15.36));
    const roof = at(tiledRoof(12.8, 4.6, 1.4), -3, 3.2, -17.2);
    g.add(roof);
    const awning = new THREE.Mesh(strip(9, 2.4),
      new THREE.MeshStandardMaterial({ map: patternTexture("awning", 4, 1), side: THREE.DoubleSide, roughness: 0.8 }));
    awning.rotation.x = -Math.PI / 2 + 0.35;
    g.add(at(awning, -3, 2.9, -14.3));
    // lệch hẳn sang phải, trên biển sạp: bên trái màn hình là chỗ bong bóng lơ xe
    g.add(at(new SignBoard("TRẠM DỪNG CHÂN", 4.4, 0.9).mesh, 3.6, 4.3, -14.75));

    // quầy phở: nồi bốc hơi, chồng bát, ly trà
    g.add(at(rounded(6, 1.1, 1.0, 0.08, soft(0x8d5a3a, 0.7)), -3, 0.55, -13.4));
    const pot = at(new THREE.Mesh(GEO.cylSmooth, soft(0xb8bec6, 0.25, 0.8)), -5, 1.4, -13.4);
    pot.scale.set(0.5, 0.6, 0.5);
    g.add(pot);
    for (let i = 0; i < 4; i++) {
      const bowl = at(new THREE.Mesh(GEO.half, soft(0xffffff, 0.3)), -3.2, 1.12 + i * 0.1, -13.4);
      bowl.scale.set(0.3, -0.16, 0.3);
      g.add(bowl);
    }
    this.steam = new Steam(new THREE.Vector3(-5, 1.8, -13.4));
    g.add(this.steam.points);

    // bàn nhựa xanh + ghế nhựa đỏ xanh + ly trà đá trên bàn
    const stoolSpots: THREE.Vector3[] = [];
    const cups: THREE.Vector3[] = [];
    for (const [x, z] of TABLES) {
      g.add(at(plasticTable(0x1e88e5), x, 0, z));
      for (const [dx, dz] of [[-0.95, 0], [0.95, 0], [0, -0.95], [0, 0.95]]) stoolSpots.push(new THREE.Vector3(x + dx, 0, z + dz));
      cups.push(new THREE.Vector3(x - 0.25, 0.76, z + 0.2), new THREE.Vector3(x + 0.3, 0.76, z - 0.15));
    }
    g.add(plasticStools(stoolSpots), teaGlasses(cups));
    this.seats.push(...stoolSpots.map((p) => v(p.x, p.z)));

    // sạp đặc sản: kệ + hộp quà nhiều màu
    g.add(at(rounded(3.4, 1.0, 1.4, 0.08, soft(0x8d5a3a, 0.7)), 5, 0.5, -15));
    g.add(at(rounded(3.6, 0.12, 1.8, 0.05, soft(0xc62828, 0.6)), 5, 2.6, -15));
    for (const x of [3.4, 6.6]) g.add(at(post(0.06, 2.6, soft(0x6d4c41, 0.7)), x, 1.3, -14.3));
    const colors = [0xc62828, 0xf4c04e, 0x2e7d32, 0xd84315, 0x6a1b9a];
    for (let i = 0; i < 8; i++) {
      g.add(at(rounded(0.55, 0.4, 0.4, 0.04, soft(colors[i % colors.length], 0.6)), 3.8 + (i % 4) * 0.8, 1.22 + Math.floor(i / 4) * 0.42, -15));
    }
    g.add(at(this.shopSign.mesh, 5, 3.1, -14.2));

    // nhà vệ sinh
    g.add(at(rounded(3, 3, 2.8, 0.12, soft(0xe9f0f7, 0.7)), 10, 1.5, -15.4));
    g.add(at(rounded(0.9, 1.9, 0.06, 0.04, soft(0x1e6fd9, 0.5)), 10, 0.95, -13.98));
    g.add(at(new SignBoard("WC", 1.6, 0.7, { bg: "#1e6fd9", fg: "#ffffff", rim: "#ffffff" }).mesh, 10, 3.4, -13.98));

    g.add(at(kumquatPot(), -10.5, 0.05, -14.2), at(kumquatPot(), 1.2, 0.05, -14.4));
    g.add(at(blossomPot(MAI), 13.6, 0.05, -13.2));
    for (const x of [2.4, 7.4]) g.add(at(chrysanthemumPot(), x, 0.05, -14.1));
    this.lanterns = new LanternString(new THREE.Vector3(-8.5, 3.2, -12.6), new THREE.Vector3(2.5, 3.2, -12.6), 6, 0.3);
    g.add(this.lanterns.group);
    shadowed(g);
  }

  /** Người gọi món đứng trước quầy (rải dọc quầy cho khỏi chồng lên nhau). */
  counterSpot(i: number): THREE.Vector3 {
    return v(-5 + (i % 5) * 1.0, -12.5);
  }

  /** Lấy chỗ ăn trống có số nhỏ nhất (ghế trước, hết ghế thì chỗ đứng); người rời cảnh thì `freeSpot`. */
  takeSpot(): number {
    let i = 0;
    while (this.taken.has(i)) i++;
    this.taken.add(i);
    return i;
  }

  freeSpot(i: number): void {
    this.taken.delete(i);
  }

  /** Toạ độ chỗ ăn thứ i: 16 ghế, rồi đứng ăn ở sân trống cạnh bàn (STAND_COLS người / hàng, từ quầy ra phía xe). */
  eatSpot(i: number): THREE.Vector3 {
    if (i < this.seats.length) return this.seats[i].clone();
    const k = i - this.seats.length;
    return v(-4.2 + (k % STAND_COLS) * 1.2, -10.6 + Math.floor(k / STAND_COLS) * 1.3);
  }

  /** Vị trí thứ i trong hàng chờ WC (xếp từ cửa ra phía trái, đủ WC_ROW người thì xuống hàng). */
  wcQueue(i: number): THREE.Vector3 {
    return v(10 - 1.1 * (i % WC_ROW), -13.1 + 1.1 * Math.floor(i / WC_ROW));
  }

  setSpecialty(text: string): void {
    this.shopSign.set(text ? `ĐẶC SẢN: ${text}` : "ĐẶC SẢN");
  }

  update(dt: number, t: number): void {
    this.steam.update(dt, t);
    this.lanterns.update(t);
  }
}

// ---- đầu ngõ quê nhà -------------------------------------------------------------------

const GATE_Z = -9.6;
const HOUSE_Z = -17;

export class HomeSet implements StageSet {
  group = new THREE.Group();
  /** Lối vào: người xuống xe đi qua cổng rồi vào cửa nhà. */
  readonly gate = v(0, GATE_Z - 0.4);
  readonly door = v(1.5, HOUSE_Z + 2.1);
  /** Nổ trước mái nhà, thấp vừa đủ để không nằm dưới băng rôn thả khách ở đầu màn hình. */
  readonly fireworksAt = new THREE.Vector3(1.5, 5.5, GATE_Z - 1);
  /** Ông bà + cháu đứng chờ trong sân, vẫy tay. */
  readonly family: THREE.Group[] = [];
  private plaque = new SignBoard("CHÀO MỪNG VỀ QUÊ", 4.4, 0.9);
  private tree = new THREE.Group();
  // đào (Bắc) / mai (nơi khác): dựng sẵn cả hai lúc khởi động, đổi thì bật / tắt — dựng lúc thả khách là cây chưa uốn
  // theo đường + biên dịch shader ngay lúc người xem đang nhìn (PLAN-133)
  private trees = new Map<number, THREE.Group>([DAO, MAI].map((c) => [c, blossomTree(c)]));
  private steam: Steam;
  private fire: THREE.MeshStandardMaterial;
  private lanterns: LanternString;

  constructor() {
    const g = this.group;
    g.add(at(floor(30, 15, "tiles", 2.2), 0, 0.04, -12.5));
    g.add(at(floor(2, HOUSE_Z + 2.2 - GATE_Z, "bricks", 0.8), 0.75, 0.06, (GATE_Z + HOUSE_Z + 2.2) / 2));

    // cổng làng: hai trụ + mái ngói nhỏ + biển tên quê + câu đối
    const ochre = soft(0xc9893f, 0.8);
    for (const x of [-1.9, 1.9]) g.add(at(rounded(0.7, 3.4, 0.7, 0.08, ochre), x, 1.7, GATE_Z));
    g.add(at(rounded(4.6, 0.5, 0.9, 0.06, ochre), 0, 3.5, GATE_Z));
    g.add(at(tiledRoof(5.4, 1.6, 0.6), 0, 3.75, GATE_Z));
    g.add(at(this.plaque.mesh, 0, 3.05, GATE_Z + 0.47));
    for (const [x, text] of [[-1.9, "AN KHANG"], [1.9, "THỊNH VƯỢNG"]] as const) {
      const panel = new SignBoard(text, 2.6, 0.5);
      panel.mesh.rotation.z = Math.PI / 2;
      g.add(at(panel.mesh, x, 1.8, GATE_Z + 0.37));
    }

    // hàng rào tre hai bên cổng (gộp một lần vẽ)
    const posts: THREE.Vector3[] = [];
    for (let x = -14; x <= 14; x += 0.45) if (Math.abs(x) > 2.4) posts.push(new THREE.Vector3(x, 0.6, GATE_Z));
    const fence = new THREE.InstancedMesh(GEO.cyl, soft(0xc8b06a, 0.8), posts.length);
    const m4 = new THREE.Matrix4();
    posts.forEach((p, i) => fence.setMatrixAt(i, m4.compose(p, new THREE.Quaternion(), new THREE.Vector3(0.08, 1.2, 0.08))));
    g.add(fence);
    for (const y of [0.4, 0.9]) {
      for (const side of [-1, 1]) {
        g.add(at(slab(11.6, 0.06, 0.06, soft(0xb0974f, 0.8)), side * 8.2, y, GATE_Z));  // nẹp ngang hàng rào
      }
    }

    // nhà: tường vàng, hiên cột, mái ngói, cửa gỗ, cửa sổ, câu đối, đèn lồng hiên
    g.add(at(rounded(10, 3, 3.6, 0.1, soft(0xf6d36b, 0.85)), 1.5, 1.5, HOUSE_Z));
    g.add(at(tiledRoof(11.4, 6.2, 1.8), 1.5, 3, HOUSE_Z + 0.6));
    for (const x of [-3, 0, 3, 6]) g.add(at(rounded(0.3, 3, 0.3, 0.06, soft(0x8d5a3a, 0.7)), x, 1.5, HOUSE_Z + 2.6));
    g.add(at(rounded(1.6, 2.2, 0.08, 0.04, soft(0x6d3b22, 0.6)), 1.5, 1.1, HOUSE_Z + 1.84));
    for (const x of [-1.6, 4.6]) g.add(at(rounded(1.3, 1.0, 0.08, 0.04, soft(0x2c4a66, 0.2, 0.4)), x, 1.7, HOUSE_Z + 1.84));
    for (const [x, text] of [[0.4, "PHÚC"], [2.6, "LỘC"]] as const) {
      const p = new SignBoard(text, 1.4, 0.45);
      p.mesh.rotation.z = Math.PI / 2;
      g.add(at(p.mesh, x, 1.4, HOUSE_Z + 1.86));
    }
    this.lanterns = new LanternString(new THREE.Vector3(-3, 3, HOUSE_Z + 2.6), new THREE.Vector3(6, 3, HOUSE_Z + 2.6), 4, 0.2);
    g.add(this.lanterns.group);

    // mâm ngũ quả trên bàn ở hiên
    g.add(at(rounded(1.6, 0.9, 0.8, 0.05, soft(0x7a3b1d, 0.6)), -1.6, 0.45, HOUSE_Z + 2.4));
    const fruits = [0xffc107, 0x8bc34a, 0xff7043, 0xe53935, 0xfff176];
    fruits.forEach((c, i) => {
      const f = at(new THREE.Mesh(GEO.sphere, soft(c, 0.5)), -2.1 + i * 0.25, 1.05 + (i % 2) * 0.12, HOUSE_Z + 2.4);
      f.scale.setScalar(0.17);
      g.add(f);
    });

    // nồi bánh chưng trên bếp củi, bốc hơi, lửa lập loè
    const potX = 7;
    const potZ = -12.6;
    for (let i = 0; i < 3; i++) {
      const stone = at(new THREE.Mesh(GEO.ball, mat(0x6b6b6b)), potX + Math.cos(i * 2.1) * 0.55, 0.2, potZ + Math.sin(i * 2.1) * 0.55);
      stone.scale.setScalar(0.28);
      g.add(stone);
    }
    this.fire = new THREE.MeshStandardMaterial({ color: 0xff7a1a, emissive: 0xff5a00, emissiveIntensity: 1.5 });
    const flame = at(new THREE.Mesh(GEO.cone, this.fire), potX, 0.35, potZ);
    flame.scale.set(0.35, 0.6, 0.35);
    const pot = at(new THREE.Mesh(GEO.cylSmooth, soft(0x3a3a3a, 0.5, 0.4)), potX, 0.95, potZ);
    pot.scale.set(0.7, 0.9, 0.7);
    g.add(flame, pot);
    this.steam = new Steam(new THREE.Vector3(potX, 1.5, potZ), 16, 2.8);
    g.add(this.steam.points);

    this.trees.forEach((tree) => { tree.visible = false; });  // chưa có khách về: setPlace bật đúng cây
    this.tree.add(...this.trees.values());
    g.add(at(this.tree, -6.5, 0, -13.5), at(kumquatPot(), 5.5, 0.05, HOUSE_Z + 2.8));
    // sân Tết (PLAN-129): cây nêu, dưa hấu bổ đôi, chồng bánh chưng cạnh nồi, cúc hai bên cửa, cờ trên trụ cổng
    g.add(at(cayNeu(), 4.3, 0.05, -11.2));  // bên phải lối vào: bên trái là chỗ bong bóng lơ xe
    g.add(at(watermelon(), -3.3, 0.05, HOUSE_Z + 3.1), at(watermelon(), -2.7, 0.05, HOUSE_Z + 3.3));
    g.add(at(banhChungStack(), potX + 1.6, 0.05, potZ - 1.0));
    for (const x of [-0.6, 3.6]) g.add(at(chrysanthemumPot(), x, 0.06, HOUSE_Z + 2.3));
    const pole = at(flag(1.6), 2.15, 3.0, GATE_Z);
    pole.rotation.z = -0.5;
    g.add(pole);

    // gia đình đứng trước cổng, bên trái lối vào (đứng trong sân thì mái cổng che mất)
    for (const [i, hue] of [[0, 20], [1, 200], [2, 330]] as const) {
      const p = makePerson(hue);
      p.scale.setScalar((i === 2 ? 0.7 : 1) * PERSON_SCALE);
      this.family.push(p);
      g.add(at(p, -4.6 + i * 1.0, WALK_Y, GATE_Z + 1.3));
    }
    shadowed(g);
  }

  /** Biển cổng làng ghi tên tỉnh người vừa về; cây đào miền Bắc, mai nơi khác. */
  setPlace(province: string, region: Region): void {
    this.plaque.set(`CHÀO MỪNG VỀ ${province.toUpperCase()}`);
    const color = region === "bac" ? DAO : MAI;
    this.trees.forEach((tree, c) => { tree.visible = c === color; });
  }

  update(dt: number, t: number): void {
    this.steam.update(dt, t);
    this.lanterns.update(t);
    this.fire.emissiveIntensity = 1.3 + Math.sin(t * 13) * 0.3 + Math.sin(t * 7.3) * 0.2;
  }
}
