// Evore CRM — Service Worker v2
const CACHE_NAME = 'evore-v2';
const OFFLINE_URL = '/offline';

const PRECACHE = [
  '/offline',
  '/static/img/evore-horizontal.svg',
  '/static/img/evore-vertical.svg',
  '/static/img/icon-192.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // Only handle GET
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Skip API, auth endpoints, and CSRF-dependent routes
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname === '/cambiar-rol') return;

  // CDN assets: cache-first
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

  // HTML pages: network-first, offline fallback
  if (event.request.headers.get('accept') &&
      event.request.headers.get('accept').includes('text/html')) {
    event.respondWith(
      fetch(event.request)
        .then(resp => {
          // Cache successful HTML responses for faster back-navigation
          if (resp.ok && !url.pathname.includes('logout')) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
          }
          return resp;
        })
        .catch(() => {
          // Try cached version first, then offline page
          return caches.match(event.request)
            .then(cached => cached || caches.match(OFFLINE_URL));
        })
    );
    return;
  }
});
