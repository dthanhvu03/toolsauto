/**
 * Entrypoint: Tích hợp Scene, Graph, Telemetry (Polling 30s) và Controls Manager.
 * Mobile (≤768px / touch phone): tắt WebGL — GPU yếu/iOS hay render màn đen.
 */
import { initScene } from './scene.js';
import { ClusterGraph } from './graph.js?v=20261021c';
import { TelemetryService } from './telemetry.js';
import { ClusterControlsManager } from './controls.js';
import { DispatchFeedTerminal } from './dispatch_feed.js?v=20261021c';

let autoRotate = true;

/** Phát hiện mobile / tablet nhỏ — không khởi tạo Three.js WebGL. */
export function isMobileClusterView() {
  if (typeof window === 'undefined') return false;
  if (window.__BUFFER_CLUSTER_MOBILE === true) return true;
  const narrow = window.matchMedia('(max-width: 768px)').matches;
  const coarse = window.matchMedia('(pointer: coarse)').matches && window.innerWidth <= 900;
  const uaMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || '');
  return narrow || (uaMobile && (narrow || coarse || window.innerWidth <= 900));
}

function createNoopGraph() {
  return {
    accountNodes: [],
    channelNodes: [],
    build() {},
    updateAnimations() {},
    applyFilter() {},
    updateAccountStatus() {},
    pulseActivity() {},
    getInteractiveMeshes() {
      return [];
    },
  };
}

document.addEventListener('DOMContentLoaded', () => {
  const mobile2d = isMobileClusterView();
  if (mobile2d) {
    document.body.classList.add('mode-2d');
    const webgl = document.getElementById('webgl-container');
    if (webgl) {
      webgl.setAttribute('aria-hidden', 'true');
      webgl.style.display = 'none';
      webgl.replaceChildren();
    }
  }

  // 0. Register PWA Service Worker
  if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js')
        .then((reg) => {
          console.log('[PWA] Service Worker registered successfully:', reg.scope);
        })
        .catch((err) => {
          console.warn('[PWA] Service Worker registration failed:', err);
        });
    });
  }

  let scene = null;
  let camera = null;
  let renderer = null;
  let controls = null;
  let graph;

  if (mobile2d) {
    // 1–2. Mobile 2D: không WebGL, chỉ HUD + account cards + inspector sheet
    graph = createNoopGraph();
    camera = null;
    controls = { update() {}, state: -1, target: { x: 0, y: 0, z: 0, clone() { return { x: 0, y: 0, z: 0, lerpVectors() {} }; } } };
  } else {
    // 1. Khởi tạo Three.js Scene
    ({ scene, camera, renderer, controls } = initScene('webgl-container'));
    // 2. Khởi tạo Graph Builder
    graph = new ClusterGraph(scene);
  }

  // 3. Khởi tạo Controls & Interactivity
  const controlsManager = new ClusterControlsManager(camera, controls, graph, { mobile2d });

  // 4. Khởi tạo Telemetry Service với 3 callbacks đồng bộ
  let didInitialFocus = false;
  const telemetry = new TelemetryService(
    (data) => {
      // Callback: onDataLoaded
      graph.build(data);
      window.dispatchTerminal?.replayPulses?.();

      const hint = document.getElementById('hud-stage-hint');
      if (hint && data.accounts && data.accounts.length) {
        hint.style.opacity = mobile2d ? '0' : '0.35';
      }

      // Lần đầu: highlight card đầu, camera overview (desktop). Không auto-mở inspector.
      if (!didInitialFocus && data.accounts && data.accounts.length) {
        didInitialFocus = true;
        const first = data.accounts[0];
        document.querySelectorAll('.account-card').forEach((c) => c.classList.remove('selected'));
        const card = document.getElementById(`card-acc-${first.index}`);
        if (card) card.classList.add('selected');

        if (!mobile2d && typeof THREE !== 'undefined' && controlsManager.smoothMoveCamera) {
          controlsManager.smoothMoveCamera(
            new THREE.Vector3(0, 140, 280),
            new THREE.Vector3(0, 20, 0)
          );
        }
      }
    },
    (acc, result) => {
      // Callback: onAccountUpdated (từ Ping Key)
      if (result && result.status) {
        graph.updateAccountStatus(acc.index, result.status);
      }
    },
    (filter) => {
      // Callback: onFilterApplied (từ Search & Platform filter)
      graph.applyFilter(filter);
    }
  );

  // Expose global telemetryService for controls
  window.telemetryService = telemetry;

  // Nút Toggle tự xoay
  const toggleRotateBtn = document.getElementById('btn-toggle-rotate');
  if (toggleRotateBtn) {
    if (mobile2d) {
      toggleRotateBtn.style.display = 'none';
    } else {
      toggleRotateBtn.addEventListener('click', (e) => {
        autoRotate = !autoRotate;
        e.target.textContent = autoRotate ? 'Dừng tự xoay' : 'Bật tự xoay';
      });
    }
  }

  // 5. Animation Render Loop — chỉ desktop WebGL
  if (!mobile2d && renderer && scene && camera && controls) {
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
  }

  // 6. Tải dữ liệu ban đầu và khởi động polling 30 giây (F7, F8, F10)
  telemetry.fetchStatus();
  telemetry.startPolling(30000);

  // 7. Live Dispatch Terminal — poll /api/buffer/dispatch-feed (F12)
  const dispatchTerminal = new DispatchFeedTerminal();
  dispatchTerminal.attachGraph(graph);
  dispatchTerminal.start(8000);
  window.dispatchTerminal = dispatchTerminal;

  // Nút Refresh (status + dispatch feed)
  const refreshBtn = document.getElementById('btn-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      telemetry.fetchStatus();
      dispatchTerminal.fetchFeed();
    });
  }

  const refreshDispatchBtn = document.getElementById('btn-refresh-dispatch');
  if (refreshDispatchBtn) {
    refreshDispatchBtn.addEventListener('click', () => dispatchTerminal.fetchFeed());
  }

  // Lắng nghe sự kiện lọc nếu được kích hoạt từ component bên ngoài
  window.addEventListener('cluster:filter-change', (e) => {
    if (e.detail) {
      telemetry.applyFilter(e.detail);
    }
  });
});
