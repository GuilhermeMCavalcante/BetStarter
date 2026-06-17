# BetStarter

**Analytical betting recommendation engine for the FIFA World Cup 2026.**

> **Disclaimer:** This is a quantitative analysis tool. It does not guarantee profit. Betting involves financial risk.

---

## Overview

BetStarter collects live fixtures and odds from the [API-Football](https://www.api-football.com/) data provider, applies a Poisson-based statistical model with team ratings and recent match statistics, and surfaces value bets where the model's estimated probability exceeds the bookmaker's implied probability by a meaningful edge.

### How the model works

1. Loads prior team strength ratings (scale 50–100) for all World Cup nations.
2. Estimates expected goals per side using rating differentials and a conservative tournament baseline.
3. Blends in live match statistics (goals-for/against averages, BTTS rate, over rates) as they accumulate during the tournament.
4. Derives market probabilities via the Poisson distribution.
5. Computes **edge** (`model_prob − implied_prob`) and **expected value** (`model_prob × odd − 1`).
6. Approves a recommendation only when both EV and edge clear market-specific thresholds.

### Supported markets

| Market | Selections |
|---|---|
| Over/Under | Over 0.5, Over 1.5, Over 2.5, Over 3.5, Under 3.5 |
| Both Teams Score | Yes, No |

### Confidence tiers

| Tier | Confidence score | Minimum edge |
|---|---|---|
| A | ≥ 82 | ≥ 10% |
| B | ≥ 72 | ≥ 7% |
| C | ≥ 62 | ≥ 5% |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  BetStarter                     │
│                                                 │
│  ┌──────────┐   ┌──────────┐   ┌─────────────┐ │
│  │ Collector│──▶│   Model  │──▶│ Recommender │ │
│  │(API-Ftbl)│   │(Poisson) │   │ (EV filter) │ │
│  └──────────┘   └──────────┘   └──────┬──────┘ │
│                                        │        │
│  ┌─────────────────────────────────────▼──────┐ │
│  │          SQLite / PostgreSQL               │ │
│  └─────────────────────────────────────┬──────┘ │
│                                        │        │
│  ┌─────────────────┐   ┌───────────────▼──────┐ │
│  │  FastAPI (REST) │   │  Streamlit Dashboard │ │
│  └─────────────────┘   └──────────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## Prerequisites

- Python 3.12+
- An [API-Football](https://www.api-football.com/) API key (free tier works for World Cup)
- Docker & Docker Compose (optional, for containerised setup)

---

## Quickstart

### 1. Clone and configure

```bash
git clone https://github.com/your-org/BetStarter.git
cd BetStarter
```

Copy the environment template and fill in your API key:

```bash
cp .env.example .env
```

```env
API_FOOTBALL_KEY=your_key_here
```

### 2. Install dependencies

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

### 3. Initialise the database

```powershell
$env:PYTHONPATH="."
py scripts/init_db.py
```

### 4. Run the dashboard

```powershell
$env:PYTHONPATH="."
py -m streamlit run dashboard/dashboard.py
```

Open [http://localhost:8501](http://localhost:8501) and click **Update Recommendations**.

### 5. Run the API server (optional)

```powershell
$env:PYTHONPATH="."
uvicorn app.main:app --reload
```

API docs available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Docker

```bash
docker compose up
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Dashboard | http://localhost:8501 |

---

## Pipeline (manual run)

```powershell
$env:PYTHONPATH="."
py scripts/pipeline.py --days 7
```

Example output:

```json
{
  "competition": "FIFA World Cup",
  "league": 1,
  "season": 2026,
  "fixtures": 15,
  "odds": 1357,
  "ratings_seeded": 48,
  "stats": 1,
  "odds_analyzed": 300,
  "recommendations": 8
}
```

---

## Configuration

All settings are read from the `.env` file (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `API_FOOTBALL_KEY` | — | API-Football v3 key (required) |
| `API_FOOTBALL_HOST` | `v3.football.api-sports.io` | API host |
| `DATABASE_URL` | `sqlite:///./bets.db` | SQLAlchemy connection string |
| `MIN_EV` | `0.05` | Minimum expected value to approve a bet |
| `DEFAULT_BANKROLL` | `1000` | Starting bankroll shown in dashboard |
| `WORLD_CUP_ONLY` | `true` | Lock the system to World Cup fixtures only |
| `WORLD_CUP_LEAGUE_ID` | `1` | API-Football league ID for the World Cup |
| `WORLD_CUP_SEASON` | `2026` | Target season |
| `TARGET_BOOKMAKER` | `Superbet` | Bookmaker whose odds are used for recommendations |

### Tuning the model

Team ratings live in [app/services/worldcup_model.py](app/services/worldcup_model.py) (`DEFAULT_TEAM_RATINGS`). Adjust them before the tournament starts or as form evolves.

Filter thresholds can be tuned in [app/services/recommender.py](app/services/recommender.py).

---

## Project structure

```
BetStarter/
├── app/
│   ├── api/               # API layer (future expansion)
│   ├── db/                # Database session and initialisation
│   ├── models/            # SQLAlchemy ORM models
│   ├── services/
│   │   ├── api_football.py    # API-Football client
│   │   ├── collector.py       # Fixture and odds ingestion
│   │   ├── recommender.py     # EV filter and recommendation engine
│   │   └── worldcup_model.py  # Poisson model and team ratings
│   ├── config.py
│   └── main.py            # FastAPI application
├── dashboard/
│   ├── pages/             # Streamlit multi-page views
│   └── dashboard.py       # Entry point
├── scripts/               # One-off and pipeline scripts
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── requirements.txt
```

---

## Troubleshooting

**Dashboard shows no recommendations**
→ Open the **Rejected / Debug** tab. If odds are being rejected, the system is working — the filter found no sufficient EV. Try lowering `MIN_EV=0.02` temporarily.

**No fixtures appear**
→ Run `scripts/pipeline.py --days 14` to widen the collection window.

**`ModuleNotFoundError: No module named 'app'`**
→ Always set `PYTHONPATH` before running scripts: `$env:PYTHONPATH="."` (PowerShell) or `export PYTHONPATH=.` (bash).
