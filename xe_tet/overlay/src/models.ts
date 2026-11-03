// Nạp sẵn các model 3D (.glb) được dựng từ Blender 4.0 trước khi tạo World,
// giúp clone đồng bộ (synchronous) trong Bus và Landscape mà không đổi kiến trúc hay làm trễ khung hình.

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { bendTree } from "./bend";

export const BLENDER_MODELS: {
  busCoach: THREE.Group | null;
  busWheel: THREE.Group | null;
  villageHouse: THREE.Group | null;
} = {
  busCoach: null,
  busWheel: null,
  villageHouse: null,
};

function prepModel(root: THREE.Group): THREE.Group {
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh) {
      m.castShadow = true;
      m.receiveShadow = true;
    }
  });
  bendTree(root);
  return root;
}

// Bật ?glb=1 (mặc định bật, hoặc ?glb=0 để ép dùng Three.js Procedural thuần phục vụ so sánh công bằng A/B/C)
const USE_GLB = new URLSearchParams(location.search).get("glb") !== "0";

export async function preloadBlenderModels(): Promise<void> {
  if (!USE_GLB) return;
  const loader = new GLTFLoader();
  const loadOne = (url: string): Promise<THREE.Group | null> =>
    new Promise((resolve) => {
      loader.load(
        url,
        (gltf) => resolve(prepModel(gltf.scene)),
        undefined,
        () => resolve(null),
      );
    });

  const [busCoach, busWheel, villageHouse] = await Promise.all([
    loadOne("/models/bus_coach.glb"),
    loadOne("/models/bus_wheel.glb"),
    loadOne("/models/village_house.glb"),
  ]);
  BLENDER_MODELS.busCoach = busCoach;
  BLENDER_MODELS.busWheel = busWheel;
  BLENDER_MODELS.villageHouse = villageHouse;
}
