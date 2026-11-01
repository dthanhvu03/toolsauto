// «Thế giới uốn cong» (BRD-tuyen-xe mục 7): xe đứng yên quanh x = 0, đoạn đường phía trước / phía sau uốn ngay trong
// shader — cua: z += curve·x²; dốc: y += grade·x + crest·x². Không phải dựng đường cong thật, mọi vật ven đường uốn theo.
// Độ uốn lấy từ hồ sơ đường thật (độ quanh co OSRM, đèo) và đổi mượt theo thời gian (scene.ts). Lượt vẽ bóng đổ
// cũng uốn (vật liệu độ sâu dùng chung) nên bóng luôn nằm đúng dưới vật dù cua gắt.

import * as THREE from "three";

const BEND = { curve: { value: 0 }, grade: { value: 0 }, crest: { value: 0 } };


// Uốn chạy trên đỉnh: mặt phẳng dài chỉ có 2 đỉnh ở hai đầu thì phần giữa nội suy thẳng — cả mặt đất bị nhấc lên
// che mất xe. Mặt dài dọc đường (mặt đường, lề, nền đất, biển) phải có đỉnh mỗi 2,5 đơn vị.
const BEND_STEP = 2.5;

const HEADER = "uniform float uBendCurve;\nuniform float uBendGrade;\nuniform float uBendCrest;\n";

// Thay khối chiếu đỉnh chuẩn của three (project_vertex): đưa sang toạ độ thế giới, uốn, rồi mới nhân view / projection.
const BENT_PROJECT = /* glsl */ `
vec4 bentPos = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	bentPos = batchingMatrix * bentPos;
#endif
#ifdef USE_INSTANCING
	bentPos = instanceMatrix * bentPos;
#endif
bentPos = modelMatrix * bentPos;
float bendX = clamp( bentPos.x, -120.0, 120.0 );
bentPos.z += uBendCurve * bendX * bendX;
bentPos.y += uBendGrade * bendX + uBendCrest * bendX * bendX;
vec4 mvPosition = viewMatrix * bentPos;
gl_Position = projectionMatrix * mvPosition;
`;

function bendMaterial(material: THREE.Material): void {
  if (material.userData.bent || material instanceof THREE.ShaderMaterial) return;
  material.userData.bent = true;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uBendCurve = BEND.curve;
    shader.uniforms.uBendGrade = BEND.grade;
    shader.uniforms.uBendCrest = BEND.crest;
    shader.vertexShader = HEADER + shader.vertexShader.replace("#include <project_vertex>", BENT_PROJECT);
  };
  material.needsUpdate = true;
}

// Bóng đổ: three vẽ bản đồ bóng bằng vật liệu độ sâu riêng, không qua vật liệu của vật → phải uốn cả vật liệu đó.
// Không vật nào đổ bóng dùng alphaTest, nên một vật liệu độ sâu chung là đủ (three tự tách bản có / không instancing).
const BENT_DEPTH = new THREE.MeshDepthMaterial();
bendMaterial(BENT_DEPTH);

/** Cho mọi vật liệu trong nhánh uốn theo đường (vật liệu đã uốn thì bỏ qua — gọi lại nhiều lần không tốn). */
export function bendTree(root: THREE.Object3D): void {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.material) return;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) bendMaterial(material);
    if (mesh.isMesh && mesh.castShadow && !mesh.customDepthMaterial) mesh.customDepthMaterial = BENT_DEPTH;
  });
}

/** Mặt phẳng dài dọc trục x (chiều dài × rộng), chia đủ đỉnh để uốn theo đường. */
export function strip(length: number, width: number): THREE.PlaneGeometry {
  return new THREE.PlaneGeometry(length, width, Math.ceil(length / BEND_STEP), 1);
}

/** Đặt độ uốn đang hiển thị (0 khi vẽ cảnh trong xe — khoang trong xe đặt xa trục, uốn sẽ méo). */
export function setBend(curve: number, grade: number, crest: number): void {
  BEND.curve.value = curve;
  BEND.grade.value = grade;
  BEND.crest.value = crest;
}
