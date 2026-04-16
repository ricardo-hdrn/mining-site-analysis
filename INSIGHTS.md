# Insight Reference

Every insight emitted by the system follows a standard structure:

```json
{
  "miner_id": "M003",
  "type": "performance_degradation",
  "severity": "critical",
  "detail": "Human-readable explanation with numeric evidence.",
  "metric": -0.90,
  "action": "Recommended operational response.",
  "business_impact": "Est. avg 19.2 TH/s lost (~$0.87/day at $0.045/TH/day)."
}
```

The `business_impact` field is optional — present only on insight types where revenue impact is directly estimable (see Business Impact section below).

Severity levels: `critical` → act now, `high` → act today, `warning` → schedule inspection, `info` → monitor.

---

## 1. Performance Impact

| Type | Severity | Trigger | Metric |
|---|---|---|---|
| `performance_degradation` | critical / high / warning | Pearson r between hashrate and chip temp < -0.5 (p < 0.05). Severity tiers at r < -0.8 (critical), r < -0.6 (high). | Pearson r value |
| `sustained_underperformance` | high / warning | Rolling 30-min mean hashrate deviates >10% below miner's median baseline. High if >20%. | Worst deviation (fraction) |

## 2. Hardware Risk

| Type | Severity | Trigger | Metric |
|---|---|---|---|
| `critical_temperature` | critical | Chip temp exceeded 90°C in any reading. | Max temperature (°C) |
| `temperature_warning` | warning | Chip temp exceeded 85°C (but not 90°C). | Max temperature (°C) |
| `rapid_temperature_rise` | critical / warning | Chip temp rose >5°C in 10 min. Critical if >10°C. | Worst spike (°C) |
| `time_above_threshold` | info | Any time spent above 85°C warning threshold. | Total minutes above |

## 3. Cooling System

| Type | Severity | Trigger | Metric |
|---|---|---|---|
| `pressure_anomaly` | critical / warning | Pressure changed >0.3 bar in 10 min. Critical if >0.5 bar. | Worst change (bar) |
| `cooling_degradation` | warning | Immersion temp rising >3°C/hour while chip temp stable (<2°C/hour). Cooling system can't reject heat. | Count of intervals |
| `cooling_ineffective` | warning | Immersion temp dropping >3°C/hour but chip temp rising >2°C/hour. Cooling active but not reaching chips. | Count of intervals |
| `poor_cooling_effectiveness` | warning | Mean (chip−immersion)/chip ratio > 0.4. Poor thermal coupling between chip and coolant. | Effectiveness ratio |

## 4. Peer Comparison

| Type | Severity | Trigger | Metric |
|---|---|---|---|
| `peer_underperformance` | critical / warning / info | Hashrate >10% below fleet median at similar temperatures (±5°C). Critical if >30% of readings, warning if >10%. | % of readings flagged |
| `peer_anomaly_repeated_daily` | warning | Underperformance detected across >1 distinct day — persistent pattern. | Number of days |
| `peer_anomaly_ranking` | info | Fleet-level summary: top 10 miners ranked by anomaly frequency. | Count of ranked miners |

## 5. Optimization Opportunities

| Type | Severity | Trigger | Metric |
|---|---|---|---|
| `thermal_headroom` | info | Chip temp <70°C but hashrate not above fleet median — overcooled with no benefit. | Headroom (°C below warning) |
| `excessive_cooling` | info | Immersion temp <90% of fleet median but hashrate not above fleet median. | Immersion temp (°C) |
| `low_cooling_efficiency` | warning | Cooling efficiency score (hashrate/ΔT) more than 1σ below fleet mean. | Score (TH/s per °C) |

## Business Impact Enrichment

A separate post-processing pass (`src/analyzers/business_impact.py`) adds an optional `business_impact` field to insights where revenue impact is directly estimable. This keeps economics decoupled from detection logic.

| Insight Type | Impact Estimation Method |
|---|---|
| `performance_degradation` | Avg hashrate loss (max - mean) × hash price |
| `sustained_underperformance` | Peak deviation × baseline hashrate × hash price |
| `critical_temperature` | Throttling estimate (5 TH/s per °C above 90°C) × % time in critical × hash price |
| `peer_underperformance` | Avg gap below fleet median × hash price |
| `thermal_headroom` | Conservative overclock potential (1 TH/s per 3°C headroom) × hash price |

Types not listed (pressure anomalies, cooling degradation/ineffective, time above threshold, etc.) represent *risk* signals without directly measurable hashrate loss — no `business_impact` is added.
