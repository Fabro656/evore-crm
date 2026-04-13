// Evore CRM — Service Worker v3
const CACHE_NAME = 'evore-v3';

self.addEventListener('install', event => {
  // Skip waiting to activate immediately
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  // Delete ALL old caches and claim clients
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // Only intercept GET requests
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Never cache API, auth, or dynamic routes
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname === '/cambiar-rol') return;
  if (url.pathname === '/login') return;
  if (url.pathname === '/logout') return;

  // CDN assets (Bootstrap, icons): cache-first
  if (url.hostname === 'cdn.jsdelivr.net') {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
          }
          return resp;
        }).catch(() => caches.match(event.request));
      })
    );
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
          }
          return resp;
        }).catch(() => new Response('', { status: 408 }));
      })
    );
    return;
  }

  // All other requests (HTML pages): always network, no cache
  // This prevents stale pages after deploys
});
