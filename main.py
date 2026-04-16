"""
Mining Site Operational Analysis — Entry Point.

Loads site telemetry data, runs all analyzers, and produces a formatted
console report, a JSON export, and a human-readable text file.

Usage:
    python main.py                          # uses data/site_telemetry.csv
    python main.py path/to/custom_data.csv  # uses your own dataset
    python main.py --generate               # generates sample data and analyzes it
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.analyzers import run_all_analyzers
from src.data_generator import generate_site_data

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "site_telemetry.csv"
GENERATED_DATA_PATH = BASE_DIR / "data" / "generated_telemetry.csv"
OUTPUT_DIR = BASE_DIR / "output"
INSIGHTS_JSON = OUTPUT_DIR / "insights.json"
REPORT_TXT = OUTPUT_DIR / "report.txt"

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------
CATEGORY_LABELS: dict[str, str] = {
    "performance": "PERFORMANCE IMPACT",
    "hardware_risk": "HARDWARE RISK",
    "cooling": "COOLING SYSTEM",
    "peer_comparison": "PEER COMPARISON",
    "optimization": "OPTIMIZATION OPPORTUNITIES",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "warning": 2, "info": 3}
SEVERITY_TAG = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "warning": "WARNING",
    "info": "INFO",
}

LINE_WIDTH = 80
DOUBLE_LINE = "=" * LINE_WIDTH
THIN_LINE = "\u2500" * LINE_WIDTH


# ---------------------------------------------------------------------------
# Data loading / generation
# ---------------------------------------------------------------------------


def load_data(path: Path | None = None) -> pd.DataFrame:
    """Load CSV from the given path, falling back to the default data path."""
    target = path or DATA_PATH
    if not target.exists():
        print(f"Error: data file not found at {target}")
        print("  Place your CSV in data/site_telemetry.csv or pass a path as argument.")
        print("  To generate sample data: python main.py --generate")
        sys.exit(1)

    print(f"Loading data from {target} ...")
    df = pd.read_csv(target, parse_dates=["timestamp"])
    return df


def generate_and_save() -> pd.DataFrame:
    """Generate extended telemetry to a separate file (preserves original data)."""
    print("Generating sample telemetry (10 miners x 7 days @ 5-min intervals) ...")
    df = generate_site_data()
    GENERATED_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(GENERATED_DATA_PATH, index=False)
    print(f"Saved {len(df):,} rows to {GENERATED_DATA_PATH}")
    return df


# ---------------------------------------------------------------------------
# Insight formatting
# ---------------------------------------------------------------------------


def _format_insight(insight: dict) -> str:
    """Render a single insight as a multi-line block."""
    tag = SEVERITY_TAG.get(insight["severity"], insight["severity"].upper())
    miner = insight.get("miner_id", "FLEET")
    itype = insight.get("type", "").replace("_", " ").title()

    lines = [f"  [{tag}] {miner} \u2014 {itype}"]

    detail = insight.get("detail", "")
    for dline in detail.split("\n"):
        lines.append(f"    {dline.strip()}")

    impact = insight.get("business_impact", {})
    if isinstance(impact, dict) and impact.get("status") == "estimated":
        lines.append(f"    \u25b8 Impact: {impact.get('summary', '')}")

    action = insight.get("action", "")
    if action:
        lines.append(f"    \u25b8 Action: {action}")

    return "\n".join(lines)


def _sort_insights(insights: list[dict]) -> list[dict]:
    """Sort by severity (critical first), then miner_id."""
    return sorted(
        insights,
        key=lambda i: (
            SEVERITY_ORDER.get(i.get("severity", "info"), 9),
            i.get("miner_id", ""),
        ),
    )


# ---------------------------------------------------------------------------
# Data quality assessment
# ---------------------------------------------------------------------------


def _assess_data_quality(df: pd.DataFrame) -> list[str]:
    """Check dataset quality and return warning/ok messages."""
    notes: list[str] = []
    n_miners = df["miner_id"].nunique()
    rows_per_miner = len(df) / max(n_miners, 1)
    time_span = df["timestamp"].max() - df["timestamp"].min()
    total_min = time_span.total_seconds() / 60
    missing_pct = df.isna().sum().sum() / df.size * 100

    if rows_per_miner < 10:
        notes.append(
            f"\u26a0 Only {rows_per_miner:.0f} readings per miner. "
            f"Correlation and trend analyses require longer observation windows."
        )
    if total_min < 60:
        notes.append(
            f"\u26a0 Dataset spans only {total_min:.0f} min. "
            f"Sustained deviation and cooling trend detection need \u22651 hour of data."
        )
    if n_miners < 3:
        notes.append(
            f"\u26a0 Only {n_miners} miner(s) — peer comparison has limited statistical power."
        )
    if missing_pct > 5:
        notes.append(f"\u26a0 {missing_pct:.1f}% missing values detected across the dataset.")
    elif missing_pct > 0:
        notes.append(f"\u2139 {missing_pct:.1f}% missing values — handled via NaN-safe operations.")
    else:
        notes.append("\u2713 No missing values detected.")

    if rows_per_miner >= 10 and total_min >= 60 and n_miners >= 3:
        notes.append("\u2713 Dataset size is sufficient for all analyses.")

    return notes


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_report(
    results: dict[str, list[dict]],
    df: pd.DataFrame,
    generated_at: str,
) -> str:
    """Build the full text report and return it as a string."""
    n_miners = df["miner_id"].nunique()
    time_span = df["timestamp"].max() - df["timestamp"].min()
    n_obs = len(df)

    if time_span.days >= 1:
        span_str = f"{time_span.days} days"
    else:
        total_min = int(time_span.total_seconds() / 60)
        span_str = (
            f"{total_min // 60}h {total_min % 60}m" if total_min >= 60 else f"{total_min} min"
        )

    lines: list[str] = []
    lines.append(DOUBLE_LINE)
    lines.append("  MINING SITE OPERATIONAL ANALYSIS \u2014 INSIGHTS REPORT")
    lines.append(DOUBLE_LINE)
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Data: {n_miners} miners, {span_str}, {n_obs:,} observations")
    lines.append(THIN_LINE)
    lines.append("")

    # --- Data quality notes ---
    quality_notes = _assess_data_quality(df)
    lines.append("DATA QUALITY")
    lines.append("\u2500" * 14)
    for note in quality_notes:
        lines.append(f"  {note}")
    lines.append("")

    # Flatten for counting / summary later
    all_insights: list[dict] = []
    section_num = 0

    for key, label in CATEGORY_LABELS.items():
        insights = results.get(key, [])
        if not insights:
            continue
        insights = _sort_insights(insights)
        all_insights.extend(insights)

        section_num += 1
        lines.append(f"{section_num}. {label}")
        lines.append("\u2500" * (len(label) + len(str(section_num)) + 2))

        for ins in insights:
            lines.append(_format_insight(ins))
            lines.append("")

    # --- Executive summary ---
    lines.append(DOUBLE_LINE)
    lines.append("  EXECUTIVE SUMMARY")
    lines.append(DOUBLE_LINE)
    lines.append("")

    severity_counts = {}
    for ins in all_insights:
        sev = SEVERITY_TAG.get(ins["severity"], ins["severity"].upper())
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    lines.append("Insights by severity:")
    for sev_key in ("CRITICAL", "HIGH", "WARNING", "INFO"):
        count = severity_counts.get(sev_key, 0)
        if count:
            lines.append(f"  {sev_key:10s}  {count}")
    lines.append(f"  {'TOTAL':10s}  {len(all_insights)}")
    lines.append("")

    # Top 3 priority actions (from highest-severity insights)
    priority = _sort_insights(all_insights)[:3]
    lines.append("Top priority actions:")
    for i, ins in enumerate(priority, 1):
        tag = SEVERITY_TAG.get(ins["severity"], ins["severity"].upper())
        miner = ins.get("miner_id", "FLEET")
        action = ins.get("action", "N/A")
        lines.append(f"  {i}. [{tag}] {miner}: {action}")
    lines.append("")

    # Fleet health score
    miners_with_issues: set[str] = set()
    for ins in all_insights:
        sev = ins.get("severity", "info")
        if sev in ("critical", "high", "warning"):
            mid = ins.get("miner_id", "")
            if mid and mid.lower() != "fleet":
                miners_with_issues.add(mid)

    healthy = n_miners - len(miners_with_issues)
    health_pct = healthy / n_miners * 100 if n_miners else 0
    lines.append(
        f"Fleet health score: {healthy}/{n_miners} miners with no issues ({health_pct:.0f}%)"
    )
    lines.append(THIN_LINE)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------


def _serialise_results(results: dict[str, list[dict]]) -> dict:
    """Make the results dict JSON-safe."""
    safe = {}
    for key, insights in results.items():
        safe[key] = []
        for ins in insights:
            entry = {}
            for k, v in ins.items():
                if isinstance(v, float) and (v != v):  # NaN check
                    entry[k] = None
                else:
                    entry[k] = v
            safe[key].append(entry)
    return safe


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Data — parse CLI args
    args = sys.argv[1:]
    if "--generate" in args:
        df = generate_and_save()
    elif args and not args[0].startswith("-"):
        df = load_data(Path(args[0]))
    else:
        df = load_data()

    # 2. Analysis
    print("Running analyzers ...")
    results = run_all_analyzers(df)

    total_insights = sum(len(v) for v in results.values())
    print(f"  {total_insights} insights generated across {len(results)} categories.\n")

    # 3. Console report
    report = build_report(results, df, generated_at)
    print(report)

    # 4. Persist outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(INSIGHTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(
            _serialise_results(results),
            fh,
            indent=2,
            default=str,
        )
    print(f"\nInsights saved to {INSIGHTS_JSON}")

    with open(REPORT_TXT, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"Report  saved to {REPORT_TXT}")


if __name__ == "__main__":
    main()
