// 離線快取：資料更新時請修改 VERSION
var VERSION = 'nhi-v5';
var FILES = ['./', 'index.html', 'style.css', 'app.js', 'data/urology.js', 'data/all-codes.js',
  'manifest.webmanifest', 'icon.svg'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(FILES); }));
  self.skipWaiting();
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== VERSION; })
      .map(function (k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});
// 先用網路（取得最新版），失敗再用快取
self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).then(function (res) {
    var copy = res.clone();
    caches.open(VERSION).then(function (c) { c.put(e.request, copy); });
    return res;
  }).catch(function () {
    return caches.match(e.request, { ignoreSearch: true });
  }));
});
