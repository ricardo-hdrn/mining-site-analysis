"""Shared constants and utilities for all analyzers."""

from __future__ import annotations

from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Thresholds (immersion-cooled ASIC operating ranges)
#
# Rationale:
#   - Chip temps: Bitmain S19/S21 max junction temp is ~95-105°C per datasheet.
#     Warning at 85°C gives margin before throttling; critical at 90°C is ~5°C
#     below hard limits. Immersion cooling allows ~5°C higher than air-cooled
#     thresholds (~80°C) due to superior heat dissipation.
#   - Rapid temp rise: Normal fluctuation is ±1-2°C between 5-min readings.
#     A 5°C jump in 10 min indicates a step-change event (pump failure,
#     coolant flow interruption), not gradual drift.
#   - Pressure change: Derived from the provided sample — M003 shows a 0.3 bar
#     jump (1.8→2.1) in one interval, the smallest anomalous change in the data.
#   - Hashrate deviation: ±10% is a standard industrial SPC threshold for
#     "out of normal range." Smaller catches too much sensor noise.
#   - Sustained minutes: A 5-min dip can be a pool hiccup. 30 min (6 readings)
#     confirms a real operational issue, not transient noise.
#   - Cool underutilised: 15°C below warning threshold. In an immersion setup,
#     this much headroom means cooling energy is being wasted.
#
#   In production, these should be configurable per miner model and calibrated
#   against historical site data.
# ---------------------------------------------------------------------------

# Thermal thresholds
# Source: Bitmain S19/S21 datasheet max junction ~95-105°C. Warning at 85°C
# gives operational margin; critical at 90°C is ~5°C below hard limits.
# Immersion allows ~5°C higher than air-cooled (~80°C) due to better dissipation.
CHIP_TEMP_WARNING = 85.0  # °C — warning threshold
CHIP_TEMP_CRITICAL = 90.0  # °C — critical threshold
# Source: Normal reading-to-reading fluctuation is ±1-2°C. A 5°C jump in 10 min
# is a step-change (pump failure, flow interruption), not gradual drift.
# Two detection windows serve different purposes:
#   - 10-min (RAPID_TEMP_WINDOW_MIN): detects acute events — pump failures,
#     coolant blockages, pressure spikes. These happen fast; a longer window
#     would average out the spike and miss it. At 5-min sampling, this is
#     2 readings — enough to catch single-interval jumps and short ramps.
#   - 30-min (SUSTAINED_MINUTES): confirms chronic problems — persistent
#     hashrate underperformance. A 5-min dip is normal variance (pool latency,
#     share luck). 30 min of continuous deviation = real operational issue.
# Short window → acute events.  Long window → chronic problems.
RAPID_TEMP_RISE = 5.0  # °C — threshold
RAPID_TEMP_WINDOW_MIN = 10  # minutes — acute event detection window
# Source: 15°C below warning threshold. In immersion, this much headroom
# means cooling energy is being wasted on this miner.
COOL_UNDERUTILISED_TEMP = 70.0  # °C — well below thermal limits

# Hashrate thresholds
# Source: ±10% is standard industrial SPC for "out of normal range."
# 20% is severe — likely hardware failure, not sensor noise.
HASHRATE_DEVIATION_PCT = 0.10  # sustained deviation flag (10%)
HASHRATE_DEVIATION_SEVERE = 0.20  # severe deviation (20%)
# Source: A 5-min dip can be a pool hiccup. 30 min (6 readings at 5-min
# intervals) confirms a real operational issue.
SUSTAINED_MINUTES = 30

# Correlation thresholds (Pearson r)
# Source: Cohen's conventions — r > 0.5 is "large effect." Below -0.5 means
# temperature is strongly impacting hashrate (thermal throttling active).
# Severity tiers at -0.6 and -0.8 separate moderate from severe coupling.
CORRELATION_THRESHOLD = -0.5  # minimum r to flag
CORRELATION_CRITICAL = -0.8  # critical severity
CORRELATION_HIGH = -0.6  # high severity
P_VALUE_THRESHOLD = 0.05  # standard statistical significance

# Pressure thresholds
# Source: Derived from provided sample data — M003 shows 1.8→2.1 bar (Δ=0.3)
# in one 5-min interval, the smallest change clearly anomalous in context.
# 0.5 bar is a severe event (>25% of normal operating pressure).
PRESSURE_ABSOLUTE_CHANGE = 0.3  # bar in 10 min — anomaly flag
PRESSURE_CRITICAL_CHANGE = 0.5  # bar — critical severity

# Cooling analysis
# Source: Normal immersion temp drift is <1°C/hour (diurnal cycle). A 3°C/hour
# rise with stable chip temp means the cooling system is losing capacity
# (fouled heat exchanger, reduced flow). 2°C/hour chip stability threshold
# filters normal operating noise. 1-hour window smooths out short-term
# fluctuations while still catching real cooling degradation events.
COOLING_TREND_WINDOW_HOURS = 1  # hours — window for cooling trend analysis
COOLING_TEMP_RISE_RATE = 3.0  # °C/hour — immersion temp rise for degradation
COOLING_CHIP_STABLE = 2.0  # °C/hour — chip temp "stable" below this
# Source: In well-functioning immersion, chip-to-coolant gradient is typically
# 30-35% of chip temp. Above 40% indicates poor thermal interface.
COOLING_EFFECTIVENESS_THRESHOLD = 0.4  # (chip-immersion)/chip — poor above this

# Peer comparison
# Source: Miners in the same immersion tank share ambient conditions. ±5°C
# covers manufacturing variance; beyond that, conditions are different.
# 10% below fleet median at same temp = hardware problem, not environment.
# Severity tiers: >30% of readings anomalous = critical (persistent, severe),
# >10% = warning (recurring), below = info (occasional).
PEER_TEMP_SIMILARITY = 5.0  # °C — "similar temperature" window
PEER_HASHRATE_FLOOR = 0.10  # fraction of median — underperformance threshold
PEER_CRITICAL_PCT = 30  # % anomalous readings — critical severity
PEER_WARNING_PCT = 10  # % anomalous readings — warning severity

# Optimization
# Source: 5% tolerance avoids flagging miners marginally above fleet average.
# 90% of fleet immersion temp = meaningfully overcooled (>10% colder).
HASHRATE_HEADROOM_TOLERANCE = 1.05  # 5% above fleet avg to count as "benefiting"
EXCESSIVE_COOLING_RATIO = 0.90  # immersion temp below 90% of fleet avg

# Business impact estimation
# Source: No economics data in the provided dataset. Hash price is the revenue
# earned per TH/s of hashrate per day — it encapsulates BTC price, network
# difficulty, and block reward into a single operational metric.
# ~$0.045/TH/day is approximate as of early 2025. In production, this would
# be fetched from mempool.space or a similar API.
HASH_PRICE_USD_PER_TH_DAY = 0.045  # $/TH/day — assumed hash price

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Insight = dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ensure_sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy sorted by miner_id + timestamp with proper dtypes."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values(["miner_id", "timestamp"]).reset_index(drop=True)


def infer_freq(grp: pd.DataFrame) -> pd.Timedelta | None:
    """Infer sampling frequency from a time-indexed group."""
    freq = grp.index.to_series().diff().median()
    if pd.isna(freq) or freq <= pd.Timedelta(0):
        return None
    return freq
