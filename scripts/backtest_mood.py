"""Enkel tilbaketest av sektorstemning mot fremtidig relativ avkastning.

Bruker bare data som allerede ligger i repoet (data/*.json). Ingen konstruerte data.

Utfall: relativ 13 ukers avkastning mot likevektet sektorsnitt. Per uke brukes snittet av sektorene som oppfyller regelen.
Regimehistorikk lagres ikke i regime.json, så den rekonstrueres fra seriene i repoet: persentil mot alt som var kjent
på det tidspunktet (utvidende vindu), samme retning og snitt som i config.yaml, minst 4 av 6 indikatorer.
Robusthet: ikke overlappende vinduer (13 faser) og blokkbootstrap over kalenderen (13 ukers blokker, 90 % intervall).

Kjør: python scripts/backtest_mood.py
Merk: terskler (35 og 65) er valgt etter å ha sett dataene, så testen er in sample og gjelder bare tre år.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
HORIZON = 13          # uker frem
FEAR_BELOW = 35       # sektorstemning under dette regnes som frykt
GREED_ABOVE = 65      # sektorstemning over dette regnes som grådighet
RISE_WEEKS = 4        # vindu for "stigende stemning"
REGIME_MIN_INDICATORS = 4
REGIME_STRESS_FROM = 75
REGIME_ELEVATED_FROM = 55
BOOT_BLOCK = 13
BOOT_DRAWS = 5000
SEED = 42


def load(name: str) -> dict:
    path = DATA / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Data mangler: {path}. Kjør python -m scripts.run_all først.")
    return json.loads(path.read_text(encoding="utf-8"))


def indicator_series(file: str, ind_id: str) -> pd.Series:
    d = load(file)["indicators"][ind_id]["series"]
    s = pd.Series({x[0]: x[1] for x in d})
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def point_in_time_percentile(s: pd.Series, invert: bool, min_obs: int) -> pd.Series:
    v = s.values
    out = []
    for i in range(len(v)):
        if i + 1 < min_obs:
            out.append(np.nan)
            continue
        p = (v[: i + 1] <= v[i]).mean() * 100.0
        out.append(100.0 - p if invert else p)
    return pd.Series(out, index=s.index)


def load_mood_and_price() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = load("mood")["rows"]
    rows = {k: r for k, r in rows.items() if r.get("history") and r["history"].get("price")}
    mood = pd.DataFrame({k: pd.Series({x[0]: x[1] for x in r["history"]["mood"]}) for k, r in rows.items()}).sort_index()
    price = pd.DataFrame({k: pd.Series({x[0]: x[1] for x in r["history"]["price"]}) for k, r in rows.items()}).sort_index()
    mood.index = pd.to_datetime(mood.index)
    price.index = pd.to_datetime(price.index)
    return mood, price


def reconstruct_regime(dates: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    # (serie, invert, minste antall observasjoner). HY og IG har kort historikk i repoet (rundt 3 år).
    inputs = {
        "vix": (indicator_series("volatility", "vix"), False, 104),
        "vix_vix3m": (indicator_series("volatility", "vix_vix3m"), False, 104),
        "hy_oas": (indicator_series("macro", "hy_oas"), False, 26),
        "ig_oas": (indicator_series("macro", "ig_oas"), False, 26),
        "usd": (indicator_series("macro", "usd"), False, 104),
        "spx_dist200": (indicator_series("equities", "spx_dist200"), True, 104),
    }
    stress = pd.DataFrame({k: point_in_time_percentile(*v) for k, v in inputs.items()})
    stress = stress.reindex(stress.index.union(dates)).sort_index().ffill(limit=2).reindex(dates)
    n = stress.notna().sum(axis=1)
    mean = stress.mean(axis=1).where(n >= REGIME_MIN_INDICATORS)
    cls = pd.cut(mean, [-1, REGIME_ELEVATED_FROM, REGIME_STRESS_FROM, 101], labels=["rolig", "forhoyet", "stress"], right=False)
    return mean, cls


def block_bootstrap_ci(x: pd.Series, rng: np.random.Generator) -> tuple[float, float]:
    v = x.values
    n = len(v)
    if np.isfinite(v).sum() < 10:
        return float("nan"), float("nan")
    nb = int(np.ceil(n / BOOT_BLOCK))
    res = []
    for _ in range(BOOT_DRAWS):
        starts = rng.integers(0, n - BOOT_BLOCK + 1, nb)
        idx = np.concatenate([np.arange(s, s + BOOT_BLOCK) for s in starts])[:n]
        sample = v[idx]
        res.append(np.nanmean(sample) if np.isfinite(sample).any() else np.nan)
    lo, hi = np.nanpercentile(res, [5, 95])
    return float(lo), float(hi)


def main() -> None:
    mood, price = load_mood_and_price()
    reg_mean, reg_cls = reconstruct_regime(mood.index)

    fwd = price.shift(-HORIZON) / price - 1.0
    rel = fwd.sub(fwd.mean(axis=1), axis=0)
    valid_weeks = rel.dropna(how="all").index
    d_mood = mood - mood.shift(RISE_WEEKS)

    not_stress = ((reg_cls != "stress") & reg_mean.notna()).astype(bool)
    in_stress = (reg_cls == "stress").astype(bool)
    fear = mood < FEAR_BELOW
    rising = d_mood > 0
    rules = {
        f"A stemning under {FEAR_BELOW}": fear,
        "B A og regime ikke stress": fear.mul(not_stress, axis=0).astype(bool),
        f"C A og stigende stemning ({RISE_WEEKS}u)": fear & rising,
        "D A, B og C": (fear & rising).mul(not_stress, axis=0).astype(bool),
        "E A i stressregime": fear.mul(in_stress, axis=0).astype(bool),
        f"F stemning over {GREED_ABOVE}": mood > GREED_ABOVE,
    }

    print(f"Sektorer: {mood.shape[1]}, uker: {mood.shape[0]} ({mood.index[0].date()} til {mood.index[-1].date()})")
    print(f"Regime rekonstruert: {reg_cls.value_counts().to_dict()}")
    print(f"Utfall: relativ {HORIZON} ukers avkastning mot likevektet sektorsnitt, prosentpoeng\n")
    print(f"{'Regel':32s} {'uker':>5s} {'snitt':>7s} {'faser (snitt, min, maks, n)':>34s} {'bootstrap 90 %':>18s} {'treff':>6s}")

    rng = np.random.default_rng(SEED)
    for name, mask in rules.items():
        weekly = rel.where(mask).mean(axis=1)
        weekly = weekly[weekly.index.isin(valid_weeks)] * 100.0
        sel = weekly.dropna()
        phases, sizes = [], []
        for off in range(HORIZON):
            p = weekly.iloc[off::HORIZON].dropna()
            if len(p) >= 3:
                phases.append(p.mean())
                sizes.append(len(p))
        if len(sel) < 5 or not phases:
            print(f"{name:32s} {len(sel):5d}  for få uker")
            continue
        lo, hi = block_bootstrap_ci(weekly, rng)
        print(f"{name:32s} {len(sel):5d} {sel.mean():7.2f} "
              f"{np.mean(phases):8.2f} {min(phases):7.2f} {max(phases):7.2f} {int(np.mean(sizes)):4d}  "
              f"[{lo:6.2f}, {hi:6.2f}] {(sel > 0).mean() * 100:5.1f}%")

    print("\nA per regime (uker, snitt):")
    a_weekly = rel.where(rules[f"A stemning under {FEAR_BELOW}"]).mean(axis=1) * 100.0
    for k in ["rolig", "forhoyet", "stress"]:
        s = a_weekly[(reg_cls == k) & a_weekly.notna() & a_weekly.index.isin(valid_weeks)]
        print(f"  {k:9s} {len(s):4d} {s.mean():7.2f}" if len(s) else f"  {k:9s} {0:4d}   mangler")


if __name__ == "__main__":
    main()
