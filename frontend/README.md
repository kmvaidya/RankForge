# RankForge Frontend

React + TypeScript + Vite + Tailwind CSS single-page app for RankForge.

## Development

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api -> localhost:8000
```

Start the backend first (from the repo root):

```bash
.venv/Scripts/python -m uvicorn rankforge.main:app --reload
```

## Production build

```bash
npm run build      # type-checks then bundles to dist/
```

Set `VITE_API_URL` at build time to point the app at a deployed backend
(defaults to `/api`, which assumes a reverse proxy in front of both):

```bash
VITE_API_URL=https://api.example.com npm run build
```

## Pages

- **Leaderboard** (`/`) — sortable rankings per game
- **Record Match** (`/record`) — team assignment, outcome, instant rating deltas
- **Matchmaking** (`/matchmaking`) — balanced team generation with constraints
- **Matches** (`/matches`) — history with delete (triggers rating recalculation)
- **Games** (`/games`) — game management
- **Player profile** (`/players/:id`) — stats, rating history chart, recent matches
