// Kjør: node --test tests/js/render.test.js
// Tester at siden håndterer manglende data. Ingen datapunkter konstrueres her:
// inputene er feilobjekter, tomme/manglende filer og rene strukturtester (verdiene er kun for å teste formatering).
const test = require('node:test');
const assert = require('node:assert');
const R = require('../../docs/render.js');

const missingInd = { id: 'vix', name: 'VIX', status: 'missing', error: 'CBOE: tilkobling avvist', series: [], meaning: 'Forklaring' };

test('manglende indikatorkort viser Data mangler og feilårsak, ingen tall', () => {
  const html = R.renderIndicatorCard(missingInd, 'c1');
  assert.match(html, /Data mangler/);
  assert.match(html, /tilkobling avvist/);
  assert.doesNotMatch(html, /num-lg/);
  assert.doesNotMatch(html, /class="chip/);
});

test('manglende indikator i datafil (undefined) gir Data mangler', () => {
  assert.match(R.renderIndicatorCard(undefined, 'c1', { name: 'vix' }), /Data mangler/);
});

test('oversikt uten noen filer gir Data mangler i alle deler', () => {
  const html = R.renderOverview(null, null, null);
  assert.match(html, /Data mangler/);
  assert.doesNotMatch(html, /state-calm|state-elevated|state-stress/);
  assert.doesNotMatch(html, /class="gauge"/);
});

test('regime med status missing viser Data mangler og ingen samlet tilstand', () => {
  const html = R.renderOverview({ points: [] }, { status: 'missing', state: null, error: 'Data mangler: 0 av 6', n_used: 0, n_total: 6,
    items: [{ status: 'missing', label: 'VIX', reason: 'CBOE feilet' }], rule: { light: {}, overall: {}, min_indicators: 4, max_age_days: 21 } }, null);
  assert.match(html, /CBOE feilet/);
  assert.match(html, /Data mangler: 0 av 6/);
  assert.doesNotMatch(html, /state-calm|state-elevated|state-stress/);
});

test('statuslinjen tåler manglende meta og oppsummering', () => {
  const html = R.renderStatus(null, null);
  assert.match(html, /Data mangler/);
  assert.doesNotMatch(html, /pill-ok/);
});

test('statuslinjen viser mangler tydelig', () => {
  const html = R.renderStatus({ run_at: '2026-10-09T09:58:08+00:00' }, { health: { n_total: 26, n_ok: 25, missing: ['VIX'], proxies: [], latest_data_date: '2026-10-08' } });
  assert.match(html, /1 av 26 indikatorer mangler data/);
  assert.match(html, /pill-warn/);
  assert.match(html, /8\. okt\. 2026/);
});

test('aksjetabell, bredde, stemning og metodikk tåler manglende filer', () => {
  assert.match(R.renderEquityTable(null), /Data mangler/);
  assert.match(R.renderBreadth(null), /Data mangler/);
  assert.match(R.renderMood(null, null), /Data mangler/);
  assert.match(R.renderMethodology({ volatility: null, macro: null, equities: null }, null, null), /Data mangler/);
});

test('stemning: manglende marked og sektorer vises som Data mangler uten tall og tilstand', () => {
  const html = R.renderMood({ market: { status: 'missing', score: null, label: null, error: 'Data mangler: 0 av 8 komponenter tilgjengelig',
      components: [{ id: 'vix', label: 'VIX', status: 'missing', error: 'CBOE feilet' }], series: [] },
    rows: { xlk: { id: 'xlk', name: 'Teknologi', symbol: 'XLK', status: 'missing', error: 'yfinance feilet' } } }, null);
  assert.match(html, /CBOE feilet/);
  assert.match(html, /yfinance feilet/);
  assert.doesNotMatch(html, /id="c-mood"/);
});

test('stemning: gyldig struktur rendres med sektortabell (testverdier er kun struktur)', () => {
  const html = R.renderMood({ market: { status: 'ok', score: 50, label: 'neutral', change_1w: 0, n_used: 8, n_total: 8, ref_date: '2026-10-08',
      components: [{ id: 'vix', label: 'VIX', status: 'ok', score: 50, score_1w: 50, value: 1, decimals: 0, unit: 'x', last_date: '2026-10-08', note: '' }], series: [['2026-10-08', 50]] },
    rows: { a: { id: 'a', name: 'Sektor A', symbol: 'AAA', status: 'ok', score: 50, label: 'neutral', change_1w: 0,
      components: [{ id: 'mom200', status: 'ok', label: 'L', score: 50, value: 1, decimals: 0, unit: 'x' }] } } },
    { sectors: { rows: { a: { ret_1m: 1, rel_3m: 2, dist200: 3 } } } });
  assert.match(html, /Sektor A/);
  assert.match(html, /id="c-mood"/);
  assert.match(html, /Nøytral/);
});

test('komponent utenfor indeksen får merke, også når den mangler data', () => {
  const html = R.renderMood({ market: { status: 'ok', score: 50, label: 'neutral', n_used: 8, n_total: 8, components: [
      { id: 'naaim', label: 'NAAIM', status: 'missing', in_index: false, error: 'NAAIM: 403' },
      { id: 'vix', label: 'VIX', status: 'ok', in_index: true, score: 50, value: 1, decimals: 0, unit: 'x', last_date: '2026-10-08' }], series: [] }, rows: {} }, null);
  assert.match(html, /Utenfor indeksen/);
  assert.match(html, /NAAIM: 403/);
  assert.strictEqual((html.match(/Utenfor indeksen/g) || []).length, 1);  // ikke VIX
});

test('utdaterte data vises med dato og uten nivåetikett når persentil mangler', () => {
  const html = R.renderIndicatorCard({ id: 'x', name: 'X', status: 'ok', stale: true, last_date: '2026-01-02', last_value: 1, decimals: 1,
    percentile_10y: null, change_1w: null, source: 'test' }, 'c');
  assert.match(html, /Utdatert: siste datapunkt 2\. jan\. 2026/);
  assert.match(html, /For kort historikk/);
  assert.doesNotMatch(html, /class="chip/);
});

test('nivåetikett følger persentilgrensene 10, 25, 75 og 90', () => {
  assert.deepStrictEqual([0, 9.9, 10, 24.9, 25, 74.9, 75, 89.9, 90, 100].map(R.levelOf),
    ['very_low', 'very_low', 'low', 'low', 'normal', 'normal', 'high', 'high', 'very_high', 'very_high']);
  assert.strictEqual(R.levelOf(null), null);
});

test('indikatorkort viser forklaring, nivå og persentiltekst', () => {
  const html = R.renderIndicatorCard({ id: 'x', name: 'X', status: 'ok', last_date: '2026-10-08', last_value: 1, decimals: 1, unit: 'u', percentile_10y: 95,
    window_years: 10, change_1w: 0.5, change_kind: 'abs', source: 'test', meaning: 'Hva den måler', reading: 'Hvordan tolke' }, 'c');
  assert.match(html, /Uvanlig høyt/);
  assert.match(html, /Hva den måler/);
  assert.match(html, /Hvordan tolke/);
  assert.match(html, /Høyere enn 95 % av dagene siste 10 år/);
});

test('proxy vises med merke og forklaring på hvorfor originalen mangler', () => {
  const html = R.renderIndicatorCard({ id: 'vstoxx', name: 'Proxy X', status: 'ok', proxy: true, proxy_reason: 'VSTOXX (V2TX) utilgjengelig: ingen data',
    last_date: '2026-10-08', last_value: 1, decimals: 1, percentile_10y: null, change_1w: null, source: 'Proxy: test' }, 'c');
  assert.match(html, /Proxy<\/span>/);
  assert.match(html, /V2TX\) utilgjengelig/);
});

test('HTML escapes feilmeldinger og tekst fra data', () => {
  assert.doesNotMatch(R.missingBox('x', '<script>alert(1)</script>'), /<script>/);
  assert.doesNotMatch(R.renderOverview({ points: [{ kind: 'x', text: '<img src=x onerror=1>' }] }, null, null), /<img/);
});

test('måler og persentilbar klemmer verdier til 0 til 100', () => {
  assert.match(R.pbar(150), /left:100%/);
  assert.match(R.gauge(-5, [{ to: 100, cls: 'z' }], ['a', 'b']), /left:0%/);
  assert.match(R.pbar(null), /pbar-empty/);
});
