// Evore CRM — Service Worker v1
const CACHE_NAME = 'evore-v1';
const OFFLINE_URL = '/offline';

// Assets to precache on install
const PRECACHE = [
  '/static/img/evore-horizontal.svg',
  '/static/img/evore-vertical.svg',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
];

// Install: precache shell assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE).catch(() => {});
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first for HTML, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip non-GET and API calls
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.hostname === 'cdn.jsdelivr.net') {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: network-first with offline fallback
  if (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match(OFFLINE_URL) || new Response(
          '<html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#0F172A;color:#fff;flex-direction:column">' +
          '<h1 style="font-size:2rem;margin-bottom:1rem">Evore CRM</h1>' +
          '<p style="color:#9CA3B4">Sin conexion. Verifica tu internet e intenta de nuevo.</p>' +
          '<button onclick="location.reload()" style="margin-top:1rem;padding:8px 24px;background:#0176D3;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:1rem">Reintentar</button>' +
          '</body></html>',
          { headers: { 'Content-Type': 'text/html' } }
        );
      })
    );
    return;
  }
});
