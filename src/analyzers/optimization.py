"""Identify cooling and performance optimisation opportunities."""

from __future__ import annotations

import pandas as pd

from .base import (
    CHIP_TEMP_WARNING,
    COOL_UNDERUTILISED_TEMP,
    EXCESSIVE_COOLING_RATIO,
    HASHRATE_HEADROOM_TOLERANCE,
    Insight,
)


def analyze_optimization(df: pd.DataFrame) -> list[Insight]:
    insights: list[Insight] = []

    # Median for both: robust to outliers (crashed miners, overcooled units)
    fleet_avg_hashrate = df["hashrate_ths"].median()
    fleet_avg_immersion = df["immersion_temp_c"].median()
    scores_by_miner: dict[str, float] = {}

    miner_stats = df.groupby("miner_id").agg(
        mean_hashrate=("hashrate_ths", "mean"),
        mean_chip_temp=("chip_temp_c", "mean"),
        mean_immersion_temp=("immersion_temp_c", "mean"),
        mean_pressure=("immersion_pressure_bar", "mean"),
    )

    for miner_id, row in miner_stats.iterrows():
        # --- under-utilised thermal headroom --- espaço térmico
        if row["mean_chip_temp"] < COOL_UNDERUTILISED_TEMP:
            headroom = CHIP_TEMP_WARNING - row["mean_chip_temp"]
            if row["mean_hashrate"] <= fleet_avg_hashrate * HASHRATE_HEADROOM_TOLERANCE:
                insights.append({
                    "miner_id": miner_id,
                    "type": "thermal_headroom",
                    "severity": "info",
                    "detail": (
                        f"Operating at {row['mean_chip_temp']:.1f}°C — "
                        f"{headroom:.1f}°C below warning threshold — yet "
                        f"hashrate ({row['mean_hashrate']:.1f} TH/s) is not "
                        f"above fleet average ({fleet_avg_hashrate:.1f} TH/s)."
                    ),
                    "metric": round(float(headroom), 2),
                    "action": (
                        f"Consider overclocking {miner_id} to utilise "
                        f"available thermal headroom, or redistribute "
                        f"cooling capacity to hotter miners."
                    ),
                })

        # --- excessive cooling ---
        if (
            row["mean_immersion_temp"] < fleet_avg_immersion * EXCESSIVE_COOLING_RATIO
            and row["mean_hashrate"] <= fleet_avg_hashrate
        ):
            insights.append({
                "miner_id": miner_id,
                "type": "excessive_cooling",
                "severity": "info",
                "detail": (
                    f"Immersion temp ({row['mean_immersion_temp']:.1f}°C) is "
                    f"well below fleet average ({fleet_avg_immersion:.1f}°C) "
                    f"but hashrate ({row['mean_hashrate']:.1f} TH/s) is not "
                    f"better than fleet average."
                ),
                "metric": round(float(row["mean_immersion_temp"]), 2),
                "action": (
                    f"{miner_id} could share cooling capacity with hotter "
                    f"miners. Reduce cooling to {miner_id} to save energy."
                ),
            })

        # --- cooling efficiency score (collect for outlier detection) ---
        # -- TH/s per °C of gradient. Higher = more productive work per unit of thermal load
        delta_t = row["mean_chip_temp"] - row["mean_immersion_temp"]
        if delta_t > 0:
            scores_by_miner[miner_id] = row["mean_hashrate"] / delta_t

    # Flag miners with cooling efficiency >1σ below fleet mean
    if scores_by_miner:
        scores_series = pd.Series(scores_by_miner)
        fleet_mean_score = scores_series.mean()
        fleet_std_score = scores_series.std()
        for miner_id, score in scores_by_miner.items():
            # if the score of that miner is less than the Std deviation, it's underperforming
            if fleet_std_score > 0 and score < fleet_mean_score - fleet_std_score:
                insights.append({
                    "miner_id": miner_id,
                    "type": "low_cooling_efficiency",
                    "severity": "warning",
                    "detail": (
                        f"Cooling efficiency score {score:.2f} TH/s per °C "
                        f"— below fleet average ({fleet_mean_score:.2f}). "
                        f"High thermal gradient relative to hashrate output."
                    ),
                    "metric": round(float(score), 4),
                    "action": (
                        "Investigate coolant flow rate, thermal interface, "
                        "or degraded ASIC boards."
                    ),
                })

    return insights
