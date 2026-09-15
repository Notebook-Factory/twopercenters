// Cmd-K / Ctrl-K opens the spotlight search, Escape closes it.
//
// Dash has no keyboard event input, so the shortcut is wired here and then
// clicks the navbar's Search button. Going through that button rather than
// toggling the modal directly means there is exactly one code path that opens
// the overlay, so the two entry points cannot drift apart.
(function () {
  // Measured, rather than inferred from offsetParent: a rect is a rect
  // whatever the ancestor positioning is doing.
  function spotlightIsOpen() {
    var field = document.getElementById('spotlight-input');
    if (!field) { return false; }
    var box = field.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  }

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
      // Escape appeared to do nothing, and the reason was that it was being
      // handled twice. dbc.Modal closes itself on Escape and reports
      // is_open=false back to Dash; this handler then clicked the navbar
      // Search button, which TOGGLES, so the overlay closed and reopened in
      // the same keystroke.
      //
      // Clicking the dedicated close button instead is idempotent: it only
      // ever sets is_open false, so it agrees with whatever Bootstrap has
      // already done rather than undoing it.
      if (spotlightIsOpen()) {
        var close = document.getElementById('spotlight-close');
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
    var input = document.getElementById('spotlight-input');
    if (!input || input.offsetParent === null) { return false; }
    if (document.activeElement !== input) {
      input.focus({preventScroll: true});
      var len = (input.value || '').length;
      try { input.setSelectionRange(len, len); } catch (e) {}
    }
    return document.activeElement === input;
  }

  var wasOpen = false;
  var observer = new MutationObserver(function () {
    var field = document.getElementById('spotlight-input');
    var open = !!(field && field.offsetParent !== null);

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

// Arrow keys through the spotlight results.
//
// This tracks a highlighted row explicitly rather than moving DOM focus.
// Focus was the obvious approach and it did not survive: the field keeps
// focus while you type, which is what you want in a palette, and the focus
// this handler moved onto a row was taken straight back, so Down appeared to
// do nothing. An explicit marker is also what lets typing continue while a
// row is highlighted.
(function () {
  var HILITE = 'ev-spotlight-hit--active';

  function results() {
    return Array.prototype.slice.call(
      document.querySelectorAll('#spotlight-results .ev-spotlight-hit'));
  }

  function isOpen() {
    // dbc.Modal puts the component id on the inner .modal-dialog, not on the
    // outer .modal that carries .show, so asking the id'd element whether it
    // has .show is always false. Whether the field is laid out is the honest
    // question: offsetParent is null while the overlay is closed.
    var input = document.getElementById('spotlight-input');
    return !!(input && input.offsetParent !== null);
  }

  function highlighted(hits) {
    for (var i = 0; i < hits.length; i++) {
      if (hits[i].classList.contains(HILITE)) { return i; }
    }
    return -1;
  }

  function highlight(hits, index) {
    hits.forEach(function (el, i) { el.classList.toggle(HILITE, i === index); });
    if (hits[index]) { hits[index].scrollIntoView({block: 'nearest'}); }
  }

  document.addEventListener('keydown', function (e) {
    if (!isOpen()) { return; }
    var key = e.key;
    if (key !== 'ArrowDown' && key !== 'ArrowUp' && key !== 'Enter') { return; }

    var hits = results();
    if (!hits.length) { return; }
    var index = highlighted(hits);

    if (key === 'Enter') {
      e.preventDefault();
      (index === -1 ? hits[0] : hits[index]).click();
      return;
    }

    e.preventDefault();   // keep the caret still while arrowing the list
    if (key === 'ArrowDown') {
      index = (index === -1) ? 0 : Math.min(index + 1, hits.length - 1);
    } else {
      index = (index <= 0) ? 0 : index - 1;
    }
    highlight(hits, index);
  });

  // A fresh set of results starts unhighlighted, so Down always begins at the
  // top rather than at wherever the previous list happened to be.
  new MutationObserver(function () {
    var box = document.getElementById('spotlight-results');
    if (box && !box.querySelector('.' + HILITE)) { return; }
  }).observe(document.body, {childList: true, subtree: true});
})();


// Close the map hint on the first click, without waiting for the server.
//
// The Dash callback that hides it still runs and is what keeps it hidden, but
// a round trip is a visible delay on a button whose whole job is to get out of
// the way. Hiding it here makes the first click take effect at once; the
// callback then sets the same inline style and nothing fights.
(function () {
  document.addEventListener('click', function (e) {
    var button = e.target && e.target.closest
      ? e.target.closest('#map-hint-close') : null;
    if (!button) { return; }
    var hint = document.getElementById('map-hint');
    if (hint) { hint.style.display = 'none'; }
  }, true);
})();
