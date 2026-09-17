// Redraw the ECharts figures when the theme changes.
//
// Those charts read their colours from the CSS custom properties at draw
// time, which is what lets them follow a light/dark switch where the
// server-rendered plotly figures cannot. But reading the tokens is only half
// of it: nothing redraws a chart that is already on screen, so a chart drawn
// in dark theme kept white labels after a switch to light and became
// unreadable on the white card.
//
// The theme toggle is not a Dash callback, so there is no server round trip
// to hang this on. Each chart's draw callback leaves its own redraw function
// on the element and adds the element here; this watches the one attribute
// that matters and calls them.
(function () {
  function redraw() {
    var charts = window.__evCharts || [];
    for (var i = 0; i < charts.length; i++) {
      var el = charts[i];
      // A chart whose element Dash has since replaced is not ours to redraw.
      if (!el || !el.isConnected || typeof el.__evRedraw !== 'function') {
        continue;
      }
      try {
        el.__evRedraw();
      } catch (e) {
        /* one bad chart must not stop the rest */
      }
    }
  }

  new MutationObserver(redraw).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  });
})();
