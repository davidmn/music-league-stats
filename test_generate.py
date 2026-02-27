import textwrap
from pathlib import Path

import generate


def write_csv(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def test_load_competitors_reads_ids_and_names(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "competitors.csv",
        """
        ID,Name
        a1,Alice
        b2,Bob
        """,
    )

    result = generate.load_competitors(csv_path)

    assert result == {"a1": "Alice", "b2": "Bob"}


def test_load_voter_stats_aggregates_points_and_votes(tmp_path):
    competitors = {"v1": "Voter One", "v2": "Voter Two"}
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        track1,v1,2026-02-10T00:00:00Z,3,,r1
        track2,v1,2026-02-10T00:00:00Z,0,,r1
        track3,v1,2026-02-10T00:00:00Z,1,,r1
        track4,v2,2026-02-10T00:00:00Z,0,,r1
        """,
    )

    stats = generate.load_voter_stats(votes_csv, competitors)

    stats_by_id = {s.voter_id: s for s in stats}

    v1 = stats_by_id["v1"]
    assert v1.name == "Voter One"
    assert v1.total_points == 4
    assert v1.num_votes == 3
    assert v1.num_positive_votes == 2  # 3 and 1 are positive
    assert v1.avg_points_per_vote == 4 / 3
    assert v1.avg_points_when_positive == 4 / 2

    v2 = stats_by_id["v2"]
    assert v2.name == "Voter Two"
    assert v2.total_points == 0
    assert v2.num_votes == 1
    assert v2.num_positive_votes == 0
    assert v2.avg_points_per_vote == 0.0
    assert v2.avg_points_when_positive == 0.0


def test_build_html_sorts_by_generosity_and_embeds_json():
    voters = [
        generate.VoterStats(voter_id="v1", name="Generous", total_points=10, num_votes=5),
        generate.VoterStats(voter_id="v2", name="Stingy", total_points=2, num_votes=5),
    ]

    html = generate.build_html(voters)

    # Basic sanity checks.
    assert "<!doctype html>" in html.lower()
    assert "Voter Generosity" in html

    # Chart labels and values should be in generosity order (Generous first).
    generous_index = html.index("Generous")
    stingy_index = html.index("Stingy")
    assert generous_index < stingy_index

    assert '"Generous"' in html
    assert '"Stingy"' in html

