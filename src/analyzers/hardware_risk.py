"""Flag thermal risks: sustained high temps, rapid spikes."""

from __future__ import annotations

import pandas as pd

from .base import (
    CHIP_TEMP_CRITICAL,
    CHIP_TEMP_WARNING,
    RAPID_TEMP_RISE,
    RAPID_TEMP_WINDOW_MIN,
    Insight,
    infer_freq,
)


def analyze_hardware_risk(df: pd.DataFrame) -> list[Insight]:
    insights: list[Insight] = []

    # for simplicity it's grouping by everytime -> could cache/ pre bake.
    for miner_id, grp in df.groupby("miner_id"):
        grp = grp.set_index("timestamp").sort_index()

        # --- chip temperature thresholds ---
        above_critical = grp["chip_temp_c"] > CHIP_TEMP_CRITICAL
        above_warning = grp["chip_temp_c"] > CHIP_TEMP_WARNING

        if above_critical.any():
            pct = above_critical.mean() * 100
            max_temp = grp.loc[above_critical, "chip_temp_c"].max()
            insights.append(
                {
                    "miner_id": miner_id,
                    "type": "critical_temperature",
                    "severity": "critical",
                    "detail": (
                        f"Chip temperature exceeded {CHIP_TEMP_CRITICAL}°C in "
                        f"{pct:.1f}% of readings (max {max_temp:.1f}°C)."
                    ),
                    "metric": round(float(max_temp), 2),
                    "action": (
                        "Immediately reduce load or increase cooling. Inspect "
                        "immersion fluid level and pump operation."
                    ),
                }
            )
        elif above_warning.any():
            pct = above_warning.mean() * 100
            max_temp = grp.loc[above_warning, "chip_temp_c"].max()
            insights.append(
                {
                    "miner_id": miner_id,
                    "type": "temperature_warning",
                    "severity": "warning",
                    "detail": (
                        f"Chip temperature exceeded {CHIP_TEMP_WARNING}°C in "
                        f"{pct:.1f}% of readings (max {max_temp:.1f}°C)."
                    ),
                    "metric": round(float(max_temp), 2),
                    "action": (
                        "Monitor closely; prepare to increase cooling or reduce clock speed."
                    ),
                }
            )

        # --- rapid temperature increase (>5°C in 10 min) ---
        freq = infer_freq(grp)
        if freq is None:
            continue
        # look back of ~2
        lookback = max(1, int(pd.Timedelta(minutes=RAPID_TEMP_WINDOW_MIN) / freq))
        temp_change = grp["chip_temp_c"].diff(periods=lookback)
        spikes = temp_change[temp_change > RAPID_TEMP_RISE]
        if not spikes.empty:
            worst_spike = spikes.max()
            worst_ts = spikes.idxmax()
            insights.append(
                {
                    "miner_id": miner_id,
                    "type": "rapid_temperature_rise",
                    "severity": "critical" if worst_spike > 10 else "warning",
                    "detail": (
                        f"Chip temperature rose {worst_spike:.1f}°C within ~10 min (at {worst_ts})."
                    ),
                    "metric": round(float(worst_spike), 2),
                    "action": (
                        "Possible coolant flow interruption or pump failure. "
                        "Inspect immersion loop immediately."
                    ),
                }
            )

        # --- time above threshold ---
        if above_warning.any():
            total_above = above_warning.sum() * freq
            minutes_above = total_above.total_seconds() / 60
            insights.append(
                {
                    "miner_id": miner_id,
                    "type": "time_above_threshold",
                    "severity": "info",
                    "detail": (
                        f"Miner spent ~{minutes_above:.0f} minutes above "
                        f"{CHIP_TEMP_WARNING}°C warning threshold."
                    ),
                    "metric": round(minutes_above, 1),
                    "action": "Review cooling capacity allocation for this miner.",
                }
            )

    return insights
