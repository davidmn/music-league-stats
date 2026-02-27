from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input" / "rf"


@dataclass
class VoterStats:
    voter_id: str
    name: str
    total_points: int = 0
    num_votes: int = 0
    num_positive_votes: int = 0

    @property
    def avg_points_per_vote(self) -> float:
        if self.num_votes == 0:
            return 0.0
        return self.total_points / self.num_votes

    @property
    def avg_points_when_positive(self) -> float:
        if self.num_positive_votes == 0:
            return 0.0
        return self.total_points / self.num_positive_votes


def load_competitors(path: Path) -> Dict[str, str]:
    competitors: Dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            competitors[row["ID"]] = row["Name"]
    return competitors


def load_voter_stats(votes_path: Path, competitors: Dict[str, str]) -> List[VoterStats]:
    stats_map: Dict[str, VoterStats] = {}

    with votes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            voter_id = row["Voter ID"]
            points = int(row["Points Assigned"])

            if voter_id not in stats_map:
                name = competitors.get(voter_id, voter_id)
                stats_map[voter_id] = VoterStats(voter_id=voter_id, name=name)

            s = stats_map[voter_id]
            s.total_points += points
            s.num_votes += 1
            if points > 0:
                s.num_positive_votes += 1

    return list(stats_map.values())


def build_html(voters: List[VoterStats]) -> str:
    # Sort most generous first by average points per vote, then by total points.
    voters_sorted = sorted(
        voters,
        key=lambda v: (v.avg_points_per_vote, v.total_points),
        reverse=True,
    )

    chart_labels = [v.name for v in voters_sorted]
    chart_values = [round(v.avg_points_per_vote, 2) for v in voters_sorted]

    table_rows = []
    for rank, v in enumerate(voters_sorted, start=1):
        table_rows.append(
            {
                "rank": rank,
                "name": v.name,
                "total_points": v.total_points,
                "num_votes": v.num_votes,
                "num_positive_votes": v.num_positive_votes,
                "avg_points_per_vote": round(v.avg_points_per_vote, 2),
                "avg_points_when_positive": round(v.avg_points_when_positive, 2),
            }
        )

    # Minimal, self-contained HTML with Chart.js from CDN.
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Music League – Voter Generosity</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root {{
        color-scheme: dark light;
        --bg: #050816;
        --bg-alt: #0b1020;
        --fg: #f9fafb;
        --muted: #9ca3af;
        --accent: #fbbf24;
        --accent-soft: rgba(251, 191, 36, 0.2);
        --border: #1f2937;
        --card-radius: 16px;
        --shadow-soft: 0 18px 45px rgba(15,23,42,0.75);
        --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
                     "Segoe UI", sans-serif;
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        min-height: 100vh;
        font-family: var(--font-sans);
        background: radial-gradient(circle at top, #111827 0, #020617 55%, #000 100%);
        color: var(--fg);
        -webkit-font-smoothing: antialiased;
      }}

      .page {{
        max-width: 1080px;
        margin: 0 auto;
        padding: 32px 20px 40px;
      }}

      header {{
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-bottom: 28px;
      }}

      h1 {{
        font-size: 2rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin: 0;
        display: inline-flex;
        align-items: baseline;
        gap: 10px;
      }}

      header p {{
        margin: 0;
        color: var(--muted);
        max-width: 100%;
        line-height: 1.5;
      }}

      .card {{
        background:
          linear-gradient(145deg, rgba(15,23,42,0.96), rgba(15,23,42,0.88))
          padding-box;
        border-radius: var(--card-radius);
        border: 1px solid rgba(148,163,184,0.16);
        box-shadow: var(--shadow-soft);
        padding: 18px 18px 16px;
        position: relative;
        overflow: hidden;
      }}

      .card::before {{
        content: "";
        position: absolute;
        inset: -120px;
        background:
          radial-gradient(circle at 0 0, rgba(251,191,36,0.12), transparent 60%),
          radial-gradient(circle at 100% 0, rgba(56,189,248,0.16), transparent 60%);
        opacity: 0.75;
        pointer-events: none;
      }}

      .card-inner {{
        position: relative;
        z-index: 1;
      }}

      .card h2 {{
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: rgba(156,163,175,0.9);
        margin: 0 0 8px;
      }}

      .card h2 strong {{
        color: #e5e7eb;
      }}

      .chart-container {{
        position: relative;
        height: 420px;
        max-height: 70vh;
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 4px 2px 8px;
      }}

      @media (max-width: 600px) {{
        .chart-container {{
          height: 380px;
        }}
      }}

      .bar-row {{
        display: grid;
        grid-template-columns: minmax(0, 220px) minmax(0, 1fr) auto;
        align-items: center;
        gap: 8px;
        font-size: 0.76rem;
      }}

      .bar-label {{
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: rgba(209,213,219,0.96);
      }}

      .bar-track {{
        position: relative;
        height: 6px;
        border-radius: 999px;
        background: rgba(15,23,42,0.96);
        overflow: hidden;
      }}

      .bar-fill {{
        position: absolute;
        inset: 0;
        border-radius: inherit;
        background: linear-gradient(90deg, rgba(251,191,36,0.2), rgba(251,191,36,0.95), rgba(56,189,248,0.95));
        box-shadow: 0 0 0 1px rgba(15,23,42,0.9);
      }}

      .bar-value {{
        font-variant-numeric: tabular-nums;
        color: rgba(156,163,175,0.96);
      }}

      .rank-pill {{
        display: inline-flex;
        min-width: 1.7em;
        align-items: center;
        justify-content: center;
        padding: 1px 6px;
        border-radius: 999px;
        font-variant-numeric: tabular-nums;
        font-size: 0.72rem;
        background: rgba(15,23,42,0.9);
        border: 1px solid rgba(55,65,81,0.95);
        color: rgba(209,213,219,0.95);
      }}

      .rank-1 .rank-pill {{
        border-color: rgba(251,191,36,0.9);
        color: #fef3c7;
        background: radial-gradient(circle at top, rgba(251,191,36,0.3), rgba(15,23,42,0.95));
      }}

      .rank-2 .rank-pill {{
        border-color: rgba(156,163,175,0.95);
      }}

      .rank-3 .rank-pill {{
        border-color: rgba(248,113,113,0.9);
      }}

      .pill-name {{
        font-size: 0.82rem;
        font-weight: 500;
      }}

      .muted {{
        color: rgba(156,163,175,0.9);
      }}

      footer {{
        margin-top: 20px;
        font-size: 0.75rem;
        color: rgba(148,163,184,0.9);
      }}
    </style>
  </head>
  <body>
    <main class="page">
      <header>
        <h1>Voter Generosity</h1>
        <p>
          <strong>Generosity</strong> here is defined as the
          <strong>average points each voter gives out per track they rate</strong>.
          High averages mean someone tends to hand out bigger scores rather than spreading them out.
        </p>
      </header>

      <section class="card">
        <div class="card-inner">
          <h2>League generosity</h2>
          <div class="chart-container" id="generosity-chart"></div>
        </div>
      </section>
    </main>

    <script>
      const chartLabels = {json.dumps(chart_labels)};
      const chartValues = {json.dumps(chart_values)};
      const voters = {json.dumps(table_rows)};

      function renderChart() {{
        const container = document.getElementById("generosity-chart");
        if (!container) return;

        container.innerHTML = "";

        if (!chartLabels.length) {{
          const empty = document.createElement("div");
          empty.className = "muted";
          empty.textContent = "No voters found.";
          container.appendChild(empty);
          return;
        }}

        const maxValue = Math.max.apply(null, chartValues);

        chartLabels.forEach((label, idx) => {{
          const value = chartValues[idx];
          const row = document.createElement("div");
          row.className = "bar-row";

          const nameEl = document.createElement("div");
          nameEl.className = "bar-label";
          nameEl.textContent = label;

          const track = document.createElement("div");
          track.className = "bar-track";

          const fill = document.createElement("div");
          fill.className = "bar-fill";
          const widthPct = maxValue > 0 ? (value / maxValue) * 100 : 0;
          fill.style.width = widthPct.toFixed(1) + "%";

          track.appendChild(fill);

          const valueEl = document.createElement("div");
          valueEl.className = "bar-value";
          valueEl.textContent = value.toFixed(2);

          row.appendChild(nameEl);
          row.appendChild(track);
          row.appendChild(valueEl);

          container.appendChild(row);
        }});
      }}

      renderChart();
    </script>
  </body>
</html>
"""
    return html


def main() -> None:
    competitors_csv = INPUT_DIR / "competitors.csv"
    votes_csv = INPUT_DIR / "votes.csv"

    competitors = load_competitors(competitors_csv)
    voter_stats = load_voter_stats(votes_csv, competitors)

    html = build_html(voter_stats)
    output_path = BASE_DIR / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path.relative_to(BASE_DIR)} with {len(voter_stats)} voters.")


if __name__ == "__main__":
    main()

