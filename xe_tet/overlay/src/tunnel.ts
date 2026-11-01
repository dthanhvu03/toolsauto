// Hầm xuyên núi (PLAN-124): khi server báo xe đang trong hầm (Hải Vân, Đèo Cả, Cổ Mã, Cù Mông, Tam Điệp) — vách bê tông
// hai bên, dải đèn vàng trên vách xa lướt qua, cảnh ngoài ẩn, ánh sáng tối lại. Camera nhìn từ trên cao nên vẽ kiểu
// cắt ngang: không có trần (trần che mất xe), vách phía camera chỉ cao ngang lan can; trên hai vách là khối đá núi (che
// đất trống bên ngoài) để nhìn ra ngay là đang xuyên qua núi.

import * as THREE from "three";
import { at, noiseTexture, soft } from "./art";
import { strip } from "./bend";
import { Conveyor, WRAP } from "./road";

const FAR_WALL_Z = -6.2;  // mép đường ở z = ±4, chừa lề 2 m
const NEAR_WALL_Z = 6.2;
const WALL_HIGH = 7;
const WALL_LOW = 2.2;  // vách phía camera: thấp để mọi góc máy vẫn thấy xe
const LAMP_GAP = 4.5;
const ROCK_DEPTH = 60;  // khối đá trên vách: đủ phủ phần đất camera nhìn thấy sau / trước hầm
const FADE = 1.5;  // vào / ra hầm đổi dần trong ~0,7 giây
const SEGMENT = 6;  // vách hầm đổ bê tông từng đốt ~6 m: đường nối dọc cho mắt nhận ra là vách đứng, không phải mặt đường

/** Một đốt vách: phần dưới ốp gạch men sáng (như hầm Hải Vân), phần trên bê tông, đường nối đốt ở mép trái. */
function wallTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 128;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#b9b2a4";
  g.fillRect(0, 0, 128, 128);
  g.fillStyle = "#dfe6ea";  // gạch men 40 % dưới
  g.fillRect(0, 77, 128, 51);
  g.strokeStyle = "#9aa6ad";
  g.lineWidth = 1;
  for (let y = 77; y < 128; y += 10) g.strokeRect(0, y, 128, 10);
  for (let x = 0; x < 128; x += 16) g.strokeRect(x, 77, 16, 51);
  g.fillStyle = "#3a352e";  // đường nối đốt
  g.fillRect(0, 0, 4, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export class Tunnel {
  group = new THREE.Group();
  /** 0 ngoài hầm → 1 trong hầm (đổi mượt), scene dùng để làm tối ánh sáng, ẩn cảnh ngoài. */
  amount = 0;
  private belt = new Conveyor(1);
  private texture = noiseTexture(128, 0.7, 60);
  private wallTex = wallTexture();

  constructor() {
    // vách bê tông sáng, tự phát sáng nhẹ màu đèn natri: ánh trời đã tắt mà vách vẫn đọc ra là vách hầm
    this.wallTex.repeat.set((WRAP * 4) / SEGMENT, 1);
    const concrete = new THREE.MeshStandardMaterial({ map: this.wallTex, roughness: 0.9,
      emissive: 0x5a4628, emissiveIntensity: 0.6 });
    const rock = new THREE.MeshStandardMaterial({ color: 0x4a4038, map: this.texture, roughness: 1 });
    const far = new THREE.Mesh(strip(WRAP * 4, WALL_HIGH), concrete);
    const near = new THREE.Mesh(strip(WRAP * 4, WALL_LOW), concrete);
    near.rotation.y = Math.PI;  // quay mặt về phía đường
    this.group.add(at(far, 0, WALL_HIGH / 2, FAR_WALL_Z), at(near, 0, WALL_LOW / 2, NEAR_WALL_Z));
    for (const [y, z] of [[WALL_HIGH, FAR_WALL_Z - ROCK_DEPTH / 2], [WALL_LOW, NEAR_WALL_Z + ROCK_DEPTH / 2]]) {
      const top = new THREE.Mesh(strip(WRAP * 4, ROCK_DEPTH), rock);
      top.rotation.x = -Math.PI / 2;  // nằm ngang, mặt hướng lên camera
      this.group.add(at(top, 0, y, z));
    }
    // vạch phản quang chân vách + dải đèn vàng trên vách xa (đèn trôi theo xe → cảm giác lao trong hầm)
    const stripe = new THREE.Mesh(strip(WRAP * 4, 0.35), soft(0xf4c04e, 0.5));
    this.group.add(at(stripe, 0, 0.6, FAR_WALL_Z + 0.02));
    const lampMat = new THREE.MeshStandardMaterial({ color: 0xffe2a0, emissive: 0xffc46b, emissiveIntensity: 2.2 });
    const lampGeo = new THREE.BoxGeometry(0.8, 0.45, 0.12);  // đèn vuông: không giống vạch kẻ đường
    for (let x = -WRAP; x < WRAP; x += LAMP_GAP) {
      const lamp = new THREE.Mesh(lampGeo, lampMat);
      this.group.add(this.belt.add(at(lamp, x, WALL_HIGH - 1.2, FAR_WALL_Z + 0.08)));
    }
    this.group.visible = false;
  }

  update(dt: number, inside: boolean, dx: number): void {
    this.amount = THREE.MathUtils.clamp(this.amount + (inside ? 1 : -1) * dt * FADE, 0, 1);
    this.group.visible = this.amount > 0.02;
    if (!this.group.visible) return;
    this.belt.advance(dx);
    this.texture.offset.x += dx / (WRAP * 4 / 60);  // đá trôi cùng tốc độ đường
    this.wallTex.offset.x += dx / SEGMENT;
  }
}
