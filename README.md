# Music League Stats

Generate a static stats page for a [Music League](https://musicleague.com/) group: **vote generosity** (average points each voter gives per track) and a **vote distribution matrix** (who gave how many points to whom across all rounds).

Output is a single `index.html` you can open in a browser or host anywhere.

## Requirements

- Python 3

## Input data

Place your league data in `input/rf/` (or change `INPUT_DIR` in `generate.py` for another folder). The script expects three CSV files there:

| File | Description |
|------|-------------|
| `competitors.csv` | **ID**, **Name** — one row per competitor |
| `votes.csv` | **Spotify URI**, **Voter ID**, **Created**, **Points Assigned**, **Comment**, **Round ID** — one row per vote |
| `submissions.csv` | **Spotify URI**, **Title**, **Album**, **Artist(s)**, **Submitter ID**, **Created**, **Comment**, **Round ID**, **Visible To Voters** — one row per submitted track |

You can export these from Music League (or build them in the same format). The generator uses `Voter ID` and `Submitter ID` from the CSVs and resolves display names from `competitors.csv`.

## Usage

Generate the stats page:

```bash
python3 generate.py
```

Or use the Makefile:

```bash
make generate    # build index.html
make test        # run tests
make all         # test then generate
```

Output is written to `index.html` in the project root. Open it in a browser or serve it with any static host.

## What you get

- **Vote Generosity** — Bar chart of each voter’s average points per track they rated (higher = more generous scoring).
- **Vote Distribution** — Matrix where rows are voters, columns are submitters; each cell is the total points that row gave to that column’s tracks across all rounds.

