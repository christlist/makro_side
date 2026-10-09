// Kjør: node --test tests/js
// Tester at siden håndterer manglende data. Ingen datapunkter konstrueres her:
// inputene er kun feilobjekter og tomme/manglende filer.
const test = require('node:test');
const assert = require('node:assert');
const R = require('../../docs/render.js');

const missingInd = { id: 'vix', name: 'VIX', status: 'missing', error: 'CBOE: tilkobling avvist', series: [] };

test('manglende indikatorkort viser Data mangler og feilårsak, ingen tall', () => {
  const html = R.renderIndicatorCard(missingInd, 'c1');
  assert.match(html, /Data mangler/);
  assert.match(html, /tilkobling avvist/);
  assert.doesNotMatch(html, /class="big"/);
});

test('manglende indikator i datafil (undefined) gir Data mangler', () => {
  assert.match(R.renderIndicatorCard(undefined, 'c1', { name: 'vix' }), /Data mangler/);
});

test('regime-fil som mangler helt gir Data mangler', () => {
  assert.match(R.renderRegime(null), /Data mangler/);
});

test('regime med status missing viser Data mangler og ingen samlet tilstand', () => {
  const html = R.renderRegime({ status: 'missing', state: null, error: 'Data mangler: 0 av 6', n_used: 0, n_total: 6,
    items: [{ status: 'missing', label: 'VIX', reason: 'CBOE feilet' }], rule: { light: {}, overall: {}, min_indicators: 4, max_age_days: 21 } });
  assert.match(html, /state-missing/);
  assert.match(html, /CBOE feilet/);
  assert.doesNotMatch(html, /state-calm|state-elevated|state-stress/);
});

test('aksjetabell, sektorer, stemning og metodikk tåler manglende filer', () => {
  assert.match(R.renderEquityTable(null), /Data mangler/);
  assert.match(R.renderSectors(null), /Data mangler/);
  assert.match(R.renderMood(null), /Data mangler/);
  assert.match(R.renderMethodology({ volatility: null, macro: null, equities: null }), /Data mangler/);
  assert.match(R.renderMeta(null), /mangler/);
});

test('stemning: manglende marked og sektorer vises som Data mangler uten tall og tilstand', () => {
  const html = R.renderMood({ market: { status: 'missing', score: null, label: null, error: 'Data mangler: 0 av 8 komponenter tilgjengelig',
      components: [{ id: 'vix', label: 'VIX', status: 'missing', error: 'CBOE feilet' }], series: [] },
    rows: { xlk: { id: 'xlk', name: 'Teknologi', symbol: 'XLK', status: 'missing', error: 'yfinance feilet' } } });
  assert.match(html, /Data mangler/);
  assert.match(html, /CBOE feilet/);
  assert.match(html, /yfinance feilet/);
  assert.doesNotMatch(html, /mood-extreme|mood-fear|mood-greed|mood-neutral/);
  assert.doesNotMatch(html, /class="gauge"/);
  assert.match(html, /ikke spørreundersøkelse/i);
});

test('stemning: gyldig struktur rendres med score, etikett og sektortabell (testverdier er kun struktur)', () => {
  const html = R.renderMood({ market: { status: 'ok', score: 50, label: 'neutral', change_1w: 0, n_used: 8, n_total: 8, ref_date: '2026-10-08',
      components: [{ id: 'vix', label: 'VIX', status: 'ok', score: 50, score_1w: 50, value: 1, decimals: 0, unit: 'x', last_date: '2026-10-08', note: '' }], series: [['2026-10-08', 50]] },
    rows: { a: { id: 'a', name: 'Sektor A', symbol: 'AAA', status: 'ok', score: 50, label: 'neutral', change_1w: 0,
      components: [{ id: 'mom200', status: 'ok', label: 'L', score: 50, value: 1, decimals: 0, unit: 'x' }] } } });
  assert.match(html, /Nøytral/);
  assert.match(html, /Sektor A/);
  assert.match(html, /id="c-mood"/);
});

test('utdaterte data vises med dato', () => {
  const html = R.renderIndicatorCard({ id: 'x', name: 'X', status: 'ok', stale: true, last_date: '2026-01-02', last_value: 1, decimals: 1,
    percentile_10y: null, change_1w: null, source: 'test' }, 'c');
  assert.match(html, /Utdatert: siste datapunkt 02\.01\.2026/);
  assert.match(html, /for kort historikk/);
});

test('HTML escapes feilmeldinger', () => {
  assert.doesNotMatch(R.missingBox('x', '<script>alert(1)</script>'), /<script>/);
});
