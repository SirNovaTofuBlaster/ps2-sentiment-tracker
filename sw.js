// Spindle's service worker: lets the site be installed and open without a connection.
// Network first, always: a page or data file is fetched fresh, and the copy kept from the last
// visit is used only when the network fails. So it can never show old numbers while online.
// It keeps nothing about the visitor: the collection is stored by the page in the browser, not here.
const CACHE = 'spindle-v1';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  // Only our own pages and files; GitHub's API, CDNs and everything else go straight through.
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => caches.match(request).then(found => found || caches.match('./')))
  );
});
