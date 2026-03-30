// Beisser OPS Service Worker — Shell asset caching only (no data caching)
const CACHE_NAME = 'beisser-ops-shell-v1';
const SHELL_ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap',
  'https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/all.min.css'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Only serve from cache for shell assets (CSS, JS, fonts)
  const isShellAsset = SHELL_ASSETS.some(asset => url.href.includes(asset) || url.pathname === asset);
  if (isShellAsset) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
