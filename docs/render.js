/* Rene render-funksjoner: tar JSON, returnerer HTML-strenger. Ingen DOM-avhengighet, kan testes i node. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Render = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MISSING = 'Data mangler';
  var MONTHS = ['jan.', 'feb.', 'mars', 'apr.', 'mai', 'juni', 'juli', 'aug.', 'sep.', 'okt.', 'nov.', 'des.'];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function fmt(v, dec) { return isNum(v) ? v.toFixed(dec == null ? 2 : dec).replace('.', ',') : '–'; }
  function fmtSigned(v, dec, suffix) {
    if (!isNum(v)) return '–';
    return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(dec == null ? 2 : dec).replace('.', ',') + (suffix || '');
  }
  function fmtDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? parseInt(m[3], 10) + '. ' + MONTHS[parseInt(m[2], 10) - 1] + ' ' + m[1] : (iso ? esc(iso) : '–');
  }
  function fmtDateTime(iso) {
    var d = iso ? new Date(iso) : null;
    if (!d || isNaN(d)) return iso ? esc(iso) : '–';
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getUTCDate() + '. ' + MONTHS[d.getUTCMonth()] + ' ' + d.getUTCFullYear() + ' kl. ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ' UTC';
  }

  /* ---------------------------------------------------------- byggeklosser */
  var LEVEL_TEXT = { very_low: 'Uvanlig lavt', low: 'Lavt', normal: 'Normalt', high: 'Høyt', very_high: 'Uvanlig høyt' };
  function levelOf(p) {
    if (!isNum(p)) return null;
    return p < 10 ? 'very_low' : p < 25 ? 'low' : p < 75 ? 'normal' : p < 90 ? 'high' : 'very_high';
  }
  function chip(level) {
    return level ? '<span class="chip lvl-' + level + '">' + LEVEL_TEXT[level] + '</span>' : '';
  }

  function missingBox(name, reason) {
    return '<div class="missing" role="status"><strong>' + MISSING + '</strong>' + (name ? ' for ' + esc(name) : '') +
      (reason ? '<div class="reason">' + esc(String(reason).slice(0, 300)) + '</div>' : '') + '</div>';
  }

  /* Persentilbar: 0 til 100, ytterområdene (10 og 90) markert */
  function pbar(p, labels) {
    if (!isNum(p)) return '<div class="pbar pbar-empty" aria-hidden="true"></div>';
    var l = labels || ['Lavt', 'Høyt'];
    return '<div class="pbar" role="img" aria-label="Persentil ' + fmt(p, 0) + ' av 100"><i class="pb-tick" style="left:10%"></i><i class="pb-tick" style="left:90%"></i>' +
      '<b class="pb-dot" style="left:' + Math.max(0, Math.min(100, p)) + '%"></b></div>' +
      '<div class="pbar-ends"><span>' + esc(l[0]) + '</span><span>' + esc(l[1]) + '</span></div>';
  }

  /* Måler 0 til 100 med soner. zones: [{to, cls}] i stigende rekkefølge. */
  function gauge(value, zones, ends) {
    var from = 0, segs = zones.map(function (z) {
      var s = '<i class="g-seg ' + z.cls + '" style="left:' + from + '%;width:' + (z.to - from) + '%"></i>';
      from = z.to;
      return s;
    }).join('');
    return '<div class="gauge" role="img" aria-label="' + fmt(value, 0) + ' av 100">' + segs +
      '<b class="g-mark" style="left:' + Math.max(0, Math.min(100, value)) + '%"></b></div>' +
      '<div class="gauge-ends"><span>' + esc(ends[0]) + '</span><span>' + esc(ends[1]) + '</span></div>';
  }

  function changeText(ind) {
    if (!isNum(ind.change_1w)) return '–';
    return ind.change_kind === 'pct' ? fmtSigned(ind.change_1w, 2, ' %') : fmtSigned(ind.change_1w, ind.decimals);
  }

  /* --------------------------------------------------------------- statuslinje */
  function renderStatus(meta, summary) {
    var h = summary && summary.health;
    var latest = h && h.latest_data_date ? fmtDate(h.latest_data_date) : null;
    var line = '<div class="st-date">' + (latest ? 'Siste datapunkt <strong>' + latest + '</strong>' : 'Siste datapunkt: ' + MISSING) + '</div>';
    var run = '<div class="st-run">Siste kjøring ' + (meta ? fmtDateTime(meta.run_at) : MISSING) + '</div>';
    var pill = '';
    if (h) {
      var miss = h.missing && h.missing.length;
      pill = '<div class="pill ' + (miss ? 'pill-warn' : 'pill-ok') + '" title="' + esc((h.missing || []).join(', ')) + '"><span class="pill-ico" aria-hidden="true">' + (miss ? '▲' : '●') + '</span>' +
        (miss ? miss + ' av ' + h.n_total + ' indikatorer mangler data' : 'Alle ' + h.n_total + ' indikatorer har data') +
        (h.proxies && h.proxies.length ? ' · ' + h.proxies.length + ' proxy' : '') + '</div>';
    }
    return line + run + pill;
  }

  /* ------------------------------------------------------------------ oversikt */
  var STATE_TEXT = { calm: 'Rolig', elevated: 'Forhøyet', stress: 'Stress' };
  var MOOD_TEXT = { extreme_fear: 'Ekstrem frykt', fear: 'Frykt', neutral: 'Nøytral', greed: 'Grådighet', extreme_greed: 'Ekstrem grådighet' };

  function regimeTile(regime) {
    if (!regime || regime.status !== 'ok') {
      return '<div class="tile"><div class="tile-k">Regime</div>' + missingBox('regime', regime && regime.error) + '</div>';
    }
    var r = regime.rule || {}, lo = (r.overall || {}).elevated_from || 55, hi = (r.overall || {}).stress_from || 75;
    var greens = (regime.items || []).filter(function (i) { return i.light === 'green'; }).length;
    return '<div class="tile"><div class="tile-k">Regime</div><div class="tile-v state-' + esc(regime.state) + '"><span class="dotc" aria-hidden="true"></span>' + esc(STATE_TEXT[regime.state] || regime.state) + '</div>' +
      '<div class="tile-s">Snitt stress-persentil <strong>' + fmt(regime.mean_stress, 0) + '</strong> av 100 · ' + greens + ' av ' + regime.n_used + ' indikatorer grønne</div>' +
      gauge(regime.mean_stress, [{ to: lo, cls: 'z-calm' }, { to: hi, cls: 'z-elev' }, { to: 100, cls: 'z-stress' }], ['Rolig', 'Stress']) + '</div>';
  }

  function moodTile(mood) {
    var mk = mood && mood.market;
    if (!mk || mk.status !== 'ok') {
      return '<div class="tile"><div class="tile-k">Stemning</div>' + missingBox('stemning', mk && mk.error) + '</div>';
    }
    var b = (mood.rule || {}).bands || { extreme_fear_below: 25, fear_below: 45, neutral_below: 55, greed_below: 75 };
    return '<div class="tile"><div class="tile-k">Stemning</div><div class="tile-v">' + fmt(mk.score, 0) + '<span class="tile-v-sub">' + esc(MOOD_TEXT[mk.label] || '') + '</span></div>' +
      '<div class="tile-s">' + (isNum(mk.change_1w) ? fmtSigned(mk.change_1w, 0) + ' poeng siste uke' : 'Endring siste uke mangler') + ' · ' + mk.n_used + ' av ' + mk.n_total + ' komponenter</div>' +
      gauge(mk.score, [{ to: b.extreme_fear_below, cls: 'z-xfear' }, { to: b.fear_below, cls: 'z-fear' }, { to: b.neutral_below, cls: 'z-neutral' }, { to: b.greed_below, cls: 'z-greed' }, { to: 100, cls: 'z-xgreed' }], ['Frykt', 'Grådighet']) + '</div>';
  }

  var LIGHT = { green: ['●', 'Grønn'], yellow: ['▲', 'Gul'], red: ['■', 'Rød'] };

  function regimeCards(regime) {
    if (!regime) return missingBox('regimeindikatorene', 'Filen regime.json kunne ikke leses.');
    return '<div class="grid g3">' + (regime.items || []).map(function (it) {
      if (it.status !== 'ok') {
        return '<div class="card sema"><div class="sema-h"><h3>' + esc(it.label) + '</h3></div>' + missingBox(null, it.reason + (it.last_date ? ' (siste dato ' + fmtDate(it.last_date) + ')' : '')) + '</div>';
      }
      var L = LIGHT[it.light] || ['', ''];
      return '<div class="card sema"><div class="sema-h"><h3>' + esc(it.label) + '</h3><span class="light light-' + esc(it.light) + '"><span aria-hidden="true">' + L[0] + '</span> ' + L[1] + '</span></div>' +
        '<div class="num-lg">' + fmt(it.value, it.decimals) + ' <span class="unit">' + esc(it.unit || '') + '</span></div>' +
        pbar(it.stress_percentile, ['Lite stress', 'Mye stress']) +
        '<div class="sema-f"><span>Stress-persentil ' + fmt(it.stress_percentile, 0) + '</span><span>' + (isNum(it.change_1w) ? (it.change_kind === 'pct' ? fmtSigned(it.change_1w, 2, ' %') : fmtSigned(it.change_1w, it.decimals)) + ' siste uke' : '') + '</span></div>' +
        '<div class="src' + (it.stale ? ' stale' : '') + '">Siste datapunkt ' + fmtDate(it.last_date) + (it.stale ? ' (utdatert)' : '') + '</div></div>';
    }).join('') + '</div>';
  }

  function ruleText(regime) {
    var r = (regime && regime.rule) || {}, lg = r.light || {}, ov = r.overall || {};
    return '<details class="more"><summary>Slik beregnes regimet</summary><p>Hver indikator får en persentilrang mot siste 10 år: andelen dager nivået har vært lavere. ' +
      'Der høy verdi betyr stress brukes persentilen direkte. For S&amp;P 500 mot 200 dagers snitt, der lav verdi betyr stress, brukes 100 minus persentilen. Dette kalles stress-persentil.</p>' +
      '<p>Semafor per indikator: grønn under ' + esc(lg.yellow_from) + ', gul fra ' + esc(lg.yellow_from) + ', rød fra ' + esc(lg.red_from) + '. Samlet regime er snittet av stress-persentilene: rolig under ' + esc(ov.elevated_from) +
      ', forhøyet fra ' + esc(ov.elevated_from) + ', stress fra ' + esc(ov.stress_from) + '. Indikatorer uten data, med for kort historikk eller eldre enn ' + esc(r.max_age_days) + ' dager utelates. Færre enn ' + esc(r.min_indicators) +
      ' tilgjengelige gir «' + MISSING + '». Terskler ligger i <code>config.yaml</code>.</p></details>';
  }

  function renderOverview(summary, regime, mood) {
    var points = summary && summary.points ? summary.points.map(function (p) { return '<li class="pt pt-' + esc(p.kind) + '">' + esc(p.text) + '</li>'; }).join('') : '';
    var left = '<div class="card points"><h3 class="card-t">Hovedpunkter</h3>' + (points ? '<ul class="plist">' + points + '</ul>' : missingBox('oppsummering', 'Filen summary.json kunne ikke leses.')) + '</div>';
    return '<div class="ov-grid">' + regimeTile(regime) + moodTile(mood) + left + '</div>' +
      '<h3 class="sub">Regimets seks indikatorer</h3>' + regimeCards(regime) + ruleText(regime);
  }

  /* -------------------------------------------------------------- indikatorkort */
  function renderIndicatorCard(ind, chartId, opts) {
    opts = opts || {};
    if (!ind) return '<div class="card">' + missingBox(opts.name || 'indikator', 'Indikatoren finnes ikke i datafilen.') + '</div>';
    if (ind.status !== 'ok') return '<div class="card"><h3 class="card-t">' + esc(ind.name) + '</h3>' + (ind.meaning ? '<p class="mean">' + esc(ind.meaning) + '</p>' : '') + missingBox(ind.name, ind.error) + '</div>';
    var flags = '';
    if (ind.inverted) flags += '<span class="flag flag-bad">Invertert termstruktur</span>';
    else if (ind.inversion_threshold != null) flags += '<span class="flag flag-ok">Normal termstruktur</span>';
    if (ind.proxy) flags += '<span class="flag flag-warn">Proxy</span>';
    if (ind.stale) flags += '<span class="flag flag-warn">Utdatert: siste datapunkt ' + fmtDate(ind.last_date) + '</span>';
    var level = ind.level || levelOf(ind.percentile_10y);
    return '<div class="card ind"><div class="ind-h"><h3 class="card-t">' + esc(ind.name) + '</h3>' + chip(level) + '</div>' +
      (flags ? '<div class="flags">' + flags + '</div>' : '') +
      '<div class="ind-v"><span class="num-lg">' + fmt(ind.last_value, ind.decimals) + '</span> <span class="unit">' + esc(ind.unit || '') + '</span><span class="chg">' + changeText(ind) + ' siste uke</span></div>' +
      (ind.meaning ? '<p class="mean">' + esc(ind.meaning) + '</p>' : '') +
      (ind.percentile_10y == null ? '<div class="muted small">For kort historikk til persentilrang</div>' : pbar(ind.percentile_10y) +
        '<div class="pbar-cap">Høyere enn ' + fmt(ind.percentile_10y, 0) + ' % av dagene' + (ind.window_years != null ? ' siste ' + fmt(ind.window_years, 0) + ' år' : '') + '</div>') +
      '<div class="chart" id="' + esc(chartId) + '" role="img" aria-label="Tidsserie ' + esc(ind.name) + '"></div>' +
      (ind.reading ? '<p class="read">' + esc(ind.reading) + '</p>' : '') +
      '<div class="src">Kilde: ' + esc(ind.source) + ' · ' + fmtDate(ind.last_date) + '</div>' +
      (ind.proxy_reason ? '<div class="src stale">' + esc(ind.proxy_reason) + '</div>' : '') + '</div>';
  }

  /* --------------------------------------------------------------------- aksjer */
  function num(v, dec, kind) {
    if (!isNum(v)) return '<td class="num">–</td>';
    return '<td class="num">' + (kind === 'pct' ? fmtSigned(v, dec == null ? 1 : dec, ' %') : fmtSigned(v, dec == null ? 1 : dec, kind === 'pp' ? ' pp' : '')) + '</td>';
  }

  function renderEquityTable(eq) {
    if (!eq) return missingBox('aksjeutvikling', 'Filen equities.json kunne ikke leses.');
    var rows = Object.keys(eq.indicators || {}).filter(function (k) { return !/_dist200$/.test(k); }).map(function (k) {
      var i = eq.indicators[k];
      if (i.status !== 'ok') return '<tr><td>' + esc(i.name) + '</td><td colspan="5" class="miss-cell">' + MISSING + '<span class="reason"> ' + esc(String(i.error || '').slice(0, 160)) + '</span></td></tr>';
      var d = eq.indicators[k + '_dist200'];
      return '<tr><td>' + esc(i.name) + (i.proxy ? ' <span class="flag flag-warn" title="' + esc(i.source) + '">Proxy: ' + esc(i.source) + '</span>' : '') + '</td>' +
        num(i.ret_1w, 1, 'pct') + num(i.ret_1m, 1, 'pct') + num(i.ret_12m, 1, 'pct') + num(d && d.status === 'ok' ? d.last_value : null, 1, 'pct') +
        '<td class="num' + (i.stale ? ' stale' : '') + '">' + fmtDate(i.last_date) + '</td></tr>';
    }).join('');
    return '<div class="tablewrap"><table><thead><tr><th>Marked</th><th class="num">1 uke</th><th class="num">1 måned</th><th class="num">12 måneder</th><th class="num">Mot 200d snitt</th><th class="num">Siste dato</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function renderBreadth(eq) {
    var b = eq && eq.sectors && eq.sectors.breadth;
    if (!b) return missingBox('bredde', 'Ingen sektordata tilgjengelig.');
    return '<div class="card breadth"><div class="tile-k">Bredde</div><div class="num-lg">' + b.above_200d + ' <span class="unit">av ' + b.total + ' sektorer</span></div>' +
      '<div class="tile-s">ligger over 200 dagers snitt (' + fmt(b.share, 0) + ' %)' + (b.total < b.total_expected ? ' <span class="stale">' + (b.total_expected - b.total) + ' sektor(er) mangler</span>' : '') + '</div>' +
      gauge(b.share, [{ to: 30, cls: 'z-xfear' }, { to: 70, cls: 'z-neutral' }, { to: 100, cls: 'z-xgreed' }], ['Få', 'Mange']) +
      '<p class="read">' + esc(b.note) + '</p></div>';
  }

  /* -------------------------------------------------------------------- stemning */
  function moodColor(v) {
    if (!isNum(v)) return '';
    var d = (v - 50) / 50, a = (0.10 + 0.5 * Math.min(Math.abs(d), 1)).toFixed(2);
    return 'background:' + (d >= 0 ? 'rgba(201,115,26,' : 'rgba(47,109,181,') + a + ')';
  }

  function renderMood(m, eq) {
    if (!m) return missingBox('stemning', 'Filen mood.json kunne ikke leses.');
    var mk = m.market || {};
    var comps = (mk.components || []).map(function (c) {
      if (c.status !== 'ok') return '<tr><td>' + esc(c.label) + '</td><td colspan="4" class="miss-cell">' + MISSING + '<span class="reason"> ' + esc(String(c.error || '').slice(0, 160)) + '</span></td></tr>';
      return '<tr><td>' + esc(c.label) + '<div class="muted small">' + esc(c.note || '') + '</div></td><td class="num">' + fmt(c.value, c.decimals) + ' <span class="unit">' + esc(c.unit) + '</span></td>' +
        '<td class="num heat" style="' + moodColor(c.score) + '">' + fmt(c.score, 0) + '</td><td class="num">' + (isNum(c.score) && isNum(c.score_1w) ? fmtSigned(c.score - c.score_1w, 0) : '–') + '</td>' +
        '<td class="num' + (c.stale ? ' stale' : '') + '">' + fmtDate(c.last_date) + '</td></tr>';
    }).join('');
    var compTable = comps ? '<div class="tablewrap"><table><thead><tr><th>Komponent</th><th class="num">Nivå</th><th class="num">Score</th><th class="num">Endring 1 uke</th><th class="num">Siste dato</th></tr></thead><tbody>' + comps + '</tbody></table></div>' : '';
    var chart = (mk.series && mk.series.length) ? '<div class="card"><h3 class="card-t">Markedsstemning siste tre år</h3><div class="chart chart-tall" id="c-mood" role="img" aria-label="Markedsstemning over tid"></div></div>' : '';

    var sectorRows = ((eq && eq.sectors && eq.sectors.rows) || {});
    var rowsObj = m.rows || {};
    var rows = Object.keys(rowsObj).map(function (k) { return rowsObj[k]; });
    rows.sort(function (a, b) { return (isNum(b.score) ? b.score : -1) - (isNum(a.score) ? a.score : -1); });
    var sec = rows.map(function (r) {
      var e = sectorRows[r.id] || {};
      if (r.status !== 'ok') return '<tr><td>' + esc(r.name) + ' <span class="muted">' + esc(r.symbol) + '</span></td><td colspan="6" class="miss-cell">' + MISSING + '<span class="reason"> ' + esc(String(r.error || '').slice(0, 140)) + '</span></td></tr>';
      return '<tr><td>' + esc(r.name) + ' <span class="muted">' + esc(r.symbol) + '</span></td>' +
        '<td class="num heat strong" style="' + moodColor(r.score) + '">' + fmt(r.score, 0) + '</td><td>' + esc(MOOD_TEXT[r.label] || '') + '</td>' +
        '<td class="num">' + (isNum(r.change_1w) ? fmtSigned(r.change_1w, 0) : '–') + '</td>' + num(e.ret_1m, 1, 'pct') + num(e.rel_3m, 1, 'pp') + num(e.dist200, 1, 'pct') + '</tr>';
    }).join('');
    var detail = rows.map(function (r) {
      if (r.status !== 'ok') return '';
      var by = {};
      (r.components || []).forEach(function (c) { by[c.id] = c; });
      var cell = function (id) { var c = by[id]; return c && c.status === 'ok' ? '<td class="num heat" style="' + moodColor(c.score) + '" title="' + esc(c.label) + ': ' + fmt(c.value, c.decimals) + ' ' + esc(c.unit) + '">' + fmt(c.score, 0) + '</td>' : '<td class="num miss-cell">–</td>'; };
      return '<tr><td>' + esc(r.name) + '</td>' + cell('mom200') + cell('ret1m') + cell('rs3m') + cell('vol') + cell('dd') + '</tr>';
    }).join('');
    var secTable = rows.length
      ? '<h3 class="sub">Stemning per sektor</h3><p class="lede-s">Score 0 til 100 per sektor-ETF mot sektorens egen 10 års historikk. Sortert fra mest grådighet til mest frykt. USA som proxy for global sektorutvikling.' +
        (m.benchmark_ok === false ? ' <span class="stale">Referansen SPY mangler, relativ styrke utelates.</span>' : '') + '</p>' +
        '<div class="tablewrap"><table><thead><tr><th>Sektor</th><th class="num">Score</th><th>Stemning</th><th class="num">Endring uke</th><th class="num">1 mnd</th><th class="num">Rel. styrke 3 mnd</th><th class="num">Mot 200d snitt</th></tr></thead><tbody>' + sec + '</tbody></table></div>' +
        '<details class="more"><summary>Vis de fem delmålene per sektor</summary><p class="small muted">Hvert delmål er persentilrang mot sektorens egen historikk. Rolige kurs (lav volatilitet) og nærhet til 52 ukers høy teller som grådighet.</p><div class="tablewrap"><table><thead><tr><th>Sektor</th><th class="num">200d snitt</th><th class="num">1 mnd</th><th class="num">Rel. styrke</th><th class="num">Ro (lav vol)</th><th class="num">Nær høy</th></tr></thead><tbody>' + detail + '</tbody></table></div></details>'
      : missingBox('stemning per sektor', 'Ingen sektordata.');
    return chart + '<h3 class="sub">Hva markedsindeksen består av</h3>' + compTable + secTable;
  }

  /* -------------------------------------------------------------------- metodikk */
  function renderMethodology(files, meta, summary) {
    var rows = [];
    ['volatility', 'macro', 'equities'].forEach(function (g) {
      var f = files[g];
      if (!f) { rows.push('<tr><td colspan="5">' + missingBox(g, 'Filen ' + g + '.json kunne ikke leses.') + '</td></tr>'); return; }
      Object.keys(f.indicators || {}).forEach(function (k) {
        var i = f.indicators[k];
        if (/_dist200$/.test(k) && g === 'equities') return;
        rows.push('<tr><td>' + esc(i.name) + '</td><td>' + esc(i.description || '') + '</td><td>' +
          (i.status === 'ok' ? esc(i.source) + (i.proxy ? ' <span class="flag flag-warn">Proxy</span>' : '') : '<span class="stale">' + MISSING + '</span>') +
          '</td><td>' + esc(i.frequency || '') + '</td><td>' + esc(i.limitation || '') + '</td></tr>');
      });
    });
    var table = '<div class="tablewrap"><table><thead><tr><th>Indikator</th><th>Beskrivelse</th><th>Kilde brukt</th><th>Frekvens</th><th>Begrensninger</th></tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
    var missing = meta && meta.missing && meta.missing.length
      ? '<p class="small"><strong>Mangler i siste kjøring:</strong> ' + meta.missing.map(function (m) { return esc(m.group + '.' + m.id); }).join(', ') + '.</p>' : '<p class="small">Ingen kilder mangler i siste kjøring.</p>';
    return missing + table;
  }

  return { MISSING: MISSING, esc: esc, fmt: fmt, fmtSigned: fmtSigned, fmtDate: fmtDate, fmtDateTime: fmtDateTime, levelOf: levelOf,
    missingBox: missingBox, pbar: pbar, gauge: gauge, renderStatus: renderStatus, renderOverview: renderOverview, renderIndicatorCard: renderIndicatorCard,
    renderEquityTable: renderEquityTable, renderBreadth: renderBreadth, renderMood: renderMood, renderMethodology: renderMethodology };
});
