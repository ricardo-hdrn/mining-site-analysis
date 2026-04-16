# Threshold Rationale

All configurable thresholds are defined in [`src/analyzers/base.py`](src/analyzers/base.py). This document explains the reasoning behind each value.

## Thermal Thresholds

| Parameter | Value | Source |
|---|---|---|
| `CHIP_TEMP_WARNING` | 85°C | Bitmain S19/S21 max junction temp is ~95-105°C per datasheet. 85°C gives operational margin before throttling. Immersion cooling allows ~5°C higher than air-cooled (~80°C) due to superior heat dissipation. |
| `CHIP_TEMP_CRITICAL` | 90°C | ~5°C below manufacturer hard limits. At this point thermal throttling is active and hardware lifespan is being reduced. |
| `RAPID_TEMP_RISE` | 5°C | Normal reading-to-reading fluctuation is ±1-2°C. A 5°C jump in 10 min indicates a step-change event (pump failure, coolant blockage), not gradual drift. Validated by sample data: M001 jumps 14°C and M003 jumps 18°C — both clearly abnormal. |
| `COOL_UNDERUTILISED_TEMP` | 70°C | 15°C below warning threshold. In immersion, this much headroom means cooling energy is being wasted — the miner could be overclocked or its cooling shared with hotter units. |

## Time Windows

| Parameter | Value | Purpose |
|---|---|---|
| `RAPID_TEMP_WINDOW_MIN` | 10 min | **Acute event detection.** At 5-min sampling, this is 2 readings — catches single-interval spikes and short ramps without diluting gradual warming into false positives. |
| `SUSTAINED_MINUTES` | 30 min | **Chronic problem confirmation.** A 5-min hashrate dip can be pool latency or share luck. 30 min (6 readings) confirms a real operational issue. |
| `COOLING_TREND_WINDOW_HOURS` | 1 hour | **Cooling trend analysis.** Smooths short-term fluctuations while catching real degradation events. Normal diurnal drift is <1°C/hour. |

## Hashrate Thresholds

| Parameter | Value | Source |
|---|---|---|
| `HASHRATE_DEVIATION_PCT` | 10% | Standard industrial SPC threshold for "out of normal range." Smaller values catch too much sensor noise. |
| `HASHRATE_DEVIATION_SEVERE` | 20% | Severe deviation — likely hardware failure or thermal throttling, not normal variance. |

## Correlation (Pearson r)

| Parameter | Value | Source |
|---|---|---|
| `CORRELATION_THRESHOLD` | -0.5 | Cohen's conventions: r > 0.5 is a "large effect." Below -0.5 means temperature is strongly impacting hashrate. |
| `CORRELATION_CRITICAL` | -0.8 | Near-deterministic relationship — this miner's hashrate is dominated by thermal throttling. |
| `CORRELATION_HIGH` | -0.6 | Strong but not total — thermal stress is a significant factor but not the only one. |
| `P_VALUE_THRESHOLD` | 0.05 | Standard statistical significance. With >2000 readings per miner, even moderate effects are significant. |

## Pressure Thresholds

| Parameter | Value | Source |
|---|---|---|
| `PRESSURE_ABSOLUTE_CHANGE` | 0.3 bar | Derived from sample data: M003 shows 1.8→2.1 bar (Δ=0.3) in one interval — the smallest change clearly anomalous in the provided data. |
| `PRESSURE_CRITICAL_CHANGE` | 0.5 bar | >25% of normal operating pressure (~1.8 bar). Indicates a severe event — potential rupture, major leak, or pump cavitation. |

## Cooling Analysis

| Parameter | Value | Source |
|---|---|---|
| `COOLING_TEMP_RISE_RATE` | 3°C/hour | Normal immersion temp drift is <1°C/hour (diurnal cycle). A 3°C/hour rise with stable chip temp means the cooling system is losing capacity. |
| `COOLING_CHIP_STABLE` | 2°C/hour | Chip temp variation below this is considered "stable" — filters normal operating noise from real trends. |
| `COOLING_EFFECTIVENESS_THRESHOLD` | 0.4 | Ratio of (chip−immersion)/chip. In well-functioning immersion, the gradient is typically 30-35% of chip temp. Above 40% indicates poor thermal interface. |

## Peer Comparison

| Parameter | Value | Source |
|---|---|---|
| `PEER_TEMP_SIMILARITY` | 5°C | Miners in the same immersion tank share ambient conditions. ±5°C covers manufacturing variance; beyond that, operating conditions differ. |
| `PEER_HASHRATE_FLOOR` | 10% | 10% below fleet median at the same temperature = hardware problem, not environment. |
| `PEER_CRITICAL_PCT` | 30% | Anomalous in >30% of readings — persistent, severe hardware issue. |
| `PEER_WARNING_PCT` | 10% | Anomalous in >10% of readings — recurring pattern worth investigating. |

## Optimization

| Parameter | Value | Source |
|---|---|---|
| `HASHRATE_HEADROOM_TOLERANCE` | 1.05 | 5% above fleet median to count as "benefiting from cooling." Below this, the extra cooling isn't producing extra hashrate. |
| `EXCESSIVE_COOLING_RATIO` | 0.90 | Immersion temp below 90% of fleet median = meaningfully overcooled (>10% colder than peers). |

## Production Notes

## Business Impact Estimation

| Parameter | Value | Source |
|---|---|---|
| `HASH_PRICE_USD_PER_TH_DAY` | $0.045 | Revenue earned per TH/s per day. Encapsulates BTC price, network difficulty, and block reward. ~$0.045 is approximate as of early 2025. In production, fetched from mempool.space or similar API. |
| `THROTTLE_SLOPE_THS_PER_C` | 5.0 TH/s per °C | Approximate hashrate loss per degree above critical threshold due to firmware thermal throttling. Derived from observed sample data behavior. |

Business impact is computed as a **separate enrichment pass** after detection (see `src/analyzers/business_impact.py`). This keeps economics decoupled from signal processing — analyzers detect, the enricher translates to dollars.

## Production Notes

In a production deployment, these thresholds should be:
- **Configurable per miner model** (S21 vs M56S have different thermal envelopes)
- **Calibrated against historical site data** (6+ months of baseline operation)
- **Adaptive** via EWMA or Bayesian methods to account for seasonal changes and fleet aging
