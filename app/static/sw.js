// Службовий сценарій: дозволяє відкрити форму запису розмови без мережі,
// якщо її вже відкривали на цьому пристрої.
const CACHE = 'conferback-v1';
const STATIC = [
  '/static/vendor/bootstrap.min.css',
  '/static/vendor/bootstrap-icons.css',
  '/static/vendor/fonts/bootstrap-icons.woff2',
  '/static/vendor/bootstrap.bundle.min.js',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/js/capture.js',
  '/static/img/icon.svg',
  '/offline'
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
  ).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;

  if (url.pathname.startsWith('/static/')) {
    // Статичні файли: спершу з пам'яті
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    })));
    return;
  }

  if (req.mode === 'navigate') {
    // Сторінки: спершу мережа; форму запису розмови запам'ятовуємо на випадок втрати зв'язку
    e.respondWith(fetch(req).then((res) => {
      if (res.ok && /\/events\/\d+\/capture$/.test(url.pathname)) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || caches.match('/offline'))));
  }
});
