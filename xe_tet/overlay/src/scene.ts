// Cảnh 3D low-poly: đường cuộn, xe khách 24 giường, bến xe, trạm dừng chân, đầu ngõ, bên trong xe.
// Chỉ vẽ theo state/sự kiện từ server — không tự quyết luật chơi.

import * as THREE from "three";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { animatePerson, at, BERTHS, BERTHS_PER_FLOOR, box, Bus, CROWD, hueColor, label, makePerson, mat, Petals, SkyDome } from "./art";
import { Landscape } from "./landscape";
import { Roadway } from "./road";
import { bendTree, setBend } from "./bend";
import { BLOSSOM_TEX, Fireworks, Floaters, LANTERN_TEX, LIXI_TEX, Puffs } from "./effects";
import { BenSet, HomeSet, RestSet, type StageSet } from "./sets";
import { DAO, MAI } from "./tet";
import { Tunnel } from "./tunnel";
import { Weather } from "./weather";
import type { CamName, Control, GameEvent, Phase, Quality, Region, Route, Seat, State } from "./types";

export const W = 1080;
export const H = 1920;
const BASE_SPEED = 14; // đơn vị / giây khi speed = 1
const INSIDE_X = 500; // khoang trong xe đặt riêng một chỗ, camera riêng

// Góc máy ngoài xe admin chọn: [vị trí camera x, y, z, điểm nhìn x, y, z]
// P1 — Hạ góc nhìn xuống vừa phải + nhìn chếch theo hành trình để thấy rõ bầu trời, dãy núi, mái nhà, tán cây và dáng xe 3D
const CAMS: Record<CamName, [number, number, number, number, number, number]> = {
  wide: [8.5, 23.5, 33.5, 0.8, 1.8, -10.5], // toàn cảnh: thấy cả xe, đường quê, nhà mái ngói và chân trời/núi xa
  high: [0, 54, 14, 0, 0.5, -9], // từ trên cao
  side: [4.5, 8.0, 27.5, 0.0, 2.3, -4.5], // ngang xe: góc thấp điện ảnh thấy trọn thân xe + nhà ngói 3 gian + núi xa
  close: [14.2, 8.4, 21.5, 0.4, 2.1, -1.5], // cận xe (góc trước 3/4 nhìn trọn đầu xe + thân xe + 2 bánh xe + cảnh quê)
};
// đang chiếu video bảng quảng cáo: máy quay ngước lên khung bảng (sau xe), xe vẫn trong khung dưới
const SHOW_CAM: [number, number, number, number, number, number] = [3.5, 8.5, 25, 0.5, 6.2, -8.5];
const BOARD_H = 9.5;  // chiều cao màn bảng quảng cáo (đơn vị cảnh)
const URL_PARAMS = new URLSearchParams(location.search);
// ?res=0.5: vẽ nửa độ phân giải (thử trên máy không GPU); chất lượng «thấp» trên /control hạ tiếp xuống tối đa 0,6
// ?hour=10: ép giờ trong ngày khi thử (chụp ảnh ban ngày lúc nửa đêm); bỏ trống thì theo đồng hồ trên xe (PLAN-130:
// giờ xuất bến + giờ xe chạy — chuyến 26 tiếng thì trời qua một ngày một đêm), ở bến theo đồng hồ thật.
const FORCE_HOUR = URL_PARAMS.has("hour") ? Number(URL_PARAMS.get("hour")) : null;
const BASE_RES = Math.min(1, Math.max(0.25, Number(URL_PARAMS.get("res")) || 1));
const LOW_RES = 0.6;
const PREBUILD_GAP = 3;  // giây giữa hai lần dựng sẵn một vùng (rải ra, không khựng một lúc)
const MEDIUM_RES = 0.75;  // «Vừa»: ~56 % số điểm ảnh — TikTok nén hình về ~720p, trên điện thoại gần như không khác «Cao»
/**
 * Chỗ pháo hoa nổ: giữa cảnh, cao 5, sau xe 6 — tính theo cả 4 góc máy rơi vào khoảng trống giữa màn hình
 * (dưới bảng chữ / băng rôn ở trên, trên thân xe). Đặt cao hơn thì băng rôn che mất.
 */
const SHOW_SKY = new THREE.Vector3(0, 5, -6);
const DUST = 0xc8a878;
// Hình đường (PLAN-124), 1 đơn vị ≈ 1 m (xe dài 12). Bán kính cua theo độ quanh co đo trên đường thật (độ đổi hướng /
// km, routes.json): đồng bằng / cao tốc 10–16 → thẳng (cao tốc thật ≥ ~650 m); 18 → 140 °/km: 600 m → 40 m (đèo thật
// 15–60 m). Dốc dọc: đèo 8 % (thật 7–10 %) lên trước đỉnh, xuống sau đỉnh; đồi theo vùng ≤ 4 %; đồng bằng ≤ 1,5 %; hầm phẳng.
const HILLS: Record<Region, number> = { bac: 0.6, trung: 0.35, taynguyen: 0.7, nam: 0.08 };
const STRAIGHT_WIND = 18;
const TWISTY_WIND = 140;
const R_GENTLE = 600;
const R_TIGHT = 40;
const GRADE_PASS = 0.08;
const GRADE_HILLS = 0.04;
const GRADE_FLAT = 0.015;
const HILL_CREST = 0.0016;  // độ cong dọc của đồi lượn (đỉnh dốc / lòng chảo)
const HILL_WAVE = 400;  // một nhịp đồi lên – xuống (m)
const ROLL_PER_ACCEL = 0.015;  // xe nghiêng (rad) theo gia tốc ngang v² / R
const MAX_ROLL = 0.1;  // ~6°
const CLIMB_SLOW = 0.3;  // leo đèo hết dốc: cảnh trôi chậm 30 % (xe khách leo đèo ì ạch)

/** Bán kính cua (m) theo độ quanh co; Infinity = đường thẳng. Nội suy theo thang log: cảm giác «gắt dần» đều tay. */
function radiusFor(wind: number): number {
  if (wind <= STRAIGHT_WIND) return Infinity;
  const t = THREE.MathUtils.clamp((wind - STRAIGHT_WIND) / (TWISTY_WIND - STRAIGHT_WIND), 0, 1);
  return R_GENTLE * Math.pow(R_TIGHT / R_GENTLE, t);
}
const MAX_BUBBLES = 6;
const BOARD_STEP_S = 1.0;  // bến, khi tắt giọng lơ xe: mỗi giây một người bước lên xe
const BOARD_FALLBACK_S = 32;  // đứng quá lâu mà chưa nghe đọc tên (giọng lỗi / bị cắt) thì vẫn lên — khớp FULL_HOLD_MAX của server (35 giây)
const LINE_COLS = 8;  // hàng chờ ở cửa xe gập dòng sau 8 người
const PICKUP_STEP_S = 1.3;  // dừng đón bên đường: khớp PICKUP_STOP_STEP của server
const BUBBLE_MS = 5000;
const EXHAUST = 0x6f6f72;
const LABEL_GAP = 4;  // px giữa hai nhãn tên bị đẩy
const MAX_NUDGE = 140;  // px: đẩy xa hơn thì nhãn rời khỏi người của nó
const NUDGE_EASE = 0.3;  // nhãn trượt tới chỗ mới (không nhảy giật khi người đi ngang nhau)
const _vp = new THREE.Matrix4();
const _lp = new THREE.Vector3();
const _step = new THREE.Vector3();  // hướng đi của người đi bộ: dùng lại mỗi khung, không tạo vật mới (đỡ dọn rác bộ nhớ)

interface LabelBox {
  el: HTMLElement;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
  prio: number;
  distSq: number;
}

type SetName = "ben" | "road" | "rest" | "home";
type View = "outside" | "inside";

const SET_OF: Record<Phase, SetName> = {
  BOARDING: "ben", FINISH: "ben", DRIVING: "road", SPECIAL: "road", REST: "rest", DROPOFF: "home",
};


// CSS2DObject chỉ tự gỡ nhãn khi chính nó bị remove; xoá cả nhóm thì phải gỡ tay.
function dropLabels(obj: THREE.Object3D): void {
  obj.traverse((o) => { if (o instanceof CSS2DObject) o.element.remove(); });
}

// ---- trời theo đồng hồ trên xe ---------------------------------------------------

interface Look {
  top: number; horizon: number;  // đỉnh trời, chân trời (= màu sương)
  hemiSky: number; hemiGround: number; hemi: number;  // ánh sáng trời hắt xuống / đất hắt lên
  sunColor: number; sun: number;  // nắng (ban đêm: trăng xanh lạnh)
  exposure: number;
}

