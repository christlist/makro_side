/* Rene render-funksjoner: tar JSON, returnerer HTML-strenger. Ingen DOM-avhengighet, kan testes i node. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Render = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MISSING = 'Data mangler';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function fmt(v, dec) {
    if (!isNum(v)) return '–';
    return v.toFixed(dec == null ? 2 : dec).replace('.', ',');
  }
  function fmtSigned(v, dec, suffix) {
    if (!isNum(v)) return '–';
    return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(dec == null ? 2 : dec).replace('.', ',') + (suffix || '');
  }
  function fmtDate(iso) {
    if (!iso) return '–';
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? m[3] + '.' + m[2] + '.' + m[1] : esc(iso);
  }
  function fmtDateTime(iso) {
    if (!iso) return '–';
    var d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(d.getUTCDate()) + '.' + p(d.getUTCMonth() + 1) + '.' + d.getUTCFullYear() + ' kl. ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ' UTC';
  }

  var LIGHT_TEXT = { green: 'Grønn', yellow: 'Gul', red: 'Rød' };
  var STATE_TEXT = { calm: 'Rolig', elevated: 'Forhøyet', stress: 'Stress' };

  function missingBox(name, reason) {
    return '<div class="missing" role="status"><strong>' + MISSING + '</strong>' +
      (name ? ' for ' + esc(name) : '') +
      (reason ? '<div class="reason">' + esc(String(reason).slice(0, 300)) + '</div>' : '') + '</div>';
  }

  function changeText(ind) {
    if (!isNum(ind.change_1w)) return '–';
    return ind.change_kind === 'pct' ? fmtSigned(ind.change_1w, 2, ' %') : fmtSigned(ind.change_1w, ind.decimals);
  }

  /* ---------------------------------------------------------------- regime */
  function renderRegime(regime) {
    if (!regime) return missingBox('regimepanelet', 'Filen regime.json kunne ikke leses.');
    var items = regime.items || [];
    var head;
    if (regime.status === 'ok') {
      head = '<div class="regime-state state-' + esc(regime.state) + '"><span class="label">Samlet regime</span>' +
        '<span class="state">' + esc(STATE_TEXT[regime.state] || regime.state) + '</span>' +
        '<span class="sub">Snitt stress-persentil ' + fmt(regime.mean_stress, 0) + ' av 100 (' + regime.n_used + ' av ' + regime.n_total + ' indikatorer)</span></div>';
    } else {
      head = '<div class="regime-state state-missing"><span class="label">Samlet regime</span>' +
        '<span class="state">' + MISSING + '</span><span class="sub">' + esc(regime.error || '') + '</span></div>';
    }
    var cards = items.map(function (it) {
      if (it.status !== 'ok') {
        return '<div class="card sema"><div class="sema-head"><span class="dot dot-missing"></span><h3>' + esc(it.label) + '</h3></div>' +
          missingBox(null, it.reason + (it.last_date ? ' (siste dato ' + fmtDate(it.last_date) + ')' : '')) + '</div>';
      }
      var chg = it.change_kind === 'pct' ? fmtSigned(it.change_1w, 2, ' %') : fmtSigned(it.change_1w, it.decimals);
      return '<div class="card sema"><div class="sema-head"><span class="dot dot-' + esc(it.light) + '" aria-hidden="true"></span>' +
        '<h3>' + esc(it.label) + '</h3><span class="lighttext">' + esc(LIGHT_TEXT[it.light]) + '</span></div>' +
        '<div class="big">' + fmt(it.value, it.decimals) + '</div>' +
        '<dl class="kv"><dt>Persentilrang 10 år</dt><dd>' + fmt(it.percentile_10y, 0) + '</dd>' +
        '<dt>Stress-persentil</dt><dd>' + fmt(it.stress_percentile, 0) + '</dd>' +
        '<dt>Endring siste uke</dt><dd>' + chg + '</dd>' +
        '<dt>Siste datapunkt</dt><dd class="' + (it.stale ? 'stale' : '') + '">' + fmtDate(it.last_date) + (it.stale ? ' (utdatert)' : '') + '</dd></dl></div>';
    }).join('');
    var r = regime.rule || {};
    var rule = '<details class="rule"><summary>Slik beregnes regimet</summary><p>For hver indikator beregnes persentilrang mot siste 10 år. ' +
      'For indikatorer der høy verdi betyr stress brukes persentilen direkte. For avstand til 200 dagers snitt, der lav verdi betyr stress, brukes 100 minus persentilen (stress-persentil). ' +
      'Semafor per indikator: grønn under ' + esc((r.light || {}).yellow_from) + ', gul fra ' + esc((r.light || {}).yellow_from) + ', rød fra ' + esc((r.light || {}).red_from) + '. ' +
      'Samlet regime er snittet av stress-persentilene: rolig under ' + esc((r.overall || {}).elevated_from) + ', forhøyet fra ' + esc((r.overall || {}).elevated_from) +
      ', stress fra ' + esc((r.overall || {}).stress_from) + '. Indikatorer uten data, med for kort historikk eller eldre enn ' + esc(r.max_age_days) +
      ' dager utelates fra snittet. Færre enn ' + esc(r.min_indicators) + ' tilgjengelige indikatorer gir «' + MISSING + '». Terskler ligger i config.yaml.</p></details>';
    return head + '<div class="grid g3">' + cards + '</div>' + rule;
  }

  /* ----------------------------------------------------- indikatorkort (diagram tegnes i app.js) */
  function renderIndicatorCard(ind, chartId, opts) {
    opts = opts || {};
    if (!ind) return '<div class="card">' + missingBox(opts.name || 'indikator', 'Indikatoren finnes ikke i datafilen.') + '</div>';
    if (ind.status !== 'ok') {
      return '<div class="card"><h3>' + esc(ind.name) + '</h3>' + missingBox(ind.name, ind.error) + '</div>';
    }
    var flag = '';
    if (ind.inverted) flag = '<span class="flag flag-red">Invertert termstruktur</span>';
    else if (ind.inversion_threshold != null) flag = '<span class="flag flag-green">Normal termstruktur</span>';
    var stale = ind.stale ? '<span class="flag flag-yellow">Utdatert: siste datapunkt ' + fmtDate(ind.last_date) + '</span>' : '';
    var proxy = ind.proxy ? '<span class="flag flag-yellow">Proxy</span>' : '';
    return '<div class="card"><div class="card-head"><h3>' + esc(ind.name) + '</h3>' + flag + stale + proxy + '</div>' +
      '<div class="big">' + fmt(ind.last_value, ind.decimals) + ' <span class="unit">' + esc(ind.unit || '') + '</span></div>' +
      '<dl class="kv inline"><dt>Siste datapunkt</dt><dd>' + fmtDate(ind.last_date) + '</dd>' +
      '<dt>Persentil 10 år</dt><dd>' + (ind.percentile_10y == null ? 'for kort historikk' : fmt(ind.percentile_10y, 0)) + '</dd>' +
      '<dt>Endring 1 uke</dt><dd>' + changeText(ind) + '</dd></dl>' +
      '<div class="chart" id="' + esc(chartId) + '" role="img" aria-label="Tidsserie ' + esc(ind.name) + '"></div>' +
      '<div class="src">Kilde: ' + esc(ind.source) + (ind.window_years != null ? ' · vindu ' + fmt(ind.window_years, 1) + ' år' : '') + '</div></div>';
  }

  /* ---------------------------------------------------------------- aksjer */
  function pctCell(v) {
    if (!isNum(v)) return '<td class="num">–</td>';
    return '<td class="num ' + (v > 0 ? 'pos' : v < 0 ? 'neg' : '') + '">' + fmtSigned(v, 1, ' %') + '</td>';
  }
  function renderEquityTable(eq) {
    if (!eq) return missingBox('aksjeutvikling', 'Filen equities.json kunne ikke leses.');
    var rows = Object.keys(eq.indicators || {}).filter(function (k) { return !/_dist200$/.test(k); }).map(function (k) {
      var i = eq.indicators[k];
      if (i.status !== 'ok') {
        return '<tr><td>' + esc(i.name) + '</td><td colspan="6" class="miss-cell">' + MISSING + '<span class="reason"> ' + esc(String(i.error || '').slice(0, 160)) + '</span></td></tr>';
      }
      var d = eq.indicators[k + '_dist200'];
      var distV = d && d.status === 'ok' ? d.last_value : null;
      return '<tr><td>' + esc(i.name) + (i.proxy ? ' <span class="flag flag-yellow" title="' + esc(i.source) + '">Proxy: ' + esc(i.source) + '</span>' : '') +
        '</td>' + pctCell(i.ret_1w) + pctCell(i.ret_1m) + pctCell(i.ret_12m) + pctCell(distV) +
        '<td class="num ' + (i.stale ? 'stale' : '') + '">' + fmtDate(i.last_date) + '</td>' +
        '<td class="num">' + (d && d.status === 'ok' && d.percentile_10y != null ? fmt(d.percentile_10y, 0) : '–') + '</td></tr>';
    }).join('');
    return '<div class="tablewrap"><table><thead><tr><th>Marked</th><th class="num">1 uke</th><th class="num">1 måned</th><th class="num">12 måneder</th>' +
      '<th class="num">Avstand 200d</th><th class="num">Siste dato</th><th class="num">Persentil avstand</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function heat(v, lim) {
    if (!isNum(v)) return '';
    var a = Math.min(Math.abs(v) / lim, 1);
    return 'background:' + (v >= 0 ? 'rgba(46,160,90,' : 'rgba(215,60,60,') + (0.12 + 0.55 * a).toFixed(2) + ')';
  }
  function renderSectors(eq) {
    if (!eq || !eq.sectors) return missingBox('sektorrelativ styrke', 'Ingen sektordata i equities.json.');
    var s = eq.sectors;
    var rows = Object.keys(s.rows || {}).map(function (k) {
      var r = s.rows[k];
      if (r.status !== 'ok') return '<tr><td>' + esc(r.name) + ' (' + esc(r.symbol) + ')</td><td colspan="5" class="miss-cell">' + MISSING + '</td></tr>';
      var cell = function (v) { return '<td class="num heat" style="' + heat(v, 8) + '">' + (isNum(v) ? fmtSigned(v, 1, ' pp') : '–') + '</td>'; };
      return '<tr><td>' + esc(r.name) + ' <span class="muted">' + esc(r.symbol) + '</span></td>' + cell(r.rel_1w) + cell(r.rel_1m) + cell(r.rel_3m) +
        pctCell(r.dist200) + '<td class="num ' + (r.stale ? 'stale' : '') + '">' + fmtDate(r.last_date) + '</td></tr>';
    }).join('');
    var b = s.breadth;
    var breadth = b ? '<p class="breadth"><strong>Bredde:</strong> ' + b.above_200d + ' av ' + b.total + ' sektorer (' + fmt(b.share, 0) + ' %) over 200d snitt' +
      (b.total < b.total_expected ? ' <span class="stale">(' + (b.total_expected - b.total) + ' sektor(er) mangler)</span>' : '') + '. <span class="muted">' + esc(b.note) + '</span></p>'
      : '<p class="breadth">' + missingBox('bredde', 'Ingen sektordata tilgjengelig.') + '</p>';
    var bench = s.benchmark_ok ? '' : '<p class="stale">Referanse (' + esc(s.benchmark) + ') mangler. Relativ styrke kan ikke beregnes.</p>';
    return '<p class="note"><strong>' + esc(s.label) + '.</strong> Relativ styrke er sektor-ETFens avkastning minus ' + esc(s.benchmark) + ' i prosentpoeng.</p>' + bench + breadth +
      '<div class="tablewrap"><table><thead><tr><th>Sektor</th><th class="num">Rel. 1 uke</th><th class="num">Rel. 1 måned</th><th class="num">Rel. 3 måneder</th><th class="num">Avstand 200d</th><th class="num">Siste dato</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  /* ------------------------------------------------------------- sentiment */
  function renderSentiment(sd) {
    var warn = '<div class="warn"><strong>Eksperimentell og støyende.</strong> Kun kontekst, ikke et signal. Basert på artikkeltitler fra GDELT og en språkmodell (FinBERT) som ikke er trent på sektorspesifikk nyhetsdekning. Antall artikler er tillitsindikator, og scoren skjules ved for få artikler.</div>';
    if (!sd) return warn + missingBox('sektorsentiment', 'Filen sentiment.json kunne ikke leses.');
    var keys = Object.keys(sd.rows || {});
    if (!keys.length) return warn + missingBox('sektorsentiment', sd.group_error || sd.model_error || 'Ingen sektorer hentet.');
    var tiles = keys.map(function (k) {
      var r = sd.rows[k];
      if (r.status !== 'ok') return '<div class="tile tile-missing"><div class="t-name">' + esc(r.name) + '</div><div class="t-val">' + MISSING + '</div><div class="t-n">' + esc(String(r.error || '').slice(0, 60)) + '</div></div>';
      if (r.hidden || !isNum(r.z)) return '<div class="tile tile-hidden"><div class="t-name">' + esc(r.name) + '</div><div class="t-val">Skjult</div><div class="t-n">For få artikler (' + r.n_articles + ' av minst ' + esc(sd.min_articles) + ')</div></div>';
      return '<div class="tile" style="' + heat(r.z, 2) + '"><div class="t-name">' + esc(r.name) + '</div><div class="t-val">z ' + fmtSigned(r.z, 1) + '</div><div class="t-n">' + r.n_articles + ' artikler · snitt ' + fmtSigned(r.mean_score, 2) + '</div></div>';
    }).join('');
    return warn + '<div class="tiles">' + tiles + '</div><p class="muted">7 dagers snittscore (P(positiv) minus P(negativ)) per sektor. ' + esc(sd.z_note || '') + '</p>';
  }

  /* ------------------------------------------------------------- metodikk */
  function renderMethodology(files) {
    var rows = [];
    ['volatility', 'macro', 'equities'].forEach(function (g) {
      var f = files[g];
      if (!f) { rows.push('<tr><td colspan="6">' + missingBox(g, 'Filen ' + g + '.json kunne ikke leses.') + '</td></tr>'); return; }
      Object.keys(f.indicators || {}).forEach(function (k) {
        var i = f.indicators[k];
        if (/_dist200$/.test(k) && g === 'equities') return;
        rows.push('<tr><td>' + esc(i.name) + '</td><td>' + esc(i.description || '') + '</td><td>' +
          (i.status === 'ok' ? esc(i.source) + (i.proxy ? ' (proxy)' : '') : '<span class="stale">' + MISSING + '</span>') +
          '</td><td>' + esc(i.frequency || '') + '</td><td>' + esc(i.limitation || '') + '</td><td class="num">' +
          (i.status === 'ok' ? fmtDate(i.last_date) : '–') + '</td></tr>');
      });
    });
    return '<div class="tablewrap"><table><thead><tr><th>Indikator</th><th>Beskrivelse</th><th>Kilde brukt</th><th>Frekvens</th><th>Begrensninger</th><th class="num">Siste dato</th></tr></thead><tbody>' +
      rows.join('') + '</tbody></table></div>';
  }

  function renderMeta(meta) {
    if (!meta) return 'Kjøringsinfo mangler';
    var n = (meta.missing || []).length;
    return 'Siste kjøring: ' + fmtDateTime(meta.run_at) + (n ? ' · ' + n + ' kilde(r)/indikator(er) mangler' : '');
  }

  return { MISSING: MISSING, esc: esc, fmt: fmt, fmtSigned: fmtSigned, fmtDate: fmtDate, fmtDateTime: fmtDateTime,
    missingBox: missingBox, renderRegime: renderRegime, renderIndicatorCard: renderIndicatorCard,
    renderEquityTable: renderEquityTable, renderSectors: renderSectors, renderSentiment: renderSentiment,
    renderMethodology: renderMethodology, renderMeta: renderMeta };
});
