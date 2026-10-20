/**
 * Service Worker: Buffer 3D Cluster PWA
 * Cung cấp khả năng nạp tức thì (Instant Load) và hoạt động ngoại tuyến một phần.
 */

const CACHE_NAME = 'buffer-3d-cluster-v2.3';

const STATIC_ASSETS = [
  '/buffer-cluster',
  '/manifest.json',
  '/static/css/buffer_cluster.css?v=2.3',
  '/static/js/buffer_cluster/app.js?v=2.3',
  '/static/js/buffer_cluster/scene.js?v=2.3',
  '/static/js/buffer_cluster/graph.js?v=2.3',
  '/static/js/buffer_cluster/telemetry.js?v=2.3',
  '/static/js/buffer_cluster/controls.js?v=2.3',
  '/static/vendor/three/three.min.js',
  '/static/vendor/three/OrbitControls.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon-32.png',
];

// Install: Pre-cache core shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Pre-cache partial fail:', err);
      });
    })
  );
  self.skipWaiting();
});

// Activate: Xóa cache phiên bản cũ
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-First cho API, Stale-While-Revalidate cho static assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. Đối với API telemetry: luôn ưu tiên gọi Network để lấy số liệu thực tế
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  // 2. Đối với Static assets & HTML: Stale-While-Revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
