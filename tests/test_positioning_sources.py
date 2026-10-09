"""Parsere for CFTC og NAAIM mot små strukturelle testvektorer (ikke markedsdata). Nettverket brukes ikke."""
import io

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


def test_naaim_frame_parsing_and_errors():
    df = pd.DataFrame({"Date": ["2026-10-01", "2026-09-24"], "NAAIM Number": [60.0, "70"], "Mean/Average": [1, 2]})
    s = sources.parse_naaim_frame(df)
    assert list(s) == [70.0, 60.0] and str(s.index[0].date()) == "2026-09-24"
    with pytest.raises(SourceError, match="fant ikke"):
        sources.parse_naaim_frame(pd.DataFrame({"x": [1]}))
    with pytest.raises(SourceError, match="ingen gyldige"):
        sources.parse_naaim_frame(pd.DataFrame({"Date": ["x"], "NAAIM Number": [None]}))


def test_naaim_excel_roundtrip_with_openpyxl():
    buf = io.BytesIO()
    pd.DataFrame({"Date": ["2026-10-01"], "NAAIM Number": [55.5]}).to_excel(buf, index=False)
    s = sources.parse_naaim_frame(pd.read_excel(io.BytesIO(buf.getvalue())))
    assert float(s.iloc[0]) == 55.5


def test_find_naaim_xlsx_url():
    html = '<a href="/a.pdf">x</a><a href="/wp-content/uploads/USE_Data-since-Inception_2026.xlsx">d</a><a href="/other.xlsx">y</a>'
    assert sources.find_naaim_xlsx_url(html, "https://naaim.org/programs/naaim-exposure-index/") == \
        "https://naaim.org/wp-content/uploads/USE_Data-since-Inception_2026.xlsx"
    with pytest.raises(SourceError, match="ingen Excel-lenke"):
        sources.find_naaim_xlsx_url("<html></html>", "https://x")


def test_candidate_labels():
    assert sources.candidate_label({"source": "naaim", "page": "p"}) == "NAAIM Exposure Index"
    assert "6dca-aqww" in sources.candidate_label({"source": "cftc", "dataset": "6dca-aqww", "code": "13874A", "measure": "legacy_noncomm"})
