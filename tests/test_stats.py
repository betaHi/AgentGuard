"""Tests for statistical analysis."""

import pytest
import math
from agentguard.stats import (
    mean, median, stdev, percentile,
    detect_outliers, moving_average, detect_trend, describe,
)


class TestBasicStats:
    def test_mean(self):
        assert mean([1, 2, 3, 4, 5]) == 3

    def test_median_odd(self):
        assert median([1, 2, 3, 4, 5]) == 3

    def test_median_even(self):
        assert median([1, 2, 3, 4]) == 2.5

    def test_stdev(self):
        assert stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.138, abs=0.01)

    def test_percentile(self):
        vals = list(range(1, 101))
        assert percentile(vals, 50) == pytest.approx(50.5, abs=0.5)
        assert percentile(vals, 90) == pytest.approx(90, abs=1)


class TestOutliers:
    def test_detect_outliers(self):
        values = [1, 2, 3, 2, 3, 2, 100]  # 100 is an outlier
        outliers = detect_outliers(values)
        assert len(outliers) >= 1
        assert 100 in [v for _, v in outliers]

    def test_no_outliers(self):
        values = [1, 2, 3, 2, 3, 2, 3]
        outliers = detect_outliers(values)
        assert len(outliers) == 0


class TestMovingAverage:
    def test_basic(self):
        result = moving_average([1, 2, 3, 4, 5], window=3)
        assert len(result) == 3
        assert result[0] == 2  # (1+2+3)/3

    def test_short_input(self):
        result = moving_average([1, 2], window=3)
        assert result == [1, 2]


class TestTrend:
    def test_increasing(self):
        assert detect_trend([1, 2, 3, 4, 5, 6, 7, 8]) == "increasing"

    def test_decreasing(self):
        assert detect_trend([8, 7, 6, 5, 4, 3, 2, 1]) == "decreasing"

    def test_stable(self):
        assert detect_trend([5, 5, 5, 5, 5]) == "stable"

    def test_insufficient(self):
        assert detect_trend([1, 2]) == "insufficient_data"


class TestDescribe:
    def test_basic(self):
        stats = describe([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert stats.count == 10
        assert stats.mean == 5.5
        assert stats.median == 5.5
        assert stats.min == 1
        assert stats.max == 10

    def test_empty(self):
        stats = describe([])
        assert stats.count == 0
        assert stats.mean == 0

    def test_to_dict(self):
        stats = describe([1, 2, 3])
        d = stats.to_dict()
        assert "mean" in d
        assert "p90" in d
