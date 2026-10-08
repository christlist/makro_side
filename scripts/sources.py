"""Datakilder: CBOE, FRED, yfinance og Stooq, med kandidatliste og fallback."""
from __future__ import annotations

import io
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

from .common import SourceError, clean_series, get_logger

log = get_logger("sources")
UA = {"User-Agent": "Mozilla/5.0 (makro_side; +https://github.com/christlist/makro_side)"}


def http_get(url: str, params: Optional[dict] = None, timeout: int = 30, retries: int = 3,
             headers: Optional[dict] = None) -> requests.Response:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={**UA, **(headers or {})})
            if r.status_code == 429 or r.status_code >= 500:
                raise SourceError(f"HTTP {r.status_code} fra {url}")
            r.raise_for_status()
            return r
        except (requests.RequestException, SourceError) as exc:
            last = exc
            log.warning("Forsøk %d/%d feilet for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise SourceError(f"{url}: {last}")


def _csv_frame(text: str, header_hint: str) -> pd.DataFrame:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if header_hint in ln.lower()), None)
    if start is None:
        raise SourceError(f"Fant ikke CSV-header med '{header_hint}' (første linje: {lines[0][:80] if lines else 'tom'})")
    return pd.read_csv(io.StringIO("\n".join(lines[start:])))


def fetch_cboe(url: str, column: Optional[str], timeout: int, retries: int) -> pd.Series:
    df = _csv_frame(http_get(url, timeout=timeout, retries=retries).text, "date")
    df.columns = [str(c).strip().upper() for c in df.columns]
    date_col = df.columns[0]
    value_col = (column or "").upper()
    if value_col not in df.columns:
        value_col = df.columns[-1]
    s = pd.Series(pd.to_numeric(df[value_col], errors="coerce").values,
                  index=pd.to_datetime(df[date_col], errors="coerce"))
    s = s[s.index.notna()]
    return clean_series(s)


def fetch_fred(series_id: str, years: int, timeout: int, retries: int) -> pd.Series:
    start = (datetime.now(timezone.utc) - pd.DateOffset(years=years + 1)).strftime("%Y-%m-%d")
    r = http_get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                 params={"id": series_id, "cosd": start}, timeout=timeout, retries=retries)
    df = _csv_frame(r.text, "date")
    if df.shape[1] < 2:
        raise SourceError(f"FRED {series_id}: uventet CSV-format")
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
                  index=pd.to_datetime(df.iloc[:, 0], errors="coerce"))
    s = s[s.index.notna()]
    return clean_series(s)


def fetch_yfinance(symbol: str, years: int) -> pd.Series:
    import yfinance as yf  # importeres her slik at modulen kan testes uten yfinance

    df = yf.Ticker(symbol).history(period=f"{years + 1}y", interval="1d", auto_adjust=True)
    if df is None or df.empty or "Close" not in df.columns:
        raise SourceError(f"yfinance ga ingen data for {symbol}")
    return clean_series(df["Close"])


def fetch_stooq(symbol: str, timeout: int, retries: int) -> pd.Series:
    r = http_get("https://stooq.com/q/d/l/", params={"s": symbol, "i": "d"}, timeout=timeout, retries=retries)
    df = _csv_frame(r.text, "date")
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "close" not in df.columns:
        raise SourceError(f"Stooq {symbol}: ingen close-kolonne")
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values,
                  index=pd.to_datetime(df["date"], errors="coerce"))
    s = s[s.index.notna()]
    return clean_series(s)


def candidate_label(c: dict) -> str:
    if c.get("label"):
        return c["label"]
    src = c["source"]
    if src == "cboe":
        return "CBOE " + c["url"].rsplit("/", 1)[-1]
    if src == "fred":
        return f"FRED {c['id']}"
    return f"{src} {c.get('symbol')}"


def fetch_candidate(c: dict, settings: dict) -> pd.Series:
    years, to, rt = settings["history_years"], settings["http_timeout"], settings["http_retries"]
    src = c["source"]
    if src == "cboe":
        s = fetch_cboe(c["url"], c.get("column"), to, rt)
    elif src == "fred":
        s = fetch_fred(c["id"], years, to, rt)
    elif src == "yfinance":
        s = fetch_yfinance(c["symbol"], years)
    elif src == "stooq":
        s = fetch_stooq(c["symbol"], to, rt)
    else:
        raise SourceError(f"Ukjent kilde: {src}")
    if s.empty:
        raise SourceError("Tom serie")
    return s


def fetch_first(candidates: list[dict], settings: dict, errors: Optional[list] = None) -> tuple[pd.Series, dict]:
    """Prøv kandidatene i rekkefølge. Returnerer (serie, kandidat). Kaster SourceError
    med alle delfeil hvis ingen virker."""
    msgs: list[str] = []
    for c in candidates:
        label = candidate_label(c)
        try:
            s = fetch_candidate(c, settings)
            log.info("OK %s: %d obs, siste %s", label, len(s), s.index[-1].date())
            return s, c
        except Exception as exc:  # noqa: BLE001
            msg = f"{label}: {type(exc).__name__}: {exc}"
            log.error("FEIL %s", msg)
            msgs.append(msg)
            if errors is not None:
                errors.append(msg)
    raise SourceError(" | ".join(msgs) if msgs else "Ingen kandidater i konfigurasjonen")


def build_series_group(specs: dict, group: str, settings: dict) -> tuple[dict, dict]:
    """Hent og bygg en gruppe enkeltserier. Returnerer (indikatorer, råserier).
    En feilet serie blir en indikator med status "missing"."""
    from .common import build_indicator, missing_indicator

    indicators: dict = {}
    raw: dict = {}
    for ind_id, spec in specs.items():
        errors: list[str] = []
        try:
            s, cand = fetch_first(spec.get("candidates", []), settings, errors)
            indicators[ind_id] = build_indicator(spec, ind_id, group, s, settings,
                                                 source=candidate_label(cand),
                                                 proxy=bool(cand.get("proxy")))
            raw[ind_id] = clean_series(s)
        except Exception as exc:  # noqa: BLE001
            log.error("%s.%s mangler: %s", group, ind_id, exc)
            indicators[ind_id] = missing_indicator(spec, ind_id, group, str(exc))
    return indicators, raw
