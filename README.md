# makro_side

Statisk makroside for det globale aksjemarkedet. Gir en oversikt på under ett minutt: regime, volatilitet, kreditt, renter, råvarer, aksjer, sektorer og stemning (frykt og grådighet). Oppdateres hver lørdag av GitHub Actions og hostes på GitHub Pages.

## Prinsipper for data

- Ingen konstruerte eller dummydata, heller ikke i tester.
- Feiler en kilde, vises «Data mangler» for indikatoren, og feilen logges og lagres i JSON (`error`) og `data/meta.json`.
- Alle tall vises med dato for siste datapunkt. Siden viser tidspunktet for siste kjøring.
- Data eldre enn 10 dager merkes «utdatert». Data eldre enn 21 dager utelates fra regimet.

## Struktur

| Mappe/fil | Innhold |
|---|---|
| `config.yaml` | Kilder (kandidatlister med fallback), terskler, sektorsøkeord |
| `scripts/` | Python. `common.py` (statistikk, JSON, feilhåndtering), `sources.py` (CBOE, FRED, yfinance, Stooq), ett skript per datagruppe |
| `data/` | JSON generert av skriptene |
| `docs/` | Statisk side (HTML, CSS, vanilla JS, Plotly fra CDN) |
| `tests/` | `pytest` (persentil, z-score, regel, manglende data) og `node --test` (siden ved manglende data) |
| `.github/workflows/weekly.yml` | Lørdagskjøring (cron, UTC) og manuell kjøring |

## Kjøre lokalt

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m scripts.verify_sources          # sjekk at hver kilde virker
python -m scripts.fetch_volatility
python -m scripts.fetch_macro
python -m scripts.fetch_equities
python -m scripts.fetch_mood              # stemningsindeks, markedet og per sektor
python -m scripts.build_regime
python -m scripts.finalize
python -m scripts.build_site && python -m http.server -d site 8000
python -m pytest -q && node --test tests/js/render.test.js
```

## Oppsett på GitHub

1. Repo-innstillinger, Pages: velg *Source: GitHub Actions*.
2. Kjør workflowen «Oppdater makroside» manuelt første gang (*Run workflow*).
3. Ingen hemmelige nøkler trengs. Runneren må kunne nå `cdn.cboe.com`, `fred.stlouisfed.org`, Yahoo Finance, `stooq.com` og `api.gdeltproject.org` (standard for GitHub-hosted runners).

Workflowen kjører først `verify_sources`, som skriver en tabell over hvilke kandidatkilder som virker til jobbens summary.

## Regimeregel

Per indikator: persentilrang mot siste 10 år. Stress-persentil er persentilen (høy verdi = stress), eller 100 minus persentilen for avstand til 200d snitt. Semafor: grønn under 60, gul fra 60, rød fra 80. Samlet regime er snittet av stress-persentilene: rolig under 55, forhøyet fra 55, stress fra 75. Minst 4 indikatorer må ha gyldige, ferske data. Alle terskler ligger i `config.yaml`.

Regime-indikatorer: VIX, VIX/VIX3M, HY-spread, IG-spread, bred dollarindeks, S&P 500 avstand til 200d snitt.

## Kilder og proxyer

Se tabellen under «Metodikk og kilder» på siden (genereres fra siste kjøring). Proxyer er merket «Proxy» der de brukes: VSTOXX erstattes av realisert 21d volatilitet i Euro STOXX 50 hvis V2TX ikke finnes (bakoverskuende, ikke implisitt vol), MSCI World og EM via ETF (URTH, EEM), sektorer via SPDR-ETFer (USA), Euro STOXX 50/ETF hvis STOXX 600 mangler, NORW hvis Oslo Børs-indeks mangler.
Stemning (frykt og grådighet): prisbasert, ingen nyheter eller undersøkelser. Markedsindeksen er snittet av persentilrang (0 frykt, 100 grådighet, mot siste 10 år) for VIX, VIX/VIX3M, SKEW, høyavkastningsspread, S&P 500 mot 200d snitt, andel sektorer over 200d snitt, aksjer mot statsobligasjoner (SPY mot TLT, 20 dager) og syklisk mot defensivt (XLY mot XLP, 63 dager). Minst fem komponenter må ha data. Sektorstemning er snittet av fem mål per sektor-ETF mot sektorens egen historikk (avstand til 200d snitt, 1 måneds avkastning, relativ styrke mot SPY over 3 måneder, lav realisert volatilitet, nærhet til 52 ukers høy). Bånd i `config.yaml`. Indeksen overlapper delvis med regimepanelet.
Nyhetssentiment (GDELT, yfinance-nyheter, FinBERT) ble fjernet: GDELT ga HTTP 429 fra GitHub-runnere og Yahoo ga ingen nyheter.
