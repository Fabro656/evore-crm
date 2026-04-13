// Evore CRM — Service Worker (passthrough, only cleans old caches)
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  // Delete ALL caches from any previous SW version
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
// No fetch handler — let everything go to network naturally
