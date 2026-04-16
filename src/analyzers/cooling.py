"""Detect cooling-system anomalies via pressure and temperature signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import (
    COOLING_CHIP_STABLE,
    COOLING_EFFECTIVENESS_THRESHOLD,
    COOLING_TEMP_RISE_RATE,
    COOLING_TREND_WINDOW_HOURS,
    PRESSURE_ABSOLUTE_CHANGE,
    PRESSURE_CRITICAL_CHANGE,
    RAPID_TEMP_WINDOW_MIN,
    Insight,
    infer_freq,
)


def analyze_cooling(df: pd.DataFrame) -> list[Insight]:
    insights: list[Insight] = []
    
    # for simplicity it's grouping by everytime -> could cache/ pre bake.
    for miner_id, grp in df.groupby("miner_id"):
        grp = grp.set_index("timestamp").sort_index()

        freq = infer_freq(grp)
        if freq is None:
            continue
        lookback = max(1, int(pd.Timedelta(minutes=RAPID_TEMP_WINDOW_MIN) / freq))

        # --- pressure anomalies (absolute change) ---
        pressure = grp["immersion_pressure_bar"]
        abs_change = pressure.diff(periods=lookback).abs()

        if (abs_change > PRESSURE_ABSOLUTE_CHANGE).any():
            worst_change = abs_change.max()
            worst_ts = abs_change.idxmax()
            insights.append({
                "miner_id": miner_id,
                "type": "pressure_anomaly",
                "severity": "critical" if worst_change > PRESSURE_CRITICAL_CHANGE else "warning",
                "detail": (
                    f"Pressure spike detected: Δ={worst_change:.3f} bar "
                    f"in ~10 min at {worst_ts}."
                ),
                "metric": round(float(worst_change), 4),
                "action": (
                    "Check for leaks, blockages, or pump cavitation in the "
                    "immersion cooling loop."
                ),
            })

        #  cooling degradation: sustained immersion_temp rise 
        long_lookback = max(1, int(pd.Timedelta(hours=COOLING_TREND_WINDOW_HOURS) / freq))
        immersion_trend = grp["immersion_temp_c"].diff(periods=long_lookback)
        chip_trend = grp["chip_temp_c"].diff(periods=long_lookback)

        #  - Immersion coolant is getting hotter (rising >3°C/hour)                                                                                    
        # - But the chips aren't getting cooler (stable, changing <2°C/hour) 
        degradation = (
            (immersion_trend > COOLING_TEMP_RISE_RATE)
            & (chip_trend.abs() < COOLING_CHIP_STABLE)
        )
        if degradation.any():
            count = int(degradation.sum())
            worst_ts = immersion_trend[degradation].idxmax()
            insights.append({
                "miner_id": miner_id,
                "type": "cooling_degradation",
                "severity": "warning",
                "detail": (
                    f"Immersion temperature rising >3°C/hour while chip "
                    f"temperature stable — detected in {count} intervals "
                    f"(e.g. {worst_ts}). Cooling system losing effectiveness."
                ),
                "metric": count,
                "action": (
                    "Inspect heat exchanger fouling, coolant quality, and "
                    "ambient conditions."
                ),
            })

        # --- cooling effort not reflected in chip temp ---
        # - Coolant is getting colder (dropping >3°C/hour — the cooling system is working, rejecting heat)                                            
        # - But chips are getting hotter anyway (rising >2°C/hour)  
        cooling_effort = (
            (immersion_trend < -COOLING_TEMP_RISE_RATE)
            & (chip_trend > COOLING_CHIP_STABLE)
        )
        if cooling_effort.any():
            count = int(cooling_effort.sum())
            insights.append({
                "miner_id": miner_id,
                "type": "cooling_ineffective",
                "severity": "warning",
                "detail": (
                    f"Cooling active (immersion temp dropping) but chip "
                    f"temperature rising in {count} intervals."
                ),
                "metric": count,
                "action": (
                    "Check thermal interface between chips and coolant — "
                    "possible fluid channeling or air pocket."
                ),
            })

        # --- poor cooling effectiveness (only flag outliers) ---

        #
        #  Example with real numbers:                                                                                                                  
        # - Chip = 80°C, coolant = 52°C → (80-52)/80 = 0.35 → coolant is removing 65% of the heat, 35% remains as gradient. Good.                     
        # - Chip = 95°C, coolant = 52°C → (95-52)/95 = 0.45 → coolant only removing 55%. Bad — above the 0.4 threshold. 
        #
        ce = (grp["chip_temp_c"] - grp["immersion_temp_c"]) / grp["chip_temp_c"]
        mean_ce = ce.mean()
        if not np.isnan(mean_ce) and mean_ce > COOLING_EFFECTIVENESS_THRESHOLD:
            insights.append({
                "miner_id": miner_id,
                "type": "poor_cooling_effectiveness",
                "severity": "warning",
                "detail": (
                    f"Cooling effectiveness ratio "
                    f"(chip−immersion)/chip = {mean_ce:.3f} — above {COOLING_EFFECTIVENESS_THRESHOLD} "
                    f"threshold. Poor heat transfer to coolant."
                ),
                "metric": round(float(mean_ce), 4),
                "action": (
                    "Inspect thermal interface, fluid flow rate, and "
                    "immersion fluid quality."
                ),
            })

    return insights
