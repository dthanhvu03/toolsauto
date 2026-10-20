/**
 * Entrypoint: Tích hợp Scene, Graph, Telemetry và Controls Manager
 */
import { initScene } from './scene.js?v=2.3';
import { ClusterGraph } from './graph.js?v=2.3';
import { TelemetryService } from './telemetry.js?v=2.3';
import { ClusterControlsManager } from './controls.js?v=2.3';

let autoRotate = true;

document.addEventListener('DOMContentLoaded', () => {
  // 1. Khởi tạo Three.js Scene
  const { scene, camera, renderer, controls } = initScene('webgl-container');

  // 2. Khởi tạo Graph Builder
  const graph = new ClusterGraph(scene);

  // 3. Khởi tạo Controls & Interactivity
  const controlsManager = new ClusterControlsManager(camera, controls, graph);

  // 4. Khởi tạo Telemetry Service
  const telemetry = new TelemetryService((data) => {
    graph.build(data);

    // Mặc định: Trên desktop focus & mở drawer; Trên mobile giữ toàn cảnh 3D thoáng đãng
    const isMobile = window.innerWidth <= 768;
    if (data.accounts && data.accounts.length >= 3) {
      if (!isMobile) {
        controlsManager.focusAccountNode(3);
        controlsManager.openInspector('account', data.accounts[2]);
      }
    }
  });

  // Nút Toggle tự xoay
  const toggleRotateBtn = document.getElementById('btn-toggle-rotate');
  if (toggleRotateBtn) {
    toggleRotateBtn.addEventListener('click', (e) => {
      autoRotate = !autoRotate;
      e.target.textContent = autoRotate ? 'Dừng tự xoay' : 'Bật tự xoay';
    });
  }

  // Nút Refresh
  const refreshBtn = document.getElementById('btn-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      telemetry.fetchStatus();
    });
  }

  // 5. Animation Render Loop
  function animate() {
    requestAnimationFrame(animate);

    controls.update();

    if (autoRotate && !controls.state == -1) {
      scene.rotation.y += 0.0012;
    }

    graph.updateAnimations();

    renderer.render(scene, camera);
  }

  animate();

  // 6. Tải dữ liệu ban đầu và định kỳ 20 giây làm mới
  telemetry.fetchStatus();
  setInterval(() => {
    telemetry.fetchStatus();
  }, 20000);
});
