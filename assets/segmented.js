// The sliding pill in the edition picker.
//
// The picker is a dbc.RadioItems styled as a segmented control. Bootstrap
// marks the chosen option by putting a background on its own label, which
// reads as a row of buttons where one happens to be lit. A segmented control
// instead has ONE pill that moves, and the movement is what says the whole
// row is a single choice.
//
// The pill itself is a ::before on the .btn-group, so there are no new nodes
// and no layout has to change to gain one. It sits on the group rather than
// on the wrapper because the wrapper is the scroll container: a pill anchored
// there stayed still while the years scrolled under it and ended up marking
// the wrong year. This script only writes CSS custom properties on an element
// React already owns. That distinction matters:
// lucide.createIcons() REPLACES elements it touches, and doing that to
// React-managed DOM left stranded <svg>s in the author card when a sibling
// count changed. Setting a property on a node React created is invisible to
// React and cannot desync it.
//
// Positions are read back from the DOM rather than computed from an index,
// because the year segments are not all the same width (the first carries a
// "TO"/"IN" prefix) and because the group scrolls horizontally when the
// window is narrow.
(function () {
  var SELECTOR = '.ev-picker-left, .ev-picker-right';

  function place(wrapper) {
    // The pill lives on the button group, which is what scrolls.
    var group = wrapper.querySelector('.btn-group') || wrapper;

    // Bootstrap puts .active on the <label> of the checked radio. Falling
    // back to the checked input's own label covers the moment before
    // dash-bootstrap-components has applied the class.
    var active = group.querySelector('.btn.active');
    if (!active) {
      var checked = group.querySelector('input:checked');
      active = checked && checked.parentElement
               && checked.parentElement.querySelector('.btn');
    }
    if (!active || !active.offsetWidth) {
      group.style.setProperty('--seg-o', '0');
      return;
    }

    // Measured against the group, which scrolls with its segments, so these
    // numbers stay true no matter where the strip is scrolled to.
    var a = active.getBoundingClientRect();
    var g = group.getBoundingClientRect();
    group.style.setProperty('--seg-x', (a.left - g.left) + 'px');
    group.style.setProperty('--seg-w', a.width + 'px');
    group.style.setProperty('--seg-o', '1');
  }

  function placeAll() {
    document.querySelectorAll(SELECTOR).forEach(place);
  }

  // Keep the chosen year in view when the track is narrower than its
  // contents.
  //
  // This must never use scrollIntoView. That method scrolls EVERY scrollable
  // ancestor, the document included, and this runs on DOM changes: Dash
  // re-renders constantly, so the page was dragged back to the picker on every
  // callback and could not be scrolled at all. Writing scrollLeft moves the
  // strip and nothing else.
  function reveal(wrapper) {
    if (wrapper.scrollWidth <= wrapper.clientWidth) { return; }
    var active = wrapper.querySelector('.btn.active');
    if (!active) { return; }
    var a = active.getBoundingClientRect();
    var w = wrapper.getBoundingClientRect();
    var target = wrapper.scrollLeft + (a.left - w.left)
                 - (w.width - a.width) / 2;
    target = Math.max(0, Math.min(target,
                                  wrapper.scrollWidth - wrapper.clientWidth));
    if (Math.abs(target - wrapper.scrollLeft) > 1) {
      wrapper.scrollLeft = target;
    }
  }

  var pending = null;
  function schedule() {
    if (pending) { return; }
    pending = requestAnimationFrame(function () {
      pending = null;
      placeAll();
    });
  }

  document.addEventListener('change', function (event) {
    if (event.target && event.target.matches('.ev-picker input')) {
      schedule();
    }
  }, true);
  document.addEventListener('click', schedule, true);
  window.addEventListener('resize', schedule);
  // Dash renders pages and callback output after load, and the year options
  // are replaced whenever the dataset or the author changes, so the pill has
  // to be repositioned on DOM changes as well as on input.
  var observer = new MutationObserver(function () {
    schedule();
    document.querySelectorAll('.ev-picker-right').forEach(reveal);
  });

  function start() {
    observer.observe(document.body, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ['class', 'checked']
    });
    placeAll();
    // Web fonts land after first paint and change the measured width of a
    // label, so one more pass once they are ready.
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(placeAll);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
