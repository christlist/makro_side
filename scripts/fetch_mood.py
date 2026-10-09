"""Stemningsindeks (frykt og grådighet) for markedet og per sektor, fra prisdata og kilder som allerede brukes.

Hver komponent er en tidsserie der høy verdi enten betyr frykt eller grådighet. Scoren er persentilrang
(0 til 100) mot siste 10 år, snudd for komponenter der høy verdi betyr frykt. 100 = grådighet, 0 = frykt.
Indeksen er snittet av tilgjengelige komponenter. Ingen komponent konstrueres: mangler data, utelates den
og vises som «Data mangler».
"""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from .common import (SourceError, clean_series, get_logger, load_config, percentile_rank, run_group,
                     trailing, _num)
from .sources import candidate_label, fetch_first

log = get_logger("mood")

MAX_ASOF_GAP_DAYS = 10  # siste observasjon må ligge innenfor dette fra beregningsdatoen


# ---------------------------------------------------------------- ren beregning

def pct_at(s: pd.Series, asof: pd.Timestamp, years: int, min_obs: int) -> Optional[float]:
    """Persentilrang for siste verdi på eller før `asof`, mot trailing vindu. None hvis for lite data
    eller siste observasjon er for gammel i forhold til `asof`."""
    sub = s[s.index <= asof].dropna()
    if sub.empty or (asof - sub.index[-1]).days > MAX_ASOF_GAP_DAYS:
        return None
    win = trailing(sub, years)
    if len(win) < min_obs:
        return None
    return percentile_rank(win.values, float(win.iloc[-1]))


def score_at(s: pd.Series, asof: pd.Timestamp, invert: bool, years: int, min_obs: int) -> Optional[float]:
    p = pct_at(s, asof, years, min_obs)
    if p is None:
        return None
    return 100.0 - p if invert else p


def mean_score(scores: list[Optional[float]], min_components: int) -> Optional[float]:
    vals = [x for x in scores if x is not None]
    if len(vals) < min_components:
        return None
    return sum(vals) / len(vals)


def label_for(score: Optional[float], bands: dict) -> Optional[str]:
    if score is None:
        return None
    if score < bands["extreme_fear_below"]:
        return "extreme_fear"
    if score < bands["fear_below"]:
        return "fear"
    if score < bands["neutral_below"]:
        return "neutral"
    if score < bands["greed_below"]:
        return "greed"
    return "extreme_greed"


def dist200(s: pd.Series) -> pd.Series:
    return ((s / s.rolling(200).mean() - 1.0) * 100.0).dropna()


# ---------------------------------------------------------------- komponenter

def comp(label: str, x: Optional[pd.Series], invert: bool, unit: str, decimals: int,
         source: Optional[str] = None, error: Optional[str] = None, note: str = "") -> dict:
    return {"label": label, "x": x, "invert": invert, "unit": unit, "decimals": decimals,
            "source": source, "error": error, "note": note}


def market_components(series: dict, sources: dict, errors: dict) -> dict:
    """Bygg markedskomponentene fra hentede råserier. Mangler en forutsetning, settes feilmelding."""
    def need(*names):
        missing = [n for n in names if series.get(n) is None]
        return None if not missing else "Mangler grunnserie: " + ", ".join(
            f"{n} ({errors.get(n, 'ukjent feil')[:120]})" for n in missing)

    out = {}
    e = need("vix")
    out["vix"] = comp("VIX", None if e else series["vix"], True, "indekspunkter", 2, sources.get("vix"), e,
                      "Høy VIX = frykt")
    e = need("vix", "vix3m")
    out["vix_term"] = comp("VIX/VIX3M", None if e else (series["vix"] / series["vix3m"]).dropna(), True,
                           "forhold", 3, sources.get("vix"), e, "Høyt forhold (invertert termstruktur) = frykt")
    e = need("skew")
    out["skew"] = comp("SKEW", None if e else series["skew"], True, "indekspunkter", 1, sources.get("skew"), e,
                       "Høy SKEW = dyp nedsidebeskyttelse etterspørres = frykt")
    e = need("hy_oas")
    out["hy_oas"] = comp("Høyavkastningsspread", None if e else series["hy_oas"], True, "prosentpoeng", 2,
                         sources.get("hy_oas"), e, "Høy spread = frykt i kreditt")
    e = need("spx")
    out["spx_mom"] = comp("S&P 500 avstand til 200d snitt", None if e else dist200(series["spx"]), False,
                          "prosent", 1, sources.get("spx"), e, "Over snittet = grådighet")
    e = need(*[f"sector_{k}" for k in series.get("_sector_ids", [])]) if series.get("_sector_ids") else "Ingen sektorer"
    breadth = None
    if e is None:
        d = pd.DataFrame({k: dist200(series[f"sector_{k}"]) for k in series["_sector_ids"]})
        valid = d.notna().sum(axis=1)
        breadth = ((d > 0).sum(axis=1) / valid * 100.0)[valid >= max(1, len(series["_sector_ids"]) - 2)]
    out["breadth"] = comp("Andel sektorer over 200d snitt", breadth, False, "prosent", 0,
                          "SPDR sektor-ETFer", e, "Høy andel = grådighet")
    e = need("spy", "bond")
    haven = None
    if e is None:
        r = pd.DataFrame({"a": series["spy"].pct_change(20), "b": series["bond"].pct_change(20)}).dropna()
        haven = (r["a"] - r["b"]) * 100.0
    out["safe_haven"] = comp("Aksjer minus statsobligasjoner (20d)", haven, False, "prosentpoeng", 1,
                             f"{sources.get('spy')} mot {sources.get('bond')}", e,
                             "Aksjer slår obligasjoner = grådighet")
    e = need("xly", "xlp")
    cyc = None
    if e is None:
        ratio = (series["xly"] / series["xlp"]).dropna()
        cyc = (ratio.pct_change(63) * 100.0).dropna()
    out["cyc_def"] = comp("Syklisk mot defensivt (63d)", cyc, False, "prosent", 1, "XLY mot XLP", e,
                          "Syklisk slår defensivt = grådighet")
    return out


