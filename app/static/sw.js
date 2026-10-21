/* Buffer 3D Neural Cluster Service Worker */
/* Bump CACHE_NAME mỗi lần đổi CSS/JS để iOS/PWA không giữ bản cũ (màn tối / backdrop). */
const CACHE_NAME = 'buffer-cluster-v20261020f';
const API_CACHE_NAME = 'buffer-cluster-api-v1';

const STATIC_ASSETS = [
  '/buffer-cluster',
  '/manifest.json',
  '/static/css/buffer_cluster.css?v=20261020f',
  '/static/js/buffer_cluster/app.js?v=20261020f',
  '/static/js/buffer_cluster/scene.js',
  '/static/js/buffer_cluster/graph.js',
  '/static/js/buffer_cluster/controls.js',
  '/static/js/buffer_cluster/telemetry.js',
  '/static/js/buffer_cluster/dispatch_feed.js',
  '/static/vendor/three/three.min.js',
  '/static/vendor/three/OrbitControls.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon-32.png',
  '/static/icons/favicon.ico'
];

// 1. Install Event: Pre-cache static shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Some assets failed to pre-cache during install:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// 2. Activate Event: Clean up stale caches & claim clients
self.addEventListener('activate', (event) => {
  const currentCaches = [CACHE_NAME, API_CACHE_NAME];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (!currentCaches.includes(name)) {
            console.log('[SW] Deleting stale cache:', name);
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch Event: Dual Caching Strategy
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Non-GET requests (e.g. POST ping-key) bypass cache
  if (request.method !== 'GET') {
    return;
  }

  // Strategy A: Telemetry & Status APIs (Network-first with cache fallback)
  if (url.pathname.startsWith('/api/buffer/')) {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(API_CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return networkResponse;
        })
        .catch(async () => {
          const cachedResponse = await caches.match(request);
          if (cachedResponse) {
            return cachedResponse;
          }
          // Offline fallback JSON
          return new Response(
            JSON.stringify({
              ok: false,
              offline: true,
              message: 'Mất kết nối mạng. Đang ở chế độ offline.'
            }),
            {
              headers: { 'Content-Type': 'application/json' },
              status: 503
            }
          );
        })
    );
    return;
  }

  // Strategy B: Static assets and Shell (Cache-first with network fallback)
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        // Stale-while-revalidate for local application scripts and styles
        if (url.origin === self.location.origin && !url.pathname.startsWith('/static/vendor/')) {
          fetch(request).then((freshResponse) => {
            if (freshResponse && freshResponse.status === 200) {
              caches.open(CACHE_NAME).then((cache) => cache.put(request, freshResponse));
            }
          }).catch(() => {});
        }
        return cachedResponse;
      }

      return fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return networkResponse;
        })
        .catch(() => {
          // If navigation fails, return cached /buffer-cluster HTML
          if (request.mode === 'navigate') {
            return caches.match('/buffer-cluster');
          }
        });
    })
  );
});
