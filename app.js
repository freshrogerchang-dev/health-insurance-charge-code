(function () {
  'use strict';

  var URO = window.NHI_URO;
  var ALL = window.NHI_ALL;
  var META = window.NHI_META || {};
  var PAGE = 50;

  // ---------- 儲存（隱私模式下 localStorage 可能無法使用） ----------
  function load(key, fallback) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
    catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 忽略 */ }
  }

  // ---------- 正規化與同義字 ----------
  // 全形轉半形、小寫、去除空白與標點；同義字統一成群組第一個詞
  var synPairs = [];
  URO.synonyms.forEach(function (group) {
    group.forEach(function (w) {
      synPairs.push([w.toLowerCase(), group[0].toLowerCase()]);
    });
  });
  synPairs.sort(function (a, b) { return b[0].length - a[0].length; });

  function basic(s) {
    return (s || '').normalize('NFKC').toLowerCase()
      .replace(/[\s\-‐－—–_()（）\[\]【】,，、.。:：;；'"“”‘’/／\\+＋~～]/g, '');
  }
  function canon(s) {
    s = basic(s);
    for (var i = 0; i < synPairs.length; i++) {
      if (s.indexOf(synPairs[i][0]) !== -1) s = s.split(synPairs[i][0]).join(synPairs[i][1]);
    }
    return s;
  }

  // ---------- 建立索引 ----------
  var uroByCode = {};
  function makeItem(code, name, note, cat, alias) {
    var it = { code: code, name: name, note: note || '', cat: cat || '', alias: alias || '' };
    it.kCode = code.toLowerCase();
    it.kName = canon(name);
    it.kAlias = canon(alias);
    it.kAliasWords = (alias || '').split(/\s+/).filter(Boolean).map(canon);
    it.kCat = canon(cat);
    it.kNote = null; // 延遲建立
    return it;
  }
  var uroItems = URO.items.map(function (u) {
    var it = makeItem(u.code, u.name, u.note, u.cat, u.alias);
    uroByCode[u.code] = it;
    return it;
  });
  var allItems = null;
  function getAll() {
    if (!allItems) {
      allItems = ALL.map(function (r) {
        return uroByCode[r[0]] || makeItem(r[0], r[1], r[2], '', '');
      });
    }
    return allItems;
  }

  // ---------- 搜尋 ----------
  function subseqGap(hay, needle) {
    // needle 的每個字依序出現在 hay 中；回傳總間隔（越小越好），不符合回傳 -1
    var pos = -1, gap = 0;
    for (var i = 0; i < needle.length; i++) {
      var p = hay.indexOf(needle[i], pos + 1);
      if (p === -1) return -1;
      if (pos !== -1) gap += p - pos - 1;
      pos = p;
    }
    return gap;
  }

  function scoreToken(it, tok, raw) {
    if (it.kCode.indexOf(raw) === 0) return 1000 - it.kCode.length;
    var w = it.kAliasWords.indexOf(tok);
    if (w !== -1) return 600 - Math.min(w, 20);
    var p = it.kName.indexOf(tok);
    if (p !== -1) return 400 - Math.min(p, 50) - Math.min(it.kName.length, 50) / 10;
    if (it.kAlias.indexOf(tok) !== -1) return 300;
    if (it.kCat.indexOf(tok) !== -1) return 150;
    if (it.kCode.indexOf(raw) !== -1) return 120;
    return 0;
  }

  function search(items, query) {
    var raws = query.trim().split(/\s+/).filter(Boolean);
    var toks = raws.map(canon).filter(Boolean);
    var rawBasic = raws.map(basic);
    if (!toks.length) return { list: items.slice(), mode: 'none' };

    var hits = [];
    items.forEach(function (it) {
      var total = 0;
      for (var i = 0; i < toks.length; i++) {
        var s = scoreToken(it, toks[i], rawBasic[i]);
        if (!s) return;
        total += s;
      }
      hits.push([total, it]);
    });
    var mode = 'exact';

    if (!hits.length) {
      // 規範內文比對
      items.forEach(function (it) {
        if (it.kNote === null) it.kNote = canon(it.note);
        for (var i = 0; i < toks.length; i++) if (it.kNote.indexOf(toks[i]) === -1) return;
        hits.push([1, it]);
      });
      mode = 'note';
    }
    if (!hits.length) {
      // 模糊比對：字依序出現即可（例如「腎部切」可找到「腎部份切除術」）
      items.forEach(function (it) {
        var total = 0;
        for (var i = 0; i < toks.length; i++) {
          var g = subseqGap(it.kName + '|' + it.kAlias, toks[i]);
          if (g === -1 || g > toks[i].length * 6) return;
          total += 100 - g;
        }
        hits.push([total, it]);
      });
      mode = 'fuzzy';
    }
    hits.sort(function (a, b) { return b[0] - a[0] || (a[1].code < b[1].code ? -1 : 1); });
    return { list: hits.map(function (h) { return h[1]; }), mode: mode };
  }

  // ---------- 畫面 ----------
  var $ = function (id) { return document.getElementById(id); };
  var qEl = $('q'), listEl = $('list'), statusEl = $('status'), moreEl = $('more'), catsEl = $('cats');
  var state = { scope: load('scope', 'uro'), cat: '', shown: PAGE, results: [] };
  var favs = load('favs', []);

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function highlight(text, raws) {
    var html = esc(text);
    if (!raws.length) return html;
    var words = [];
    raws.forEach(function (r) {
      var c = canon(r);
      words.push(r);
      URO.synonyms.forEach(function (g) {
        if (g.some(function (w) { return canon(w) === c; })) words = words.concat(g);
      });
    });
    words = words.filter(function (w) { return w.length > 0; })
      .map(function (w) { return esc(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); })
      .sort(function (a, b) { return b.length - a.length; });
    try {
      return html.replace(new RegExp('(' + words.join('|') + ')', 'gi'), '<mark>$1</mark>');
    } catch (e) { return html; }
  }

  function renderCats() {
    if (state.scope === 'all') { catsEl.hidden = true; return; }
    catsEl.hidden = false;
    var cats = [''].concat(URO.categories);
    catsEl.innerHTML = cats.map(function (c) {
      return '<button type="button" data-cat="' + esc(c) + '"' + (c === state.cat ? ' class="on"' : '') + '>' +
        (c ? esc(c) : '全部分類') + '</button>';
    }).join('');
  }

  function baseItems() {
    if (state.scope === 'all') return getAll();
    var items = uroItems;
    if (state.scope === 'fav') {
      var idx = {};
      getAll().forEach(function (it) { idx[it.code] = it; });
      items = favs.map(function (c) { return idx[c]; }).filter(Boolean);
    }
    if (state.cat) items = items.filter(function (it) { return it.cat === state.cat; });
    return items;
  }

  function run() {
    var q = qEl.value;
    var r = search(baseItems(), q);
    state.results = r.list;
    state.shown = PAGE;
    var n = r.list.length;
    var msg = '';
    if (r.mode === 'none') {
      msg = state.scope === 'fav' ? '已加入常用的代碼（點 ☆ 加入）' : '共 ' + n + ' 項';
    } else {
      msg = '找到 ' + n + ' 項';
      if (r.mode === 'note') msg += '（名稱沒有，以下為支付規範內文符合）';
      if (r.mode === 'fuzzy') msg += '（模糊比對）';
      if (!n && state.scope !== 'all') msg += '，試試切到「全部」查詢';
    }
    statusEl.textContent = msg;
    render();
    suggest();
  }

  // ---------- 輸入時的下拉建議 ----------
  var sugEl = $('suggest'), sugList = [], sugIdx = -1, SUG_MAX = 8;
  function hideSug() {
    sugEl.hidden = true; sugIdx = -1;
    qEl.setAttribute('aria-expanded', 'false');
  }
  function suggest() {
    var q = qEl.value.trim();
    if (!q || document.activeElement !== qEl) { hideSug(); return; }
    var seen = {};
    sugList = state.results.slice(0, SUG_MAX).map(function (it) { seen[it.code] = 1; return { it: it, other: false }; });
    if (sugList.length < SUG_MAX && state.scope !== 'all') {
      // 目前範圍不夠時，從全部代碼補上
      search(getAll(), q).list.some(function (it) {
        if (!seen[it.code]) sugList.push({ it: it, other: true });
        return sugList.length >= SUG_MAX;
      });
    }
    var raws = q.split(/\s+/);
    var html = sugList.map(function (s, i) {
      return '<li role="option" data-i="' + i + '"' + (i === sugIdx ? ' class="active"' : '') + '>' +
        '<span class="s-code">' + highlight(s.it.code, raws) + '</span>' +
        '<span class="s-name">' + highlight(s.it.name, raws) + '</span>' +
        (s.other ? '<span class="s-tag">全部</span>' : '') + '</li>';
    }).join('');
    if (!sugList.length) html = '<li class="s-more">查無相符代碼</li>';
    else if (state.results.length > SUG_MAX) html += '<li class="s-more">共 ' + state.results.length + ' 項，按搜尋看全部</li>';
    sugEl.innerHTML = html;
    sugEl.hidden = false;
    qEl.setAttribute('aria-expanded', 'true');
  }
  function pickSug(i) {
    var s = sugList[i];
    if (!s) return;
    qEl.value = s.it.code;
    if (s.other) state.cat = '';
    hideSug();
    qEl.blur();
    if (s.other && state.scope !== 'all') setScope('all'); else run();
  }
  // 用 mousedown 避免輸入框先失焦把選單關掉
  sugEl.addEventListener('mousedown', function (e) {
    var li = e.target.closest('li[data-i]');
    e.preventDefault();
    if (li) pickSug(+li.getAttribute('data-i'));
  });
  qEl.addEventListener('keydown', function (e) {
    if (e.isComposing) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (sugEl.hidden || !sugList.length) return;
      e.preventDefault();
      var n = sugList.length;
      sugIdx = e.key === 'ArrowDown' ? (sugIdx + 1) % n : (sugIdx - 1 + n) % n;
      suggest();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (sugIdx >= 0) pickSug(sugIdx); else { hideSug(); qEl.blur(); }
    } else if (e.key === 'Escape') {
      hideSug();
    }
  });
  qEl.addEventListener('focus', suggest);
  qEl.addEventListener('blur', function () { setTimeout(hideSug, 150); });

  function render() {
    var raws = qEl.value.trim().split(/\s+/).filter(Boolean);
    var slice = state.results.slice(0, state.shown);
    if (!slice.length) {
      listEl.innerHTML = '<li class="empty">' + (state.scope === 'fav' ? '尚無常用代碼' : '查無資料') + '</li>';
    } else {
      listEl.innerHTML = slice.map(function (it) {
        var fav = favs.indexOf(it.code) !== -1;
        var sub = '';
        if (it.cat) sub += '<span class="tag">' + esc(it.cat) + '</span>';
        if (it.alias) sub += '<span class="alias">' + highlight(it.alias, raws) + '</span>';
        return '<li class="item">' +
          '<div class="row1">' +
          '<button type="button" class="code" data-copy="' + esc(it.code) + '" title="複製代碼">' + highlight(it.code, raws) + '</button>' +
          '<div class="name">' + highlight(it.name, raws) + '</div>' +
          '<button type="button" class="star' + (fav ? ' on' : '') + '" data-fav="' + esc(it.code) + '" aria-label="' + (fav ? '移除常用' : '加入常用') + '">' + (fav ? '★' : '☆') + '</button>' +
          '</div>' +
          (sub ? '<div class="sub">' + sub + '</div>' : '') +
          (it.note ? '<details><summary>支付規範</summary><p>' + highlight(it.note, raws) + '</p></details>' : '') +
          '</li>';
      }).join('');
    }
    moreEl.hidden = state.results.length <= state.shown;
  }

  var toastTimer;
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 1200);
  }
  function copy(text) {
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) { /* 忽略 */ }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).catch(fallback);
    } else { fallback(); }
    toast('已複製 ' + text);
  }

  function setScope(s) {
    state.scope = s;
    state.cat = '';
    save('scope', s);
    Array.prototype.forEach.call(document.querySelectorAll('.scope button'), function (b) {
      b.classList.toggle('on', b.getAttribute('data-scope') === s);
    });
    renderCats();
    run();
  }

  // ---------- 事件 ----------
  var debounce;
  qEl.addEventListener('input', function () {
    sugIdx = -1;
    clearTimeout(debounce);
    debounce = setTimeout(run, state.scope === 'all' ? 120 : 30);
  });
  $('clear').addEventListener('click', function () { qEl.value = ''; run(); qEl.focus(); });
  document.querySelector('.scope').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-scope]');
    if (b) setScope(b.getAttribute('data-scope'));
  });
  catsEl.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-cat]');
    if (!b) return;
    state.cat = b.getAttribute('data-cat');
    renderCats();
    run();
  });
  listEl.addEventListener('click', function (e) {
    var c = e.target.closest('[data-copy]');
    if (c) { copy(c.getAttribute('data-copy')); return; }
    var f = e.target.closest('[data-fav]');
    if (f) {
      var code = f.getAttribute('data-fav');
      var i = favs.indexOf(code);
      if (i === -1) favs.push(code); else favs.splice(i, 1);
      save('favs', favs);
      if (state.scope === 'fav') run(); else render();
    }
  });
  moreEl.addEventListener('click', function () { state.shown += PAGE; render(); });

  $('meta').textContent = '資料：' + (META.source || '健保署醫療服務給付項目') +
    (META.sourceVersion ? '（' + META.sourceVersion + ' 版，共 ' + META.count + ' 項）' : '');

  if (['uro', 'all', 'fav'].indexOf(state.scope) === -1) state.scope = 'uro';
  setScope(state.scope);

  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    navigator.serviceWorker.register('sw.js').catch(function () { /* 離線快取失敗不影響使用 */ });
  }

  // 供測試使用
  window.__nhiSearch = function (scope, q) {
    return search(scope === 'all' ? getAll() : uroItems, q).list.map(function (it) { return it.code; });
  };
})();
