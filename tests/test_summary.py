"""Tester for den regelbaserte oppsummeringen. Testvektorene er strukturerte eksempler, ikke markedsdata."""
from scripts import build_summary as bs
from scripts.common import level_for


def ind(p, name="X", **kw):
    return {"status": "ok", "name": name, "percentile_10y": p, "last_value": 1.0, "decimals": 1, "unit": "u",
            "last_date": "2026-10-08", **kw}


def test_level_for_boundaries():
    assert [level_for(x) for x in (0, 9.9, 10, 24.9, 25, 74.9, 75, 89.9, 90, 100)] == [
        "very_low", "very_low", "low", "low", "normal", "normal", "high", "high", "very_high", "very_high"]
    assert level_for(None) is None


def test_unusual_picks_extremes_sorted_by_distance_from_middle():
    files = {"volatility": {"indicators": {"a": ind(95, "A"), "b": ind(50, "B")}},
             "macro": {"indicators": {"c": ind(3, "C"), "d": {"status": "missing", "name": "D"}}}}
    u = bs.unusual(files)
    assert [i["id"] for i in u] == ["c", "a"] and u[0]["direction"] == "low" and u[1]["direction"] == "high"
    text = bs.unusual_point(u)["text"]
    assert "uvanlig høyt: A (persentil 95)" in text and "uvanlig lavt: C (persentil 3)" in text


def test_unusual_point_when_none():
    assert "Ingen" in bs.unusual_point([])["text"]


def test_regime_point_ok_and_missing():
    ok = {"status": "ok", "state": "calm", "mean_stress": 46.4, "n_used": 6,
          "items": [{"light": "green"}] * 5 + [{"light": "yellow"}]}
    assert bs.regime_point(ok)["text"] == "Regimet er rolig. Snittet av stress-persentilene er 46 av 100, og 5 av 6 indikatorer er grønne."
    assert "kan ikke beregnes" in bs.regime_point({"status": "missing"})["text"]
    assert bs.regime_point(None) is None


def test_mood_point_divergence_and_missing():
    comps = [{"status": "ok", "label": "Høy", "score": 90}, {"status": "ok", "label": "Lav", "score": 10}]
    m = {"market": {"status": "ok", "score": 50, "label": "neutral", "change_1w": 5.0, "components": comps}}
    t = bs.mood_point(m)["text"]
    assert "nøytral (50 av 100, +5 poeng siste uke)" in t and "Høy peker mot grådighet, Lav mot frykt" in t
    assert "Data mangler" in bs.mood_point({"market": {"status": "missing"}})["text"]
    assert "Data mangler" in bs.mood_point(None)["text"]


def test_term_point_only_when_inverted():
    assert bs.term_point({"indicators": {"vix_vix3m": ind(50, inverted=True)}}) is not None
    assert bs.term_point({"indicators": {"vix_vix3m": ind(50, inverted=False)}}) is None
    assert bs.term_point(None) is None


def test_compute_with_all_missing_has_valid_structure():
    s = bs.compute({n: None for n in ("regime", "volatility", "macro", "equities", "mood")})
    assert s["health"]["n_total"] == 0 and s["health"]["latest_data_date"] is None
    assert [p["kind"] for p in s["points"]] == ["mood", "unusual"]  # regime/term/equities utelates uten data