def sector_components(close: pd.Series, spy: Optional[pd.Series]) -> dict:
    ret = close.pct_change()
    rs = None
    if spy is not None:
        j = pd.DataFrame({"a": close.pct_change(63), "b": spy.pct_change(63)}).dropna()
        rs = (j["a"] - j["b"]) * 100.0
    return {
        "mom200": comp("Avstand til 200d snitt", dist200(close), False, "prosent", 1),
        "ret1m": comp("Avkastning 1 måned", (close.pct_change(21) * 100.0).dropna(), False, "prosent", 1),
        "rs3m": comp("Relativ styrke 3 mnd mot SPY", rs, False, "prosentpoeng", 1,
                     error=None if rs is not None else "Mangler referanse (SPY)"),
        "vol": comp("Realisert volatilitet 21d", (ret.rolling(21).std() * (252 ** 0.5) * 100.0).dropna(), True,
                    "prosent p.a.", 1),
        "dd": comp("Avstand til 52 ukers høy", ((close / close.rolling(252).max() - 1.0) * 100.0).dropna(), False,
                   "prosent", 1),
    }


def evaluate(components: dict, ref: pd.Timestamp, years: int, min_obs: int, max_age_days: int,
             stale_days: int, today: pd.Timestamp) -> list[dict]:
    """Score per komponent på dato `ref`, pluss score en uke tidligere."""
    out = []
    ref_1w = ref - pd.DateOffset(days=7)
    for cid, c in components.items():
        row = {"id": cid, "label": c["label"], "unit": c["unit"], "decimals": c["decimals"],
               "source": c.get("source"), "note": c.get("note", ""), "status": "ok", "error": None,
               "score": None, "score_1w": None, "value": None, "last_date": None, "stale": False}
        x = c["x"]
        if x is None or len(x.dropna()) == 0:
            row.update({"status": "missing", "error": c["error"] or "Tom serie"})
            out.append(row)
            continue
        x = x.dropna()
        last = x.index[-1]
        row["last_date"] = last.strftime("%Y-%m-%d")
        row["value"] = _num(float(x.iloc[-1]), 4)
        row["stale"] = bool((today - last).days > stale_days)
        if (ref - last).days > max_age_days:
            row.update({"status": "missing", "error": f"Data for gamle (siste punkt {row['last_date']})"})
        else:
            sc = score_at(x, ref, c["invert"], years, min_obs)
            if sc is None:
                row.update({"status": "missing", "error": "For kort historikk til persentilrang"})
            else:
                row["score"] = _num(sc, 1)
                row["score_1w"] = _num(score_at(x, ref_1w, c["invert"], years, min_obs), 1)
                w = trailing(x, years)
                row["window_years"] = _num((last - w.index[0]).days / 365.25, 1)
        out.append(row)
    return out


def index_history(components: dict, ref: pd.Timestamp, weeks: int, years: int, min_obs: int,
                  min_components: int) -> list[list]:
    pts = []
    for asof in pd.date_range(end=ref, periods=weeks, freq="7D"):
        sc = mean_score([score_at(c["x"].dropna(), asof, c["invert"], years, min_obs)
                         for c in components.values() if c["x"] is not None], min_components)
        if sc is not None:
            pts.append([asof.strftime("%Y-%m-%d"), _num(sc, 1)])
    return pts