const LOOKS: Record<"dawn" | "day" | "dusk" | "night", Look> = {
  dawn: { top: 0x567ec2, horizon: 0xffb47e, hemiSky: 0xffe2c2, hemiGround: 0x5c4f3b, hemi: 1.05, sunColor: 0xffc282, sun: 2.35, exposure: 1.04 },
  day: { top: 0x3586d0, horizon: 0xffe2b5, hemiSky: 0xfff0d4, hemiGround: 0x5a623c, hemi: 1.08, sunColor: 0xffe8c2, sun: 2.75, exposure: 1.03 },
  dusk: { top: 0x364886, horizon: 0xff8e56, hemiSky: 0xffcca6, hemiGround: 0x4f4339, hemi: 1.02, sunColor: 0xff9a58, sun: 2.25, exposure: 1.06 },
  // đêm Tết: trời xanh thẫm + ánh trăng đủ sáng để nhìn rõ xe / người trên điện thoại
  night: { top: 0x1b3672, horizon: 0x465d98, hemiSky: 0xaab9ea, hemiGround: 0x484256, hemi: 1.0, sunColor: 0xc8d4ff, sun: 1.15, exposure: 1.0 },
};

// mốc giờ → cảnh trời; giữa hai mốc pha màu dần (đồng hồ xe chạy nhanh: không đổi trời giật cục)
const SKY_KEYS: [number, keyof typeof LOOKS][] = [
  [0, "night"], [4.6, "night"], [5.8, "dawn"], [7.2, "day"], [16.6, "day"], [17.8, "dusk"], [19, "night"], [24, "night"],
];
const SKY_CATCH_UP = 1.5;  // giờ / giây: đồng hồ nhảy (xe về bến → giờ thật) thì trời chuyển dần, không cắt
const tmpA = new THREE.Color();
const tmpB = new THREE.Color();
const mixHex = (a: number, b: number, f: number) => tmpA.setHex(a).lerp(tmpB.setHex(b), f).getHex();

function lookAt(hour: number): Look {
  const h = ((hour % 24) + 24) % 24;
  const i = SKY_KEYS.findIndex(([at], k) => h >= at && h < SKY_KEYS[k + 1][0]);
  const [h0, a] = SKY_KEYS[i];
  const [h1, b] = SKY_KEYS[i + 1];
  const f = (h - h0) / (h1 - h0);
  const from = LOOKS[a];
  const to = LOOKS[b];
  if (from === to) return from;
  return {
    top: mixHex(from.top, to.top, f), horizon: mixHex(from.horizon, to.horizon, f),
    hemiSky: mixHex(from.hemiSky, to.hemiSky, f), hemiGround: mixHex(from.hemiGround, to.hemiGround, f),
    hemi: from.hemi + (to.hemi - from.hemi) * f, sunColor: mixHex(from.sunColor, to.sunColor, f),
    sun: from.sun + (to.sun - from.sun) * f, exposure: from.exposure + (to.exposure - from.exposure) * f,
  };
}

const isNight = (hour: number) => { const h = ((hour % 24) + 24) % 24; return h < 5.4 || h >= 18.4; };
const realHour = () => { const d = new Date(); return d.getHours() + d.getMinutes() / 60; };

// ---- người đi bộ -------------------------------------------------------------

interface Walker {
  obj: THREE.Object3D;
  path: THREE.Vector3[];
  speed: number;
  wait: number;
  phase: number;
  hold: boolean; // hết đường thì đứng yên (hàng WC) thay vì biến mất
  onDone?: () => void;
  onRemove?: () => void;  // rời cảnh (về tới xe, đổi cảnh, quá trần): trả chỗ ăn
  name?: string;  // hàng lên xe ở bến: tên người (khớp tên lơ xe đọc)
  queuedAt?: number;  // lúc đứng vào hàng
  callAt?: number;  // lúc lơ xe đọc tới tên mình → bước lên
}

// ---- thế giới ---------------------------------------------------------------

/** Biển chỉ đường: các điểm sắp tới (điểm trả + tỉnh đi qua, bỏ trạm dừng), km còn lại tính từ xe. */
function aheadRows(route: Route): { name: string; km: number }[] {
  const next = [...route.stops.filter((x) => x.kind === "stop" && !x.done), ...(route.via ?? []).filter((v) => !v.done)]
    .filter((x) => x.km > route.odo)
    .sort((a, b) => a.km - b.km);
  const rows: { name: string; km: number }[] = [];
  for (const x of next) {
    if (!rows.some((r) => r.name === x.name)) rows.push({ name: x.name, km: x.km - route.odo });
    if (rows.length === 5) break;  // biển ở xa bỏ dòng đã qua, còn đủ 3 dòng
  }
  return rows;
}

export class World {
  private renderer: THREE.WebGLRenderer;
  private labels: CSS2DRenderer;
  private scene = new THREE.Scene();
  private camOut = new THREE.PerspectiveCamera(42, W / H, 0.5, 600);
  private camIn = new THREE.PerspectiveCamera(42, W / H, 1, 200);
  private hemi = new THREE.HemisphereLight(0xfff4e0, 0x6a7a48, 1.25);
  private sun = new THREE.DirectionalLight(0xfff0d6, 2.4);
  private sky = new SkyDome();
  private petals = new Petals();
  private stars: THREE.Points;
  private bus = new Bus();
  private road = new Roadway();
  private land = new Landscape();
  private tunnel = new Tunnel();
  private inTunnel = false;
  private look: Look = LOOKS.day;
  private weather = new Weather();
  private ben = new BenSet();
  private rest = new RestSet();
  private home = new HomeSet();
  private stages: Record<Exclude<SetName, "road">, StageSet> = { ben: this.ben, rest: this.rest, home: this.home };
  private seatTurn = 0;
  private inside = new THREE.Group();
  private berths: { blanket: THREE.Mesh; head: THREE.Group; tag: CSS2DObject; bubbleAt: THREE.Vector3 }[] = [];
  private bubbles: CSS2DObject[] = [];  // bong bóng chat đang hiện (giới hạn MAX_BUBBLES)
  private walkers: Walker[] = [];
  private wcLine: Walker[] = [];
  private boardLine: Walker[] = [];  // bến: hàng người có vé chờ bước lên xe (PLAN-145)
  private roadside: Walker[] = [];
  private blockProp: THREE.Group | null = null;  // trạm thu phí / chốt công an trước đầu xe (PLAN-148)
  private blockArm: THREE.Object3D | null = null;  // cần barie (mở khi góp đủ)
  private blockLeaving = false;
  private showCam = false;
  private board: { group: THREE.Group; video: HTMLVideoElement; tex: THREE.VideoTexture; url: string } | null = null;  // người chờ ở điểm đón bên đường; xe chạy lại mà máy chậm chưa kịp bước thì coi như đã lên
  private boardTimer = 0;
  private fx = new Fireworks();
  private dust = new Puffs(72);
  // hiệu ứng quà (PLAN-142): mỗi món một kiểu — sprite gom sẵn, có trần
  private lixi = new Floaters(LIXI_TEX, 24, { scale: 0.9, rise: 2.4, sway: 0.8, life: 4 });
  private skyLanterns = new Floaters(LANTERN_TEX, 12, { scale: 1.4, rise: 1.5, sway: 0.5, life: 7 });
  private blossoms = new Floaters(BLOSSOM_TEX, 40, { scale: 0.7, rise: -1.6, sway: 1.2, life: 6 });
  private blossomColor = 0xffd23f;
  private dustTimer = 0;
  private quality: Quality = "high";
  private frameNo = 0;
  private prebuildWait = PREBUILD_GAP;
  private shape = { curve: 0, grade: 0, crest: 0 };  // độ uốn đường đang hiển thị (đổi mượt)
  private curvePhase = 0;
  private hillPhase = 0;
  private bendSweep = 0;
  private fade: HTMLElement;
  onView?: (view: View) => void;
  onVideo?: (video: HTMLVideoElement | null) => void;  // bảng quảng cáo: tiếng video đi qua bộ trộn âm thanh

  private state: State | null = null;
  private set: SetName = "ben";
  private view: View = "outside";
  private region: Region | null = null;
  private seatsKey = "";
  private speed = 0;
  private t = 0;
  private night = false;
  private skyHour: number | null = null;  // giờ trời đang vẽ (đuổi theo đồng hồ trên xe)
  private skyCheck = 0;
  private switching = false;
  private wcTimer = 0;
  private early: GameEvent[] = []; // sự kiện trạm / thả khách tới trước khi cảnh kịp đổi
  private control: Control = { view: "outside", cam: "wide", zoom: 1, fade: false };
  private camPos = new THREE.Vector3();
  private camLook = new THREE.Vector3();
  private camPosTo = new THREE.Vector3();
  private camLookTo = new THREE.Vector3();
  private labelSize = new WeakMap<HTMLElement, { w: number; h: number }>();  // đo một lần: tên không đổi chữ
  private labelNudge = new WeakMap<HTMLElement, number>();  // độ đẩy đang hiển thị (px, âm = lên)

