from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input" / "rf"

# Strip emoji for sort keys (common Unicode blocks for symbols/pictographs/emoji).
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F9FF"  # Misc Symbols and Pictographs, etc.
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F680-\U0001F6FF"  # Transport and Map
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\u2600-\u26FF"  # Misc symbols
    "\u2700-\u27BF"  # Dingbats
    "]+",
    flags=re.UNICODE,
)


def _name_sort_key(name: str) -> str:
    """Normalise name for sorting: lowercase, no emoji."""
    cleaned = _EMOJI_PATTERN.sub("", name).strip().lower()
    return cleaned or name.lower()


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


def _load_submission_map(path: Path) -> Dict[tuple[str, str], str]:
    """Map (round_id, spotify_uri) -> submitter_id."""
    submission_map: Dict[tuple[str, str], str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            round_id = row["Round ID"]
            uri = row["Spotify URI"]
            submitter = row["Submitter ID"]
            submission_map[(round_id, uri)] = submitter
    return submission_map


def build_vote_matrix(
    votes_path: Path, submissions_path: Path, competitors: Dict[str, str]
) -> tuple[List[str], List[List[int]]]:
    """
    Build a matrix of total points each competitor has given to every other
    competitor (sum of points from positive votes only).
    """
    submission_map = _load_submission_map(submissions_path)

    # Use a stable, human-friendly ordering by competitor name.
    competitor_ids = sorted(competitors.keys(), key=lambda cid: _name_sort_key(competitors[cid]))
    names = [competitors[cid] for cid in competitor_ids]

    index_for: Dict[str, int] = {cid: idx for idx, cid in enumerate(competitor_ids)}
    size = len(competitor_ids)
    matrix: List[List[int]] = [[0 for _ in range(size)] for _ in range(size)]

    with votes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            voter_id = row["Voter ID"]
            points = int(row["Points Assigned"])
            round_id = row["Round ID"]
            uri = row["Spotify URI"]

            if points <= 0:
                continue

            submitter_id = submission_map.get((round_id, uri))
            if submitter_id is None:
                continue

            if voter_id == submitter_id:
                continue

            giver_idx = index_for.get(voter_id)
            receiver_idx = index_for.get(submitter_id)
            if giver_idx is None or receiver_idx is None:
                continue

            matrix[giver_idx][receiver_idx] += points

    return names, matrix


def build_top_tracks(
    votes_path: Path,
    submissions_path: Path,
    rounds_path: Path,
    competitors: Dict[str, str],
    top_n: int = 3,
) -> List[dict]:
    """
    Return top N tracks by total points received. Each item: title, artist, submitter_name, round_name, points.
    """
    submission_map = _load_submission_map(submissions_path)
    # (round_id, uri) -> total points
    track_points: Dict[tuple[str, str], int] = defaultdict(int)
    with votes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            round_id = row["Round ID"]
            uri = row["Spotify URI"]
            points = int(row["Points Assigned"])
            track_points[(round_id, uri)] += points

    # Build list of tracks with metadata from submissions
    round_names: Dict[str, str] = {}
    if rounds_path.exists():
        for rid, rname in load_rounds(rounds_path):
            round_names[rid] = rname

    tracks: List[dict] = []
    with submissions_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            round_id = row["Round ID"]
            uri = row["Spotify URI"]
            key = (round_id, uri)
            pts = track_points.get(key, 0)
            submitter_name = competitors.get(row["Submitter ID"], row["Submitter ID"])
            round_name = round_names.get(round_id, "Round")
            tracks.append(
                {
                    "title": row["Title"],
                    "artist": row["Artist(s)"],
                    "submitter_name": submitter_name,
                    "round_name": round_name,
                    "points": pts,
                }
            )

    tracks.sort(key=lambda t: t["points"], reverse=True)
    return tracks[:top_n]


def build_top_artists(
    votes_path: Path,
    submissions_path: Path,
    top_n: int = 3,
) -> List[dict]:
    """
    Return top N artists by total points received by their tracks. Each item: artist, points.
    """
    track_points: Dict[tuple[str, str], int] = defaultdict(int)
    with votes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            round_id = row["Round ID"]
            uri = row["Spotify URI"]
            points = int(row["Points Assigned"])
            track_points[(round_id, uri)] += points

    artist_points: Dict[str, int] = defaultdict(int)
    with submissions_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            round_id = row["Round ID"]
            uri = row["Spotify URI"]
            artist = row["Artist(s)"]
            pts = track_points.get((round_id, uri), 0)
            artist_points[artist] += pts

    sorted_artists = sorted(
        artist_points.items(),
        key=lambda x: x[1],
        reverse=True,
    )
    return [{"artist": a, "points": p} for a, p in sorted_artists[:top_n]]


def build_point_histogram(votes_path: Path) -> List[dict]:
    """
    Return histogram of point allocations across all votes: list of {points, count}
    for each point value from 0 to max observed, in order.
    """
    counts: Dict[int, int] = defaultdict(int)
    with votes_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pts = int(row["Points Assigned"])
            counts[pts] += 1
    if not counts:
        return []
    max_pts = max(counts.keys())
    return [{"points": p, "count": counts.get(p, 0)} for p in range(max_pts + 1)]


def load_rounds(path: Path) -> List[tuple[str, str]]:
    """Return list of (round_id, round_name) sorted by Created."""
    rows: List[tuple[str, str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((row["ID"], row["Name"], row["Created"]))
    rows.sort(key=lambda r: r[2])
    return [(r[0], r[1]) for r in rows]


def build_html(
    voters: List[VoterStats],
    matrix_names: List[str] | None = None,
    matrix: List[List[int]] | None = None,
    top_tracks: List[dict] | None = None,
    top_artists: List[dict] | None = None,
    point_histogram: List[dict] | None = None,
) -> str:
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

    if matrix_names is None:
        matrix_names = []
    if matrix is None:
        matrix = []
    if top_tracks is None:
        top_tracks = []
    if top_artists is None:
        top_artists = []
    if point_histogram is None:
        point_histogram = []

    # Minimal, self-contained HTML.
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Music League – Voter Stats</title>
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
        max-width: 2000px;
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
      .card + .card {{
        margin-top: 22px;
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
        overflow-y: auto;
        flex-shrink: 0;
        -webkit-overflow-scrolling: touch;
      }}

      @media (max-width: 600px) {{
        .chart-container {{
          height: 380px;
        }}
      }}

      .chart-container.histogram-chart {{
        height: auto;
        max-height: 320px;
        gap: 4px;
        overflow-y: visible;
        padding: 4px 2px 8px;
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

      .table-wrapper {{
        margin-top: 8px;
        border-radius: 12px;
        border: 1px solid rgba(31,41,55,0.9);
        background:
          linear-gradient(180deg, rgba(15,23,42,0.96), rgba(15,23,42,0.96));
        width: 100%;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }}

      .matrix-scroll {{
        display: block;
        width: 100%;
        min-width: max-content;
      }}

      table.matrix {{
        width: 100%;
        min-width: max-content;
        border-collapse: collapse;
        font-size: 0.75rem;
      }}

      table.matrix thead {{
        position: sticky;
        top: 0;
        z-index: 1;
        background: linear-gradient(180deg, rgba(15,23,42,0.96), rgba(15,23,42,0.96));
      }}

      table.matrix th,
      table.matrix td {{
        padding: 5px 7px;
        text-align: center;
        white-space: nowrap;
      }}

      table.matrix th:first-child,
      table.matrix td:first-child {{
        text-align: left;
        position: sticky;
        left: 0;
        z-index: 2;
        background: rgba(15,23,42,0.96);
        max-width: 170px;
        width: 170px;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
      }}

      table.matrix th {{
        font-size: 0.76rem;
        color: rgba(209,213,219,0.96);
        border-bottom: 1px solid rgba(31,41,55,0.9);
      }}

      table.matrix tbody td {{
        font-variant-numeric: tabular-nums;
        color: rgba(148,163,184,0.96);
        border-bottom: 1px solid rgba(17,24,39,0.6);
      }}

      table.matrix tbody tr:nth-child(odd) td {{
        background: rgba(15,23,42,0.96);
      }}

      table.matrix tbody tr:nth-child(even) td {{
        background: rgba(15,23,42,0.9);
      }}

      table.matrix td.matrix-cell {{
        color: #fefce8;
      }}

      table.matrix td.nonzero {{
        font-weight: 500;
      }}

      table.matrix td.diagonal-cell {{
        background: #000 !important;
        color: rgba(148,163,184,0.96);
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
      .matrix-caption {{
        margin-top: 12px;
        font-size: 0.9rem;
        color: rgba(156,163,175,0.9);
        line-height: 1.5;
      }}

      .top-tracks-list {{
        list-style: none;
        margin: 0;
        padding: 0;
      }}
      .top-track-item {{
        padding: 12px 0;
        border-bottom: 1px solid rgba(31,41,55,0.9);
        font-size: 0.9rem;
      }}
      .top-track-item:last-child {{
        border-bottom: none;
      }}
      .top-track-title {{
        color: rgba(209,213,219,0.96);
        font-weight: 500;
      }}
      .top-track-meta {{
        color: rgba(156,163,175,0.9);
        font-size: 0.85rem;
        margin-top: 4px;
      }}
      .top-track-points {{
        font-variant-numeric: tabular-nums;
        color: rgba(251,191,36,0.95);
      }}

      .page-footer {{
        margin-top: 28px;
        font-size: 0.85rem;
        text-align: center;
      }}
      .page-footer .credit {{
        display: block;
        margin-top: 4px;
        color: rgba(148,163,184,0.8);
      }}
      .page-footer a {{
        color: rgba(148,163,184,0.9);
        text-decoration: none;
      }}
      .page-footer a:hover {{
        color: rgba(209,213,219,0.96);
        text-decoration: underline;
      }}
    </style>
  </head>
  <body>
    <main class="page">
      <header>
        <h1>Vote Stats</h1>
      </header>

      <section class="card">
        <div class="card-inner">
          <h2>Vote Generosity</h2>
          <div class="chart-container" id="generosity-chart"></div>
          <p class="matrix-caption">
            Generosity is the average points each voter gives out per track they rate with positive votes. High averages mean someone tends to hand out bigger scores rather than spreading them out.
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-inner">
          <h2>Top 3 Tracks</h2>
          <div id="top-tracks"></div>
          <p class="matrix-caption">
            Tracks with the most points across all rounds.
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-inner">
          <h2>Top 3 Artists</h2>
          <div id="top-artists"></div>
          <p class="matrix-caption">
            Artists whose tracks received the most points across all rounds.
          </p>
        </div>
      </section>

      <section class="card matrix-card">
        <div class="card-inner">
          <h2>Vote Distribution</h2>
          <div class="table-wrapper" id="vote-matrix"></div>
          <p class="matrix-caption">
            Rows = voter (the person giving points).
            Column headers = receiver (the person who submitted the track).
            Cell at (row, column) = total points the row person gave to the column person's tracks (sum of all positive points across rounds).
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-inner">
          <h2>Point Allocation</h2>
          <div class="chart-container histogram-chart" id="point-histogram"></div>
          <p class="matrix-caption">
            How many times each point value was given across the entire league.
          </p>
        </div>
      </section>

      <footer class="page-footer">
        <a href="https://github.com/davidmn/music-league-stats" target="_blank" rel="noopener noreferrer">GitHub</a>
        <span class="credit">Made by MegaSlippers</span>
      </footer>
    </main>

    <script>
      const chartLabels = {json.dumps(chart_labels)};
      const chartValues = {json.dumps(chart_values)};
      const voters = {json.dumps(table_rows)};
      const matrixNames = {json.dumps(matrix_names)};
      const matrix = {json.dumps(matrix)};
      const topTracks = {json.dumps(top_tracks)};
      const topArtists = {json.dumps(top_artists)};
      const pointHistogram = {json.dumps(point_histogram)};

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

      function truncName(name, max) {{
        if (!name) return "";
        if (name.length <= max) return name;
        return name.slice(0, max - 1) + "…";
      }}

      function renderPointHistogram() {{
        const container = document.getElementById("point-histogram");
        if (!container) return;

        container.innerHTML = "";

        if (!pointHistogram.length) {{
          const empty = document.createElement("div");
          empty.className = "muted";
          empty.textContent = "No vote data available.";
          container.appendChild(empty);
          return;
        }}

        const maxCount = Math.max.apply(null, pointHistogram.map(function(d) {{ return d.count; }}));

        pointHistogram.forEach(function(d) {{
          const row = document.createElement("div");
          row.className = "bar-row";
          const nameEl = document.createElement("div");
          nameEl.className = "bar-label";
          nameEl.textContent = d.points + " pt" + (d.points === 1 ? "" : "s");
          const track = document.createElement("div");
          track.className = "bar-track";
          const fill = document.createElement("div");
          fill.className = "bar-fill";
          const widthPct = maxCount > 0 ? (d.count / maxCount) * 100 : 0;
          fill.style.width = widthPct.toFixed(1) + "%";
          track.appendChild(fill);
          const valueEl = document.createElement("div");
          valueEl.className = "bar-value";
          valueEl.textContent = String(d.count);
          row.appendChild(nameEl);
          row.appendChild(track);
          row.appendChild(valueEl);
          container.appendChild(row);
        }});
      }}

      function renderTopTracks() {{
        const container = document.getElementById("top-tracks");
        if (!container) return;

        container.innerHTML = "";

        if (!topTracks.length) {{
          const empty = document.createElement("p");
          empty.className = "muted";
          empty.textContent = "No track data available.";
          container.appendChild(empty);
          return;
        }}

        const ul = document.createElement("ul");
        ul.className = "top-tracks-list";
        topTracks.forEach(function(t, idx) {{
          const li = document.createElement("li");
          li.className = "top-track-item";
          const title = document.createElement("div");
          title.className = "top-track-title";
          title.textContent = (idx + 1) + ". " + t.title;
          const meta = document.createElement("div");
          meta.className = "top-track-meta";
          meta.textContent = t.artist + " · " + t.round_name + " · submitted by " + t.submitter_name + " · ";
          const pts = document.createElement("span");
          pts.className = "top-track-points";
          pts.textContent = t.points + " pts";
          meta.appendChild(pts);
          li.appendChild(title);
          li.appendChild(meta);
          ul.appendChild(li);
        }});
        container.appendChild(ul);
      }}

      function renderTopArtists() {{
        const container = document.getElementById("top-artists");
        if (!container) return;

        container.innerHTML = "";

        if (!topArtists.length) {{
          const empty = document.createElement("p");
          empty.className = "muted";
          empty.textContent = "No artist data available.";
          container.appendChild(empty);
          return;
        }}

        const ul = document.createElement("ul");
        ul.className = "top-tracks-list";
        topArtists.forEach(function(t, idx) {{
          const li = document.createElement("li");
          li.className = "top-track-item";
          const title = document.createElement("div");
          title.className = "top-track-title";
          title.textContent = (idx + 1) + ". " + t.artist;
          const meta = document.createElement("div");
          meta.className = "top-track-meta";
          const pts = document.createElement("span");
          pts.className = "top-track-points";
          pts.textContent = t.points + " pts";
          meta.appendChild(pts);
          li.appendChild(title);
          li.appendChild(meta);
          ul.appendChild(li);
        }});
        container.appendChild(ul);
      }}

      function renderMatrix() {{
        const container = document.getElementById("vote-matrix");
        if (!container) return;

        container.innerHTML = "";

        if (!matrixNames.length) {{
          const empty = document.createElement("div");
          empty.className = "muted";
          empty.textContent = "No vote data available.";
          container.appendChild(empty);
          return;
        }}

        const scrollDiv = document.createElement("div");
        scrollDiv.className = "matrix-scroll";

        const table = document.createElement("table");
        table.className = "matrix";

        // Find global min/max to normalise the colour scale (yellow at min, blue at max).
        let minCell = 0;
        let maxCell = 0;
        let seen = false;
        matrix.forEach((row) => {{
          (row || []).forEach((val) => {{
            if (!seen) {{ minCell = val; maxCell = val; seen = true; }}
            else {{ if (val < minCell) minCell = val; if (val > maxCell) maxCell = val; }}
          }});
        }});
        const range = maxCell - minCell;

        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");

        const corner = document.createElement("th");
        corner.textContent = "";
        headRow.appendChild(corner);

        matrixNames.forEach((name) => {{
          const th = document.createElement("th");
          th.textContent = truncName(name, 8);
          th.title = name;
          headRow.appendChild(th);
        }});

        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement("tbody");

        matrixNames.forEach((giverName, rowIdx) => {{
          const tr = document.createElement("tr");

          const rowHeader = document.createElement("th");
          rowHeader.textContent = truncName(giverName, 22);
          rowHeader.title = giverName;
          tr.appendChild(rowHeader);

          const rowData = matrix[rowIdx] || [];
          matrixNames.forEach((_, colIdx) => {{
            const td = document.createElement("td");
            const value = rowData[colIdx] ?? 0;
            td.textContent = rowIdx === colIdx ? "–" : String(value);

            if (rowIdx === colIdx) {{
              td.classList.add("matrix-cell", "diagonal-cell");
            }} else if (range > 0) {{
              const t = (value - minCell) / range; // 0 = min (yellow), 1 = max (blue)
              const r = Math.round(251 + (56 - 251) * t);
              const g = Math.round(191 + (189 - 191) * t);
              const b = Math.round(36 + (248 - 36) * t);
              const alpha = 0.45 + 0.5 * t;
              td.classList.add("matrix-cell");
              td.style.backgroundColor = `rgba(${{r}}, ${{g}}, ${{b}}, ${{alpha.toFixed(2)}})`;
              if (value > 0) td.classList.add("nonzero");
            }} else if (value > 0) {{
              td.classList.add("nonzero");
            }}

            tr.appendChild(td);
          }});

          tbody.appendChild(tr);
        }});

        table.appendChild(tbody);
        scrollDiv.appendChild(table);
        container.appendChild(scrollDiv);
      }}

      renderChart();
      renderPointHistogram();
      renderTopTracks();
      renderTopArtists();
      renderMatrix();
    </script>
  </body>
</html>
"""
    return html


def main() -> None:
    competitors_csv = INPUT_DIR / "competitors.csv"
    votes_csv = INPUT_DIR / "votes.csv"
    submissions_csv = INPUT_DIR / "submissions.csv"
    rounds_csv = INPUT_DIR / "rounds.csv"

    competitors = load_competitors(competitors_csv)
    voter_stats = load_voter_stats(votes_csv, competitors)
    matrix_names, matrix = build_vote_matrix(votes_csv, submissions_csv, competitors)
    top_tracks = build_top_tracks(votes_csv, submissions_csv, rounds_csv, competitors, top_n=3)
    top_artists = build_top_artists(votes_csv, submissions_csv, top_n=3)
    point_histogram = build_point_histogram(votes_csv)

    html = build_html(
        voter_stats,
        matrix_names,
        matrix,
        top_tracks=top_tracks,
        top_artists=top_artists,
        point_histogram=point_histogram,
    )
    output_path = BASE_DIR / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path.relative_to(BASE_DIR)} with {len(voter_stats)} voters.")


if __name__ == "__main__":
    main()

