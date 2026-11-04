/*
 * Home Assistant ingress shim for SillyTavern.
 *
 * Ingress serves the add-on under /api/hassio_ingress/<token>/, but SillyTavern
 * builds root-absolute URLs ("/api/...", "/scripts/..."). nginx rewrites the
 * static HTML/CSS; this script rewrites URLs that JavaScript creates at runtime.
 * The prefix is taken from this script's own URL.
 */
(function () {
  'use strict';
  var cs = document.currentScript;
  if (!cs || !cs.src || window.__ingressShim) return;
  var P = new URL(cs.src).pathname.replace(/\/__ingress_shim\.js$/, '');
  if (!P) return;
  window.__ingressShim = P;
  var ORIGIN = location.origin;

  function inScope(p) {
    return p === P || p.indexOf(P + '/') === 0 || p.indexOf(P + '?') === 0 || p.indexOf(P + '#') === 0;
  }
  function fixStr(u) {
    if (u.charAt(0) === '/') {
      return (u.charAt(1) === '/' || inScope(u)) ? u : P + u;
    }
    if (u.indexOf(ORIGIN + '/') === 0) {
      var rest = u.slice(ORIGIN.length);
      return (rest.charAt(1) === '/' || inScope(rest)) ? u : ORIGIN + P + rest;
    }
    return u;
  }
  function fix(u) {
    if (typeof u === 'string') return fixStr(u);
    if (u instanceof URL) {
      var s = fixStr(u.href);
      return s === u.href ? u : new URL(s);
    }
    return u;
  }

  // ---- network ------------------------------------------------------------
  var _fetch = window.fetch;
  window.fetch = function (input, init) {
    if (typeof Request !== 'undefined' && input instanceof Request) {
      var f = fixStr(input.url);
      if (f !== input.url) input = new Request(f, input);
    } else {
      input = fix(input);
    }
    return _fetch.call(this, input, init);
  };

  var _xhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    var a = Array.prototype.slice.call(arguments);
    a[1] = fixStr(typeof url === 'string' ? url : String(url));
    return _xhrOpen.apply(this, a);
  };

  var _WS = window.WebSocket;
  var WS = function (url, protocols) {
    try {
      var u = new URL(url, location.href);
      if (u.host === location.host && !inScope(u.pathname)) {
        u.pathname = P + u.pathname;
        url = u.href;
      }
    } catch (e) { /* leave as is */ }
    return protocols === undefined ? new _WS(url) : new _WS(url, protocols);
  };
  WS.prototype = _WS.prototype;
  ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach(function (k) { WS[k] = _WS[k]; });
  window.WebSocket = WS;

  if (window.EventSource) {
    var _ES = window.EventSource;
    var ES = function (url, cfg) { return new _ES(fix(String(url)), cfg); };
    ES.prototype = _ES.prototype;
    window.EventSource = ES;
  }
  if (navigator.sendBeacon) {
    var _beacon = navigator.sendBeacon;
    navigator.sendBeacon = function (url, data) { return _beacon.call(this, fix(String(url)), data); };
  }
  var _open = window.open;
  window.open = function (url) {
    var a = Array.prototype.slice.call(arguments);
    if (typeof url === 'string') a[0] = fixStr(url);
    return _open.apply(this, a);
  };
  ['pushState', 'replaceState'].forEach(function (m) {
    var o = history[m];
    history[m] = function (state, title, url) {
      return o.call(this, state, title, url == null ? url : fixStr(String(url)));
    };
  });

  // ---- DOM properties and attributes -------------------------------------
  function wrapSetter(proto, prop, fn) {
    if (!proto) return;
    var d = Object.getOwnPropertyDescriptor(proto, prop);
    if (!d || !d.set) return;
    Object.defineProperty(proto, prop, {
      configurable: true,
      enumerable: d.enumerable,
      get: d.get,
      set: function (v) { d.set.call(this, fn(v)); }
    });
  }
  var toFixed = function (v) { return fixStr(String(v)); };
  [
    [window.HTMLImageElement, 'src'],
    [window.HTMLScriptElement, 'src'],
    [window.HTMLLinkElement, 'href'],
    [window.HTMLAnchorElement, 'href'],
    [window.HTMLIFrameElement, 'src'],
    [window.HTMLSourceElement, 'src'],
    [window.HTMLMediaElement, 'src'],
    [window.HTMLVideoElement, 'poster'],
    [window.HTMLFormElement, 'action']
  ].forEach(function (p) { if (p[0]) wrapSetter(p[0].prototype, p[1], toFixed); });

  var URL_ATTRS = { src: 1, href: 1, poster: 1, action: 1 };
  var _setAttr = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (typeof value === 'string' && URL_ATTRS[String(name).toLowerCase()]) value = fixStr(value);
    return _setAttr.call(this, name, value);
  };

  var _Audio = window.Audio;
  var AudioShim = function (src) {
    var a = new _Audio();
    if (src !== undefined) a.src = src;
    return a;
  };
  AudioShim.prototype = _Audio.prototype;
  window.Audio = AudioShim;

  // ---- HTML strings and inline CSS ---------------------------------------
  var attrRe = /(\s(?:src|href|poster|action)\s*=\s*["'])(\/(?!\/)[^"'\s>]*)/gi;
  var urlRe = /url\(\s*(["']?)(\/(?!\/)[^)"']*)/gi;
  function fixCss(v) {
    return typeof v === 'string' ? v.replace(urlRe, function (m, q, p) { return 'url(' + q + fixStr(p); }) : v;
  }
  function fixHTML(h) {
    if (typeof h !== 'string') return h;
    return fixCss(h.replace(attrRe, function (m, a, p) { return a + fixStr(p); }));
  }
  wrapSetter(Element.prototype, 'innerHTML', fixHTML);
  wrapSetter(Element.prototype, 'outerHTML', fixHTML);
  var _iah = Element.prototype.insertAdjacentHTML;
  Element.prototype.insertAdjacentHTML = function (pos, html) { return _iah.call(this, pos, fixHTML(html)); };
  if (window.Range && Range.prototype.createContextualFragment) {
    var _ccf = Range.prototype.createContextualFragment;
    Range.prototype.createContextualFragment = function (html) { return _ccf.call(this, fixHTML(html)); };
  }
  if (window.CSSStyleDeclaration) {
    var sp = CSSStyleDeclaration.prototype;
    var _sp = sp.setProperty;
    sp.setProperty = function (n, v, pr) { return _sp.call(this, n, fixCss(v), pr); };
    ['cssText', 'background', 'backgroundImage', 'maskImage', 'webkitMaskImage', 'listStyleImage']
      .forEach(function (p) { wrapSetter(sp, p, fixCss); });
  }

  // ---- catch-all for anything inserted by other means --------------------
  function fixEl(el) {
    ['src', 'href', 'poster'].forEach(function (a) {
      var v = el.getAttribute && el.getAttribute(a);
      if (v && v.charAt(0) === '/') {
        var f = fixStr(v);
        if (f !== v) _setAttr.call(el, a, f);
      }
    });
  }
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      if (m.type === 'attributes') { fixEl(m.target); return; }
      m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        fixEl(n);
        if (n.querySelectorAll) n.querySelectorAll('[src],[href],[poster]').forEach(fixEl);
      });
    });
  }).observe(document.documentElement, {
    childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'href', 'poster']
  });

  // ---- location.href = '/...' cannot be patched; redirect via Navigation API
  if (window.navigation && navigation.addEventListener) {
    navigation.addEventListener('navigate', function (e) {
      try {
        if (!e.cancelable || e.downloadRequest !== null) return;
        var d = new URL(e.destination.url);
        if (d.origin !== ORIGIN || inScope(d.pathname)) return;
        e.preventDefault();
        location.href = ORIGIN + P + d.pathname + d.search + d.hash;
      } catch (err) { /* ignore */ }
    });
  }

  console.info('[ha-ingress] SillyTavern shim active, base =', P);
})();
