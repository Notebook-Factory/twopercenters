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

  // Focus the field when the overlay appears. The modal mounts asynchronously,
  // so this watches for it rather than assuming it is already in the DOM.
  var observer = new MutationObserver(function () {
    var modal = document.getElementById('spotlight');
    if (modal && modal.classList.contains('show')) {
      var input = modal.querySelector('input');
      if (input && document.activeElement !== input) { input.focus(); }
    }
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
