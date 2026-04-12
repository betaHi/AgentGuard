"""Statistical analysis utilities for trace metrics.

Provides basic statistical functions without external dependencies:
- Descriptive stats (mean, median, stdev, percentiles)
- Trend detection (moving average, direction)
- Outlier detection (IQR method)
- Correlation between metrics
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def mean(values: list[float]) -> float:
    """Calculate arithmetic mean."""
    return sum(values) / max(len(values), 1)


def median(values: list[float]) -> float:
    """Calculate median."""
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    if n % 2 == 0:
        return (s[n // 2 - 1] + s[n // 2]) / 2
    return s[n // 2]


def stdev(values: list[float]) -> float:
    """Calculate sample standard deviation."""
    if len(values) < 2:
        return 0
    m = mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def percentile(values: list[float], p: float) -> float:
    """Calculate percentile (0-100)."""
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def detect_outliers(values: list[float], factor: float = 1.5) -> list[tuple[int, float]]:
    """Detect outliers using the IQR method.
    
    Returns list of (index, value) tuples for outliers.
    """
    if len(values) < 4:
        return []
    
    q1 = percentile(values, 25)
    q3 = percentile(values, 75)
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    
    return [(i, v) for i, v in enumerate(values) if v < lower or v > upper]


def moving_average(values: list[float], window: int = 3) -> list[float]:
    """Calculate simple moving average."""
    if len(values) < window:
        return values[:]
    
    result = []
    for i in range(len(values) - window + 1):
        avg = sum(values[i:i + window]) / window
        result.append(avg)
    return result


def detect_trend(values: list[float]) -> str:
    """Detect trend direction: "increasing", "decreasing", "stable", "volatile"."""
    if len(values) < 3:
        return "insufficient_data"
    
    # Simple linear regression slope
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    if denominator == 0:
        return "stable"
    
    slope = numerator / denominator
    y_stdev = stdev(values)
    
    if y_stdev == 0:
        return "stable"
    
    # Normalize slope relative to data spread
    normalized_slope = slope / y_stdev
    
    if abs(normalized_slope) < 0.1:
        return "stable"
    elif normalized_slope > 0.3:
        return "increasing"
    elif normalized_slope < -0.3:
        return "decreasing"
    else:
        # Check volatility (coefficient of variation)
        cv = y_stdev / abs(y_mean) if y_mean != 0 else 0
        if cv > 0.3:
            return "volatile"
        return "stable"


@dataclass
class DescriptiveStats:
    """Descriptive statistics for a set of values."""
    count: int
    mean: float
    median: float
    stdev: float
    min: float
    max: float
    p25: float
    p75: float
    p90: float
    p99: float
    
    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean": round(self.mean, 2),
            "median": round(self.median, 2),
            "stdev": round(self.stdev, 2),
            "min": round(self.min, 2),
            "max": round(self.max, 2),
            "p25": round(self.p25, 2),
            "p75": round(self.p75, 2),
            "p90": round(self.p90, 2),
            "p99": round(self.p99, 2),
        }


def describe(values: list[float]) -> DescriptiveStats:
    """Calculate descriptive statistics."""
    if not values:
        return DescriptiveStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    
    return DescriptiveStats(
        count=len(values),
        mean=mean(values),
        median=median(values),
        stdev=stdev(values),
        min=min(values),
        max=max(values),
        p25=percentile(values, 25),
        p75=percentile(values, 75),
        p90=percentile(values, 90),
        p99=percentile(values, 99),
    )
