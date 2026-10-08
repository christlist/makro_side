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

test('aksjetabell, sektorer, sentiment og metodikk tåler manglende filer', () => {
  assert.match(R.renderEquityTable(null), /Data mangler/);
  assert.match(R.renderSectors(null), /Data mangler/);
  assert.match(R.renderSentiment(null), /Data mangler/);
  assert.match(R.renderMethodology({ volatility: null, macro: null, equities: null }), /Data mangler/);
  assert.match(R.renderMeta(null), /mangler/);
});

test('sentiment: skjuler score ved for få artikler og viser mangel per sektor', () => {
  const html = R.renderSentiment({ min_articles: 15, rows: {
    a: { id: 'a', name: 'Energi', status: 'ok', hidden: true, n_articles: 3, z: null, mean_score: 0.1 },
    b: { id: 'b', name: 'Helse', status: 'missing', error: 'GDELT feilet' } } });
  assert.match(html, /Skjult/);
  assert.match(html, /For få artikler \(3 av minst 15\)/);
  assert.match(html, /GDELT feilet/);
  assert.match(html, /støyende/i);
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
