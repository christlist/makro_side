"""Pipeline-tester for manglende data: ingen kilder tilgjengelig skal gi status "missing",
gyldig JSON og ingen verdier, aldri et unntak."""
import json

import pandas as pd
import pytest

from scripts import build_regime, common, fetch_equities, fetch_macro, fetch_volatility
from scripts.common import SourceError, load_config


@pytest.fixture
def offline(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise SourceError("Testen simulerer at kilden er utilgjengelig")
    monkeypatch.setattr("scripts.sources.fetch_candidate", boom)
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    monkeypatch.setattr("scripts.fetch_equities.time.sleep", lambda s: None)
    return tmp_path


def test_all_sources_down_volatility(offline):
    payload = common.run_group("volatility", fetch_volatility.build, common.get_logger("t"))
    assert set(payload["missing"]) == set(payload["indicators"])
    for ind in payload["indicators"].values():
        assert ind["status"] == "missing"
        assert ind["last_value"] is None and ind["series"] == []
        assert ind["error"]
    on_disk = json.loads((offline / "volatility.json").read_text(encoding="utf-8"))
    assert on_disk["missing"]


def test_all_sources_down_macro_and_equities(offline):
    macro = common.run_group("macro", fetch_macro.build, common.get_logger("t"))
    assert all(i["status"] == "missing" for i in macro["indicators"].values())
    eq = common.run_group("equities", fetch_equities.build, common.get_logger("t"))
    assert all(i["status"] == "missing" for i in eq["indicators"].values())
    assert eq["sectors"]["breadth"] is None
    assert all(r["status"] == "missing" for r in eq["sectors"]["rows"].values())


def test_group_builder_crash_still_writes_valid_file(offline):
    def crash():
        raise RuntimeError("uventet")
    payload = common.run_group("volatility", crash, common.get_logger("t"))
    assert payload["group_error"].startswith("RuntimeError")
    assert (offline / "volatility.json").exists()


def test_regime_is_missing_without_inputs():
    cfg = load_config()
    res = build_regime.compute(cfg, {n: None for n in ("volatility", "macro", "equities")})
    assert res["status"] == "missing" and res["state"] is None and res["mean_stress"] is None
    assert "Data mangler" in res["error"]
    assert all(i["status"] == "missing" for i in res["items"])


def _ind(pct, last_date="2026-10-02"):
    return {"status": "ok", "last_value": 1.0, "decimals": 1, "unit": "x", "last_date": last_date,
            "percentile_10y": pct, "change_1w": 0.1, "change_kind": "abs", "window_years": 10}


def test_regime_rule_thresholds_and_direction():
    """Testvektorer for regelen (ikke markedsdata): stress-persentil snur retning for lower_is_stress."""
    cfg = load_config()
    today = pd.Timestamp("2026-10-08")
    vals = {"vix": 90, "vix_vix3m": 90, "hy_oas": 90, "ig_oas": 90, "usd": 90, "spx_dist200": 10}
    files = {"volatility": {"indicators": {k: _ind(vals[k]) for k in ("vix", "vix_vix3m")}},
             "macro": {"indicators": {k: _ind(vals[k]) for k in ("hy_oas", "ig_oas", "usd")}},
             "equities": {"indicators": {"spx_dist200": _ind(vals["spx_dist200"])}}}
    res = build_regime.compute(cfg, files, today)
    assert res["status"] == "ok" and res["state"] == "stress" and res["mean_stress"] == 90.0
    assert {i["id"]: i["light"] for i in res["items"]}["spx_dist200"] == "red"  # 100 - 10 = 90


def test_regime_drops_old_data_and_requires_minimum():
    cfg = load_config()
    today = pd.Timestamp("2026-10-08")
    old = {"indicators": {k: _ind(50, "2026-01-01") for k in ("vix", "vix_vix3m", "hy_oas", "ig_oas", "usd", "spx_dist200")}}
    files = {"volatility": old, "macro": old, "equities": old}
    res = build_regime.compute(cfg, files, today)
    assert res["status"] == "missing" and res["n_used"] == 0
    assert "gamle" in res["items"][0]["reason"]
