/* Laster JSON fra data/, rendrer seksjoner med Render.* og tegner diagrammer med Plotly. */
(function () {
  'use strict';
  var R = window.Render;
  var $ = function (id) { return document.getElementById(id); };

  function loadJSON(name) {
    return fetch('data/' + name + '.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .catch(function (e) { console.error('Kunne ikke lese ' + name + '.json', e); return null; });
  }

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function drawChart(id, ind, extra) {
    var el = $(id);
    if (!el || !ind || ind.status !== 'ok' || !ind.series || !ind.series.length) return;
    if (!window.Plotly) { el.innerHTML = '<div class="muted">Diagrambiblioteket (Plotly) kunne ikke lastes. Tall vises over.</div>'; return; }
    var x = ind.series.map(function (p) { return p[0]; });
    var y = ind.series.map(function (p) { return p[1]; });
    var shapes = [], b = ind.bands;
    if (b) {
      var rect = function (y0, y1, color) { return { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: y0, y1: y1, fillcolor: color, line: { width: 0 }, layer: 'below' }; };
      shapes.push(rect(b.p10, b.p90, css('--band1')), rect(b.p25, b.p75, css('--band2')));
      shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: b.p50, y1: b.p50, line: { color: css('--muted'), width: 1, dash: 'dot' } });
    }
    var traces = [{ x: x, y: y, type: 'scatter', mode: 'lines', name: ind.name, line: { color: css('--accent'), width: 1.6 }, hovertemplate: '%{x}<br>%{y}<extra></extra>' }];
    if (extra && extra.series && extra.series.length) {
      traces.push({ x: extra.series.map(function (p) { return p[0]; }), y: extra.series.map(function (p) { return p[1]; }), type: 'scatter', mode: 'lines', name: extra.name, line: { color: css('--yellow'), width: 1.2 } });
    }
    if (extra && extra.refLine != null) shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: extra.refLine, y1: extra.refLine, line: { color: css('--red'), width: 1.2, dash: 'dash' } });
    var layout = {
      margin: { l: 42, r: 8, t: 6, b: 28 }, showlegend: !!extra && !!extra.series, legend: { orientation: 'h', y: 1.18 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: css('--text'), size: 11 },
      xaxis: { gridcolor: css('--line'), type: 'date' }, yaxis: { gridcolor: css('--line'), zeroline: false }, shapes: shapes
    };
    window.Plotly.newPlot(el, traces, layout, { displayModeBar: false, responsive: true });
  }

  function drawMood(id, mood) {
    var el = $(id);
    if (!el) return;
    if (!window.Plotly) { el.innerHTML = '<div class="muted">Diagrambiblioteket (Plotly) kunne ikke lastes.</div>'; return; }
    var ser = mood.market.series, b = (mood.rule || {}).bands || {};
    var rect = function (y0, y1, color) { return { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: y0, y1: y1, fillcolor: color, line: { width: 0 }, layer: 'below' }; };
    var shapes = [rect(0, b.fear_below || 45, 'rgba(60,120,210,.10)'), rect(b.greed_below || 75, 100, 'rgba(230,140,40,.12)')];
    window.Plotly.newPlot(el, [{ x: ser.map(function (p) { return p[0]; }), y: ser.map(function (p) { return p[1]; }), type: 'scatter', mode: 'lines', name: 'Stemning', line: { color: css('--accent'), width: 1.6 }, hovertemplate: '%{x}<br>%{y}<extra></extra>' }],
      { margin: { l: 36, r: 8, t: 6, b: 28 }, showlegend: false, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: css('--text'), size: 11 },
        xaxis: { gridcolor: css('--line'), type: 'date' }, yaxis: { gridcolor: css('--line'), range: [0, 100], zeroline: false }, shapes: shapes },
      { displayModeBar: false, responsive: true });
  }

  function init() {
    var theme = $('theme');
    theme.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* ignorer */ }
      render(window.__data);
    });
    try { var t = localStorage.getItem('theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch (e) { /* ignorer */ }

    var names = ['meta', 'regime', 'volatility', 'macro', 'equities', 'mood'];
    Promise.all(names.map(loadJSON)).then(function (res) {
      var d = {}; names.forEach(function (n, i) { d[n] = res[i]; });
      window.__data = d;
      render(d);
    });
  }

  function cards(file, ids, prefix, label) {
    if (!file) return R.missingBox(label, 'Filen kunne ikke leses.');
    return ids.map(function (id) { return R.renderIndicatorCard((file.indicators || {})[id], prefix + id, { name: id }); }).join('');
  }

  function render(d) {
    $('meta').textContent = R.renderMeta(d.meta);
    $('regime-body').innerHTML = R.renderRegime(d.regime);

    var volIds = ['vix', 'vix3m', 'vix_vix3m', 'vvix', 'skew', 'vstoxx'];
    var vol = d.volatility;
    // VIX3M tegnes inn i VIX-diagrammet; eget kort vises også for dato og persentil
    $('vol-body').innerHTML = cards(vol, volIds, 'c-vol-', 'volatilitet');
    var macroIds = ['hy_oas', 'ig_oas', 't10y2y', 'dgs10', 'usd', 'wti'];
    $('macro-body').innerHTML = cards(d.macro, macroIds, 'c-mac-', 'kreditt, renter og råvarer');
    $('eq-body').innerHTML = R.renderEquityTable(d.equities);
    $('sector-body').innerHTML = R.renderSectors(d.equities);
    $('mood-body').innerHTML = R.renderMood(d.mood);
    $('method-body').innerHTML = R.renderMethodology({ volatility: d.volatility, macro: d.macro, equities: d.equities });

    if (vol) {
      volIds.forEach(function (id) {
        var ind = (vol.indicators || {})[id], extra = null;
        if (id === 'vix' && vol.indicators.vix3m && vol.indicators.vix3m.status === 'ok') extra = { name: 'VIX3M', series: vol.indicators.vix3m.series };
        if (id === 'vix_vix3m' && ind) extra = { refLine: ind.inversion_threshold };
        drawChart('c-vol-' + id, ind, extra);
      });
    }
    if (d.mood && d.mood.market && d.mood.market.series && d.mood.market.series.length) drawMood('c-mood', d.mood);
    if (d.macro) macroIds.forEach(function (id) { drawChart('c-mac-' + id, (d.macro.indicators || {})[id]); });
  }

  init();
})();
