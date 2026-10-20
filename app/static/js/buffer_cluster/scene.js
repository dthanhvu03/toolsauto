/**
 * Module Scene: Khởi tạo Scene, Camera, Renderer, Ánh sáng và Môi trường không gian Three.js
 */
export function initScene(containerId) {
  const container = document.getElementById(containerId);
  const width = window.innerWidth;
  const height = window.innerHeight;

  // Scene
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x07090e, 0.0018);

  // Camera: Adapt FOV & position for mobile screens
  const isMobile = width <= 768;
  const camera = new THREE.PerspectiveCamera(isMobile ? 65 : 55, width / height, 0.1, 2000);
  camera.position.set(0, isMobile ? 180 : 140, isMobile ? 380 : 280);

  // Renderer
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  container.appendChild(renderer.domElement);

  // Controls (Touch-optimized for 1-finger rotate & 2-finger zoom/pan)
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.maxDistance = 700;
  controls.minDistance = 60;
  controls.maxPolarAngle = Math.PI / 2 + 0.1;
  controls.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_PAN
  };

  // Lights
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
  scene.add(ambientLight);

  const dirLight1 = new THREE.DirectionalLight(0x00f0ff, 1.8);
  dirLight1.position.set(100, 200, 100);
  scene.add(dirLight1);

  const dirLight2 = new THREE.DirectionalLight(0xec4899, 1.2);
  dirLight2.position.set(-100, -100, -100);
  scene.add(dirLight2);

  // Environment elements
  createCyberGrid(scene);
  createStarfield(scene);

  // Resize handler
  window.addEventListener('resize', () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    camera.aspect = w / h;
    camera.fov = (w <= 768) ? 65 : 55;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  });

  return { scene, camera, renderer, controls };
}

function createCyberGrid(scene) {
  const size = 600;
  const divisions = 50;
  const gridHelper = new THREE.GridHelper(size, divisions, 0x00f0ff, 0x112233);
  gridHelper.position.y = -60;
  gridHelper.material.opacity = 0.35;
  gridHelper.material.transparent = true;
  scene.add(gridHelper);
}

function createStarfield(scene) {
  const count = 1200;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 1200;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 800;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 1200;

    const isCyan = Math.random() > 0.5;
    colors[i * 3] = isCyan ? 0.0 : 0.9;
    colors[i * 3 + 1] = isCyan ? 0.8 : 0.3;
    colors[i * 3 + 2] = 1.0;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: 2,
    vertexColors: true,
    transparent: true,
    opacity: 0.7,
  });

  const starMesh = new THREE.Points(geometry, material);
  scene.add(starMesh);
}
