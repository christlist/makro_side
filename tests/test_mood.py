"""Tester for stemningsindeksen. Testvektorene er rene regneeksempler (rampeserier med kjente svar),
ikke markedsdata, og skrives aldri til data/ eller docs/."""
import math

import pandas as pd
import pytest

from scripts import common, fetch_mood as fm
from scripts.common import load_config

BANDS = {"extreme_fear_below": 25, "fear_below": 45, "neutral_below": 55, "greed_below": 75}


def ramp(n, start="2015-01-05", step=1.0, base=100.0, end=None):
    idx = pd.bdate_range(end=end, periods=n) if end is not None else pd.bdate_range(start, periods=n)
    return pd.Series([base + i * step for i in range(n)], index=idx)


def test_pct_at_and_score_invert():
    s = ramp(300)  # stigende serie: siste verdi er størst
    asof = s.index[-1]
    p = fm.pct_at(s, asof, 10, 250)
    assert p == pytest.approx(100 * (299 + 300) / (2 * 300))
    assert fm.score_at(s, asof, False, 10, 250) == pytest.approx(p)
    assert fm.score_at(s, asof, True, 10, 250) == pytest.approx(100 - p)


def test_pct_at_requires_history_and_fresh_data():
    s = ramp(100)
    assert fm.pct_at(s, s.index[-1], 10, 250) is None  # for kort historikk
    s = ramp(300)
    assert fm.pct_at(s, s.index[-1] + pd.Timedelta(days=30), 10, 250) is None  # for gammel mot asof


def test_pct_at_ignores_future_values():
    s = ramp(300)
    asof = s.index[-50]
    assert fm.pct_at(s, asof, 10, 100) == pytest.approx(100 * (250 + 251) / (2 * 251))  # 251 verdier til og med asof


def test_mean_score_minimum_components():
    assert fm.mean_score([10.0, 30.0, None], 2) == pytest.approx(20.0)
    assert fm.mean_score([10.0, None, None], 2) is None


@pytest.mark.parametrize("score,label", [(0, "extreme_fear"), (24.9, "extreme_fear"), (25, "fear"), (44.9, "fear"),
                                         (45, "neutral"), (54.9, "neutral"), (55, "greed"), (74.9, "greed"),
                                         (75, "extreme_greed"), (100, "extreme_greed")])
def test_label_bands(score, label):
    assert fm.label_for(score, BANDS) == label
    assert fm.label_for(None, BANDS) is None


def test_summarize_missing_and_ok():
    rows = [{"status": "ok", "score": 80.0, "score_1w": 70.0}, {"status": "ok", "score": 60.0, "score_1w": 50.0},
            {"status": "missing", "score": None, "score_1w": None}]
    ok = fm.summarize(rows, BANDS, 2)
    assert ok["status"] == "ok" and ok["score"] == 70.0 and ok["label"] == "greed"
    assert ok["score_1w"] == 60.0 and ok["change_1w"] == 10.0 and ok["n_used"] == 2 and ok["n_total"] == 3
    miss = fm.summarize(rows, BANDS, 3)
    assert miss["status"] == "missing" and miss["score"] is None and "Data mangler" in miss["error"]


def test_sector_components_known_answers():
    close = ramp(400)
    spy = ramp(400, step=0.5)
    c = fm.sector_components(close, spy)
    assert set(c) == {"mom200", "ret1m", "rs3m", "vol", "dd"}
    # stigende serie ligger alltid på 52 ukers høy: avstand = 0
    assert c["dd"]["x"].iloc[-1] == pytest.approx(0.0)
    assert c["vol"]["invert"] is True
    # sektoren stiger raskere enn referansen: positiv relativ styrke
    assert c["rs3m"]["x"].iloc[-1] > 0
    assert fm.sector_components(close, None)["rs3m"]["x"] is None


def test_evaluate_marks_missing_and_stale():
    ref = pd.Timestamp("2026-10-08")
    comps = {"a": fm.comp("A", ramp(400, end=ref), False, "x", 1),
             "b": fm.comp("B", None, False, "x", 1, error="Kilden feilet"),
             "c": fm.comp("C", ramp(400, start="2020-01-01"), False, "x", 1)}
    rows = {r["id"]: r for r in fm.evaluate(comps, ref, 10, 250, 21, 10, ref)}
    assert rows["a"]["status"] == "ok" and rows["a"]["score"] is not None and rows["a"]["last_date"] is not None
    assert rows["b"]["status"] == "missing" and rows["b"]["error"] == "Kilden feilet" and rows["b"]["value"] is None
    assert rows["c"]["status"] == "missing" and "gamle" in rows["c"]["error"]


def test_full_pipeline_with_ramp_stubs(monkeypatch, tmp_path):
    """Hele flyten med stub-fetcher (rampeserier). Verifiserer struktur, ikke verdier."""
    def stub(cands, settings, label, errors):
        step = 0.1 if label.startswith("sector_") or label in ("spy", "spx", "bond") else 0.01
        return ramp(700, start="2023-06-01", step=step), f"stub {label}"
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    payload = common.run_group("mood", lambda: fm.build(stub), common.get_logger("t"))
    m = payload["market"]
    assert m["status"] == "ok" and 0 <= m["score"] <= 100 and m["n_total"] == 8
    assert all(math.isfinite(p[1]) for p in m["series"]) and len(m["series"]) > 10
    assert len(payload["rows"]) == 11 and all(r["status"] == "ok" for r in payload["rows"].values())
    assert all(len(r["components"]) == 5 for r in payload["rows"].values())
    assert (tmp_path / "mood.json").exists()


def test_all_sources_down(monkeypatch, tmp_path):
    def down(cands, settings, label, errors):
        errors[label] = "Testen simulerer at kilden er utilgjengelig"
        return None, None
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    payload = common.run_group("mood", lambda: fm.build(down), common.get_logger("t"))
    assert payload["market"]["status"] == "missing" and payload["market"]["score"] is None
    assert all(r["status"] == "missing" for r in payload["rows"].values())
    assert all(c["status"] == "missing" and c["error"] for c in payload["market"]["components"])
    assert payload["missing"]  # mangler listes i meta
