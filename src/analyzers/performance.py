"""Detect hashrate degradation correlated with thermal stress."""

from __future__ import annotations

import pandas as pd
from scipy import stats

from .base import (
    CORRELATION_CRITICAL,
    CORRELATION_HIGH,
    CORRELATION_THRESHOLD,
    HASHRATE_DEVIATION_PCT,
    HASHRATE_DEVIATION_SEVERE,
    P_VALUE_THRESHOLD,
    SUSTAINED_MINUTES,
    Insight,
    infer_freq,
)


def analyze_performance(df: pd.DataFrame) -> list[Insight]:
    """Per-miner: Pearson correlation (hashrate vs chip temp) and
    sustained deviation from baseline hashrate."""
    insights: list[Insight] = []

    # for simplicity it's grouping by everytime -> could cache/ pre bake.
    for miner_id, grp in df.groupby("miner_id"):
        grp = grp.set_index("timestamp").sort_index()

        # --- correlation: hashrate vs chip temp ---
        valid = grp[["hashrate_ths", "chip_temp_c"]].dropna()
        if len(valid) >= 5 and valid["hashrate_ths"].std() > 0 and valid["chip_temp_c"].std() > 0:
            r, p = stats.pearsonr(valid["hashrate_ths"], valid["chip_temp_c"])
            if r < CORRELATION_THRESHOLD and p < P_VALUE_THRESHOLD:
                severity = (
                    "critical"
                    if r < CORRELATION_CRITICAL
                    else "high"
                    if r < CORRELATION_HIGH
                    else "warning"
                )
                insights.append(
                    {
                        "miner_id": miner_id,
                        "type": "performance_degradation",
                        "severity": severity,
                        "detail": (
                            f"Hashrate negatively correlated with chip temperature "
                            f"(r={r:.2f}, p={p:.4f}). Performance drops as chip heats up."
                        ),
                        "metric": round(r, 4),
                        "action": (
                            "Inspect cooling path for this miner; consider throttle "
                            "adjustment or coolant flow increase."
                        ),
                    }
                )

        # --- sustained deviation from baseline ---
        # Median baseline: robust to intermittent crashes dragging the average down
        overall_baseline = grp["hashrate_ths"].median()
        if overall_baseline <= 0 or pd.isna(overall_baseline):
            continue

        freq = infer_freq(grp)
        if freq is None:
            continue
        window_size = max(1, int(pd.Timedelta(minutes=SUSTAINED_MINUTES) / freq))

        rolling_mean = (
            grp["hashrate_ths"]
            .rolling(
                window=window_size,
                min_periods=window_size,
            )
            .mean()
        )
        # % percentage deviation
        deviation = (rolling_mean - overall_baseline) / overall_baseline

        below = deviation < -HASHRATE_DEVIATION_PCT
        if below.any():
            worst_dev = deviation[below].min()
            # got worst at this timestamp
            worst_ts = deviation[below].idxmin()
            insights.append(
                {
                    "miner_id": miner_id,
                    "type": "sustained_underperformance",
                    "severity": "high" if worst_dev < -HASHRATE_DEVIATION_SEVERE else "warning",
                    "detail": (
                        f"Hashrate deviated {worst_dev:.1%} below baseline "
                        f"for >{SUSTAINED_MINUTES} min (worst at {worst_ts})."
                    ),
                    "metric": round(float(worst_dev), 4),
                    "action": (
                        "Check for firmware issues, degraded ASIC boards, or "
                        "insufficient coolant flow."
                    ),
                }
            )

    return insights
