// Chanakya AI Service Worker — PWA + basic caching
const CACHE_NAME = 'chanakya-ai-v1.3.0';
const PRECACHE_URLS = [
  '/app/niv-chat',
  '/assets/niv_ai/css/niv_widget.css',
  '/assets/niv_ai/images/niv-icon-192.png',
  '/assets/niv_ai/images/niv-icon-512.png',
  '/assets/niv_ai/images/niv_logo.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => {
      return Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Network first, fallback to cache (for API calls always network)
  if (event.request.url.includes('/api/') || event.request.method !== 'GET') {
    return;
  }
  event.respondWith(
    fetch(event.request).then((response) => {
      // Cache successful responses
      if (response.ok && response.type === 'basic') {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
      }
      return response;
    }).catch(() => {
      return caches.match(event.request);
    })
  );
});
