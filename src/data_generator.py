"""
Bitcoin mining immersion-cooled site telemetry data generator.

Generates realistic 7-day telemetry for 10 ASIC miners (M001-M010) at 5-minute
intervals, embedding specific failure modes, degradation patterns, and cooling
anomalies typical of immersion-cooled deployments.
"""

import os
from datetime import datetime

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NUM_MINERS = 10
MINER_IDS = [f"M{i:03d}" for i in range(1, NUM_MINERS + 1)]
INTERVAL_MINUTES = 5
DAYS = 7
START_TIME = datetime(2026, 4, 9, 0, 0, 0)  # 7 days before today

# Normal operating ranges
HASH_BASE = 110.0  # TH/s centre
HASH_SPREAD = 10.0  # +/- around base
CHIP_TEMP_BASE = 77.5  # degC centre (70-85 range)
CHIP_TEMP_SPREAD = 7.5
IMM_TEMP_BASE = 51.5  # degC centre (48-55 range)
IMM_TEMP_SPREAD = 3.5
PRESSURE_BASE = 1.75  # bar centre (1.6-1.9 range)
PRESSURE_SPREAD = 0.15

# Thermal throttling threshold
THROTTLE_THRESHOLD_C = 85.0
# Hashrate penalty per degree above threshold (TH/s per degC)
THROTTLE_SLOPE = 5.0

# Seed for reproducibility
RNG_SEED = 42


