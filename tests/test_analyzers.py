"""Tests for mining site telemetry analyzers.

Each test constructs a minimal DataFrame with a known pattern and verifies
the corresponding analyzer detects it with the expected type and severity.
"""

import pandas as pd
import pytest

from src.analyzers.performance import analyze_performance
from src.analyzers.hardware_risk import analyze_hardware_risk
from src.analyzers.cooling import analyze_cooling
from src.analyzers.peer_comparison import analyze_peers
from src.analyzers.optimization import analyze_optimization
from src.analyzers import run_all_analyzers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame from row dicts with proper types."""
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _stable_miner(miner_id: str, n: int = 60, start: str = "2025-01-01T00:00:00Z",
                   hashrate: float = 110, chip_temp: float = 75,
                   immersion_temp: float = 52, pressure: float = 1.8) -> list[dict]:
    """Generate n rows of stable readings for a single miner."""
    timestamps = pd.date_range(start, periods=n, freq="5min")
    return [
        {
            "timestamp": ts.isoformat(),
            "miner_id": miner_id,
            "hashrate_ths": hashrate,
            "chip_temp_c": chip_temp,
            "immersion_temp_c": immersion_temp,
            "immersion_pressure_bar": pressure,
        }
        for ts in timestamps
    ]


# ===========================================================================
# Performance
# ===========================================================================

class TestPerformance:
    def test_detects_hashrate_temp_correlation(self):
        """Miner with hashrate inversely tracking chip temp should be flagged."""
        rows = []
        timestamps = pd.date_range("2025-01-01", periods=20, freq="5min")
        for i, ts in enumerate(timestamps):
            # Temp rises linearly, hashrate drops linearly
            rows.append({
                "timestamp": ts.isoformat(),
                "miner_id": "M001",
                "hashrate_ths": 120 - i * 3,
                "chip_temp_c": 70 + i * 2,
                "immersion_temp_c": 52,
                "immersion_pressure_bar": 1.8,
            })
        insights = analyze_performance(_make_df(rows))
        types = [i["type"] for i in insights]
        assert "performance_degradation" in types

    def test_no_correlation_on_stable_miner(self):
        """Stable miner should not be flagged for performance degradation."""
        rows = _stable_miner("M001", n=20)
        insights = analyze_performance(_make_df(rows))
        degradation = [i for i in insights if i["type"] == "performance_degradation"]
        assert len(degradation) == 0

    def test_sustained_underperformance(self):
        """Miner whose hashrate drops 50% for 30+ min should be flagged."""
        rows = _stable_miner("M001", n=30, hashrate=110)
        # Drop hashrate for last 10 readings (50 min)
        for r in rows[-10:]:
            r["hashrate_ths"] = 50
        insights = analyze_performance(_make_df(rows))
        types = [i["type"] for i in insights]
        assert "sustained_underperformance" in types

    def test_skip_short_dip(self):
        """A brief 1-reading dip should not trigger sustained underperformance."""
        rows = _stable_miner("M001", n=20, hashrate=110)
        rows[10]["hashrate_ths"] = 50  # single dip
        insights = analyze_performance(_make_df(rows))
        sustained = [i for i in insights if i["type"] == "sustained_underperformance"]
        assert len(sustained) == 0


# ===========================================================================
# Hardware Risk
# ===========================================================================

class TestHardwareRisk:
    def test_critical_temperature(self):
        """Chip temp above 90°C should trigger critical."""
        rows = _stable_miner("M001", n=10, chip_temp=92)
        insights = analyze_hardware_risk(_make_df(rows))
        critical = [i for i in insights if i["type"] == "critical_temperature"]
        assert len(critical) == 1
        assert critical[0]["severity"] == "critical"

    def test_warning_temperature(self):
        """Chip temp 85-90°C should trigger warning, not critical."""
        rows = _stable_miner("M001", n=10, chip_temp=87)
        insights = analyze_hardware_risk(_make_df(rows))
        warnings = [i for i in insights if i["type"] == "temperature_warning"]
        assert len(warnings) == 1
        assert warnings[0]["severity"] == "warning"

    def test_no_alert_below_threshold(self):
        """Chip temp below 85°C should not trigger any temperature alert."""
        rows = _stable_miner("M001", n=10, chip_temp=75)
        insights = analyze_hardware_risk(_make_df(rows))
        temp_alerts = [i for i in insights if "temperature" in i["type"] or "temp" in i["type"]]
        assert len(temp_alerts) == 0

    def test_rapid_temperature_rise(self):
        """A 15°C jump in 10 min should trigger critical rapid rise."""
        rows = _stable_miner("M001", n=10, chip_temp=70)
        rows[2]["chip_temp_c"] = 85  # +15°C from row 0
        insights = analyze_hardware_risk(_make_df(rows))
        spikes = [i for i in insights if i["type"] == "rapid_temperature_rise"]
        assert len(spikes) == 1
        assert spikes[0]["severity"] == "critical"

    def test_time_above_threshold(self):
        """Miner with readings above 85°C should report time above threshold."""
        rows = _stable_miner("M001", n=10, chip_temp=88)
        insights = analyze_hardware_risk(_make_df(rows))
        above = [i for i in insights if i["type"] == "time_above_threshold"]
        assert len(above) == 1
        assert above[0]["metric"] > 0


# ===========================================================================
# Cooling
# ===========================================================================

class TestCooling:
    def test_pressure_spike(self):
        """A 0.5 bar pressure jump should be flagged."""
        rows = _stable_miner("M001", n=10, pressure=1.8)
        rows[2]["immersion_pressure_bar"] = 2.3  # +0.5 bar
        insights = analyze_cooling(_make_df(rows))
        pressure = [i for i in insights if i["type"] == "pressure_anomaly"]
        assert len(pressure) == 1

    def test_no_pressure_alert_on_stable(self):
        """Stable pressure should not trigger alerts."""
        rows = _stable_miner("M001", n=10, pressure=1.8)
        insights = analyze_cooling(_make_df(rows))
        pressure = [i for i in insights if i["type"] == "pressure_anomaly"]
        assert len(pressure) == 0

    def test_cooling_degradation(self):
        """Immersion temp rising while chip stable should flag degradation."""
        rows = []
        timestamps = pd.date_range("2025-01-01", periods=20, freq="5min")
        for i, ts in enumerate(timestamps):
            rows.append({
                "timestamp": ts.isoformat(),
                "miner_id": "M001",
                "hashrate_ths": 110,
                "chip_temp_c": 75,  # stable
                "immersion_temp_c": 50 + i * 0.5,  # rising fast
                "immersion_pressure_bar": 1.8,
            })
        insights = analyze_cooling(_make_df(rows))
        degradation = [i for i in insights if i["type"] == "cooling_degradation"]
        assert len(degradation) == 1


# ===========================================================================
# Peer Comparison
# ===========================================================================

class TestPeerComparison:
    def test_detects_underperformer(self):
        """One miner consistently below peers should be flagged."""
        rows = []
        timestamps = pd.date_range("2025-01-01", periods=20, freq="5min")
        for ts in timestamps:
            for mid, hr in [("M001", 110), ("M002", 108), ("M003", 80)]:
                rows.append({
                    "timestamp": ts.isoformat(),
                    "miner_id": mid,
                    "hashrate_ths": hr,
                    "chip_temp_c": 75,
                    "immersion_temp_c": 52,
                    "immersion_pressure_bar": 1.8,
                })
        insights = analyze_peers(_make_df(rows))
        flagged = [i for i in insights if i["type"] == "peer_underperformance"]
        assert any(i["miner_id"] == "M003" for i in flagged)

    def test_no_flag_when_peers_similar(self):
        """All miners performing equally should not trigger peer alerts."""
        rows = []
        timestamps = pd.date_range("2025-01-01", periods=10, freq="5min")
        for ts in timestamps:
            for mid in ["M001", "M002", "M003"]:
                rows.append({
                    "timestamp": ts.isoformat(),
                    "miner_id": mid,
                    "hashrate_ths": 110,
                    "chip_temp_c": 75,
                    "immersion_temp_c": 52,
                    "immersion_pressure_bar": 1.8,
                })
        insights = analyze_peers(_make_df(rows))
        flagged = [i for i in insights if i["type"] == "peer_underperformance"]
        assert len(flagged) == 0

    def test_repeated_daily_pattern(self):
        """Underperformer across multiple days should trigger repeated_daily."""
        rows = []
        timestamps = pd.date_range("2025-01-01", periods=3 * 24 * 12, freq="5min")  # 3 days
        for ts in timestamps:
            for mid, hr in [("M001", 110), ("M002", 108), ("M003", 80)]:
                rows.append({
                    "timestamp": ts.isoformat(),
                    "miner_id": mid,
                    "hashrate_ths": hr,
                    "chip_temp_c": 75,
                    "immersion_temp_c": 52,
                    "immersion_pressure_bar": 1.8,
                })
        insights = analyze_peers(_make_df(rows))
        repeated = [i for i in insights if i["type"] == "peer_anomaly_repeated_daily"]
        assert any(i["miner_id"] == "M003" for i in repeated)


# ===========================================================================
# Optimization
# ===========================================================================

class TestOptimization:
    def test_thermal_headroom(self):
        """Overcooled miner with no hashrate benefit should be flagged."""
        rows = (
            _stable_miner("M001", n=20, chip_temp=75, hashrate=110) +
            _stable_miner("M002", n=20, chip_temp=75, hashrate=110) +
            _stable_miner("M003", n=20, chip_temp=60, hashrate=108, immersion_temp=42)
        )
        insights = analyze_optimization(_make_df(rows))
        headroom = [i for i in insights if i["type"] == "thermal_headroom"]
        assert any(i["miner_id"] == "M003" for i in headroom)

    def test_no_headroom_on_hot_miner(self):
        """Miner running at 80°C should not be flagged for thermal headroom."""
        rows = (
            _stable_miner("M001", n=20, chip_temp=80, hashrate=110) +
            _stable_miner("M002", n=20, chip_temp=80, hashrate=110)
        )
        insights = analyze_optimization(_make_df(rows))
        headroom = [i for i in insights if i["type"] == "thermal_headroom"]
        assert len(headroom) == 0

    def test_low_cooling_efficiency(self):
        """Miner with much higher thermal gradient should be flagged."""
        rows = (
            _stable_miner("M001", n=20, chip_temp=75, immersion_temp=52, hashrate=110) +
            _stable_miner("M002", n=20, chip_temp=75, immersion_temp=52, hashrate=110) +
            _stable_miner("M003", n=20, chip_temp=95, immersion_temp=52, hashrate=80)  # big gradient, low hashrate
        )
        insights = analyze_optimization(_make_df(rows))
        low_eff = [i for i in insights if i["type"] == "low_cooling_efficiency"]
        assert any(i["miner_id"] == "M003" for i in low_eff)


# ===========================================================================
# Integration — run_all_analyzers
# ===========================================================================

class TestRunAll:
    def test_returns_all_categories(self):
        """run_all_analyzers should return all 5 category keys."""
        rows = _stable_miner("M001", n=10)
        results = run_all_analyzers(_make_df(rows))
        assert set(results.keys()) == {
            "performance", "hardware_risk", "cooling",
            "peer_comparison", "optimization",
        }

    def test_each_category_returns_list(self):
        """Each category should return a list (possibly empty)."""
        rows = _stable_miner("M001", n=10)
        results = run_all_analyzers(_make_df(rows))
        for key, insights in results.items():
            assert isinstance(insights, list), f"{key} returned {type(insights)}"

    def test_sample_data(self):
        """The provided sample data should produce insights."""
        df = pd.read_csv("data/site_telemetry.csv", parse_dates=["timestamp"])
        results = run_all_analyzers(df)
        total = sum(len(v) for v in results.values())
        assert total > 0

    def test_insight_structure(self):
        """Every insight should have the required keys."""
        df = pd.read_csv("data/site_telemetry.csv", parse_dates=["timestamp"])
        results = run_all_analyzers(df)
        required_keys = {"miner_id", "type", "severity", "detail", "metric", "action"}
        for category, insights in results.items():
            for insight in insights:
                missing = required_keys - set(insight.keys())
                assert not missing, f"{category}: insight missing keys {missing}"

    def test_severity_values(self):
        """All severities should be one of the valid levels."""
        df = pd.read_csv("data/site_telemetry.csv", parse_dates=["timestamp"])
        results = run_all_analyzers(df)
        valid = {"critical", "high", "warning", "info"}
        for category, insights in results.items():
            for insight in insights:
                assert insight["severity"] in valid, (
                    f"{category}: invalid severity '{insight['severity']}'"
                )
