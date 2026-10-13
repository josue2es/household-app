/*
 * Service worker: makes the app installable and shows a friendly page when
 * there's no connection. It doesn't cache the app itself: NiceGUI pages need
 * a live connection to the server for everything anyway.
 *
 * Served at /sw.js (see app/pwa.py) so it covers every page of the site.
 * Bump CACHE when offline.html changes, so phones fetch the new one.
 */
const CACHE = 'hogar-offline-v1';
const OFFLINE_URL = '/pwa/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// Page loads go to the network as usual; only when that fails (offline) do
// we answer with the offline page. Everything else (scripts, the websocket,
// photo uploads) is left to the browser.
self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
});
