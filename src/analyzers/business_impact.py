"""Enrich insights with business impact estimates.

Runs as a separate pass after detection — keeps economics logic
decoupled from signal processing. Each analyzer stays focused on
detection; this module translates findings into revenue impact.

Business impact is a structured dict:
{
    "summary": "Human-readable impact description",
    "hashrate_loss_ths": 19.2,
    "revenue_impact_usd_day": 0.87,
    "hash_price_usd_th_day": 0.045,
    "method": "thermal_throttling_correlation",
    "confidence": "medium"
}
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import CHIP_TEMP_CRITICAL, HASH_PRICE_USD_PER_TH_DAY, Insight

THROTTLE_SLOPE_THS_PER_C = 5.0  # approx hashrate loss per °C above critical


def _make_impact(
    summary: str,
    *,
    hashrate_loss_ths: float | None = None,
    hashrate_gain_ths: float | None = None,
    revenue_impact_usd_day: float | None = None,
    revenue_gain_usd_day: float | None = None,
    pct_time_affected: float | None = None,
    method: str = "",
    confidence: str = "medium",
) -> dict[str, Any]:
    """Build a structured business impact dict."""
    impact: dict[str, Any] = {
        "summary": summary,
        "hash_price_usd_th_day": HASH_PRICE_USD_PER_TH_DAY,
        "method": method,
        "confidence": confidence,
    }
    if hashrate_loss_ths is not None:
        impact["hashrate_loss_ths"] = round(hashrate_loss_ths, 2)
    if hashrate_gain_ths is not None:
        impact["hashrate_gain_ths"] = round(hashrate_gain_ths, 2)
    if revenue_impact_usd_day is not None:
        impact["revenue_impact_usd_day"] = round(revenue_impact_usd_day, 4)
    if revenue_gain_usd_day is not None:
        impact["revenue_gain_usd_day"] = round(revenue_gain_usd_day, 4)
    if pct_time_affected is not None:
        impact["pct_time_affected"] = round(pct_time_affected, 2)
    return impact


def _impact_performance_degradation(insight: Insight, df: pd.DataFrame) -> dict | None:
    """Thermal correlation — estimate avg hashrate lost to throttling."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    hr = miner["hashrate_ths"].dropna()
    if hr.empty:
        return None
    loss_ths = hr.max() - hr.mean()
    daily_loss = loss_ths * HASH_PRICE_USD_PER_TH_DAY
    return _make_impact(
        f"Est. avg {loss_ths:.1f} TH/s lost to thermal throttling "
        f"(~${daily_loss:.2f}/day at ${HASH_PRICE_USD_PER_TH_DAY}/TH/day).",
        hashrate_loss_ths=loss_ths,
        revenue_impact_usd_day=daily_loss,
        method="thermal_throttling_correlation",
        confidence="medium",
    )


def _impact_sustained_underperformance(insight: Insight, df: pd.DataFrame) -> dict | None:
    """Sustained deviation — estimate hashrate loss from metric (deviation fraction)."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    baseline = miner["hashrate_ths"].median()
    if pd.isna(baseline) or baseline <= 0:
        return None
    deviation = abs(insight.get("metric", 0))
    loss_ths = deviation * baseline
    daily_loss = loss_ths * HASH_PRICE_USD_PER_TH_DAY
    return _make_impact(
        f"Peak loss of {loss_ths:.1f} TH/s (~${daily_loss:.2f}/day if sustained).",
        hashrate_loss_ths=loss_ths,
        revenue_impact_usd_day=daily_loss,
        method="baseline_deviation",
        confidence="high" if deviation > 0.3 else "medium",
    )


def _impact_critical_temperature(insight: Insight, df: pd.DataFrame) -> dict | None:
    """Critical temp — estimate throttling loss during overtemp periods."""
    miner = df[df["miner_id"] == insight["miner_id"]]
    above = miner["chip_temp_c"] > CHIP_TEMP_CRITICAL
    if not above.any():
        return None
    pct_time = above.mean()
    mean_excess = (miner.loc[above, "chip_temp_c"] - CHIP_TEMP_CRITICAL).mean()
    est_loss = mean_excess * THROTTLE_SLOPE_THS_PER_C
    daily_loss = est_loss * HASH_PRICE_USD_PER_TH_DAY * pct_time
    return _make_impact(
        f"Est. ~{est_loss:.0f} TH/s lost to throttling during critical periods "
        f"({pct_time:.0%} of time). ~${daily_loss:.2f}/day revenue impact.",
        hashrate_loss_ths=est_loss,
        revenue_impact_usd_day=daily_loss,
        pct_time_affected=pct_time * 100,
        method="thermal_throttling_threshold",
        confidence="medium",
    )


def _impact_peer_underperformance(insight: Insight, df: pd.DataFrame) -> dict | None:
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
    return _make_impact(
        f"Avg {gap:.1f} TH/s below fleet median (~${daily_loss:.2f}/day unrealised revenue).",
        hashrate_loss_ths=gap,
        revenue_impact_usd_day=daily_loss,
        method="peer_median_residual",
        confidence="high",
    )


def _impact_thermal_headroom(insight: Insight, df: pd.DataFrame) -> dict | None:
    """Thermal headroom — estimate potential gain from overclocking."""
    headroom = insight.get("metric", 0)
    # Conservative: ~1 TH/s gain per 3°C of available headroom
    potential_gain = headroom / 3.0
    daily_gain = potential_gain * HASH_PRICE_USD_PER_TH_DAY
    return _make_impact(
        f"~{headroom:.0f}°C headroom available. Conservative overclock could add "
        f"~{potential_gain:.1f} TH/s (~${daily_gain:.2f}/day potential gain).",
        hashrate_gain_ths=potential_gain,
        revenue_gain_usd_day=daily_gain,
        method="thermal_headroom_overclock",
        confidence="low",
    )


# Registry: insight type → impact estimator
_IMPACT_ESTIMATORS = {
    "performance_degradation": _impact_performance_degradation,
    "sustained_underperformance": _impact_sustained_underperformance,
    "critical_temperature": _impact_critical_temperature,
    "peer_underperformance": _impact_peer_underperformance,
    "thermal_headroom": _impact_thermal_headroom,
}


_NON_MEASURABLE: dict[str, Any] = {
    "summary": "Risk signal — no direct hashrate impact measurable from telemetry.",
    "status": "not_measurable",
    "hash_price_usd_th_day": HASH_PRICE_USD_PER_TH_DAY,
    "hashrate_loss_ths": 0,
    "revenue_impact_usd_day": 0,
    "method": "none",
    "confidence": "n/a",
}


def enrich_with_business_impact(
    results: dict[str, list[Insight]],
    df: pd.DataFrame,
) -> dict[str, list[Insight]]:
    """Add business_impact dict to every insight.

    Insights with a matching estimator get a quantified impact.
    Others get a standard 'not_measurable' stamp with zeroed fields —
    always present, always structured, no nullable checks downstream.
    """
    for insights in results.values():
        for insight in insights:
            estimator = _IMPACT_ESTIMATORS.get(insight.get("type"))
            if estimator is not None:
                impact = estimator(insight, df)
                if impact:
                    impact["status"] = "estimated"
                    insight["business_impact"] = impact
                    continue
            insight["business_impact"] = _NON_MEASURABLE.copy()
    return results
