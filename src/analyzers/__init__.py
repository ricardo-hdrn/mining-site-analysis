"""
Mining site telemetry analyzers.

Five modules detecting performance degradation, hardware risk,
cooling anomalies, peer comparison outliers, and optimization
opportunities across a fleet of immersion-cooled miners.

Expected input DataFrame columns:
    timestamp, miner_id, hashrate_ths, chip_temp_c,
    immersion_temp_c, immersion_pressure_bar
"""

from __future__ import annotations

import pandas as pd

from .base import Insight, ensure_sorted
from .cooling import analyze_cooling
from .hardware_risk import analyze_hardware_risk
from .optimization import analyze_optimization
from .peer_comparison import analyze_peers
from .performance import analyze_performance


def run_all_analyzers(df: pd.DataFrame) -> dict[str, list[Insight]]:
    """Execute all five analyzers and return a consolidated report."""
    prepared = ensure_sorted(df)
    return {
        "performance": analyze_performance(prepared),
        "hardware_risk": analyze_hardware_risk(prepared),
        "cooling": analyze_cooling(prepared),
        "peer_comparison": analyze_peers(prepared),
        "optimization": analyze_optimization(prepared),
    }
