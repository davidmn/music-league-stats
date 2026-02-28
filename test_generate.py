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
    assert "Voter Stats" in html

    # Chart labels and values should be in generosity order (Generous first).
    generous_index = html.index("Generous")
    stingy_index = html.index("Stingy")
    assert generous_index < stingy_index

    assert '"Generous"' in html
    assert '"Stingy"' in html


# --- VoterStats ---


def test_voter_stats_avg_points_per_vote_zero_votes():
    v = generate.VoterStats(voter_id="x", name="X", total_points=0, num_votes=0)
    assert v.avg_points_per_vote == 0.0


def test_voter_stats_avg_points_when_positive_zero_positive_votes():
    v = generate.VoterStats(
        voter_id="x", name="X", total_points=0, num_votes=5, num_positive_votes=0
    )
    assert v.avg_points_when_positive == 0.0


# --- load_competitors ---


def test_load_competitors_empty_file(tmp_path):
    csv_path = write_csv(tmp_path, "competitors.csv", "ID,Name\n")
    assert generate.load_competitors(csv_path) == {}


# --- load_voter_stats ---


def test_load_voter_stats_unknown_voter_uses_id_as_name(tmp_path):
    competitors = {"v1": "Alice"}
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        track1,unknown_id,2026-02-10T00:00:00Z,2,,r1
        """,
    )
    stats = generate.load_voter_stats(votes_csv, competitors)
    assert len(stats) == 1
    assert stats[0].voter_id == "unknown_id"
    assert stats[0].name == "unknown_id"


# --- _name_sort_key (emoji stripping) ---


def test_name_sort_key_lowercases():
    assert generate._name_sort_key("Alice") == "alice"


def test_name_sort_key_strips_emoji():
    # Emoji removed; trailing space is stripped by _name_sort_key.
    assert generate._name_sort_key("Bee \U0001F41D") == "bee"


def test_name_sort_key_only_emoji_falls_back_to_lower():
    # When everything is stripped, fallback to name.lower()
    result = generate._name_sort_key("\U0001F41D")
    assert result == "\U0001F41D".lower()


# --- build_vote_matrix ---


def test_build_vote_matrix_orders_by_name_ignoring_emoji(tmp_path):
    competitors = {"id_a": "Alice", "id_b": "Bee \U0001F41D"}
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Title,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_b,2026-02-10T00:00:00Z,3,,r1
        """,
    )
    names, matrix = generate.build_vote_matrix(votes_csv, submissions_csv, competitors)
    # Order should be Alice, Bee (emoji stripped for sort)
    assert names == ["Alice", "Bee \U0001F41D"]
    # Bee (row 1) gave 3 points to Alice's track (col 0); matrix stores total points
    assert matrix[1][0] == 3
    assert matrix[0][0] == 0
    assert matrix[0][1] == 0
    assert matrix[1][1] == 0


def test_build_vote_matrix_ignores_self_vote(tmp_path):
    competitors = {"id_a": "Alice", "id_b": "Bob"}
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Title,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_a,2026-02-10T00:00:00Z,4,,r1
        """,
    )
    names, matrix = generate.build_vote_matrix(votes_csv, submissions_csv, competitors)
    assert names == ["Alice", "Bob"]
    # Alice voting for own submission should not count
    assert matrix[0][0] == 0


def test_build_vote_matrix_ignores_zero_points(tmp_path):
    competitors = {"id_a": "Alice", "id_b": "Bob"}
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Title,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_b,2026-02-10T00:00:00Z,0,,r1
        """,
    )
    names, matrix = generate.build_vote_matrix(votes_csv, submissions_csv, competitors)
    assert matrix[1][0] == 0


# --- build_top_tracks ---


def test_build_top_tracks_returns_top_n_by_points(tmp_path):
    competitors = {"id_a": "Alice", "id_b": "Bob"}
    rounds_csv = write_csv(
        tmp_path,
        "rounds.csv",
        """
        ID,Created,Name,Description,Playlist URL
        r1,2026-02-10T00:00:00Z,Round One,,https://example.com/1
        """,
    )
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Hit Song,Album A,Artist A,id_a,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:2,Okay Song,Album B,Artist B,id_b,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:3,Low Song,Album C,Artist C,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_b,2026-02-10T00:00:00Z,10,,r1
        spotify:track:1,id_a,2026-02-10T00:00:00Z,5,,r1
        spotify:track:2,id_a,2026-02-10T00:00:00Z,8,,r1
        spotify:track:3,id_b,2026-02-10T00:00:00Z,1,,r1
        """,
    )

    result = generate.build_top_tracks(
        votes_csv, submissions_csv, rounds_csv, competitors, top_n=3
    )

    assert len(result) == 3
    assert result[0]["title"] == "Hit Song"
    assert result[0]["points"] == 15
    assert result[0]["artist"] == "Artist A"
    assert result[0]["submitter_name"] == "Alice"
    assert result[0]["round_name"] == "Round One"

    assert result[1]["title"] == "Okay Song"
    assert result[1]["points"] == 8

    assert result[2]["title"] == "Low Song"
    assert result[2]["points"] == 1


def test_build_top_tracks_respects_top_n(tmp_path):
    competitors = {"id_a": "Alice"}
    rounds_csv = write_csv(tmp_path, "rounds.csv", "ID,Created,Name,Description,Playlist URL\n")
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,First,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:2,Second,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:3,Third,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_a,2026-02-10T00:00:00Z,5,,r1
        spotify:track:2,id_a,2026-02-10T00:00:00Z,3,,r1
        spotify:track:3,id_a,2026-02-10T00:00:00Z,1,,r1
        """,
    )

    result = generate.build_top_tracks(
        votes_csv, submissions_csv, rounds_csv, competitors, top_n=2
    )

    assert len(result) == 2
    assert result[0]["title"] == "First"
    assert result[1]["title"] == "Second"


