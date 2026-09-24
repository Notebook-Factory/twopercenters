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

  // And follow their container. echarts measures the element once, at draw
  // time, and keeps that size: a chart drawn while its panel was narrow -- or
  // one whose column changed width -- kept painting at the old width and its
  // bars ran out past the edge of the card.
  if (window.ResizeObserver) {
    var sizes = new ResizeObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        var el = entries[i].target;
        if (!window.echarts) { continue; }
        var chart = window.echarts.getInstanceByDom(el);
        // Width only: the height is set in CSS, and reacting to it as well
        // makes a resize that changes height loop.
        if (chart && el.clientWidth) {
          try { chart.resize({width: el.clientWidth}); } catch (e) {}
        }
      }
    });
    window.__evObserveSize = function (el) { sizes.observe(el); };
  }
})();
