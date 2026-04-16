"""Compare each miner against fleet median to find outliers."""

from __future__ import annotations

import pandas as pd

from .base import (
    PEER_CRITICAL_PCT,
    PEER_HASHRATE_FLOOR,
    PEER_TEMP_SIMILARITY,
    PEER_WARNING_PCT,
    Insight,
)


def analyze_peers(df: pd.DataFrame) -> list[Insight]:
    insights: list[Insight] = []

    # --- per-timestamp fleet statistics --- median is robust to outliers, because if a miner is 0TH/s the mean drops.
    fleet_stats = df.groupby("timestamp").agg(
        median_hashrate=("hashrate_ths", "median"),
        median_chip_temp=("chip_temp_c", "median"),
    ).reset_index() # turns the timestamp index back into a column to merge later
    
    merged = df.merge(fleet_stats, on="timestamp", how="left") #join left like
    merged["hashrate_residual"] = merged["hashrate_ths"] - merged["median_hashrate"] # compute diffs from median
    merged["temp_diff"] = merged["chip_temp_c"] - merged["median_chip_temp"] # compute diffs from median

    # Flag: similar temp (within 5°C) but hashrate >10% below fleet median
    similar_temp = merged["temp_diff"].abs() < PEER_TEMP_SIMILARITY
    hashrate_threshold = -PEER_HASHRATE_FLOOR * merged["median_hashrate"]
    # diff. performance under same temperature
    merged["anomaly"] = similar_temp & (merged["hashrate_residual"] < hashrate_threshold)

    anomaly_counts = (
        merged[merged["anomaly"]]
        .groupby("miner_id")
        .size()
        .sort_values(ascending=False)
    )
    total_per_miner = merged.groupby("miner_id").size()

    for miner_id, count in anomaly_counts.items():
        total = total_per_miner.get(miner_id, 1)
        pct = count / total * 100
        mean_residual = (
            merged.loc[
                (merged["miner_id"] == miner_id) & merged["anomaly"],
                "hashrate_residual",
            ].mean()
        )
        severity = "critical" if pct > PEER_CRITICAL_PCT else "warning" if pct > PEER_WARNING_PCT else "info"
        insights.append({
            "miner_id": miner_id,
            "type": "peer_underperformance",
            "severity": severity,
            "detail": (
                f"Under-performed fleet median in {count} of {total} readings "
                f"({pct:.1f}%) at similar temperatures. Mean hashrate "
                f"residual: {mean_residual:.2f} TH/s."
            ),
            "metric": round(float(pct), 2),
            "action": (
                "Investigate ASIC board health and firmware version for "
                "this miner."
            ),
        })

    # --- repeated anomaly patterns (daily) --- anomaly repeating!
    if not merged[merged["anomaly"]].empty:
        merged["date"] = pd.to_datetime(merged["timestamp"]).dt.date
        daily = (
            merged[merged["anomaly"]]
            .groupby(["miner_id", "date"])
            .size()
            .reset_index(name="anomaly_count")
        )
        multi_day = daily.groupby("miner_id")["date"].nunique()
        for miner_id, n_days in multi_day.items():
            if n_days > 1:
                insights.append({
                    "miner_id": miner_id,
                    "type": "peer_anomaly_repeated_daily",
                    "severity": "warning",
                    "detail": (
                        f"Underperformance vs peers detected across {n_days} "
                        f"distinct days — pattern is persistent, not transient. "
                        f"Suggests hardware degradation rather than environmental "
                        f"or network issue."
                    ),
                    "metric": int(n_days),
                    "action": (
                        "Schedule physical inspection; likely failing ASIC "
                        "boards or degraded thermal interface."
                    ),
                })

    # --- fleet-level anomaly ranking (top 10) ---
    if not anomaly_counts.empty:
        top_n = anomaly_counts.head(10)
        ranking = {
            str(mid): round(float(cnt / total_per_miner.get(mid, 1) * 100), 2)
            for mid, cnt in top_n.items()
        }
        insights.append({
            "miner_id": "fleet",
            "type": "peer_anomaly_ranking",
            "severity": "info",
            "detail": (
                f"Top anomaly frequency ranking (% of readings flagged): "
                f"{ranking}"
            ),
            "metric": len(ranking),
            "action": "Prioritise inspection of top-ranked miners.",
        })

    return insights
