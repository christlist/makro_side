"""Delt hjelpemodul: konfig, logging, feilhåndtering, statistikk og JSON-bygging.

Prinsipp: en feilet kilde gir en indikator med status "missing" og en feilmelding.
Det genereres aldri erstatningsverdier, og gamle verdier vises alltid med dato.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config.yaml"


class SourceError(Exception):
    """En datakilde ga ingen brukbare data."""


def load_config(path: Optional[Path] = None) -> dict:
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(name: str, payload: dict, data_dir: Optional[Path] = None) -> Path:
    out_dir = data_dir or DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")
    return path


def read_json(name: str, data_dir: Optional[Path] = None) -> Optional[dict]:
    path = (data_dir or DATA_DIR) / f"{name}.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- statistikk

def percentile_rank(window: Iterable[float], value: float) -> float:
    """Persentilrang (0 til 100) for `value` i `window`, "mean"-konvensjon:
    (andel strengt mindre + andel mindre eller lik) / 2. NaN i vinduet ignoreres."""
    a = np.asarray(list(window), dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0 or value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    strict = (a < value).sum()
    weak = (a <= value).sum()
    return float(100.0 * (strict + weak) / (2.0 * a.size))


def zscores(values: Iterable[float]) -> list[float]:
    """z-score for hver verdi mot utvalget, utvalgsstandardavvik (ddof=1).
    Færre enn 2 verdier eller null spredning gir NaN."""
    a = np.asarray(list(values), dtype=float)
    if a.size < 2:
        return [float("nan")] * a.size
    sd = a.std(ddof=1)
    if sd == 0 or math.isnan(sd):
        return [float("nan")] * a.size
    return [float(x) for x in (a - a.mean()) / sd]


def trailing(s: pd.Series, years: int) -> pd.Series:
    if s.empty:
        return s
    cutoff = s.index[-1] - pd.DateOffset(years=years)
    return s[s.index > cutoff]


def value_at_or_before(s: pd.Series, ts: pd.Timestamp) -> Optional[float]:
    sub = s[s.index <= ts]
    if sub.empty:
        return None
    return float(sub.iloc[-1])


def change_over(s: pd.Series, offset: pd.DateOffset, kind: str) -> Optional[float]:
    """Endring fra siste verdi mot siste observasjon på eller før (siste dato minus offset).
    kind: "abs" for differanse, "pct" for prosent. None hvis historikken ikke rekker."""
    if s.empty:
        return None
    ref_ts = s.index[-1] - offset
    if s.index[0] > ref_ts:
        return None
    ref = value_at_or_before(s, ref_ts)
    if ref is None:
        return None
    last = float(s.iloc[-1])
    if kind == "pct":
        if ref == 0:
            return None
        return (last / ref - 1.0) * 100.0
    return last - ref


def clean_series(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def level_for(percentile: Optional[float]) -> Optional[str]:
    """Nivåetikett fra persentilrang: very_low under 10, low under 25, normal til 75, high til 90, very_high over."""
    if percentile is None or (isinstance(percentile, float) and math.isnan(percentile)):
        return None
    if percentile < 10:
        return "very_low"
    if percentile < 25:
        return "low"
    if percentile < 75:
        return "normal"
    if percentile < 90:
        return "high"
    return "very_high"


def _num(x: Optional[float], dec: int = 4) -> Optional[float]:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), dec)


def chart_series(s: pd.Series, weeks: int) -> list[list]:
    """Ukentlig (siste observasjon per uke) for kompakthet, med eksakt siste punkt."""
    w = s.resample("W-FRI").last().dropna()
    w = w.iloc[-weeks:]
    w = w[w.index < s.index[-1]]
    pts = [[d.strftime("%Y-%m-%d"), _num(v)] for d, v in w.items()]
    pts.append([s.index[-1].strftime("%Y-%m-%d"), _num(s.iloc[-1])])
    return pts


# ---------------------------------------------------------------- indikatorer

def _base(spec: dict, ind_id: str, group: str) -> dict:
    return {
        "id": ind_id,
        "group": group,
        "name": spec.get("name", ind_id),
        "unit": spec.get("unit"),
        "decimals": spec.get("decimals", 2),
        "description": spec.get("description"),
        "meaning": spec.get("meaning"),
        "reading": spec.get("reading"),
        "frequency": spec.get("frequency"),
        "limitation": spec.get("limitation"),
    }


def missing_indicator(spec: dict, ind_id: str, group: str, error: str) -> dict:
    d = _base(spec, ind_id, group)
    d.update({"status": "missing", "error": error, "source": None, "proxy": False,
              "last_date": None, "last_value": None, "series": []})
    return d


def build_indicator(spec: dict, ind_id: str, group: str, series: pd.Series,
                    settings: dict, source: Optional[str] = None, proxy: bool = False,
                    today: Optional[pd.Timestamp] = None) -> dict:
    s = clean_series(series)
    if s.empty:
        raise SourceError("Kilden ga ingen gyldige observasjoner")
    today = today if today is not None else pd.Timestamp(datetime.now(timezone.utc).date())
    last_date = s.index[-1]
    last = float(s.iloc[-1])
    win = trailing(s, settings["history_years"])
    pct = None
    bands = None
    if len(win) >= settings["min_obs_percentile"]:
        pct = _num(percentile_rank(win.values, last), 1)
        q = win.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
        bands = {k: _num(v) for k, v in zip(["p10", "p25", "p50", "p75", "p90"], q.values)}
    kind = spec.get("change", "abs")
    d = _base(spec, ind_id, group)
    d.update({
        "status": "ok",
        "error": None,
        "source": source,
        "proxy": proxy,
        "last_date": last_date.strftime("%Y-%m-%d"),
        "last_value": _num(last),
        "stale": bool((today - last_date).days > settings["stale_days"]),
        "age_days": int((today - last_date).days),
        "percentile_10y": pct,
        "level": level_for(pct),
        "window_start": win.index[0].strftime("%Y-%m-%d"),
        "window_years": _num((last_date - win.index[0]).days / 365.25, 1),
        "n_obs": int(len(win)),
        "bands": bands,
        "change_1w": _num(change_over(s, pd.DateOffset(days=7), kind)),
        "change_kind": kind,
        "series": chart_series(s, settings["chart_weeks"]),
    })
    return d


def run_group(name: str, builder, log: logging.Logger) -> dict:
    """Kjør en gruppebygger. Uventede feil gir en gyldig, men tom fil med feilmelding."""
    try:
        payload = builder()
    except Exception as exc:  # noqa: BLE001  skriptet skal aldri velte hele kjøringen
        log.exception("Gruppen %s feilet totalt", name)
        payload = {"indicators": {}, "group_error": f"{type(exc).__name__}: {exc}"}
    payload["group"] = name
    payload["generated_at"] = now_iso()
    parts = [payload.get("indicators", {}), payload.get("rows", {}),
             (payload.get("sectors") or {}).get("rows", {})]
    payload["missing"] = sorted(k for part in parts for k, v in part.items() if v.get("status") != "ok")
    write_json(name, payload)
    log.info("Skrev %s.json (%d indikatorer, %d mangler)", name,
             len(payload.get("indicators", {})), len(payload["missing"]))
    return payload
