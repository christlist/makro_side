/* Laster JSON fra data/, rendrer seksjoner med Render.* og tegner diagrammer med Plotly. */
(function () {
  'use strict';
  var R = window.Render;
  var $ = function (id) { return document.getElementById(id); };
  var MACRO_IDS = ['hy_oas', 'ig_oas', 't10y2y', 'dgs10', 'usd', 'wti'];
  var VOL_IDS = ['vix', 'vix3m', 'vix_vix3m', 'vvix', 'skew', 'vstoxx'];

  function loadJSON(name) {
    return fetch('data/' + name + '.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .catch(function (e) { console.error('Kunne ikke lese ' + name + '.json', e); return null; });
  }
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function layout(extra) {
    var base = {
      margin: { l: 40, r: 8, t: 6, b: 24 }, showlegend: false, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'IBM Plex Sans, system-ui, sans-serif', color: css('--ink-2'), size: 11 },
      xaxis: { gridcolor: css('--rule'), linecolor: css('--rule'), type: 'date', tickformat: '%Y', nticks: 6, fixedrange: true },
      yaxis: { gridcolor: css('--rule'), zeroline: false, fixedrange: true, separatethousands: false },
      hoverlabel: { font: { family: 'IBM Plex Sans, system-ui, sans-serif', size: 12 } }
    };
    for (var k in extra) base[k] = extra[k];
    return base;
  }
  function plot(el, traces, lay) {
    if (!window.Plotly) { el.innerHTML = '<div class="muted small">Diagrambiblioteket kunne ikke lastes. Tallene vises over.</div>'; return; }
    window.Plotly.newPlot(el, traces, lay, { displayModeBar: false, responsive: true });
  }

  function drawIndicator(id, ind, extra) {
    var el = $(id);
    if (!el || !ind || ind.status !== 'ok' || !ind.series || !ind.series.length) return;
    var shapes = [], b = ind.bands;
    if (b) {
      var rect = function (y0, y1, color) { return { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: y0, y1: y1, fillcolor: color, line: { width: 0 }, layer: 'below' }; };
      shapes.push(rect(b.p10, b.p90, css('--band1')), rect(b.p25, b.p75, css('--band2')));
      shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: b.p50, y1: b.p50, line: { color: css('--ink-3'), width: 1, dash: 'dot' } });
    }
    if (extra && extra.refLine != null) shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: extra.refLine, y1: extra.refLine, line: { color: css('--bad'), width: 1.2, dash: 'dash' } });
    var traces = [{ x: ind.series.map(function (p) { return p[0]; }), y: ind.series.map(function (p) { return p[1]; }), type: 'scatter', mode: 'lines', name: ind.name, line: { color: css('--accent'), width: 1.8 }, hovertemplate: '%{x|%d.%m.%Y}<br><b>%{y}</b><extra></extra>' }];
    if (extra && extra.series && extra.series.length) {
      traces.push({ x: extra.series.map(function (p) { return p[0]; }), y: extra.series.map(function (p) { return p[1]; }), type: 'scatter', mode: 'lines', name: extra.name, line: { color: css('--series2'), width: 1.4 }, hovertemplate: '%{x|%d.%m.%Y}<br>' + extra.name + ' <b>%{y}</b><extra></extra>' });
    }
    var lay = layout({ shapes: shapes, showlegend: !!(extra && extra.series), legend: { orientation: 'h', x: 0, y: 1.22, font: { size: 11 } }, margin: { l: 40, r: 8, t: extra && extra.series ? 22 : 6, b: 24 } });
    plot(el, traces, lay);
  }

  function drawMood(mood) {
    var el = $('c-mood');
    if (!el || !mood || !mood.market || !mood.market.series) return;
    var ser = mood.market.series, b = (mood.rule || {}).bands || {};
    var rect = function (y0, y1, color) { return { type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: y0, y1: y1, fillcolor: color, line: { width: 0 }, layer: 'below' }; };
    var shapes = [rect(0, b.fear_below || 45, css('--fear-soft')), rect(b.greed_below || 75, 100, css('--greed-soft'))];
    plot(el, [{ x: ser.map(function (p) { return p[0]; }), y: ser.map(function (p) { return p[1]; }), type: 'scatter', mode: 'lines', name: 'Stemning', line: { color: css('--accent'), width: 1.8 }, hovertemplate: '%{x|%d.%m.%Y}<br>Stemning <b>%{y}</b><extra></extra>' }],
      layout({ shapes: shapes, yaxis: { gridcolor: css('--rule'), range: [0, 100], zeroline: false, fixedrange: true, tickvals: [0, 25, 50, 75, 100] }, annotations: [
        { xref: 'paper', yref: 'y', x: 0.995, y: 8, text: 'Frykt', showarrow: false, xanchor: 'right', font: { size: 10, color: css('--fear') } },
        { xref: 'paper', yref: 'y', x: 0.995, y: 92, text: 'Grådighet', showarrow: false, xanchor: 'right', font: { size: 10, color: css('--greed') } }] }));
  }

  function cards(file, ids, prefix, label) {
    if (!file) return R.missingBox(label, 'Filen kunne ikke leses.');
    return ids.map(function (id) { return R.renderIndicatorCard((file.indicators || {})[id], prefix + id, { name: id }); }).join('');
  }

  function render(d) {
    $('status').innerHTML = R.renderStatus(d.meta, d.summary);
    $('overview-body').innerHTML = R.renderOverview(d.summary, d.regime, d.mood);
    $('vol-body').innerHTML = cards(d.volatility, VOL_IDS, 'c-vol-', 'volatilitet');
    $('macro-body').innerHTML = cards(d.macro, MACRO_IDS, 'c-mac-', 'kreditt, renter og råvarer');
    $('eq-body').innerHTML = R.renderEquityTable(d.equities);
    $('breadth-body').innerHTML = R.renderBreadth(d.equities);
    $('mood-body').innerHTML = R.renderMood(d.mood, d.equities);
    $('method-body').innerHTML = R.renderMethodology({ volatility: d.volatility, macro: d.macro, equities: d.equities }, d.meta, d.summary);
    $('foot-run').textContent = d.meta ? 'Siste kjøring ' + R.fmtDateTime(d.meta.run_at).replace(/&[a-z]+;/g, '') + '. Kilder: CBOE, FRED, Yahoo Finance.' : '';

    var vol = d.volatility;
    if (vol) VOL_IDS.forEach(function (id) {
      var ind = (vol.indicators || {})[id], extra = null;
      if (id === 'vix' && vol.indicators.vix3m && vol.indicators.vix3m.status === 'ok') extra = { name: 'VIX3M', series: vol.indicators.vix3m.series };
      if (id === 'vix_vix3m' && ind) extra = { refLine: ind.inversion_threshold };
      drawIndicator('c-vol-' + id, ind, extra);
    });
    if (d.macro) MACRO_IDS.forEach(function (id) { drawIndicator('c-mac-' + id, (d.macro.indicators || {})[id]); });
    drawMood(d.mood);
  }

  function initNav() {
    var links = [].slice.call(document.querySelectorAll('.tabs a'));
    var secs = links.map(function (a) { return document.querySelector(a.getAttribute('href')); });
    var ticking = false;
    function update() {
      ticking = false;
      var cur = 0;
      secs.forEach(function (s, i) { if (s && s.getBoundingClientRect().top <= 120) cur = i; });
      links.forEach(function (a, i) { a.classList.toggle('on', i === cur); });
    }
    window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  function init() {
    $('theme').addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* ignorer */ }
      if (window.__data) render(window.__data);
    });
    try { var t = localStorage.getItem('theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch (e) { /* ignorer */ }
    initNav();
    var names = ['meta', 'summary', 'regime', 'volatility', 'macro', 'equities', 'mood'];
    Promise.all(names.map(loadJSON)).then(function (res) {
      var d = {}; names.forEach(function (n, i) { d[n] = res[i]; });
      window.__data = d;
      render(d);
    });
  }

  init();
})();
