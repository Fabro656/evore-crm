// Evore CRM — Service Worker (minimal, no HTML caching)
const V = 'evore-static-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const u = new URL(e.request.url);
  // Only cache CDN and /static/ assets — never HTML
  if (u.hostname === 'cdn.jsdelivr.net' || u.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(e.request).then(c => c || fetch(e.request).then(r => {
      if (r.ok) { const cl = r.clone(); caches.open(V).then(ca => ca.put(e.request, cl)); }
      return r;
    })));
  }
});
