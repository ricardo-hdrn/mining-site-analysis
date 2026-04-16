# Mining Site Operational Analysis

[![CI](https://github.com/ricardo-hdrn/mining-site-analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ricardo-hdrn/mining-site-analysis/actions/workflows/ci.yml)

Analysis system for bitcoin mining immersion-cooled site telemetry. Processes miner hashrate, chip temperature, and immersion cooling data to produce actionable, decision-oriented insights.

## Setup & Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas numpy scipy
python main.py
```

### Usage modes

```bash
python main.py                          # analyze data/site_telemetry.csv (provided sample)
python main.py path/to/custom_data.csv  # analyze any CSV with the expected columns
python main.py --generate               # generate extended dataset (10 miners, 7 days) and analyze it
```

The `--generate` flag writes to `data/generated_telemetry.csv` — the original sample is never overwritten.

Output is written to:
- **Console** — formatted report with severity-tagged insights
- `output/insights.json` — machine-readable insights
- `output/report.txt` — same report as console output

## Project Structure

```
├── main.py                  # Entry point — load data, run analyzers, generate report
├── src/
│   ├── data_generator.py    # Generates realistic 7-day, 10-miner telemetry dataset
│   └── analyzers.py         # Five analyzer modules matching the assessment categories
├── data/
│   └── site_telemetry.csv   # Generated telemetry (20,160 rows)
└── output/
    ├── insights.json         # Structured analysis results
    └── report.txt            # Human-readable report
```

## Approach & Reasoning

### Data Handling

The system works with any CSV containing the expected columns (`timestamp, miner_id, hashrate_ths, chip_temp_c, immersion_temp_c, immersion_pressure_bar`). The default `data/site_telemetry.csv` contains the provided 9-row sample dataset, which the analyzers process as-is.

The `--generate` flag produces an extended dataset: **10 miners over 7 days at 5-minute intervals** (20,160 rows), embedding realistic operational patterns for richer analysis:

- **Normal operation**: hashrate ~110 TH/s, chip temp 70–85°C, immersion temp 48–55°C, pressure 1.6–1.9 bar
- **Thermal throttling**: hashrate drops proportionally when chip temp exceeds 85°C (5 TH/s per degree)
- **Degrading miners** (M003, M007): gradual efficiency loss over 7 days
- **Intermittent failures** (M005): occasional crashes with offline periods
- **Cooling anomalies**: pressure spike on M008 (day 4), fleet-wide cooling degradation (day 5)
- **Peer outlier** (M009): consistently underperforms at same temperatures — bad hardware
- **Overcooled miner** (M010): excessive cooling with no performance benefit
- **Daily ambient cycle**: immersion temperature follows a diurnal sine wave

### Analysis System

Five analyzer modules, each producing structured insights with severity, numeric evidence, and recommended actions:

1. **Performance Analyzer** — Pearson correlation between hashrate and chip temperature per miner. Detects sustained deviation from baseline using rolling 30-min windows vs overall mean, flagging >10% drops.

2. **Hardware Risk Analyzer** — Flags chip temperatures exceeding 85°C (warning) / 90°C (critical) thresholds for immersion-cooled ASICs. Detects rapid temperature rises (>5°C in 10 min) that indicate coolant flow interruptions. Computes time-above-threshold per miner.

3. **Cooling Analyzer** — Detects pressure anomalies via absolute rate-of-change (>0.3 bar in 10 min). Identifies cooling degradation (immersion temp rising >3°C/hour while chip temp stable) and ineffective cooling (immersion dropping but chips still heating). These thresholds filter normal sensor noise while catching real events.

4. **Peer Comparison Analyzer** — Compares each miner against fleet median at each timestamp. Flags disproportionate hashrate loss at similar temperatures using hashrate residuals. Detects repeated anomaly patterns across multiple days — persistent patterns suggest hardware degradation vs transient issues.

5. **Optimization Analyzer** — Identifies miners with thermal headroom (chip <70°C) producing no hashrate benefit — candidates for overclocking or cooling redistribution. Computes cooling efficiency score (hashrate / thermal gradient) to rank fleet-wide cooling effectiveness.

### Design Decisions

- **Threshold-based detection over ML**: With 10 miners and 7 days, statistical methods (z-scores, correlation, rolling windows) are more interpretable and robust than training ML models. In production with thousands of miners, Isolation Forest or gradient boosting would add value.

- **Per-miner analysis loop**: Each analyzer iterates per miner to maintain context (baseline, trends). This is O(miners × timestamps) — linear and fast for operational fleet sizes.

- **Severity classification**: Critical/High/Warning/Info maps directly to operational urgency. Critical = act now, Warning = schedule inspection, Info = monitor.

- **Immersion cooling thresholds**: 85°C warning / 90°C critical are higher than air-cooled thresholds (~80/85°C) because immersion cooling allows chips to operate at higher temperatures safely, with more consistent heat dissipation.

## Insight & Threshold Documentation

- [INSIGHTS.md](INSIGHTS.md) — Reference of every insight type the system can emit, with triggers, severity levels, and metrics.
- [THRESHOLDS.md](THRESHOLDS.md) — Rationale behind every configurable threshold value.

## Threshold Rationale

All detection thresholds are defined in [`src/analyzers/base.py`](src/analyzers/base.py) with inline documentation. For the full rationale behind each value — sources, derivations, and production calibration notes — see [THRESHOLDS.md](THRESHOLDS.md).

## Key Assumptions

1. **Safe operating range**: Chip temp <85°C is normal for immersion-cooled ASICs; >90°C indicates risk
2. **Baseline hashrate**: Each miner's overall mean hashrate serves as its baseline — a production system would use a configurable nominal spec per model
3. **5-minute intervals**: Analysis window sizes (30 min for sustained deviation, 10 min for rapid spikes, 1 hour for cooling trends) are calibrated to 5-minute data frequency
4. **Fleet homogeneity**: Peer comparison assumes miners should perform similarly at similar temperatures — different miner models would require model-aware grouping
5. **Cooling system shared**: All miners share an immersion cooling loop — fleet-wide temperature rises indicate system-level events, not individual miner issues

## Generated Insights Summary

### On the provided sample (9 rows, 3 miners)

The system finds **10 insights**:

- **M001**: Critical — chip temp spiked 14°C in 10 min (78→92°C), causing hashrate to drop from 112→95 TH/s. Thermal throttling confirmed.
- **M003**: Critical — chip temp spiked 18°C in 10 min (80→98°C), hashrate crashed 115→70 TH/s, pressure spike from 1.8→2.1 bar. Simultaneous thermal and cooling anomaly.
- **M002**: Healthy — stable temperatures, consistent hashrate, no anomalies detected.

### On the extended sample (`--generate`, 20K rows, 10 miners)

The system produces **~55 insights**:

- **Performance**: M003/M007 show strong hashrate-temperature correlation (r=-0.90) and sustained degradation. M005 has intermittent complete outages.
- **Hardware Risk**: M003/M007 exceed critical temperature thresholds. Multiple miners show rapid temperature spikes indicating possible coolant flow interruptions.
- **Cooling**: M008 had a significant pressure spike (0.48 bar in 10 min). Fleet-wide cooling degradation events detected across multiple miners simultaneously.
- **Peer Comparison**: M009 underperforms in 90.6% of readings at similar temperatures — persistent hardware issue across all 7 days.
- **Optimization**: M010 operates 20°C below thermal limits with no hashrate advantage — candidate for overclocking or cooling reallocation.

## Production Extension

To extend this to a real-time production system integrated with MOS/MDK:

1. **Streaming ingestion**: Replace CSV loading with a time-series database (TimescaleDB, InfluxDB) or Hypercore/Hyperbee (MOS native storage). Analyzers would run on sliding windows via cron (matching MOS's 5m/30m/3h/1D aggregation schedule).

2. **Alerting integration**: Map insight severity to MOS alert levels. Critical insights trigger immediate notifications; warnings feed into the maintenance scheduling queue.

3. **Model-aware analysis**: Use MOS's `nominalHashrateMhs` and `nominalEfficiencyWThs` per miner type instead of fleet-derived baselines. Group peer comparisons by model (S21 vs M63 vs M56S).

4. **Adaptive thresholds**: Replace fixed thresholds with per-miner learned baselines that account for age, firmware version, and seasonal ambient conditions. EWMA-based drift detection would catch slow degradation earlier.

5. **Curtailment integration**: Connect cooling optimization insights to the `nextHourShouldMine` decision logic — miners with excessive cooling could absorb hash rate from overheated peers before curtailing to sleep mode.

6. **Historical trending**: Store daily analyzer outputs to track fleet health over months. Degradation slopes become predictive maintenance inputs for scheduling repairs during planned downtime windows.