def test_build_top_tracks_unknown_submitter_uses_id(tmp_path):
    competitors = {"id_a": "Alice"}
    rounds_csv = write_csv(tmp_path, "rounds.csv", "ID,Created,Name,Description,Playlist URL\n")
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Title,Album,Artist,unknown_id,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_a,2026-02-10T00:00:00Z,4,,r1
        """,
    )

    result = generate.build_top_tracks(
        votes_csv, submissions_csv, rounds_csv, competitors, top_n=3
    )

    assert len(result) == 1
    assert result[0]["submitter_name"] == "unknown_id"


def test_build_top_tracks_missing_rounds_uses_round_label(tmp_path):
    competitors = {"id_a": "Alice"}
    rounds_path = tmp_path / "rounds.csv"  # do not create
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Title,Album,Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_a,2026-02-10T00:00:00Z,1,,r1
        """,
    )

    result = generate.build_top_tracks(
        votes_csv, submissions_csv, rounds_path, competitors, top_n=3
    )

    assert result[0]["round_name"] == "Round"


# --- build_top_artists ---


def test_build_top_artists_aggregates_points_by_artist(tmp_path):
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Song A,Album,Artist X,id_a,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:2,Song B,Album,Artist X,id_b,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:3,Song C,Album,Artist Y,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_b,2026-02-10T00:00:00Z,5,,r1
        spotify:track:2,id_a,2026-02-10T00:00:00Z,4,,r1
        spotify:track:3,id_b,2026-02-10T00:00:00Z,10,,r1
        """,
    )

    result = generate.build_top_artists(votes_csv, submissions_csv, top_n=3)

    assert len(result) == 2
    # Artist Y: 10 pts (one track). Artist X: 5+4 = 9 pts (two tracks).
    assert result[0]["artist"] == "Artist Y"
    assert result[0]["points"] == 10
    assert result[1]["artist"] == "Artist X"
    assert result[1]["points"] == 9


def test_build_top_artists_respects_top_n(tmp_path):
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Song A,Album,Artist A,id_a,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:2,Song B,Album,Artist B,id_a,2026-02-10T00:00:00Z,,r1,Yes
        spotify:track:3,Song C,Album,Artist C,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        """
        Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID
        spotify:track:1,id_a,2026-02-10T00:00:00Z,10,,r1
        spotify:track:2,id_a,2026-02-10T00:00:00Z,5,,r1
        spotify:track:3,id_a,2026-02-10T00:00:00Z,1,,r1
        """,
    )

    result = generate.build_top_artists(votes_csv, submissions_csv, top_n=2)

    assert len(result) == 2
    assert result[0]["artist"] == "Artist A"
    assert result[0]["points"] == 10
    assert result[1]["artist"] == "Artist B"
    assert result[1]["points"] == 5


def test_build_top_artists_empty_submissions_returns_empty(tmp_path):
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        "Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters\n",
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        "Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID\n",
    )

    result = generate.build_top_artists(votes_csv, submissions_csv, top_n=3)

    assert result == []


def test_build_top_artists_tracks_with_zero_votes_included(tmp_path):
    submissions_csv = write_csv(
        tmp_path,
        "submissions.csv",
        """
        Spotify URI,Title,Album,Artist(s),Submitter ID,Created,Comment,Round ID,Visible To Voters
        spotify:track:1,Only Song,Album,Only Artist,id_a,2026-02-10T00:00:00Z,,r1,Yes
        """,
    )
    votes_csv = write_csv(
        tmp_path,
        "votes.csv",
        "Spotify URI,Voter ID,Created,Points Assigned,Comment,Round ID\n",
    )

    result = generate.build_top_artists(votes_csv, submissions_csv, top_n=3)

    assert len(result) == 1
    assert result[0]["artist"] == "Only Artist"
    assert result[0]["points"] == 0


# --- build_html ---


def test_build_html_empty_voters():
    html = generate.build_html([])
    assert "<!doctype html>" in html.lower()
    assert "Voter Stats" in html
    assert "chartLabels = []" in html or 'chartLabels = []' in html
    assert "chartValues = []" in html or 'chartValues = []' in html


def test_build_html_includes_vote_matrix_when_provided():
    voters = [
        generate.VoterStats(voter_id="v1", name="A", total_points=5, num_votes=5),
    ]
    matrix_names = ["Alice", "Bob"]
    matrix = [[0, 1], [2, 0]]
    html = generate.build_html(voters, matrix_names=matrix_names, matrix=matrix)
    assert "Vote Distribution" in html
    assert "Alice" in html
    assert "Bob" in html
    assert "matrixNames = [\"Alice\", \"Bob\"]" in html or "matrixNames = ['Alice', 'Bob']" in html