def summarize(rows: list[dict], bands: dict, min_components: int) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    score = mean_score([r["score"] for r in ok], min_components)
    prev = mean_score([r["score_1w"] for r in ok], min_components)
    if score is None:
        return {"status": "missing", "score": None, "label": None, "score_1w": None, "change_1w": None,
                "n_used": len(ok), "n_total": len(rows),
                "error": f"Data mangler: {len(ok)} av {len(rows)} komponenter tilgjengelig, minst {min_components} kreves."}
    return {"status": "ok", "score": _num(score, 1), "label": label_for(score, bands),
            "score_1w": _num(prev, 1), "change_1w": _num(score - prev, 1) if prev is not None else None,
            "n_used": len(ok), "n_total": len(rows), "error": None}


# ---------------------------------------------------------------- henting

def fetch_series(candidates: list[dict], settings: dict, label: str, errors: dict) -> tuple[Optional[pd.Series], Optional[str]]:
    errs: list[str] = []
    try:
        s, cand = fetch_first(candidates, settings, errs)
        return clean_series(s), candidate_label(cand)
    except Exception as exc:  # noqa: BLE001
        errors[label] = str(exc)
        log.error("%s mangler: %s", label, exc)
        return None, None


def build(fetcher: Callable = fetch_series) -> dict:
    cfg = load_config()
    settings, mcfg = cfg["settings"], cfg["mood"]
    years, min_obs = settings["history_years"], settings["min_obs_percentile"]
    bands = mcfg["bands"]
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    errors: dict = {}
    series: dict = {}
    sources: dict = {}

    wanted = {
        "vix": cfg["volatility"]["series"]["vix"]["candidates"],
        "vix3m": cfg["volatility"]["series"]["vix3m"]["candidates"],
        "skew": cfg["volatility"]["series"]["skew"]["candidates"],
        "hy_oas": cfg["macro"]["series"]["hy_oas"]["candidates"],
        "spx": cfg["equities"]["indices"]["spx"]["candidates"],
        "spy": cfg["equities"]["benchmark"]["candidates"],
        "bond": mcfg["bond_candidates"],
    }
    sec_cfg = cfg["equities"]["sectors"]
    for sid, sp in sec_cfg.items():
        wanted[f"sector_{sid}"] = [{"source": "yfinance", "symbol": sp["symbol"]}]
    for name, cands in wanted.items():
        series[name], sources[name] = fetcher(cands, settings, name, errors)
    series["_sector_ids"] = [k for k in sec_cfg if series.get(f"sector_{k}") is not None]
    series["xly"], series["xlp"] = series.get("sector_xly"), series.get("sector_xlp")
    for k in ("xly", "xlp"):
        if series[k] is None:
            errors[k] = errors.get(f"sector_{k}", "mangler")
    if len(series["_sector_ids"]) < len(sec_cfg):
        lost = [k for k in sec_cfg if k not in series["_sector_ids"]]
        errors["_sectors"] = "Mangler: " + ", ".join(lost)

    # --- marked
    mcomps = market_components(series, sources, errors)
    last_dates = [c["x"].dropna().index[-1] for c in mcomps.values() if c["x"] is not None and len(c["x"].dropna())]
    ref = max(last_dates) if last_dates else today
    rows = evaluate(mcomps, ref, years, min_obs, mcfg["max_age_days"], settings["stale_days"], today)
    market = summarize(rows, bands, mcfg["min_components_market"])
    market.update({"components": rows, "ref_date": ref.strftime("%Y-%m-%d") if last_dates else None,
                   "series": index_history(mcomps, ref, mcfg["index_weeks"], years, min_obs,
                                           mcfg["min_components_market"]) if last_dates else []})

    # --- sektorer
    spy = series.get("spy")
    sectors: dict = {}
    for sid, sp in sec_cfg.items():
        base = {"id": sid, "name": sp["name"], "symbol": sp["symbol"]}
        close = series.get(f"sector_{sid}")
        if close is None:
            sectors[sid] = {**base, "status": "missing", "error": errors.get(f"sector_{sid}", "Mangler kurs")}
            continue
        comps = sector_components(close, spy)
        s_ref = close.index[-1]
        srows = evaluate(comps, s_ref, years, min_obs, mcfg["max_age_days"], settings["stale_days"], today)
        summ = summarize(srows, bands, mcfg["min_components_sector"])
        sectors[sid] = {**base, **summ, "last_date": s_ref.strftime("%Y-%m-%d"), "components": srows,
                        "error": summ["error"], "source": sources.get(f"sector_{sid}")}
        if summ["status"] != "ok":
            sectors[sid]["status"] = "missing"

    indicators = {r["id"]: {"status": r["status"], "error": r["error"]} for r in rows}
    return {"indicators": indicators, "market": market, "rows": sectors,
            "rule": {"bands": bands, "min_components_market": mcfg["min_components_market"],
                     "min_components_sector": mcfg["min_components_sector"], "window_years": years},
            "benchmark_ok": spy is not None}


def main() -> None:
    run_group("mood", build, log)


if __name__ == "__main__":
    main()