def generate_site_data(seed: int = RNG_SEED) -> pd.DataFrame:
    """Generate 7 days of immersion-cooled mining site telemetry.

    Returns a DataFrame with columns:
        timestamp, miner_id, hashrate_ths, chip_temp_c,
        immersion_temp_c, immersion_pressure_bar
    """
    rng = np.random.default_rng(seed)

    # --- Time axis ---
    total_points = DAYS * 24 * 60 // INTERVAL_MINUTES  # 2016 per miner
    timestamps = pd.date_range(start=START_TIME, periods=total_points, freq="5min")
    # Fractional day index (0.0 .. 7.0), handy for daily cycles and event windows
    day_frac = np.array([(t - START_TIME).total_seconds() / 86400 for t in timestamps])
    hour_of_day = (day_frac % 1.0) * 24.0  # 0..24

    # --- Daily ambient / immersion temperature sine wave (pattern 8) ---
    # Peak at ~15:00 (hour 15), trough at ~05:00
    ambient_cycle = 1.5 * np.sin(2 * np.pi * (hour_of_day - 9) / 24.0)

    # --- Day-5 afternoon cooling partial failure window (pattern 5b) ---
    # Day 5 = day_frac 4.0..5.0; afternoon = hours 12-15 -> frac 4.5..4.625
    cooling_failure_mask = (day_frac >= 4.5) & (day_frac < 4.625)  # 3 hours
    cooling_bump = np.where(cooling_failure_mask, 6.0, 0.0)  # +6 degC fleet-wide

    rows = []

    for miner_id in MINER_IDS:
        n = total_points

        # ----- Base signals with noise (pattern 10) -----
        noise_hash = rng.normal(0, 2.0, n)
        noise_chip = rng.normal(0, 1.5, n)
        noise_imm = rng.normal(0, 0.8, n)
        noise_pres = rng.normal(0, 0.03, n)

        hashrate = HASH_BASE + noise_hash
        chip_temp = CHIP_TEMP_BASE + noise_chip + ambient_cycle * 0.6
        imm_temp = IMM_TEMP_BASE + noise_imm + ambient_cycle + cooling_bump
        pressure = PRESSURE_BASE + noise_pres

        # ----- Pattern 3: Degrading miners M003, M007 -----
        if miner_id in ("M003", "M007"):
            # Linear ramp over 7 days: chip temp rises +12 degC, hashrate drops -20 TH/s
            degradation = day_frac / DAYS  # 0..1
            chip_temp += 12.0 * degradation
            hashrate -= 20.0 * degradation

        # ----- Pattern 6: Peer outlier M009 (bad ASIC silicon) -----
        if miner_id == "M009":
            # Consistently ~15 TH/s below peers at same temps
            hashrate -= 15.0

        # ----- Pattern 7: Overcooled miner M010 -----
        if miner_id == "M010":
            # Much lower immersion temp, lower chip temp, but normal hashrate
            imm_temp = 42.0 + noise_imm * 0.5 + ambient_cycle * 0.4
            chip_temp = 65.0 + noise_chip * 0.5 + ambient_cycle * 0.3
            # hashrate stays at fleet-normal levels (no adjustment needed)

        # ----- Pattern 5a: M008 pressure spike on day 4 -----
        if miner_id == "M008":
            # Day 4 = day_frac 3.0..4.0; spike window ~30 min starting at hour 10
            spike_centre = 3.0 + 10.0 / 24.0  # day 4, 10:00
            spike_half = (30 / 2) / (24 * 60)  # 15 min in day-fraction
            dist_from_centre = np.abs(day_frac - spike_centre)
            spike_mask = dist_from_centre < spike_half
            # Triangular spike from 1.8 -> 2.5 bar (delta 0.7)
            spike_intensity = np.where(
                spike_mask,
                0.7 * (1.0 - dist_from_centre / spike_half),
                0.0,
            )
            pressure += spike_intensity

        # ----- Pattern 4: Intermittent failures M005 -----
        if miner_id == "M005":
            # ~6 offline episodes scattered across the week, each 15-60 min
            num_episodes = 6
            episode_starts = rng.uniform(0.5, 6.5, num_episodes)  # day-fraction
            episode_durations = rng.uniform(15, 60, num_episodes) / (24 * 60)  # in day-frac

            for start, dur in zip(episode_starts, episode_durations, strict=True):
                offline = (day_frac >= start) & (day_frac < start + dur)
                hashrate[offline] = 0.0
                chip_temp[offline] = imm_temp[offline]  # cools to coolant temp
                pressure[offline] = pressure[offline]  # pressure stays (loop still on)

        # ----- Pattern 2: Thermal throttling -----
        # Applied after all temp modifications so it captures degradation & cooling failure
        over_temp = np.maximum(chip_temp - THROTTLE_THRESHOLD_C, 0.0)
        hashrate -= THROTTLE_SLOPE * over_temp

        # Clamp to physical limits
        hashrate = np.clip(hashrate, 0.0, 150.0)
        chip_temp = np.clip(chip_temp, 30.0, 120.0)
        imm_temp = np.clip(imm_temp, 35.0, 75.0)
        pressure = np.clip(pressure, 1.0, 3.0)

        # ----- Pattern 9: ~1% random missing data (NaN) -----
        for arr in (hashrate, chip_temp, imm_temp, pressure):
            nan_mask = rng.random(n) < 0.01
            arr[nan_mask] = np.nan

        # Build per-miner frame
        miner_df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "miner_id": miner_id,
                "hashrate_ths": np.round(hashrate, 2),
                "chip_temp_c": np.round(chip_temp, 2),
                "immersion_temp_c": np.round(imm_temp, 2),
                "immersion_pressure_bar": np.round(pressure, 3),
            }
        )
        rows.append(miner_df)

    df = pd.concat(rows, ignore_index=True)
    df.sort_values(["timestamp", "miner_id"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating site telemetry (10 miners x 7 days @ 5-min intervals)...")
    data = generate_site_data()

    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "site_telemetry.csv")

    data.to_csv(out_path, index=False)
    print(f"Wrote {len(data):,} rows to {out_path}")
    print(f"Miners: {data['miner_id'].nunique()}")
    print(f"Time range: {data['timestamp'].min()} -> {data['timestamp'].max()}")
    print(
        f"NaN cells: {data.isna().sum().sum()} ({data.isna().sum().sum() / data.size * 100:.1f}%)"
    )
