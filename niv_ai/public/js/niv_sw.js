// Niv AI Service Worker — basic cache for PWA
const CACHE_NAME = 'niv-ai-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Let all requests pass through — no offline caching for now
  // This SW exists only to enable PWA "Add to Home Screen"
  event.respondWith(fetch(event.request));
});
