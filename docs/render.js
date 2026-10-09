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

  /* --------------------------------------------------------------- stemning */
  var MOOD_TEXT = { extreme_fear: 'Ekstrem frykt', fear: 'Frykt', neutral: 'Nøytral', greed: 'Grådighet', extreme_greed: 'Ekstrem grådighet' };

  /* score 0 (frykt, blå) til 100 (grådighet, oransje) */
  function moodColor(v) {
    if (!isNum(v)) return '';
    var d = (v - 50) / 50, a = (0.12 + 0.55 * Math.min(Math.abs(d), 1)).toFixed(2);
    return 'background:' + (d >= 0 ? 'rgba(230,140,40,' : 'rgba(60,120,210,') + a + ')';
  }
  function scoreBar(v) {
    if (!isNum(v)) return '';
    return '<div class="gauge" role="img" aria-label="Score ' + fmt(v, 0) + ' av 100"><div class="gauge-mark" style="left:' + Math.max(0, Math.min(100, v)) + '%"></div></div>' +
      '<div class="gauge-ends"><span>Frykt</span><span>Grådighet</span></div>';
  }
  function moodWeek(v) { return isNum(v) ? fmtSigned(v, 0) + ' siste uke' : 'endring siste uke mangler'; }

  function renderMood(m) {
    var intro = '<div class="warn"><strong>Prisbasert stemning, ikke spørreundersøkelse.</strong> Hver komponent er persentilrang mot siste 10 år (0 = frykt, 100 = grådighet). ' +
      'Indeksen overlapper delvis med regimepanelet (VIX og kreditt), men regimet måler stress mens stemningen også ser på momentum, bredde og risikoappetitt. Sektorstemning sammenlignes mot sektorens egen historikk, ikke mot andre sektorer. Kontekst, ikke et handelssignal.</div>';
    if (!m) return intro + missingBox('stemning', 'Filen mood.json kunne ikke leses.');
    var mk = m.market || {};
    var head;
    if (mk.status === 'ok') {
      head = '<div class="card mood-head"><div class="mood-main"><div class="label">Markedsstemning</div><div class="state mood-' + esc(mk.label) + '">' + fmt(mk.score, 0) + ' <span class="mood-text">' + esc(MOOD_TEXT[mk.label] || '') + '</span></div>' +
        '<div class="sub">' + moodWeek(mk.change_1w) + ' · ' + mk.n_used + ' av ' + mk.n_total + ' komponenter' + (mk.ref_date ? ' · per ' + fmtDate(mk.ref_date) : '') + '</div></div>' + scoreBar(mk.score) + '</div>';
    } else {
      head = '<div class="card mood-head">' + missingBox('markedsstemning', mk.error || 'Ingen markedsdata.') + '</div>';
    }
    var comps = (mk.components || []).map(function (c) {
      if (c.status !== 'ok') return '<tr><td>' + esc(c.label) + '</td><td colspan="4" class="miss-cell">' + MISSING + '<span class="reason"> ' + esc(String(c.error || '').slice(0, 160)) + '</span></td></tr>';
      return '<tr><td>' + esc(c.label) + '<div class="muted">' + esc(c.note || '') + '</div></td><td class="num">' + fmt(c.value, c.decimals) + ' <span class="muted">' + esc(c.unit) + '</span></td>' +
        '<td class="num heat" style="' + moodColor(c.score) + '">' + fmt(c.score, 0) + '</td><td class="num">' + fmtSigned(isNum(c.score) && isNum(c.score_1w) ? c.score - c.score_1w : null, 0) + '</td>' +
        '<td class="num ' + (c.stale ? 'stale' : '') + '">' + fmtDate(c.last_date) + (c.stale ? ' (utdatert)' : '') + '</td></tr>';
    }).join('');
    var compTable = comps ? '<div class="tablewrap"><table><thead><tr><th>Komponent</th><th class="num">Nivå</th><th class="num">Score</th><th class="num">Endring 1 uke</th><th class="num">Siste dato</th></tr></thead><tbody>' + comps + '</tbody></table></div>' : '';
    var chart = (mk.series && mk.series.length) ? '<div class="chart" id="c-mood" role="img" aria-label="Markedsstemning over tid"></div>' : '';

    var rowsObj = m.rows || {};
    var rows = Object.keys(rowsObj).map(function (k) { return rowsObj[k]; });
    rows.sort(function (a, b) { return (isNum(b.score) ? b.score : -1) - (isNum(a.score) ? a.score : -1); });
    var sec = rows.map(function (r) {
      if (r.status !== 'ok') return '<tr><td>' + esc(r.name) + ' <span class="muted">' + esc(r.symbol) + '</span></td><td colspan="8" class="miss-cell">' + MISSING + '<span class="reason"> ' + esc(String(r.error || '').slice(0, 140)) + '</span></td></tr>';
      var by = {};
      (r.components || []).forEach(function (c) { by[c.id] = c; });
      var cell = function (id) { var c = by[id]; return c && c.status === 'ok' ? '<td class="num heat" style="' + moodColor(c.score) + '" title="' + esc(c.label) + ': ' + fmt(c.value, c.decimals) + ' ' + esc(c.unit) + '">' + fmt(c.score, 0) + '</td>' : '<td class="num miss-cell">–</td>'; };
      return '<tr><td>' + esc(r.name) + ' <span class="muted">' + esc(r.symbol) + '</span></td>' +
        '<td class="num heat strong" style="' + moodColor(r.score) + '">' + fmt(r.score, 0) + '</td><td>' + esc(MOOD_TEXT[r.label] || '') + '</td><td class="num">' + (isNum(r.change_1w) ? fmtSigned(r.change_1w, 0) : '–') + '</td>' +
        cell('mom200') + cell('ret1m') + cell('rs3m') + cell('vol') + cell('dd') + '</tr>';
    }).join('');
    var secTable = rows.length ? '<h3 class="sub">Stemning per sektor</h3><p class="note">Score 0 til 100 per sektor-ETF, snitt av fem prisbaserte mål mot sektorens egen 10 års historikk. Sortert etter score. Fargene viser frykt (blå) til grådighet (oransje). USA som proxy for global sektorutvikling.' +
      (m.benchmark_ok === false ? ' <span class="stale">Referansen SPY mangler, relativ styrke utelates.</span>' : '') + '</p>' +
      '<div class="tablewrap"><table><thead><tr><th>Sektor</th><th class="num">Score</th><th>Stemning</th><th class="num">Endring 1 uke</th><th class="num">200d snitt</th><th class="num">1 mnd</th><th class="num">Rel. styrke</th><th class="num">Ro (lav vol)</th><th class="num">Nær høy</th></tr></thead><tbody>' + sec + '</tbody></table></div>' : missingBox('stemning per sektor', 'Ingen sektordata.');
    return intro + head + chart + '<h3 class="sub">Komponenter i markedsindeksen</h3>' + compTable + secTable;
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
    renderEquityTable: renderEquityTable, renderSectors: renderSectors, renderMood: renderMood,
    renderMethodology: renderMethodology, renderMeta: renderMeta };
});
