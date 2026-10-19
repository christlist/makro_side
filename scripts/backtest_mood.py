"""Enkel tilbaketest av sektorstemning mot fremtidig relativ avkastning. Skriver data/backtest.json.

Bruker bare data som allerede ligger i data/*.json. Ingen konstruerte data: mangler grunnlaget, skrives status
"missing" med feilmelding, og siden viser «Data mangler».

Utfall: relativ 13 ukers avkastning mot likevektet sektorsnitt. Per uke brukes snittet av sektorene som oppfyller regelen.
Regimehistorikk lagres ikke i regime.json, så den rekonstrueres fra seriene i repoet: persentil mot alt som var kjent
på det tidspunktet (utvidende vindu), samme retning og snitt som regimet ellers, minst 4 av 6 indikatorer.
Robusthet: ikke overlappende vinduer (13 faser) og blokkbootstrap over kalenderen (13 ukers blokker, 90 % intervall).

Kjør: python -m scripts.backtest_mood
Merk: terskler (35 og 65) er valgt etter å ha sett dataene, så testen er in sample og gjelder bare tre år.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .common import SourceError, _num, get_logger, now_iso, read_json, write_json

log = get_logger("backtest_mood")

HORIZON = 13          # uker frem
FEAR_BELOW = 35       # sektorstemning under dette regnes som frykt
GREED_ABOVE = 65      # sektorstemning over dette regnes som grådighet
RISE_WEEKS = 4        # vindu for "stigende stemning"
MIN_SECTORS = 8
MIN_WEEKS = 60
REGIME_MIN_INDICATORS = 4
REGIME_ELEVATED_FROM = 55
REGIME_STRESS_FROM = 75
BOOT_BLOCK = 13
BOOT_DRAWS = 5000
SEED = 42
MIN_RULE_WEEKS = 5
STATE_KEY = {"rolig": "calm", "forhoyet": "elevated", "stress": "stress"}


def indicator_series(data: dict, file: str, ind_id: str) -> pd.Series:
    try:
        raw = data[file]["indicators"][ind_id]["series"]
    except (KeyError, TypeError):
        raise SourceError(f"Serien {file}.{ind_id} mangler")
    if not raw:
        raise SourceError(f"Serien {file}.{ind_id} er tom")
    s = pd.Series({x[0]: x[1] for x in raw}, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def point_in_time_percentile(s: pd.Series, invert: bool, min_obs: int) -> pd.Series:
    """Persentilrang (andel verdier mindre eller lik, 0 til 100) mot alt som var kjent til og med hvert tidspunkt."""
    v = s.values
    out = []
    for i in range(len(v)):
        if i + 1 < min_obs:
            out.append(np.nan)
            continue
        p = (v[: i + 1] <= v[i]).mean() * 100.0
        out.append(100.0 - p if invert else p)
    return pd.Series(out, index=s.index)


def load_mood_and_price(mood_json: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rows = {k: r for k, r in (mood_json.get("rows") or {}).items()
            if r.get("status") == "ok" and (r.get("history") or {}).get("price")
            and len(r["history"]["price"]) == len(r["history"]["mood"])}
    if len(rows) < MIN_SECTORS:
        raise SourceError(f"For få sektorer med historikk ({len(rows)} av minst {MIN_SECTORS})")
    mood = pd.DataFrame({k: pd.Series({x[0]: x[1] for x in r["history"]["mood"]}, dtype=float) for k, r in rows.items()}).sort_index()
    price = pd.DataFrame({k: pd.Series({x[0]: x[1] for x in r["history"]["price"]}, dtype=float) for k, r in rows.items()}).sort_index()
    mood.index = pd.to_datetime(mood.index)
    price.index = pd.to_datetime(price.index)
    if len(mood) < MIN_WEEKS:
        raise SourceError(f"For kort historikk ({len(mood)} uker, minst {MIN_WEEKS})")
    meta = {k: {"name": r.get("name"), "symbol": r.get("symbol")} for k, r in rows.items()}
    return mood, price, meta


def reconstruct_regime(data: dict, dates: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    # (serie, invert, minste antall observasjoner). HY og IG har kort historikk i repoet (rundt 3 år).
    spec = {
        "vix": ("volatility", "vix", False, 104),
        "vix_vix3m": ("volatility", "vix_vix3m", False, 104),
        "hy_oas": ("macro", "hy_oas", False, 26),
        "ig_oas": ("macro", "ig_oas", False, 26),
        "usd": ("macro", "usd", False, 104),
        "spx_dist200": ("equities", "spx_dist200", True, 104),
    }
    cols = {}
    for key, (file, ind_id, invert, min_obs) in spec.items():
        try:
            cols[key] = point_in_time_percentile(indicator_series(data, file, ind_id), invert, min_obs)
        except SourceError as exc:
            log.warning("Regimeinput utelatt: %s", exc)
    if len(cols) < REGIME_MIN_INDICATORS:
        raise SourceError(f"Regimet kan ikke rekonstrueres: bare {len(cols)} av {len(spec)} serier finnes")
    stress = pd.DataFrame(cols)
    stress = stress.reindex(stress.index.union(dates)).sort_index().ffill(limit=2).reindex(dates)
    n = stress.notna().sum(axis=1)
    mean = stress.mean(axis=1).where(n >= REGIME_MIN_INDICATORS)
    cls = pd.cut(mean, [-1, REGIME_ELEVATED_FROM, REGIME_STRESS_FROM, 101], labels=["rolig", "forhoyet", "stress"], right=False)
    return mean, cls


def block_bootstrap_ci(x: pd.Series, rng: np.random.Generator, block: int = BOOT_BLOCK, draws: int = BOOT_DRAWS) -> tuple[Optional[float], Optional[float]]:
    """90 % intervall for snittet ved blokkbootstrap over kalenderen. Uker uten signal (NaN) beholdes i serien,
    slik at blokkene bevarer tidsrekkefølgen, og snittet tas over ukene med signal i hver trekning."""
    v = x.values
    n = len(v)
    if np.isfinite(v).sum() < 10 or n < block:
        return None, None
    nb = int(np.ceil(n / block))
    res = []
    for _ in range(draws):
        starts = rng.integers(0, n - block + 1, nb)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        sample = v[idx]
        res.append(np.nanmean(sample) if np.isfinite(sample).any() else np.nan)
    lo, hi = np.nanpercentile(res, [5, 95])
    return float(lo), float(hi)


def build(data_dir: Optional[Path] = None) -> dict:
    data = {name: read_json(name, data_dir) for name in ("mood", "volatility", "macro", "equities")}
    for name, d in data.items():
        if d is None:
            raise SourceError(f"Filen {name}.json mangler eller er ugyldig")
    mood, price, names = load_mood_and_price(data["mood"])
    reg_mean, reg_cls = reconstruct_regime(data, mood.index)

    fwd = price.shift(-HORIZON) / price - 1.0
    rel = fwd.sub(fwd.mean(axis=1), axis=0)
    valid_weeks = rel.dropna(how="all").index
    d_mood = mood - mood.shift(RISE_WEEKS)

    not_stress = ((reg_cls != "stress") & reg_mean.notna()).astype(bool)
    in_stress = (reg_cls == "stress").astype(bool)
    fear = mood < FEAR_BELOW
    rising = d_mood > 0
    rules = [
        ("A", f"Stemning under {FEAR_BELOW} (frykt)", "Sektoren har lav stemning.", fear),
        ("B", "A og regimet ikke i stress", "Frykt i sektoren når samlet regime ikke er stress.", fear.mul(not_stress, axis=0).astype(bool)),
        ("C", f"A og stigende stemning ({RISE_WEEKS} uker)", "Frykt i sektoren, men stemningen har steget siste uker.", fear & rising),
        ("D", "A, B og C", "Alle tre vilkårene samtidig.", (fear & rising).mul(not_stress, axis=0).astype(bool)),
        ("E", "A i stressregime", "Frykt i sektoren når samlet regime er stress.", fear.mul(in_stress, axis=0).astype(bool)),
        ("F", f"Stemning over {GREED_ABOVE} (grådighet)", "Sektoren har høy stemning.", mood > GREED_ABOVE),
    ]

    rng = np.random.default_rng(SEED)
    out_rules, current = [], {}
    last = mood.index[-1]
    for rid, label, desc, mask in rules:
        weekly = rel.where(mask).mean(axis=1)
        weekly = weekly[weekly.index.isin(valid_weeks)] * 100.0
        sel = weekly.dropna()
        phases, sizes = [], []
        for off in range(HORIZON):
            p = weekly.iloc[off::HORIZON].dropna()
            if len(p) >= 3:
                phases.append(float(p.mean()))
                sizes.append(len(p))
        entry = {"id": rid, "label": label, "description": desc, "n_weeks": int(len(sel))}
        if len(sel) < MIN_RULE_WEEKS or not phases:
            entry.update({"status": "too_few", "mean_rel": None, "phase_mean": None, "phase_min": None, "phase_max": None,
                          "phase_n": None, "boot_lo": None, "boot_hi": None, "hit_rate": None})
        else:
            lo, hi = block_bootstrap_ci(weekly, rng)
            entry.update({"status": "ok", "mean_rel": _num(sel.mean(), 2), "phase_mean": _num(np.mean(phases), 2),
                          "phase_min": _num(min(phases), 2), "phase_max": _num(max(phases), 2),
                          "phase_n": int(round(float(np.mean(sizes)))), "boot_lo": _num(lo, 2), "boot_hi": _num(hi, 2),
                          "hit_rate": _num((sel > 0).mean() * 100.0, 1)})
        out_rules.append(entry)
        now = mask.loc[last]
        current[rid] = [{"id": k, "name": names[k]["name"], "symbol": names[k]["symbol"], "score": _num(mood.loc[last, k], 1)}
                        for k in mood.columns[now.values.astype(bool)]]

    a_weekly = rel.where(rules[0][3]).mean(axis=1) * 100.0
    by_regime = []
    for k in ("rolig", "forhoyet", "stress"):
        s = a_weekly[(reg_cls == k) & a_weekly.notna() & a_weekly.index.isin(valid_weeks)]
        by_regime.append({"regime": STATE_KEY[k], "n_weeks": int(len(s)), "mean_rel": _num(s.mean(), 2) if len(s) else None})

    cls_last = reg_cls.iloc[-1]
    return {
        "status": "ok",
        "error": None,
        "params": {"horizon_weeks": HORIZON, "fear_below": FEAR_BELOW, "greed_above": GREED_ABOVE, "rise_weeks": RISE_WEEKS,
                   "bootstrap_block_weeks": BOOT_BLOCK, "bootstrap_draws": BOOT_DRAWS, "regime_elevated_from": REGIME_ELEVATED_FROM,
                   "regime_stress_from": REGIME_STRESS_FROM},
        "sample": {"n_sectors": int(mood.shape[1]), "n_weeks": int(mood.shape[0]), "start": mood.index[0].strftime("%Y-%m-%d"),
                   "end": last.strftime("%Y-%m-%d"),
                   "regime_weeks": {STATE_KEY[k]: int((reg_cls == k).sum()) for k in ("rolig", "forhoyet", "stress")}},
        "rules": out_rules,
        "by_regime": by_regime,
        "current": {"ref_date": last.strftime("%Y-%m-%d"),
                    "regime": STATE_KEY.get(str(cls_last)) if pd.notna(cls_last) else None,
                    "regime_mean": _num(reg_mean.iloc[-1], 1), "rules": current},
    }


def main() -> None:
    try:
        payload = build()
    except Exception as exc:  # noqa: BLE001  skriptet skal aldri velte hele kjøringen
        log.exception("Tilbaketesten feilet")
        payload = {"status": "missing", "error": f"{type(exc).__name__}: {exc}", "params": None, "sample": None,
                   "rules": [], "by_regime": [], "current": None, "group_error": f"{type(exc).__name__}: {exc}"}
    payload["group"] = "backtest"
    payload["generated_at"] = now_iso()
    write_json("backtest", payload)
    log.info("Skrev backtest.json (status %s)", payload["status"])


if __name__ == "__main__":
    main()
