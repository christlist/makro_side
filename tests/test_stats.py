"""Enhetstester for persentilrang, z-score og endringer mot små kjente testvektorer.
Vektorene er rene regneeksempler for funksjonene, ikke markedsdata, og skrives aldri til data/ eller docs/."""
import math

import pandas as pd
import pytest

from scripts.common import change_over, percentile_rank, trailing, zscores


def test_percentile_rank_middle():
    # strengt lavere: 2, lavere eller lik: 3 => (2+3)/(2*5) = 50
    assert percentile_rank([1, 2, 3, 4, 5], 3) == pytest.approx(50.0)


def test_percentile_rank_extremes():
    assert percentile_rank([1, 2, 3, 4, 5], 5) == pytest.approx(90.0)   # (4+5)/10
    assert percentile_rank([1, 2, 3, 4, 5], 1) == pytest.approx(10.0)   # (0+1)/10


def test_percentile_rank_outside_range():
    assert percentile_rank([1, 2, 3, 4, 5], 99) == pytest.approx(100.0)
    assert percentile_rank([1, 2, 3, 4, 5], -1) == pytest.approx(0.0)


def test_percentile_rank_ties():
    # [2,2,2,2]: strengt 0, lavere eller lik 4 => 50
    assert percentile_rank([2, 2, 2, 2], 2) == pytest.approx(50.0)


def test_percentile_rank_ignores_nan_and_handles_empty():
    assert percentile_rank([1, float("nan"), 3], 3) == pytest.approx(75.0)  # (1+2)/(2*2)
    assert math.isnan(percentile_rank([], 1))
    assert math.isnan(percentile_rank([float("nan")], 1))


def test_zscores_known():
    # snitt 3, utvalgs-sd = sqrt(2.5)
    z = zscores([1, 2, 3, 4, 5])
    sd = math.sqrt(2.5)
    assert z == pytest.approx([-2 / sd, -1 / sd, 0, 1 / sd, 2 / sd])
    assert sum(z) == pytest.approx(0.0)


def test_zscores_degenerate():
    assert all(math.isnan(x) for x in zscores([5, 5, 5]))
    assert all(math.isnan(x) for x in zscores([5]))
    assert zscores([]) == []


def _s(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_change_over_abs_and_pct():
    s = _s([10, 11, 12, 13, 14, 15, 16, 17, 18, 20])  # siste = 20 på dag 10
    # 7 dager før siste dato (2024-01-10) er 2024-01-03 => verdi 12
    assert change_over(s, pd.DateOffset(days=7), "abs") == pytest.approx(8.0)
    assert change_over(s, pd.DateOffset(days=7), "pct") == pytest.approx((20 / 12 - 1) * 100)


def test_change_over_insufficient_history_and_zero_ref():
    assert change_over(_s([1, 2, 3]), pd.DateOffset(days=7), "abs") is None
    assert change_over(_s([0, 1, 2, 3, 4, 5, 6, 7, 8]), pd.DateOffset(days=8), "pct") is None


def test_trailing_window():
    s = pd.Series(range(5), index=pd.to_datetime(["2014-01-01", "2016-01-01", "2020-01-01", "2024-01-01", "2026-01-01"]))
    assert list(trailing(s, 10).index.year) == [2020, 2024, 2026]
