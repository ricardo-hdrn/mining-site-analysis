"""Enrich insights with business impact estimates.

Runs as a separate pass after detection — keeps economics logic
decoupled from signal processing. Each analyzer stays focused on
detection; this module translates findings into revenue impact.
"""

from __future__ import annotations

import pandas as pd

from .base import CHIP_TEMP_CRITICAL, HASH_PRICE_USD_PER_TH_DAY, Insight

# Maps insight types to impact estimation functions.
# Types not listed here get no business_impact field (risk signals
# like pressure anomalies where hashrate impact isn't directly measurable).

THROTTLE_SLOPE_THS_PER_C = 5.0  # approx hashrate loss per °C above critical


def _impact_performance_degradation(insight: Insight, df: pd.DataFrame) -> str | None:
    """Thermal correlation — estimate avg hashrate lost to throttling."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    hr = miner["hashrate_ths"].dropna()
    if hr.empty:
        return None
    loss_ths = hr.max() - hr.mean()
    daily_loss = loss_ths * HASH_PRICE_USD_PER_TH_DAY
    return (
        f"Est. avg {loss_ths:.1f} TH/s lost to thermal throttling "
        f"(~${daily_loss:.2f}/day at ${HASH_PRICE_USD_PER_TH_DAY}/TH/day)."
    )


def _impact_sustained_underperformance(insight: Insight, df: pd.DataFrame) -> str | None:
    """Sustained deviation — estimate hashrate loss from metric (deviation fraction)."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    baseline = miner["hashrate_ths"].median()
    if pd.isna(baseline) or baseline <= 0:
        return None
    deviation = abs(insight.get("metric", 0))
    loss_ths = deviation * baseline
    daily_loss = loss_ths * HASH_PRICE_USD_PER_TH_DAY
    return f"Peak loss of {loss_ths:.1f} TH/s (~${daily_loss:.2f}/day if sustained)."


def _impact_critical_temperature(insight: Insight, df: pd.DataFrame) -> str | None:
    """Critical temp — estimate throttling loss during overtemp periods."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    above = miner["chip_temp_c"] > CHIP_TEMP_CRITICAL
    if not above.any():
        return None
    pct_time = above.mean()
    mean_excess = (miner.loc[above, "chip_temp_c"] - CHIP_TEMP_CRITICAL).mean()
    est_loss = mean_excess * THROTTLE_SLOPE_THS_PER_C
    daily_loss = est_loss * HASH_PRICE_USD_PER_TH_DAY * pct_time
    return (
        f"Est. ~{est_loss:.0f} TH/s lost to throttling during critical periods "
        f"({pct_time:.0%} of time). ~${daily_loss:.2f}/day revenue impact."
    )


def _impact_peer_underperformance(insight: Insight, df: pd.DataFrame) -> str | None:
    """Peer comparison — revenue gap from hashrate residual."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    fleet_median = df.groupby("timestamp")["hashrate_ths"].median()
    merged = (
        miner.set_index("timestamp")["hashrate_ths"].to_frame().join(fleet_median, rsuffix="_fleet")
    )
    gap = (merged["hashrate_ths_fleet"] - merged["hashrate_ths"]).clip(lower=0).mean()
    if pd.isna(gap) or gap <= 0:
        return None
    daily_loss = gap * HASH_PRICE_USD_PER_TH_DAY
    return f"Avg {gap:.1f} TH/s below fleet median (~${daily_loss:.2f}/day unrealised revenue)."


def _impact_thermal_headroom(insight: Insight, df: pd.DataFrame) -> str | None:
    """Thermal headroom — estimate potential gain from overclocking."""
    headroom = insight.get("metric", 0)
    # Conservative: ~1 TH/s gain per 3°C of available headroom
    potential_gain = headroom / 3.0
    daily_gain = potential_gain * HASH_PRICE_USD_PER_TH_DAY
    return (
        f"~{headroom:.0f}°C headroom available. Conservative overclock could add "
        f"~{potential_gain:.1f} TH/s (~${daily_gain:.2f}/day potential gain)."
    )


# Registry: insight type → impact estimator
_IMPACT_ESTIMATORS = {
    "performance_degradation": _impact_performance_degradation,
    "sustained_underperformance": _impact_sustained_underperformance,
    "critical_temperature": _impact_critical_temperature,
    "peer_underperformance": _impact_peer_underperformance,
    "thermal_headroom": _impact_thermal_headroom,
}


def enrich_with_business_impact(
    results: dict[str, list[Insight]],
    df: pd.DataFrame,
) -> dict[str, list[Insight]]:
    """Add business_impact field to insights where revenue impact is estimable.

    Mutates insights in place and returns the same results dict.
    Insights without a matching estimator are left unchanged (no business_impact key).
    """
    for insights in results.values():
        for insight in insights:
            estimator = _IMPACT_ESTIMATORS.get(insight.get("type"))
            if estimator is not None:
                impact = estimator(insight, df)
                if impact:
                    insight["business_impact"] = impact
    return results
