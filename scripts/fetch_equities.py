"""Global aksjeutvikling, avstand til 200 dagers snitt, bredde og sektorrelativ styrke."""
from __future__ import annotations

import time

import pandas as pd

from .common import (SourceError, build_indicator, change_over, clean_series, get_logger,
                     load_config, missing_indicator, run_group, _num)
from .sources import candidate_label, fetch_first

log = get_logger("equities")


def returns(s: pd.Series) -> dict:
    return {
        "ret_1w": _num(change_over(s, pd.DateOffset(days=7), "pct"), 2),
        "ret_1m": _num(change_over(s, pd.DateOffset(months=1), "pct"), 2),
        "ret_3m": _num(change_over(s, pd.DateOffset(months=3), "pct"), 2),
        "ret_12m": _num(change_over(s, pd.DateOffset(years=1), "pct"), 2),
    }


def dist200_series(s: pd.Series) -> pd.Series:
    ma = s.rolling(200).mean()
    return ((s / ma - 1.0) * 100.0).dropna()


def build_equity(spec: dict, ind_id: str, group: str, settings: dict, extra_errors: list):
    """Returnerer (kurs-indikator, dist200-indikator, råserie). Kaster SourceError ved feil."""
    s, cand = fetch_first(spec["candidates"], settings, extra_errors)
    s = clean_series(s)
    label = candidate_label(cand)
    proxy = bool(cand.get("proxy"))
    px_spec = {"name": spec["name"], "description": spec.get("description"), "change": "pct",
               "decimals": 2, "unit": "kurs",
               "frequency": "Daglig", "limitation": "Kursavkastning for indekser; ETF-proxyer er justert for utbytte."}
    ind = build_indicator(px_spec, ind_id, group, s, settings, source=label, proxy=proxy)
    ind.update(returns(s))
    d200 = dist200_series(s)
    dist = None
    if len(d200):
        d_spec = {"name": f"{spec['name']}: avstand til 200d snitt", "unit": "prosent", "change": "abs",
                  "decimals": 2,
                  "description": "Kurs i prosent over eller under 200 handelsdagers glidende snitt.",
                  "frequency": "Daglig",
                  "limitation": "Trend, ikke prognose. Persentilen er mot de siste 10 årene av samme mål."}
        dist = build_indicator(d_spec, f"{ind_id}_dist200", group, d200, settings, source=label, proxy=proxy)
    ind["dist200"] = dist["last_value"] if dist else None
    return ind, dist, s


def build() -> dict:
    cfg = load_config()
    settings = cfg["settings"]
    ecfg = cfg["equities"]
    indicators: dict = {}
    sectors: dict = {}

    for ind_id, spec in ecfg["indices"].items():
        errs: list[str] = []
        try:
            ind, dist, _ = build_equity(spec, ind_id, "equities", settings, errs)
            indicators[ind_id] = ind
            if dist:
                indicators[f"{ind_id}_dist200"] = dist
            else:
                indicators[f"{ind_id}_dist200"] = missing_indicator(
                    spec, f"{ind_id}_dist200", "equities", "For kort historikk til 200d snitt")
        except Exception as exc:  # noqa: BLE001
            log.error("equities.%s mangler: %s", ind_id, exc)
            indicators[ind_id] = missing_indicator(spec, ind_id, "equities", str(exc))
            indicators[f"{ind_id}_dist200"] = missing_indicator(
                spec, f"{ind_id}_dist200", "equities", f"Mangler grunnserie ({ind_id})")

    # Sektor-ETFer og referanse
    bench = ecfg["benchmark"]
    bench_s = None
    try:
        bench_s, bcand = fetch_first(bench["candidates"], settings)
        bench_s = clean_series(bench_s)
    except SourceError as exc:
        log.error("Benchmark %s mangler: %s", bench["id"], exc)

    sector_rows: dict = {}
    for sid, sspec in ecfg["sectors"].items():
        time.sleep(0.3)
        spec = {"name": sspec["name"], "description": f"SPDR {sspec['symbol']}",
                "candidates": [{"source": "yfinance", "symbol": sspec["symbol"]},
                               {"source": "stooq", "symbol": f"{sspec['symbol'].lower()}.us"}]}
        try:
            ind, dist, s = build_equity(spec, sid, "sectors", settings, [])
            row = {"id": sid, "name": sspec["name"], "symbol": sspec["symbol"], "status": "ok",
                   "source": ind["source"], "last_date": ind["last_date"], "stale": ind["stale"],
                   "dist200": ind["dist200"], **returns(s)}
            for k, off in (("rel_1w", pd.DateOffset(days=7)), ("rel_1m", pd.DateOffset(months=1)),
                           ("rel_3m", pd.DateOffset(months=3))):
                if bench_s is None:
                    row[k] = None
                    continue
                a = change_over(s, off, "pct")
                b = change_over(bench_s.loc[:s.index[-1]], off, "pct")
                row[k] = _num(a - b, 2) if a is not None and b is not None else None
            sector_rows[sid] = row
        except Exception as exc:  # noqa: BLE001
            log.error("sektor %s mangler: %s", sid, exc)
            sector_rows[sid] = {"id": sid, "name": sspec["name"], "symbol": sspec["symbol"],
                                "status": "missing", "error": str(exc)}

    ok = [r for r in sector_rows.values() if r["status"] == "ok" and r.get("dist200") is not None]
    breadth = None
    if ok:
        above = sum(1 for r in ok if r["dist200"] > 0)
        breadth = {"above_200d": above, "total": len(ok), "total_expected": len(sector_rows),
                   "share": _num(100.0 * above / len(ok), 0),
                   "note": "Andel av de elleve SPDR-sektor-ETFene (USA) som ligger over 200d snitt. USA som proxy for global bredde."}
    return {"indicators": indicators,
            "sectors": {"label": "USA som proxy for global sektorutvikling",
                        "benchmark": bench["name"], "benchmark_ok": bench_s is not None,
                        "benchmark_last_date": bench_s.index[-1].strftime("%Y-%m-%d") if bench_s is not None else None,
                        "rows": sector_rows, "breadth": breadth}}


def main() -> None:
    run_group("equities", build, log)


if __name__ == "__main__":
    main()
