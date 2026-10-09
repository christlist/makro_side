"""Tester for nyhetsparsing og sentimentflyt uten nettverk. Strukturelle testvektorer, ikke markedsdata."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts import common, fetch_sentiment as fs
from scripts.common import SourceError

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def test_parse_new_schema():
    t, ts = fs.parse_news_item({"content": {"title": "  Tittel  A ", "pubDate": "2026-10-07T08:30:00Z"}})
    assert t == "Tittel A" and ts == datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc)


def test_parse_old_schema():
    t, ts = fs.parse_news_item({"title": "Tittel B", "providerPublishTime": 1790000000})
    assert t == "Tittel B" and ts == datetime.fromtimestamp(1790000000, tz=timezone.utc)


def test_parse_missing_fields():
    assert fs.parse_news_item({}) == (None, None)
    assert fs.parse_news_item({"content": {"title": "X"}})[1] is None


def test_select_titles_filters_by_age_and_drops_undated():
    items = [
        {"content": {"title": "Ny", "pubDate": (NOW - timedelta(days=2)).isoformat()}},
        {"content": {"title": "Gammel", "pubDate": (NOW - timedelta(days=9)).isoformat()}},
        {"content": {"title": "Uten dato"}},
        {},
    ]
    assert fs.select_titles(items, 7, NOW) == ["Ny"]
    assert fs.select_titles(None, 7, NOW) == []


def test_all_sources_down_gives_missing_rows_and_never_loads_model(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise SourceError("Testen simulerer at kilden er utilgjengelig")
    monkeypatch.setattr(fs, "yf_titles", boom)
    monkeypatch.setattr(fs, "gdelt_titles", boom)
    monkeypatch.setattr(fs, "load_finbert", lambda cfg: pytest.fail("Modellen skal ikke lastes uten titler"))
    monkeypatch.setattr(fs.time, "sleep", lambda s: None)
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    payload = common.run_group("sentiment", fs.build, common.get_logger("t"))
    assert payload["rows"] and all(r["status"] == "missing" and r["error"] for r in payload["rows"].values())
    assert sorted(payload["missing"]) == sorted(payload["rows"])  # mangler vises i missing-listen
    assert (tmp_path / "sentiment.json").exists()