  constructor(canvas: HTMLCanvasElement, labelsEl: HTMLElement, fade: HTMLElement) {
    this.fade = fade;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(BASE_RES);
    this.renderer.setSize(W, H, false);
    // màu kiểu điện ảnh + bóng đổ mềm (chỉ tính quanh khu xe cho nhẹ máy)
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    // three 0.187 bỏ PCFSoft, tự đổi sang PCF ở lượt vẽ bóng đầu tiên — để PCFSoft thì warmUp biên dịch sẵn nhầm biến thể
    // (bóng «basic»), vật ngoài khung hình (hơi nồi đầu ngõ) vẫn biên dịch lại giữa trận. Hình y như trước.
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.labels = new CSS2DRenderer({ element: labelsEl });
    this.labels.setSize(W, H);
    // không xếp chồng nhãn theo độ sâu mỗi khung (duyệt cả cây cảnh + ghi zIndex từng nhãn); nhãn sinh sau nằm trên — đủ
    this.labels.sortObjects = false;

    this.aimCamera(true);
    this.camIn.position.set(INSIDE_X, 66, 1);
    this.camIn.lookAt(INSIDE_X, 0, -8.5);

    this.scene.fog = new THREE.Fog(0xffe5bd, 42, 220);
    // Tạo môi trường phản chiếu Stylized (bầu trời ấm + nắng chiều + mặt đất) để kính xe, sơn xe và inox có ánh bóng tự nhiên
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const envScene = new THREE.Scene();
    const envSky = new THREE.Mesh(
      new THREE.SphereGeometry(20, 16, 12),
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        vertexShader: `varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
        fragmentShader: `varying vec3 vP; void main(){
          vec3 sky = mix(vec3(1.0, 0.88, 0.72), vec3(0.28, 0.58, 0.88), clamp(vP.y * 1.4, 0.0, 1.0));
          vec3 gnd = vec3(0.32, 0.36, 0.25);
          vec3 col = vP.y >= 0.0 ? sky : mix(vec3(0.85, 0.75, 0.62), gnd, clamp(-vP.y * 2.5, 0.0, 1.0));
          float sunDot = max(0.0, dot(vP, normalize(vec3(0.55, 0.65, 0.52))));
          col += vec3(1.0, 0.92, 0.75) * pow(sunDot, 24.0) * 2.2;
          gl_FragColor = vec4(col, 1.0);
        }`,
      }),
    );
    envScene.add(envSky);
    this.scene.environment = pmrem.fromScene(envScene, 0.03).texture;
    this.scene.environmentIntensity = 0.65;
    pmrem.dispose();

    this.sun.position.set(26, 34, 24);
    this.sun.target.position.set(0, 0, -6);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    Object.assign(this.sun.shadow.camera, { left: -24, right: 24, top: 22, bottom: -22, near: 1, far: 120 });
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.025;
    this.scene.add(this.hemi, this.sun, this.sun.target, this.sky.mesh, this.petals.points);

    this.stars = this.buildStars();
    this.scene.add(this.land.group, this.road.group, this.tunnel.group, this.weather.lines, this.bus.group, this.fx.group,
      this.dust.group, this.lixi.group, this.skyLanterns.group, this.blossoms.group);

    for (const stage of Object.values(this.stages)) this.scene.add(stage.group);
    this.buildInside();
    this.scene.add(this.inside);
    this.scene.add(CROWD.mesh, CROWD.blobs);  // mọi người đi bộ / đứng: một lượt vẽ (PLAN-139)
    bendTree(CROWD.blobs);
    this.setRegion("nam");
    this.applySet("ben");
    this.updateSky(true);
    this.applyQuality("high");
    bendTree(this.scene);
  }

  // ---- dựng cảnh ----------------------------------------------------------

  private buildStars(): THREE.Points {
    const n = 300;
    const pos = new Float32Array(n * 3);  // sao ở rất xa: không uốn theo đường (uốn sẽ làm trời «trôi» theo khúc cua)
    for (let i = 0; i < n; i++) pos.set([(Math.random() - 0.5) * 400, 60 + Math.random() * 80, -150 - Math.random() * 60], i * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const material = new THREE.PointsMaterial({ color: 0xffffff, size: 0.8, fog: false });
    material.userData.bent = true;  // bendTree bỏ qua
    const stars = new THREE.Points(geo, material);
    this.scene.add(stars);
    return stars;
  }

  private setRegion(region: Region): void {
    if (region === this.region) return;
    this.region = region;
    this.land.setRegion(region);
    bendTree(this.land.group);  // cảnh vùng mới dựng: uốn theo đường ngay, không đợi lượt quét
    const rain = region === "bac";  // mưa phùn miền Bắc
    this.weather.set(rain ? "drizzle" : "clear");
    this.road.setWet(rain);
    this.petals.setColor(region === "bac" ? 0xffa6c4 : 0xffd23f); // đào hồng miền Bắc, mai vàng nơi khác
    this.blossomColor = region === "bac" ? 0xffa6c4 : 0xffd23f;
    this.road.setBlossom(region === "bac" ? DAO : MAI);
  }

  private buildInside(): void {
    const g = this.inside;
    g.position.x = INSIDE_X;
    g.add(at(box(22, 0.3, 27, 0x5d4037), 0, -0.2, 0)); // sàn xe
    g.add(at(box(0.4, 1.2, 27, 0xc62828), -11.2, 0.4, 0));
    g.add(at(box(0.4, 1.2, 27, 0xc62828), 11.2, 0.4, 0));
    g.add(at(box(1.2, 0.05, 25, 0x8d6e63), 0, 0, 0)); // lối đi
    for (const [x, text] of [[-6.3, "TẦNG DƯỚI"], [6.3, "TẦNG TRÊN"]] as const) {
      const l = label(text, "lbl floor");
      l.position.set(x, 1, -12.6);
      g.add(l);
    }
    for (let i = 0; i < BERTHS; i++) {
      const floor = i < BERTHS_PER_FLOOR ? 0 : 1;
      const k = i % BERTHS_PER_FLOOR;
      const col = k % 2;
      const row = Math.floor(k / 2);
      const x = (floor === 0 ? -8.4 : 4.2) + col * 4.2;
      const z = -10 + row * 4;
      g.add(at(box(3.6, 0.5, 3.5, 0xe0d6c8), x, 0.25, z)); // nệm
      g.add(at(box(3.6, 0.25, 0.8, 0xffffff), x, 0.6, z - 1.25)); // gối
      const blanket = at(box(3.62, 0.3, 2.2, 0xb0a596), x, 0.62, z + 0.6);
      g.add(blanket);
      const head = makePerson(0, undefined, false, 1, true); // chỉ thấy đầu trên gối
      head.position.set(x, -0.62, z - 1.2);
      head.visible = false;
      g.add(head);
      const tag = label("trống", "lbl berth empty");
      tag.position.set(x, 1.1, z + 0.9);
      g.add(tag);
      this.berths.push({ blanket, head, tag, bubbleAt: new THREE.Vector3(x, 2.2, z - 0.8) });
    }
  }

  // ---- cập nhật từ state ----------------------------------------------------

  update(state: State): void {
    const prev = this.state;
    this.state = state;
    const c = state.control;
    if (c && (c.cam !== this.control.cam || c.zoom !== this.control.zoom || c.view !== this.control.view)) {
      this.control = { ...this.control, view: c.view, cam: c.cam, zoom: c.zoom };
      this.aimCamera(false);
    }
    if (c) this.control.fade = !!c.fade;
    const quality: Quality = c?.quality === "low" || c?.quality === "medium" ? c.quality : "high";
    if (quality !== this.quality) this.applyQuality(quality);
    // Chúc Tết (quà lớn) chen vào giữa bến / đường / trạm: giữ nguyên cảnh đang có, không nhảy cảnh.
    const want = state.phase === "SPECIAL" ? this.set : SET_OF[state.phase];
    if (want !== this.set) this.transition(() => this.applySet(want));
    if (state.region !== this.region && (state.phase === "DRIVING" || !prev)) this.setRegion(state.region);
    const leg = state.legs[state.leg_index];
    if (leg && state.phase === "DRIVING") {  // cột cây số: điểm tới + km còn lại (khớp số km trên bảng tuyến)
      this.road.setTarget(leg.kind === "rest" ? "TRẠM DỪNG" : leg.label, leg.km - state.trip_km);
    }
    if (state.route && state.phase === "DRIVING") this.road.setAhead(aheadRows(state.route), state.route.odo);
    // qua ranh tỉnh thật (cùng một xe đang chiếu, đang chạy): biển «TỈNH … Kính chào quý khách» hiện ra phía trước
    if (prev && prev.phase === "DRIVING" && state.phase === "DRIVING" && prev.featured === state.featured
      && state.place && state.place !== prev.place) this.road.welcome(state.place);
    const key = JSON.stringify(state.bus.seats);
    if (key !== this.seatsKey) {
      this.seatsKey = key;
      this.refreshBerths(state.bus.seats);
    }
    this.bus.setBanner(state.bus.banner);
    if (state.care) this.bus.setDirt(state.care.dirt);
    // bảng LED đầu xe: điểm trả cuối của CHUYẾN đang chạy (anh báo 02/11: xe đi Hải Phòng mà LED vẫn ghi điểm cuối của làn
    // «→ HÀ NỘI»); chưa xuất bến thì điểm cuối của làn
    const last = [...state.legs].reverse().find((l) => l.kind === "stop");
    this.bus.setRoute(`${state.departure.short} → ${last && state.phase !== "BOARDING" ? last.label : state.bus.to}`);
    this.ben.setStation(state.departure.name);
    this.ben.setLanes(state.lanes);
  }

  private refreshBerths(seats: (Seat | null)[]): void {
    seats.forEach((s, i) => {
      const b = this.berths[i];
      if (!b) return;
      b.blanket.material = mat(s ? (s.vip ? 0xffc93c : hueColor(s.hue, 0.55)) : 0xb0a596);  // tặng quà: giường vàng (PLAN-144)
      b.head.visible = !!s;
      b.tag.element.className = s ? (s.vip ? "lbl berth vip" : "lbl berth") : "lbl berth empty";
      b.tag.element.textContent = s ? `${s.vip ? "⭐ " : ""}${s.name}` : `trống`;
    });
  }

  // ?cam=x,y,z,lx,ly,lz trên URL ghi đè lựa chọn của admin (dùng khi thử góc máy mới)
  private aimCamera(snap: boolean): void {
    const custom = URL_PARAMS.get("cam")?.split(",").map(Number);
    const [cx, cy, cz, lx, ly, lz] = custom?.length === 6 ? custom : CAMS[this.control.cam];
    this.camLookTo.set(lx, ly, lz);
    this.camPosTo.set(cx, cy, cz).sub(this.camLookTo).multiplyScalar(this.control.zoom).add(this.camLookTo);
    if (snap) {
      this.camPos.copy(this.camPosTo);
      this.camLook.copy(this.camLookTo);
    }
  }

  // Mặc định cắt cảnh thẳng: màn đen 0,3 s mỗi lần đổi bến / đường / trạm / nhà nhìn như nhấp nháy.
  // Admin bật «Hiệu ứng chuyển cảnh» thì chỉ mờ nhẹ (style.css #fade.on).
  private transition(apply: () => void): void {
    if (!this.control.fade) {
      apply();
      return;
    }
    if (this.switching) return;
    this.switching = true;
    this.fade.classList.add("on");
    window.setTimeout(() => {
      apply();
      this.fade.classList.remove("on");
      this.switching = false;
    }, 300);
  }

  private applySet(name: SetName): void {
    this.set = name;
    for (const [k, stage] of Object.entries(this.stages)) stage.group.visible = k === name;
    this.road.roadside.visible = this.land.near.visible = name === "road";  // bối cảnh chiếm chỗ đồ ven đường
    for (const w of [...this.walkers]) this.removeWalker(w);
    this.wcLine = [];
    this.boardLine = [];
    this.roadside = [];
    this.dropBlock();
    this.dropBillboard();
    this.bus.group.position.set(0, 0, 0);
    const early = this.early;
    this.early = [];
    for (const e of early) {
      if (name === "rest" && e.type === "rest_action") this.restAction(e);
      if (name === "home" && e.type === "dropoff") this.dropoff(e);
    }
  }

  // ---- sự kiện ----------------------------------------------------------

  onEvent(e: GameEvent): void {
    switch (e.type) {
      case "ticket":
        if (!e.next && this.set === "ben" && !e.changed) this.boardWalk(e.name ?? "", e.hue ?? 0);
        break;
      case "goal_step":  // mục tiêu buổi live qua mốc: cảnh vui to cho cả phòng (chúc Tết do server chen cảnh)
        if (e.fx === "lixi" || e.fx === "lantern") this.giftFx(e.fx, 6);
        else if (e.fx === "firework") for (let i = 0; i < 5; i++) window.setTimeout(() => this.fireworks(SHOW_SKY, 2), i * 500);
        break;
      case "speak":  // lơ xe đọc tên người lên xe: đúng người đó bước lên
        if (e.names?.length && this.set === "ben") this.callNames(e.names, e.seconds ?? 3);
        break;
      case "pickup_stop":  // người hẹn đứng chờ sẵn bên lề / ở trạm, lên xe từng người (PLAN-145)
        this.roadsidePickup(e);
        break;
      case "chat":
        if (e.seat != null) this.bubble(e.seat, e.text ?? "");
        break;
      case "rest":
        this.rest.setSpecialty(e.specialty ?? "");
        break;
      case "rest_action":
        if (this.set === "rest") this.restAction(e);
        else this.early = [...this.early.slice(-30), e];
        break;
      case "honk":
        for (const w of this.walkers) {
          (w.obj.userData.food as THREE.Object3D | undefined)?.removeFromParent();  // còi giục: bỏ dở tô phở, không mang lên xe
          w.wait = 0;
          w.hold = false;
          w.onDone = undefined;
          w.speed = 7.5;
          w.path = [this.bus.doorSpot.clone()];
        }
        this.wcLine = [];
        break;
      case "dropoff":
        if (e.region) this.home.setPlace(e.province ?? "", e.region);
        if (this.set === "home") this.dropoff(e);
        else this.early = [...this.early.slice(-30), e];
        break;
      case "relief_dropoff":  // xe tăng cường chạy ngầm: cảnh 3D giữ nguyên, khách VIP vẫn có pháo hoa trên trời
        if (e.fireworks) this.fireworks(SHOW_SKY, 2);
        break;
      case "gift":
        if (e.tier_up && (e.tier ?? 0) >= 2) this.fireworks(SHOW_SKY, 2); // chỉ khi lên bậc
        this.giftFx(e.fx, e.fx_n ?? 1);
        break;
      case "special":
        for (let i = 0; i < 6; i++) {
          window.setTimeout(() => this.fireworks(SHOW_SKY.clone().add(new THREE.Vector3(-6 + i * 2.4, (i % 2) * 1.5, 0)), 1), i * 600);
        }
        break;
      case "like_milestone":
        this.fireworks(SHOW_SKY, 2);
        break;
      case "treat":
        this.fireworks(SHOW_SKY, 1);
        break;
      case "wash":  // rửa xe ở bến: nước xịt + bọt quanh thân xe (PLAN-137)
        for (let i = 0; i < 14; i++) {
          const side = i % 2 ? 1.5 : -1.5;
          this.dust.emit(new THREE.Vector3(-5.5 + Math.random() * 11, 1 + Math.random() * 2.6, side),
            new THREE.Vector3((Math.random() - 0.5) * 0.6, 0.4 + Math.random() * 0.6, side * 0.5), 0xe3f4ff, 0.65, 1.3, 0.7);
        }
        break;
      case "fuel":  // đổ xăng: tia sáng vàng ở nắp bình phía đuôi xe
        for (let i = 0; i < 6; i++) {
          this.dust.emit(new THREE.Vector3(-5.2, 1.2, 1.4), new THREE.Vector3((Math.random() - 0.5) * 0.8, 1 + Math.random(), 0.6),
            0xffd23f, 0.8, 0.9, 0.35);
        }
        break;
    }
  }

  private addWalker(obj: THREE.Object3D, path: THREE.Vector3[], speed: number, onDone?: () => void, wait = 0): Walker {
    const w: Walker = { obj, path, speed, wait, phase: Math.random() * 6, hold: false, onDone };
    bendTree(obj);  // uốn ngay: vẽ bản chưa uốn rồi lượt quét mới uốn là biên dịch shader hai lần giữa trận
    this.scene.add(obj);
    this.walkers.push(w);
    if (this.walkers.length > 60) this.removeWalker(this.walkers[0]);
    return w;
  }

  private removeWalker(w: Walker): void {
    w.onRemove?.();
    w.onRemove = undefined;
    dropLabels(w.obj);
    this.scene.remove(w.obj);
    this.walkers = this.walkers.filter((x) => x !== w);
    this.wcLine = this.wcLine.filter((x) => x !== w);
  }

  /** Dừng đón: người hẹn đứng ở lề (đường) / sân (trạm, đầu ngõ) cạnh cửa xe, có biển điểm đón; lần lượt bước lên. */
  private roadsidePickup(e: GameEvent): void {
    // đứng ở lề PHÍA CAMERA (anh 03/11: lề bên kia bị thân xe che hết) dọc thân xe, ngay dưới cửa trước; tới lượt thì bước sát
    // hông xe ở cửa trước rồi khuất vào xe. Trạm / đầu ngõ cũng đứng phía này cho thấy rõ.
    const curb = this.set === "road" ? 4.3 : 3.6;
    const doorX = this.bus.doorSpot.x - 1.6;  // cửa trước ngay sau bánh trước
    (e.people ?? []).forEach((person, i) => {
      const p = makePerson(person.hue ?? 0, person.name);
      p.position.set(doorX - 0.6 - (i % 6) * 0.8, 0.1, curb + Math.floor(i / 6) * 0.8);
      this.roadside.push(this.addWalker(p, [new THREE.Vector3(doorX, 0.1, 2.4), new THREE.Vector3(doorX, 0.1, 1.5)], 3.2,
        undefined, 2 + i * PICKUP_STEP_S));
    });
    const sign = label(`🚏 ĐIỂM ĐÓN · ${e.place ?? ""}`, "lbl sign");
    sign.position.set(doorX + 3.4, 1.1, curb + 0.6);  // bên phải nhóm người, thấp — không đè tên
    this.scene.add(sign);
    window.setTimeout(() => sign.removeFromParent(), Math.max(3000, (e.seconds ?? 4) * 1000));
  }

  /** Trạm thu phí (barie ngang làn + chòi) / chốt công an (chú CSGT + nón giao thông) ngay trước đầu xe, phía camera; góp đủ
   * thì barie nhấc lên rồi dỡ cảnh. Dựng theo state (màn mở giữa lúc bị chặn vẫn thấy). */
  private updateBlock(kind: string | null, dt: number): void {
    if (kind && this.set === "road" && !this.blockProp) this.buildBlock(kind);
    if (!kind && this.blockProp && !this.blockLeaving) {
      this.blockLeaving = true;
      window.setTimeout(() => this.dropBlock(), 1600);
    }
    if (this.blockArm) {
      const want = this.blockLeaving ? 1.35 : 0;
      this.blockArm.rotation.x += (want - this.blockArm.rotation.x) * Math.min(1, dt * 4);
    }
  }

  private buildBlock(kind: string): void {
    const g = new THREE.Group();
    if (kind === "toll") {
      g.add(at(box(1.6, 2.3, 1.6, 0x1e88e5), 8.6, 1.15, 4.0), at(box(2.4, 0.25, 2.2, 0xc62828), 8.6, 2.45, 4.0),
        at(box(0.9, 0.7, 0.06, 0xbbdefb, 0x223344), 8.6, 1.6, 3.18), at(box(0.32, 1.1, 0.32, 0xffd23f), 7.3, 0.55, 3.0));
      const arm = new THREE.Group();
      arm.position.set(7.3, 1.05, 3.0);
      for (let i = 0; i < 6; i++) arm.add(at(box(0.16, 0.16, 0.8, i % 2 ? 0xffffff : 0xe53935), 0, 0, -0.4 - i * 0.8));
      g.add(arm);
      this.blockArm = arm;
      const sign = label("🚧 TRẠM THU PHÍ", "lbl sign");
      sign.position.set(4.6, 0.3, 4.6);  // lề phía camera, dưới thân xe: không bị mép khung cắt
      g.add(sign);
    } else {
      const cop = makePerson(55, "👮 CSGT");
      cop.position.set(7.0, 0.1, 2.6);
      cop.rotation.y = -Math.PI / 2;  // quay mặt về đầu xe
      g.add(cop);
      for (const z of [0.4, 1.4, -0.6]) g.add(at(box(0.3, 0.55, 0.3, 0xff6d00), 7.8, 0.28, z));
      const sign = label("👮 CHỐT CSGT · DỪNG XE", "lbl sign");
      sign.position.set(4.6, 0.3, 4.6);
      g.add(sign);
    }
    bendTree(g);
    this.scene.add(g);
    this.blockProp = g;
    this.blockLeaving = false;
  }

  /** Bảng quảng cáo bên đường (anh 03/11): xe dừng, bảng LED lớn phía sau xe chiếu video anh tải lên, xong thì dỡ. Bắt đầu
   * đúng chỗ server đang chiếu (màn mở giữa chừng vẫn khớp). Video dọc (TikTok) hay ngang đều co theo khung. */
  private updateBillboard(show: { url: string; seconds: number; left: number } | null): void {
    if (!show || this.set !== "road") {
      if (this.board) this.dropBillboard();
      return;
    }
    if (this.board?.url === show.url) return;
    this.dropBillboard();
    const video = document.createElement("video");
    video.src = show.url;
    video.playsInline = true;
    video.preload = "auto";
    video.crossOrigin = "anonymous";
    const tex = new THREE.VideoTexture(video);
    tex.colorSpace = THREE.SRGBColorSpace;
    const g = new THREE.Group();
    const H = BOARD_H;  // rộng theo tỉ lệ video (dọc TikTok hay ngang)
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
    screen.scale.set(H * 16 / 9, H, 1);
    screen.position.set(0, 2.2 + H / 2, 0.08);
    const frame = at(box(1, 1, 0.3, 0x263238), 0, 2.2 + H / 2, -0.1);
    frame.scale.set(H * 16 / 9 + 0.6, H + 0.6, 0.3);
    g.add(screen, frame, at(box(0.4, 2.4, 0.4, 0x546e7a), -2, 1.2, -0.2), at(box(0.4, 2.4, 0.4, 0x546e7a), 2, 1.2, -0.2));
    const tag = label("📺 BẢNG QUẢNG CÁO", "lbl sign");
    tag.position.set(0, 2.2 + H + 0.9, 0);
    g.add(tag);
    g.position.set(0.5, 0, -8.5);  // lề bên kia đường, sau thân xe: cao hơn nóc xe nên không bị che
    video.addEventListener("loadedmetadata", () => {
      const ratio = video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 16 / 9;
      screen.scale.set(H * ratio, H, 1);
      frame.scale.set(H * ratio + 0.6, H + 0.6, 0.3);
      video.currentTime = Math.max(0, show.seconds - show.left);  // khớp chỗ server đang chiếu
    }, { once: true });
    this.scene.add(g);
    this.board = { group: g, video, tex, url: show.url };
    this.onVideo?.(video);
    video.play().catch(() => {  // trình duyệt chặn tự phát có tiếng: phát câm (hình vẫn chạy)
      video.muted = true;
      void video.play().catch(() => undefined);
    });
  }

  private dropBillboard(): void {
    if (!this.board) return;
    const { group, video, tex } = this.board;
    this.board = null;
    this.onVideo?.(null);
    video.pause();
    video.removeAttribute("src");
    video.load();
    tex.dispose();
    dropLabels(group);
    this.scene.remove(group);
  }

  private dropBlock(): void {
    if (!this.blockProp) return;
    dropLabels(this.blockProp);
    this.scene.remove(this.blockProp);
    this.blockProp = null;
    this.blockArm = null;
    this.blockLeaving = false;
  }

  /** Bến: người có vé xếp hàng ở cửa xe, lơ xe đọc tới tên ai thì người đó bước lên (anh 03/11 «lên xe là phải xếp hàng lên
   * từ từ, đọc tên là lên xe»; «đồng bộ chỗ này»). Hàng dài thì gập hai dòng. */
  private boardWalk(name: string, hue: number): void {
    const p = makePerson(hue, name);
    const { x0, x1, z0, z1 } = this.ben.waiting;
    p.position.set(x0 + Math.random() * (x1 - x0), 0.1, z0 + Math.random() * (z1 - z0));
    const w = this.addWalker(p, [this.lineSpot(this.boardLine.length)], 4.2);
    w.hold = true;
    w.name = name;
    w.queuedAt = this.t;
    this.boardLine.push(w);
  }

  private lineSpot(k: number): THREE.Vector3 {
    const door = this.bus.doorSpot;
    return new THREE.Vector3(door.x + 1.1 + (k % LINE_COLS) * 0.75, 0.1, door.z - 1.6 - Math.floor(k / LINE_COLS) * 0.8);
  }

  /** Câu lơ xe đọc tên người lên xe vừa phát (`speak` kèm `names`): hẹn từng người bước lên rải theo độ dài câu. */
  private callNames(names: string[], seconds: number): void {
    names.forEach((name, i) => {
      const w = this.boardLine.find((x) => x.name === name && x.callAt === undefined);
      if (w) w.callAt = this.t + seconds * (i + 1) / (names.length + 1);
    });
  }

  private stepBoardLine(dt: number): void {
    if (!this.boardLine.length) return;
    this.boardTimer += dt;
    const voiceOff = this.state?.control?.voice_on === false;
    let go = this.boardLine.find((w) => w.callAt !== undefined && this.t >= w.callAt);
    const head = this.boardLine[0];
    if (!go && this.boardTimer >= BOARD_STEP_S && (voiceOff || this.t - (head.queuedAt ?? 0) > BOARD_FALLBACK_S)) go = head;
    if (!go) return;
    this.boardTimer = 0;
    this.boardLine = this.boardLine.filter((w) => w !== go);
    go.hold = false;
    go.path = [this.bus.doorSpot.clone()];  // tới cửa thì lên xe (hết đường đi → gỡ khỏi cảnh)
    this.boardLine.forEach((w, i) => { w.path = [this.lineSpot(i)]; });
  }

  private bubble(seat: number, text: string): void {
    const inside = this.view === "inside";
    const spot = inside ? this.berths[seat]?.bubbleAt : this.bus.windowSpots[seat];
    if (!spot) return;
    const l = label(text, "lbl chat");
    l.position.copy(spot);
    (inside ? this.inside : this.bus.group).add(l);
    this.bubbles.push(l);
    while (this.bubbles.length > MAX_BUBBLES) this.bubbles.shift()!.removeFromParent();  // chat dồn dập: không chồng lên nhau
    window.setTimeout(() => {
      l.removeFromParent();
      this.bubbles = this.bubbles.filter((b) => b !== l);
    }, BUBBLE_MS);
  }

  private restAction(e: GameEvent): void {
    const p = makePerson(e.hue ?? 0, e.name);
    p.position.copy(this.bus.doorSpot).add(new THREE.Vector3(Math.random() - 0.5, 0.1, -0.3));
    if (e.action === "food") {
      const turn = this.seatTurn++;
      const spot = this.rest.takeSpot();  // chỗ riêng, không ngồi đè người khác
      const w = this.addWalker(p, [this.rest.counterSpot(turn), this.rest.eatSpot(spot)], 3.6, undefined);
      w.onRemove = () => this.rest.freeSpot(spot);
      const icon = label(e.emoji ?? "🍜", "lbl emoji");
      icon.position.y = 3;
      p.add(icon);
      p.userData.food = icon;
      w.onDone = () => {  // tới chỗ ngồi: ăn 16 giây, ăn xong để tô / ly lại quán rồi mới về xe (anh 03/11: đem đồ ăn lên xe)
        w.wait = 16;
        w.onDone = () => {
          icon.removeFromParent();
          w.path = [this.bus.doorSpot.clone()];
        };
      };
    } else if (e.action === "wc") {
      const w = this.addWalker(p, [this.rest.wcQueue(this.wcLine.length)], 4);
      w.hold = true;
      this.wcLine.push(w);
    } else {
      const w = this.addWalker(p, [this.rest.shop.clone()], 4);
      w.onDone = () => {
        p.add(at(box(0.5, 0.5, 0.3, 0xd32f2f), 0.45, 0.7, 0)); // túi quà
        bendTree(p);
        w.path = [this.bus.doorSpot.clone()];
        w.wait = 2;
        w.onDone = undefined;
      };
    }
  }

  /** Hiệu ứng riêng của món quà (server chọn theo tên / giá món): lì xì bay, đèn lồng thả trời, mưa hoa, pháo nhỏ. Tim bay và
   * còi xe do HUD / âm thanh lo. Nhiều món một lượt thì nhiều hơn, có trần. */
  private giftFx(fx: string | undefined, n: number): void {
    const more = Math.min(n, 6);
    if (fx === "lixi") this.lixi.emit(new THREE.Vector3(0, 4.8, 0), 6 + more * 2, 5);
    else if (fx === "lantern") this.skyLanterns.emit(new THREE.Vector3(0, 5, -3), 4 + more, 7);
    else if (fx === "petals") this.blossoms.emit(new THREE.Vector3(0, 13, -2), 10 + more * 4, 9, this.blossomColor);
    else if (fx === "firework") this.fireworks(SHOW_SKY, Math.min(3, n));
  }

  private dropoff(e: GameEvent): void {
    (e.people ?? []).forEach((person, i) => {
      const p = makePerson(person.hue, person.name, person.vip);
      if (person.parcels) {  // thùng quà Tết đi theo xe: đội trên đầu vào cổng — camera nhìn từ trên cao thấy rõ (PLAN-134 C)
        p.add(at(box(0.66, 0.42, 0.56, 0xc62828), 0, 1.86, 0), at(box(0.68, 0.07, 0.16, 0xffd23f), 0, 2.08, 0),
          at(box(0.16, 0.07, 0.58, 0xffd23f), 0, 2.08, 0));
      }
      p.position.copy(this.bus.doorSpot).add(new THREE.Vector3(0, 0.1, 0));
      const gate = this.home.gate.clone().add(new THREE.Vector3(-0.6 + (i % 4) * 0.4, 0, 0));
      this.addWalker(p, [new THREE.Vector3(0, 0.1, -6), gate, this.home.door.clone()], 2.6, undefined, i * 0.8);
    });
    if (e.fireworks) {
      const sky = this.home.fireworksAt;
      for (let i = 0; i < 4; i++) {
        window.setTimeout(() => this.fireworks(sky.clone().add(new THREE.Vector3(-3 + i * 2, 0, 0)), 1), 1500 + i * 500);
      }
    }
  }

  private fireworks(origin: THREE.Vector3, count = 1): void {
    this.fx.launch(origin, count);
  }

  /**
   * Chất lượng: «Cao» đủ 1080×1920 + bóng đổ mỗi khung; «Vừa» 75 % độ phân giải, bóng vẽ lại cách khung (máy bận vẽ thì
   * Chrome hụt tiếng — anh nghe lẹt xẹt ở «Cao»); «Thấp» ~60 %, tắt bóng, bớt cánh hoa / mưa / hạt pháo hoa / bụi.
   * Bật tắt bóng bằng castShadow (three tự dựng lại shader), không phải tải lại trang.
   */
  private applyQuality(quality: Quality): void {
    this.quality = quality;
    const low = quality === "low";
    const res = low ? LOW_RES : quality === "medium" ? MEDIUM_RES : 1;
    this.renderer.setPixelRatio(Math.min(BASE_RES, res));
    this.sun.castShadow = !low;
    this.petals.setDensity(low ? 0.35 : quality === "medium" ? 0.7 : 1);
    this.weather.setDensity(low ? 0.4 : 1);
    this.fx.setQuality(low);
    this.dust.setQuality(low);
    (this.renderer.domElement.parentElement as HTMLElement).dataset.quality = quality;
  }

  /**
   * Đường quanh co / đèo dốc / đồng bằng theo hồ sơ đường thật: độ quanh co OSRM ở km đang chạy quyết định cua dày
   * và gắt cỡ nào; đèo thì thêm dốc lên xuống; vùng quyết định đồi lượn. Dừng (bến / trạm / nhà) thì đường duỗi thẳng.
   */
  private updateRoadShape(dt: number, moving: boolean): void {
    const terrain = this.state?.terrain;
    const open = moving && !terrain?.tunnel;  // trong hầm: thẳng, phẳng
    const radius = open ? radiusFor(terrain?.wind ?? 0) : Infinity;
    const climb = open ? terrain?.climb ?? 0 : 0;
    const hills = open && !climb ? HILLS[this.region ?? "nam"] : 0;
    const dx = this.speed * dt;
    // một nhịp cua trái → phải dài ~6 bán kính: đèo cua dồn dập, quốc lộ cua thoải thưa
    this.curvePhase += (Math.PI * 2 * dx) / THREE.MathUtils.clamp(6 * radius, 240, 3600);
    this.hillPhase += (Math.PI * 2 * dx) / HILL_WAVE;
    const rolling = THREE.MathUtils.lerp(GRADE_FLAT, GRADE_HILLS, hills);  // biên độ dốc đồi lượn theo vùng
    const target = {
      curve: Number.isFinite(radius) ? Math.sin(this.curvePhase) / (2 * radius) : 0,  // z += curve·x² ⇒ R = 1 / (2·curve)
      grade: climb ? climb * GRADE_PASS : open ? rolling * Math.cos(this.hillPhase) : 0,
      crest: -HILL_CREST * hills * Math.sin(this.hillPhase),  // đồi lượn: dốc và độ cong lệch nhau một phần tư nhịp
    };
    const k = Math.min(1, dt * 0.8);  // đổi mượt ~1–2 giây (qua đỉnh đèo: từ lên dốc sang đổ dốc)
    this.shape.curve += (target.curve - this.shape.curve) * k;
    this.shape.crest += (target.crest - this.shape.crest) * k;
    this.shape.grade += (target.grade - this.shape.grade) * k;
    const lateral = this.speed * this.speed * 2 * this.shape.curve;  // v² / R
    this.bus.setLean(THREE.MathUtils.clamp(-ROLL_PER_ACCEL * lateral, -MAX_ROLL, MAX_ROLL));
  }

  /** Bụi bốc sau bánh sau + khói ống xả khi xe chạy; chạy càng nhanh càng dày. */
  private trailDust(dt: number): void {
    this.dustTimer += dt;
    const every = Math.max(0.06, 0.3 - this.speed * 0.012);
    if (this.dustTimer < every) return;
    this.dustTimer = 0;
    for (const z of [1.3, -1.3]) {
      this.dust.emit(new THREE.Vector3(-4.4, 0.3, z), new THREE.Vector3(-this.speed * 0.7, 0.6, z * 0.2), DUST, 0.22, 1.1, 0.7);
    }
    const strain = Math.max(0, this.shape.grade) / GRADE_PASS;  // leo đèo: ống xả phun khói dày, to
    if (Math.random() < 0.5 + 0.5 * strain) {
      this.dust.emit(new THREE.Vector3(-6.2, 0.55, -0.9), new THREE.Vector3(-this.speed * 0.6 - 1, 0.9, 0), EXHAUST,
        0.3 + 0.25 * strain, 1.4, 0.5 + 0.2 * strain);
    }
  }

  /** Sập ổ gà: bụi tung mạnh ở đúng bánh vừa sập. */
  private kickDust(axle: "front" | "rear", side: number): void {
    const wheel = this.bus.wheelSpots.find((w) => w.axle === axle && Math.sign(w.z) === side);
    if (!wheel) return;
    for (let i = 0; i < 5; i++) {
      const vel = new THREE.Vector3(-this.speed * 0.5 + (Math.random() - 0.5) * 2, 1.4 + Math.random(), side * Math.random());
      this.dust.emit(new THREE.Vector3(wheel.x, 0.3, wheel.z), vel, DUST, 0.45, 1.3, 0.9);
    }
  }

  // ---- vòng vẽ ----------------------------------------------------------

  private updateSky(force = false): void {
    if (!force && this.t - this.skyCheck < 0.25) return;  // 4 lần / giây là đủ mượt
    const dt = this.t - this.skyCheck;
    this.skyCheck = this.t;
    const target = FORCE_HOUR ?? this.state?.route?.clock.hour ?? realHour();
    if (this.skyHour === null || force) {
      this.skyHour = target;
    } else {
      const diff = ((target - this.skyHour + 36) % 24) - 12;  // đi đường ngắn quanh vòng 24 giờ
      this.skyHour += Math.sign(diff) * Math.min(Math.abs(diff), SKY_CATCH_UP * dt);
    }
    const look = this.look = lookAt(this.skyHour);
    this.night = isNight(this.skyHour);
    this.sky.set(look.top, look.horizon);
    this.scene.background = null;
    (this.scene.fog as THREE.Fog).color.setHex(look.horizon);
    (this.renderer.domElement.parentElement as HTMLElement).style.background = `#${look.horizon.toString(16).padStart(6, "0")}`;
    this.hemi.color.setHex(look.hemiSky);
    this.hemi.groundColor.setHex(look.hemiGround);
    this.hemi.intensity = look.hemi;
    this.sun.color.setHex(look.sunColor);
    this.sun.intensity = look.sun;
    this.scene.environmentIntensity = this.night ? 0.25 : 0.65;
    this.renderer.toneMappingExposure = look.exposure;
    this.stars.visible = this.night;
    this.road.setNight(this.night);
    this.land.setNight(this.night);
  }


  /** Vào / ra hầm: vách + đèn hầm hiện dần, ánh sáng trời tối lại, cảnh hai bên ẩn khi đã vào hẳn. */
  private updateTunnel(dt: number, inside: boolean): void {
    this.tunnel.update(dt, inside, this.speed * dt);
    const dim = this.tunnel.amount;
    this.sun.intensity = this.look.sun * (1 - 0.85 * dim);
    this.hemi.intensity = this.look.hemi * (1 - 0.55 * dim);
    const deep = dim > 0.5;
    if (deep === this.inTunnel) return;
    this.inTunnel = deep;
    this.land.setSides(!deep);
    this.road.roadside.visible = this.land.near.visible = !deep && this.set === "road";
  }

  /** Dựng sẵn từng vùng chưa tới khi xe đang đứng đón khách ở bến (lúc rảnh, cảnh không trôi): xe qua vùng mới giữa đường
   * thì chỉ gắn vào cảnh, không dựng hàng trăm vật + vẽ chữ biển hiệu ngay lúc người xem đang nhìn. */
  private prebuildIdle(dt: number): void {
    if (this.state?.phase !== "BOARDING") return;
    this.prebuildWait -= dt;
    if (this.prebuildWait > 0) return;
    this.prebuildWait = PREBUILD_GAP;
    const next = this.land.missing()[0];
    if (next) this.land.prebuild(next);
  }

  /**
   * Biên dịch sẵn mọi shader trước khi hiện cảnh (PLAN-133): vật đang ẩn (pháo hoa, bối cảnh khác, trong xe, hầm) mà để
   * tới lúc hiện mới biên dịch thì khựng hình đúng lúc đó. compileAsync dùng KHR_parallel_shader_compile — biên dịch song
   * song, không chặn luồng chính; một lượt vẽ với mọi vật hiện ra để biên dịch nốt shader bóng đổ (vật liệu độ sâu).
   */
  async warmUp(): Promise<void> {
    const hidden: THREE.Object3D[] = [];
    this.scene.traverse((o) => {
      if (!o.visible) {
        hidden.push(o);
        o.visible = true;
      }
    });
    try {
      await this.renderer.compileAsync(this.scene, this.camOut);
      // máy không có KHR_parallel_shader_compile: shader chỉ thật sự dựng ở lần dùng đầu → ép dựng xong ngay bây giờ
      for (const program of this.renderer.info.programs ?? []) program.getUniforms();
      this.renderer.render(this.scene, this.camOut);
    } finally {
      for (const o of hidden) o.visible = false;
    }
    this.renderer.render(this.scene, this.camOut);  // cùng một lượt: trình duyệt chỉ hiện khung đúng này
  }

  /**
   * Quản lý nhãn tên hành khách thông minh tại bến/trạm đông người (V2):
   * 1) Đặt ưu tiên hiển thị: Khách VIP (⭐) > Người đang di chuyển (mới lên xe/gọi món) > Người đứng yên chờ, kết hợp gần camera hơn.
   * 2) Che khuất theo khoảng cách (Distance Culling): quá xa camera hoặc sát rìa khung hình thì ẩn.
   * 3) Không bao giờ cho nhãn đè lên vùng HUD thông tin quan trọng (Bảng tuyến/CTA ở y < 700, Bảng phải/TikTok feed ở y > 1320).
   * 4) Giới hạn tối đa 14 nhãn hiển thị rõ ràng cùng lúc và triệt tiêu hoàn toàn chồng lấn (nếu hết chỗ đẩy thì ẩn nhãn ưu tiên thấp).
   */
  private declutter(cam: THREE.Camera): void {
    _vp.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
    const camPos = cam.position;
    const candidates: LabelBox[] = [];

    for (let wi = 0; wi < this.walkers.length; wi++) {
      const w = this.walkers[wi];
      const moving = w.path.length > 0 && w.wait <= 0;
      const distSq = w.obj.position.distanceToSquared(camPos);

      // Ẩn icon món ăn (emoji) cho những người đã ngồi yên trên bàn ăn hoặc ở xa để tránh 30 icon chồng thành đám mây ở trạm dừng
      for (const o of w.obj.children) {
        if (!(o instanceof CSS2DObject)) continue;
        const el = o.element;
        if (el.classList.contains("emoji")) {
          el.style.opacity = moving && distSq < 1800 ? "0.95" : "0";
          continue;
        }
        let size = this.labelSize.get(el);
        if (!size) {
          const wPx = el.offsetWidth || 110;
          const hPx = el.offsetHeight || 32;
          size = { w: wPx, h: hPx };
          if (el.offsetWidth > 0) this.labelSize.set(el, size);
        }
        _lp.setFromMatrixPosition(o.matrixWorld).applyMatrix4(_vp);
        // Ngoài tầm nhìn hoặc quá xa camera (> 46m) -> ẩn ngay
        if (_lp.z > 1 || _lp.z < -1 || distSq > 2100) {
          el.style.opacity = "0";
          continue;
        }
        const x = (_lp.x + 1) * W / 2;
        const y = (1 - _lp.y) * H / 2;
        // Chặn vùng cấm HUD quan trọng (trên y < 680 là Header/Tuyến/CTA/Lơ xe; dưới y > 1340 là Bảng tỉnh/Trạm dừng/TikTok chat)
        // đồng thời tránh vùng bong bóng Lơ xe bên trái (x < 420 && y < 860)
        if (y < 680 || y > 1340 || x < 75 || x > W - 75 || (x < 430 && y < 860)) {
          el.style.opacity = "0";
          continue;
        }
        const isVip = el.classList.contains("vip");
        const prio = (isVip ? 1000 : 0) + (moving ? 300 : 0) + wi * 4 - distSq * 0.08;
        candidates.push({
          el,
          x0: x - size.w / 2,
          x1: x + size.w / 2,
          y0: y - size.h / 2,
          y1: y + size.h / 2,
          prio,
          distSq,
        });
      }
    }

    // Sắp xếp theo độ ưu tiên giảm dần, chỉ hiện tối đa 10 nhãn rõ nhất trên màn hình
    candidates.sort((a, b) => b.prio - a.prio);
    const MAX_VISIBLE_LABELS = 10;
    const placed: LabelBox[] = [];

    for (let i = 0; i < candidates.length; i++) {
      const b = candidates[i];
      if (i >= MAX_VISIBLE_LABELS) {
        b.el.style.opacity = "0";
        continue;
      }
      let dy = 0;
      let overlapped = false;
      for (let step = 0; step < 5; step++) {
        overlapped = false;
        for (const p of placed) {
          if (b.x1 + LABEL_GAP + 6 <= p.x0 || b.x0 >= p.x1 + LABEL_GAP + 6) continue;
          if (b.y1 + dy + LABEL_GAP + 4 <= p.y0 || b.y0 + dy >= p.y1 + LABEL_GAP + 4) continue;
          dy = p.y0 - (LABEL_GAP + 4) - b.y1;
          overlapped = true;
          break;
        }
        if (!overlapped) break;
      }
      // Nếu đẩy quá 64px (tránh nhãn bay lơ lửng xa đầu nhân vật) hoặc chạm vùng HUD trên -> ẩn luôn
      if (overlapped || -dy > 64 || b.y0 + dy < 680 || -dy > MAX_NUDGE) {
        b.el.style.opacity = "0";
        continue;
      }
      placed.push({ ...b, y0: b.y0 + dy, y1: b.y1 + dy });
      const distAlpha = THREE.MathUtils.clamp(1.18 - Math.sqrt(b.distSq) / 46, 0.72, 1.0);
      b.el.style.opacity = distAlpha.toFixed(2);
      const shown = this.labelNudge.get(b.el) ?? 0;
      const next = Math.abs(dy - shown) < 0.5 ? dy : shown + (dy - shown) * NUDGE_EASE;
      this.labelNudge.set(b.el, next);
      if (next) b.el.style.transform += ` translateY(${next.toFixed(1)}px)`;
    }
  }

  /** Số liệu vẽ của khung vừa rồi — cho đồng hồ ?fps=1. */
  stats(): { calls: number; triangles: number; geometries: number; textures: number } {
    const { render, memory } = this.renderer.info;
    return { calls: render.calls, triangles: render.triangles, geometries: memory.geometries, textures: memory.textures };
  }

  frame(dt: number): void {
    this.t += dt;
    this.updateSky();
    const s = this.state;
    const moving = s?.phase === "DRIVING" && this.set === "road" && !s?.halt && !s?.block;  // dừng đón / bị chặn: đứng yên
    this.updateBlock(s?.block?.kind ?? null, dt);
    this.updateBillboard(s?.show ?? null);
    if (moving && this.roadside.length) {
      this.roadside.forEach((w) => this.walkers.includes(w) && this.removeWalker(w));
      this.roadside = [];
    }
    const uphill = Math.max(0, this.shape.grade) / GRADE_PASS;  // leo dốc: cảnh trôi chậm lại (chỉ hình, km do server)
    const target = moving ? BASE_SPEED * (s?.speed ?? 1) * (1 - CLIMB_SLOW * uphill) : 0;
    this.speed += (target - this.speed) * Math.min(1, dt * 2);
    if (this.speed > 0.01) {
      const dx = this.speed * dt;
      for (const bump of this.road.advance(dx, this.bus.wheelSpots)) {  // ổ gà → xe nảy + bụi tung
        this.bus.bump(bump);
        this.kickDust(bump.axle, bump.side);
      }
      this.land.advance(dx);
      if (moving) this.trailDust(dt);
    }
    this.updateRoadShape(dt, moving);
    this.updateTunnel(dt, moving && !!s?.terrain?.tunnel);
    this.bus.update(dt, this.speed, this.night || this.inTunnel);  // trong hầm bật đèn xe
    this.weather.update(dt, moving ? this.speed * 0.1 : 0);

    // người đi bộ
    for (const w of [...this.walkers]) {
      w.phase += dt * 10;
      if (w.wait > 0) {
        w.wait -= dt;
        animatePerson(w.obj, "idle", w.phase);
        continue;
      }
      const dest = w.path[0];
      if (!dest) {
        if (w.onDone) {
          const done = w.onDone;
          w.onDone = undefined;
          done();
        } else if (!w.hold) {
          this.removeWalker(w);
        } else {
          animatePerson(w.obj, "idle", w.phase);
        }
        continue;
      }
      const d = _step.subVectors(dest, w.obj.position);
      d.y = 0;
      const dist = d.length();
      const step = w.speed * dt;
      if (dist <= step) {
        w.obj.position.x = dest.x;
        w.obj.position.z = dest.z;
        w.path.shift();
      } else {
        w.obj.position.addScaledVector(d.normalize(), step);
        w.obj.rotation.y = Math.atan2(d.x, d.z);
      }
      w.obj.position.y = 0.1 + Math.abs(Math.sin(w.phase)) * 0.12;
      animatePerson(w.obj, "walk", w.phase);
    }
    this.stepBoardLine(dt);
    // hàng WC: mỗi 4 s người đầu hàng xong việc, quay lại xe
    if (this.wcLine.length) {
      this.wcTimer += dt;
      if (this.wcTimer > 4) {
        this.wcTimer = 0;
        const first = this.wcLine.shift()!;
        first.hold = false;
        first.path = [this.bus.doorSpot.clone()];
        this.wcLine.forEach((w, i) => { w.path = [this.rest.wcQueue(i)]; });
      }
    }
    // bối cảnh đang hiện: hơi nồi, đèn lồng, lửa bếp; gia đình ở đầu ngõ vẫy tay
    if (this.set !== "road") this.stages[this.set].update(dt, this.t);
    if (this.set === "home") {
      this.home.family.forEach((c) => {
        c.position.y = 0.1 + Math.abs(Math.sin(this.t * 4 + c.position.x)) * 0.12;
        animatePerson(c, "wave", this.t * 6 + c.position.x);
      });
    }
    this.fx.update(dt);
    this.dust.update(dt);
    this.lixi.update(dt);
    this.skyLanterns.update(dt);
    this.blossoms.update(dt);

    // góc nhìn do admin chọn (?view= trên URL ghi đè khi thử); camera trượt mượt tới góc mới
    const view: View = (URL_PARAMS.get("view") as View | null) ?? this.control.view;
    const showing = !!this.board && view === "outside";
    if (showing) {  // xem video: ngước máy quay lên bảng quảng cáo
      const [cx, cy, cz, lx, ly, lz] = SHOW_CAM;
      this.camLookTo.set(lx, ly, lz);
      this.camPosTo.set(cx, cy, cz);
    } else if (this.showCam) {
      this.aimCamera(false);  // hết video: về góc máy admin chọn
    }
    this.showCam = showing;
    const k = Math.min(1, dt * (showing ? 1.5 : 3));
    this.camPos.lerp(this.camPosTo, k);
    this.camLook.lerp(this.camLookTo, k);
    this.camOut.position.copy(this.camPos);
    this.camOut.lookAt(this.camLook);
    if (view !== this.view && !this.switching) {
      this.transition(() => {
        this.view = view;
        this.inside.visible = view === "inside";
        this.onView?.(view);
      });
    }
    this.inside.visible = this.view === "inside";
    const cam = this.view === "inside" ? this.camIn : this.camOut;
    if (this.view === "inside") setBend(0, 0, 0);  // khoang trong xe đặt xa trục: uốn sẽ méo
    else setBend(this.shape.curve, this.shape.grade, this.shape.crest);
    this.bendSweep += dt;
    if (this.bendSweep > 2) {  // vật mới (người đi bộ, cảnh vùng…) cũng uốn theo
      this.bendSweep = 0;
      bendTree(this.scene);
    }
    this.sky.mesh.position.copy(cam.position);
    this.petals.points.visible = this.view === "outside";
    this.petals.update(dt, this.t, moving ? this.speed * 0.12 : 0.25);
    // bóng đổ: «Cao» mỗi khung, «Vừa» 15 khung/giây; cảnh trong xe không thấy bóng ngoài trời → khỏi vẽ bóng
    const shadows = this.view === "outside" && this.quality !== "low";
    this.renderer.shadowMap.autoUpdate = shadows && this.quality === "high";
    if (shadows && this.quality === "medium") this.renderer.shadowMap.needsUpdate = this.frameNo++ % 2 === 0;
    // ma trận cả cây cảnh tính một lần: đám đông chép vị trí người, rồi lượt vẽ WebGL và nhãn chữ dùng lại
    this.scene.updateMatrixWorld();
    CROWD.sync(this.scene);
    this.scene.matrixWorldAutoUpdate = false;
    this.renderer.render(this.scene, cam);
    this.labels.render(this.scene, cam);
    this.scene.matrixWorldAutoUpdate = true;
    this.declutter(cam);
    this.prebuildIdle(dt);
  }
}

