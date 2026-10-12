/*
 * Registers the service worker and asks the user to install the app.
 * Loaded on every page (see app/pwa.py).
 *
 * - Android, and Chrome/Edge on a computer: the browser fires
 *   `beforeinstallprompt`. We keep that event and show our own banner;
 *   its "Instalar" button opens the browser's install dialog.
 * - iPhone/iPad: Safari has no install dialog, so the banner explains
 *   how to add the app with Share → "Agregar a inicio".
 * - Opened from the home screen (already installed): nothing is shown.
 *
 * "Ahora no" hides the banner for SNOOZE_DAYS on this device.
 */
(function () {
  'use strict';

  var SNOOZE_DAYS = 3;
  var STORAGE_KEY = 'hogar-install-snoozed-at';

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function (err) {
        console.warn('Service worker registration failed:', err);
      });
    });
  }

  var installed = window.matchMedia('(display-mode: standalone)').matches ||
                  window.navigator.standalone === true;  // iOS
  if (installed) return;

  function isSnoozed() {
    try {
      var at = Number(localStorage.getItem(STORAGE_KEY));
      return at > 0 && Date.now() - at < SNOOZE_DAYS * 24 * 60 * 60 * 1000;
    } catch (e) {
      return false;  // storage blocked (private mode): just ask again
    }
  }

  function snooze() {
    try { localStorage.setItem(STORAGE_KEY, String(Date.now())); } catch (e) { /* ignore */ }
  }

  var banner = null;

  function hide() {
    if (banner) {
      banner.remove();
      banner = null;
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  // buttons: [{label, primary, onClick}]; body: a node or a string
  function show(title, body, buttons) {
    hide();
    banner = el('div', 'pwa-install');
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', title);

    var top = el('div', 'pwa-install__top');
    var icon = el('img', 'pwa-install__icon');
    icon.src = '/pwa/icon-192.png';
    icon.alt = '';
    var text = el('div', 'pwa-install__text');
    text.appendChild(el('div', 'pwa-install__title', title));
    var bodyNode = typeof body === 'string' ? el('div', 'pwa-install__body', body) : body;
    text.appendChild(bodyNode);
    top.appendChild(icon);
    top.appendChild(text);
    banner.appendChild(top);

    var row = el('div', 'pwa-install__buttons');
    buttons.forEach(function (b) {
      var button = el('button', 'pwa-install__button' + (b.primary ? ' pwa-install__button--primary' : ''), b.label);
      button.type = 'button';
      button.addEventListener('click', b.onClick);
      row.appendChild(button);
    });
    banner.appendChild(row);
    document.body.appendChild(banner);
  }

  function later() {
    snooze();
    hide();
  }

  // --- Android / Chrome / Edge ---
  var deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();  // we show our own banner instead of Chrome's mini-infobar
    deferredPrompt = event;
    if (isSnoozed()) return;
    show('Instala Hogar en tu teléfono',
         'Ábrela desde tu pantalla de inicio, como cualquier otra app.',
         [
           {label: 'Ahora no', onClick: later},
           {label: 'Instalar', primary: true, onClick: function () {
             hide();
             if (!deferredPrompt) return;
             deferredPrompt.prompt();
             deferredPrompt.userChoice.then(function (choice) {
               if (choice.outcome !== 'accepted') snooze();
             });
             deferredPrompt = null;  // a prompt event can only be used once
           }}
         ]);
  });

  window.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    hide();
  });

  // --- iPhone / iPad ---
  // iPadOS reports itself as a Mac, but Macs have no touch screen.
  var isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
              (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

  function showIosHelp() {
    var body = el('div', 'pwa-install__body');
    body.appendChild(document.createTextNode('Toca '));
    var share = el('span', 'pwa-install__share');
    share.setAttribute('aria-label', 'Compartir');
    // Safari's "Share" icon: a box with an arrow pointing up
    share.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M12 3v12M7 8l5-5 5 5"/><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/></svg>';
    body.appendChild(share);
    body.appendChild(document.createTextNode(' (Compartir) y luego «Agregar a inicio».'));
    show('Instala Hogar en tu iPhone', body, [{label: 'Entendido', primary: true, onClick: later}]);
  }

  if (isIos && !isSnoozed()) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', showIosHelp);
    } else {
      showIosHelp();
    }
  }
})();
