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
  // away. The modal mounts asynchronously and Bootstrap animates it in, so a
  // single focus() on open lands before the element is focusable. This retries
  // briefly instead, and stops as soon as the field has focus.
  function focusSearch() {
    var modal = document.getElementById('spotlight');
    if (!modal || !modal.classList.contains('show')) { return false; }
    var input = document.getElementById('spotlight-input');
    if (!input) { return false; }
    if (document.activeElement === input) { return true; }
    input.focus();
    // Put the caret after any existing text rather than selecting it.
    var len = (input.value || '').length;
    try { input.setSelectionRange(len, len); } catch (e) {}
    return document.activeElement === input;
  }

  var wasOpen = false;
  var observer = new MutationObserver(function () {
    var modal = document.getElementById('spotlight');
    var open = !!(modal && modal.classList.contains('show'));

    if (open && !wasOpen) {
      // Opened just now: try until it takes, for at most ~600ms.
      var tries = 0;
      var timer = setInterval(function () {
        if (focusSearch() || ++tries > 12) { clearInterval(timer); }
      }, 50);
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
