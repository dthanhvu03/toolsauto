/**
 * Entrypoint: Tích hợp Scene, Graph, Telemetry và Controls Manager
 * Hỗ trợ PWA Service Worker & Mobile Web App Standalone.
 */
import { initScene } from './scene.js?v=2.4';
import { ClusterGraph } from './graph.js?v=2.4';
import { TelemetryService } from './telemetry.js?v=2.4';
import { ClusterControlsManager } from './controls.js?v=2.4';

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

    // Mặc định: Chỉ tự động focus & mở drawer trên Desktop để giữ mobile thoáng đãng
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

  // Nút Refresh Telemetry
  const refreshBtn = document.getElementById('btn-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      telemetry.fetchStatus();
    });
  }

  // Nút Tải lại toàn bộ Web App (Hard Reload & Clear Cache)
  const reloadBtn = document.getElementById('btn-hard-reload');
  if (reloadBtn) {
    reloadBtn.addEventListener('click', () => {
      window.location.href = window.location.origin + window.location.pathname + '?_reload=' + Date.now();
    });
  }

  // 5. PWA Installation Handler
  let deferredPrompt = null;
  const installBtn = document.getElementById('btn-install-pwa');

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (installBtn) {
      installBtn.style.display = 'flex';
    }
  });

  if (installBtn) {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    const isStandalone = window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches;
    if (isIOS && !isStandalone) {
      installBtn.style.display = 'flex';
    }

    installBtn.addEventListener('click', async () => {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        if (outcome === 'accepted') {
          installBtn.style.display = 'none';
        }
        deferredPrompt = null;
      } else {
        if (window.showToast) {
          window.showToast('Trên iPhone: Bấm nút Chia sẻ ⎋ -> chọn "Thêm vào MH chính" ➕', 4500);
        } else {
          alert('Để cài app trên iPhone: Bấm nút Chia sẻ ⎋ của Safari -> chọn "Thêm vào MH chính" ➕');
        }
      }
    });
  }

  window.addEventListener('appinstalled', () => {
    console.log('[PWA] App installed successfully');
    if (installBtn) installBtn.style.display = 'none';
  });

  // 6. Animation Render Loop
  function animate() {
    requestAnimationFrame(animate);

    controls.update();

    if (autoRotate && controls.state === -1) {
      scene.rotation.y += 0.0012;
    }

    graph.updateAnimations();

    renderer.render(scene, camera);
  }

  animate();

  // 7. Tải dữ liệu ban đầu và định kỳ 20 giây làm mới
  telemetry.fetchStatus();
  setInterval(() => {
    telemetry.fetchStatus();
  }, 20000);
});

// 8. Đăng ký Service Worker cho PWA
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').then((reg) => {
      console.log('[PWA] ServiceWorker registered with scope:', reg.scope);
    }).catch((err) => {
      console.warn('[PWA] ServiceWorker registration failed:', err);
    });
  });
}
