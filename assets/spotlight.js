// Cmd-K / Ctrl-K opens the spotlight search, Escape closes it.
//
// Dash has no keyboard event input, so the shortcut is wired here and then
// clicks the navbar's Search button. Going through that button rather than
// toggling the modal directly means there is exactly one code path that opens
// the overlay, so the two entry points cannot drift apart.
(function () {
  function onKeyDown(e) {
    var key = (e.key || '').toLowerCase();

    if ((e.metaKey || e.ctrlKey) && key === 'k') {
      var button = document.getElementById('spotlight-open');
      if (button) {
        e.preventDefault();   // don't let the browser take Cmd-K for its own search
        button.click();
      }
      return;
    }

    if (key === 'escape') {
      // Only steal Escape when the overlay is actually showing.
      var modal = document.getElementById('spotlight');
      if (modal && modal.classList.contains('show')) {
        var close = document.getElementById('spotlight-open');
        if (close) { close.click(); }
      }
    }
  }

  document.addEventListener('keydown', onKeyDown);

  // Focus the field the moment the overlay appears, so you can type straight
  // away.
  //
  // A single focus() on open is not enough, and neither is stopping at the
  // first success. The modal mounts asynchronously, Bootstrap animates it in,
  // and react-bootstrap's own focus management then moves focus to the dialog
  // element AFTER the transition. So an early focus lands and is immediately
  // taken away again. This keeps putting focus back for the length of the
  // animation, and only gives up once the field has held focus across
  // consecutive checks.
  function focusSearch() {
    var modal = document.getElementById('spotlight');
    if (!modal || !modal.classList.contains('show')) { return false; }
    var input = document.getElementById('spotlight-input');
    if (!input) { return false; }
    if (document.activeElement !== input) {
      input.focus({preventScroll: true});
      var len = (input.value || '').length;
      try { input.setSelectionRange(len, len); } catch (e) {}
    }
    return document.activeElement === input;
  }

  var wasOpen = false;
  var observer = new MutationObserver(function () {
    var modal = document.getElementById('spotlight');
    var open = !!(modal && modal.classList.contains('show'));

    if (open && !wasOpen) {
      var held = 0;
      var elapsed = 0;
      var timer = setInterval(function () {
        elapsed += 40;
        held = focusSearch() ? held + 1 : 0;
        // Held for ~200ms, or we have been trying for 1.2s: stop either way.
        if (held >= 5 || elapsed > 1200) { clearInterval(timer); }
      }, 40);
    }
    wasOpen = open;
  });
  observer.observe(document.body, {childList: true, subtree: true,
                                   attributes: true, attributeFilter: ['class']});
})();

// Restore the saved theme before first paint so a light-theme user does not
// get a dark flash on every load. The toggle itself lives in a Dash
// clientside callback; this only replays the remembered choice.
(function () {
  try {
    var saved = window.localStorage.getItem('ev-theme');
    if (saved) { document.documentElement.dataset.theme = saved; }
  } catch (e) { /* private mode: fall through to the dark default */ }
})();

// Show the intro panel on a first visit only.
//
// It used to open on every load, with a backdrop dimming the whole dashboard
// until it was dismissed. An introduction is worth reading once; after that
// the More info button is the way back to it. The "seen" flag lives in
// localStorage, so it is per browser and survives reloads. If storage is
// unavailable (private mode), the catch leaves the panel closed rather than
// showing it every time, which is the failure people would find least
// annoying.
(function () {
  var KEY = 'ev-intro-seen';
  var seen;
  try { seen = window.localStorage.getItem(KEY); } catch (e) { seen = '1'; }
  if (seen) { return; }

  var tries = 0;
  var timer = setInterval(function () {
    var button = document.getElementById('off');   // the More info button
    if (button) {
      clearInterval(timer);
      try { window.localStorage.setItem(KEY, '1'); } catch (e) {}
      button.click();                              // one code path opens it
    } else if (++tries > 40) {
      clearInterval(timer);
    }
  }, 150);
})();

// Render Lucide icons, and re-render after Dash swaps content in.
//
// lucide.createIcons() replaces every <i data-lucide="..."> present at the
// time it runs. Dash builds tab contents on demand, so icons that arrive
// later would stay as empty <i> elements. Watching the DOM and re-running is
// what keeps them appearing in content that was not there at load.
(function () {
  function render() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      try { window.lucide.createIcons(); } catch (e) {}
    }
  }

  var pending = null;
  function scheduleRender() {
    if (pending) { return; }
    pending = setTimeout(function () { pending = null; render(); }, 120);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }

  new MutationObserver(scheduleRender)
    .observe(document.body, {childList: true, subtree: true});
})();
