"""Tester for tilbaketesten av sektorstemning. Testvektorene er rene regneeksempler (ramper og konstante serier
med kjente svar), ikke markedsdata, og skrives aldri til data/ eller docs/ (kun til tmp)."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts import backtest_mood as bt, common
from scripts.common import SourceError


def ramp(n, start="2015-01-02", step=1.0, base=100.0):
    idx = pd.date_range(start, periods=n, freq="W-FRI")
    return pd.Series([base + i * step for i in range(n)], index=idx)


def test_point_in_time_percentile_uses_only_the_past():
    s = ramp(300)  # stigende: hver verdi er størst av alt som var kjent
    p = bt.point_in_time_percentile(s, False, 250)
    assert p.iloc[:249].isna().all()
    assert p.iloc[249] == pytest.approx(100.0) and p.iloc[299] == pytest.approx(100.0)
    inv = bt.point_in_time_percentile(s, True, 250)
    assert inv.iloc[249] == pytest.approx(0.0)


def test_point_in_time_percentile_known_rank():
    s = pd.Series([1.0, 3.0, 2.0], index=pd.date_range("2020-01-03", periods=3, freq="W-FRI"))
    p = bt.point_in_time_percentile(s, False, 1)
    assert list(p) == pytest.approx([100.0, 100.0, 200.0 / 3.0])  # 2 er blant tre kjente verdier, to er mindre eller lik


def test_block_bootstrap_constant_series_and_too_few():
    rng = np.random.default_rng(1)
    x = pd.Series([5.0] * 60)
    lo, hi = bt.block_bootstrap_ci(x, rng, block=13, draws=200)
    assert lo == pytest.approx(5.0) and hi == pytest.approx(5.0)
    few = pd.Series([1.0] * 5 + [np.nan] * 60)
    assert bt.block_bootstrap_ci(few, rng, block=13, draws=50) == (None, None)


def test_block_bootstrap_ignores_weeks_without_signal():
    rng = np.random.default_rng(1)
    x = pd.Series([2.0 if i % 2 == 0 else np.nan for i in range(80)])
    lo, hi = bt.block_bootstrap_ci(x, rng, block=13, draws=200)
    assert lo == pytest.approx(2.0) and hi == pytest.approx(2.0)


def test_build_without_files_raises_source_error(tmp_path):
    with pytest.raises(SourceError):
        bt.build(tmp_path)


def test_main_writes_valid_missing_file_without_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    bt.main()
    d = json.loads((tmp_path / "backtest.json").read_text(encoding="utf-8"))
    assert d["status"] == "missing" and d["error"] and d["group_error"]
    assert d["rules"] == [] and d["current"] is None and d["group"] == "backtest"


def _write(tmp_path, name, payload):
    (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_build_structure_on_arithmetic_inputs(tmp_path):
    """Regnemessige inndata (ramper og et fast mønster), kun for å teste at kjeden gir gyldig, ferdig JSON."""
    weeks = pd.date_range("2022-01-07", periods=156, freq="W-FRI")
    dates = [d.strftime("%Y-%m-%d") for d in weeks]
    rows = {}
    for k in range(10):
        mood = [[d, float((i * 7 + k * 13) % 100)] for i, d in enumerate(dates)]
        px = [[d, round(100.0 * (1.001 + 0.0001 * k) ** i, 2)] for i, d in enumerate(dates)]
        rows[f"s{k}"] = {"id": f"s{k}", "name": f"Sektor {k}", "symbol": f"S{k}", "status": "ok",
                         "history": {"mood": mood, "price": px}}
    rows["bad"] = {"id": "bad", "name": "Uten historikk", "symbol": "BAD", "status": "missing", "history": None}
    _write(tmp_path, "mood", {"rows": rows})

    def ind(series):
        return {"series": [[d.strftime("%Y-%m-%d"), float(v)] for d, v in series.items()]}
    long = ramp(300, start="2020-01-03")
    _write(tmp_path, "volatility", {"indicators": {"vix": ind(long), "vix_vix3m": ind(long)}})
    _write(tmp_path, "macro", {"indicators": {"usd": ind(long), "hy_oas": ind(long.iloc[-100:]), "ig_oas": ind(long.iloc[-100:])}})
    _write(tmp_path, "equities", {"indicators": {"spx_dist200": ind(long)}})

    out = bt.build(tmp_path)
    assert out["status"] == "ok" and out["sample"]["n_sectors"] == 10 and out["sample"]["n_weeks"] == 156
    assert [r["id"] for r in out["rules"]] == list("ABCDEF")
    for r in out["rules"]:
        assert r["status"] in ("ok", "too_few")
        if r["status"] == "ok":
            assert r["boot_lo"] <= r["mean_rel"] <= r["boot_hi"] or r["n_weeks"] < 30
    assert set(out["current"]["rules"]) == set("ABCDEF")
    assert {x["regime"] for x in out["by_regime"]} == {"calm", "elevated", "stress"}
    json.dumps(out, allow_nan=False)  # ingen NaN eller uendelig
