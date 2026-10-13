"""Parser for CFTC mot små strukturelle testvektorer (ikke markedsdata). Nettverket brukes ikke."""
import pandas as pd
import pytest

from scripts import sources
from scripts.common import SourceError


def rows(long_f="noncomm_positions_long_all", short_f="noncomm_positions_short_all"):
    return [{"report_date_as_yyyy_mm_dd": "2026-09-29T00:00:00.000", long_f: "300", short_f: "100", "open_interest_all": "1000"},
            {"report_date_as_yyyy_mm_dd": "2026-09-22T00:00:00.000", long_f: "100", short_f: "300", "open_interest_all": "500"}]


def test_cftc_net_percent_of_open_interest_legacy():
    s = sources.parse_cftc_rows(rows(), "legacy_noncomm")
    assert list(s.round(6)) == [-40.0, 20.0]  # sortert stigende på dato: (100-300)/500, (300-100)/1000
    assert str(s.index[0].date()) == "2026-09-22" and str(s.index[-1].date()) == "2026-09-29"


def test_cftc_tff_accepts_either_field_naming():
    for lf, sf in (("lev_money_positions_long_all", "lev_money_positions_short_all"), ("lev_money_positions_long", "lev_money_positions_short")):
        assert len(sources.parse_cftc_rows(rows(lf, sf), "tff_lev")) == 2


def test_cftc_bad_input_gives_clear_source_error():
    with pytest.raises(SourceError, match="ingen rader"):
        sources.parse_cftc_rows([], "legacy_noncomm")
    with pytest.raises(SourceError, match="fant ikke forventede felt"):
        sources.parse_cftc_rows([{"a": 1}], "legacy_noncomm")
    with pytest.raises(SourceError, match="Ukjent"):
        sources.parse_cftc_rows(rows(), "annet")
    zero_oi = rows()
    for r in zero_oi:
        r["open_interest_all"] = "0"
    with pytest.raises(SourceError, match="ingen gyldige"):
        sources.parse_cftc_rows(zero_oi, "legacy_noncomm")


def test_cftc_candidate_label_and_vix_contract_code_in_config():
    from scripts.common import load_config

    assert "6dca-aqww" in sources.candidate_label({"source": "cftc", "dataset": "6dca-aqww", "code": "13874A", "measure": "legacy_noncomm"})
    pos = load_config()["mood"]["positioning"]
    assert {k: v["candidates"][0]["code"] for k, v in pos.items()} == {"cftc_spec": "13874A", "cftc_vix": "1170E1"}
    assert all(v["in_index"] for v in pos.values())
