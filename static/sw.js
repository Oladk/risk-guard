// Service worker minimal : rend l'app installable (PWA).
// Un handler `fetch` (même pass-through) est requis pour l'installabilité.
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => self.clients.claim());
self.addEventListener('fetch', (e) => { /* pass-through réseau */ });
