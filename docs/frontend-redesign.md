# RankForge Frontend v2 — PRD & Design Specification

Status: **in progress** · Started 2026-07-04 · Owner: frontend

This document is the source of truth for the v2 frontend redesign: why v1
fails, the product thinking behind v2, the visual language, per-system
specifications, and the rollout plan. Each rollout phase lands as its own
commit with build + lint green.

---

## 1. Why redesign

Three structural failures in v1, in increasing order of severity:

1. **Generic aesthetics.** v1 is the default dark-dashboard look: blue-slate
   surfaces, indigo accent, one sans-serif at one optical size, cards
   everywhere with equal visual weight. Nothing about it says "competitive
   ranking" — it could be any admin panel. Numbers (the heart of a rating
   app) get no typographic treatment at all.
2. **Two-team assumption.** The backend is genuinely game-agnostic: N teams
   of M players, per-team ranked outcomes with ties, free-for-all as N teams
   of 1. The Record page hardcodes `team1`/`team2`, a three-way
   winner toggle, and two score fields. Golf and GeoGuessr — real games in
   the live database — literally cannot be recorded from the UI. Matchmaking
   can generate 3+ team splits that Record cannot accept ("Use this →
   Record" is hidden for them, silently).
3. **Pickleball-shaped Session.** "Courts", fixed two-teams-per-court,
   winner-only recording (no draws), team size capped at 3. The session
   runner is the app's most differentiated feature and it only works for one
   of the six live games.

Secondary issues: every page carries its own game dropdown (the game is
really app-level context); no way to backdate a match from the UI despite
backend support; native `<select>`s for actions that deserve real controls;
inconsistent confirm patterns; no mobile posture despite "at the table" being
the primary recording context.

## 2. Product context

RankForge serves three goals: (1) a fun, fast way to be competitive with
friends, (2) a portfolio-grade showcase, (3) potential productization. The
frontend must serve two distinct postures:

- **At the table** (phone, one thumb, mid-game-night): record a result in
  seconds, fill a court, see who's up next. Speed and touch targets dominate.
- **On the couch** (laptop, browsing): leaderboards, profiles, history,
  prediction quality. Information density and readability dominate.

Every screen should know which posture it primarily serves.

## 3. Design language — "Forge"

The identity leans into the name: a forge is dark, warm, and industrial, and
the thing being forged here is a ranking. Dark warm-graphite grounds (not
blue slate), a single ember accent used sparingly, athletic condensed display
type, and monospaced data numerals that read like a scoreboard.

### Color tokens

| Token | Value | Role |
|---|---|---|
| `bg` | `#0B0C0E` | page ground (warm near-black) |
| `surface` | `#131518` | cards, header |
| `raised` | `#1B1E23` | nested surfaces, hovers, inputs |
| `line` | `#262B31` | default borders |
| `line-strong` | `#3A4149` | emphasized borders, focus edges |
| `ink` | `#F2F3F5` | primary text |
| `mute` | `#A9B0B9` | secondary text |
| `faint` | `#71787F` | tertiary text, captions |
| `ember` | `#FF6A3D` | THE accent: primary actions, active nav, brand, focus |
| `ember-bright` | `#FF8A5C` | hover states of ember elements |
| `ember-ink` | `#211008` | text on ember fills |
| `win` | `#3ECF8E` | positive outcomes only |
| `loss` | `#F0566A` | negative outcomes only |
| `warn` | `#F5B83D` | attention (lopsided, provisional) |
| `gold` / `silver` / `bronze` | `#E8B33C` / `#C9CDD3` / `#C08A5A` | podium ranks |

Rules: ember is interaction + brand, never an outcome. Win/loss colors never
decorate anything that isn't an outcome. Amber warns. One accent per view
dominates; everything else stays neutral.

### Typography

| Face | Package | Role |
|---|---|---|
| **Barlow Condensed** (500–700) | `@fontsource/barlow-condensed` | display: page titles, section labels (uppercase, tracked), team names, big stat headlines |
| **Barlow** (400–600) | `@fontsource/barlow` | body, controls, prose |
| **IBM Plex Mono** (500) | `@fontsource/ibm-plex-mono` | all data numerals: ratings, records, percentages, deltas |

Barlow is a superfamily (body + condensed share DNA — industrial signage
heritage, fits "forge"), and Plex Mono makes every number feel like
instrumentation. Numbers always get `font-data`; never render a rating in the
body face.

### Shape, depth, motion

- Radii: 4px inputs/chips, 8px cards. No pill-shaped buttons (pills are
  reserved for status).
- Depth via border + subtle surface steps, not shadows.
- Motion: 150ms color/opacity transitions; nothing moves position except
  explicit reorder interactions. Respect `prefers-reduced-motion`.
- Focus: 2px ember ring on `:focus-visible` everywhere.

### Voice

Sentence case everywhere (no Title Case buttons). Controls say what happens:
"Record match", "Fill court", "Start season". Stats explain themselves in one
quiet caption, not a paragraph. No exclamation marks except the upset call-out.

## 4. Information architecture

- **Global game context.** The selected game moves into the app header —
  a single switcher visible on every page (it already persists in
  localStorage). Pages stop rendering their own `GamePicker`. Player profile
  is the only cross-game page and says so.
- **Navigation** (desktop header / mobile bottom bar):
  `Leaderboard · Record · Session · Matchmaking · Matches · Games`.
  Record and Session are the "at the table" pair; the rest is "couch".
- **Brand.** Text wordmark: `RANK` in ink + `FORGE` in ember, Barlow
  Condensed 700, all caps. No logo box.

## 5. System specifications

### 5.1 App shell
Header: wordmark · nav · game switcher (right-aligned, custom listbox showing
the game's rating strategy as a caption). Mobile (<640px): nav collapses into
a fixed bottom tab bar (5 slots: Leaderboard, Record, Session, Matches,
More→sheet with Matchmaking/Games); header keeps wordmark + game switcher.

### 5.2 Component kit (`components/ui.tsx`)
`Button` (primary ember / secondary outline / ghost / danger, sm+md sizes),
`Field` + `Input` + `Select` + `Textarea` (shared styling, error state),
`SegmentedControl`, `Card`/`CardTitle`, `StatCard` (label + Plex Mono value +
caption), `Pill` (win/loss/draw/warn/flag), `Avatar` (deterministic hue from
name), `PlayerChip` (avatar + name, removable), `RankBadge` (podium metals),
`ConfidenceBar`, `ProbBar` (N-segment stacked win-probability bar with team
labels), `FairnessMeter`, `RatingDelta`, `Spinner`, `Note` (error/success),
`EmptyState`, `PageHeader`, `ConfirmButton` (unified two-step destructive
confirm).

### 5.3 Record match — the N-team rebuild (posture: table)
- Teams are a dynamic list (2–8). "Add team" appends; each team card holds
  member chips and an optional score input. Removing a team returns members
  to the pool.
- **Assignment model:** one team is *armed* (highlighted); tapping a player
  in the pool adds/removes them from the armed team. Tapping another team
  arms it. No dropdown-per-player.
- **Free-for-all switch:** converts the current selection into N single
  player teams (golf, GeoGuessr). Pool taps then create/remove solo teams.
- **Outcome entry adapts to team count:**
  - 2 teams → segmented control: Team A won / Draw / Team B won.
  - 3+ teams → finishing order: teams listed with up/down reorder controls
    and a "tied with above" toggle per row → derives `rank` per team (ties
    share a rank, next rank skips accordingly — standard competition
    ranking).
- Per-team scores → `match_metadata.team_scores` keyed by team id; two-team
  games keep `final_score` for compatibility. Score preset quick-fill stays.
- **Backdate control:** optional "played earlier" datetime → `played_at`.
- Prediction: N-team stacked `ProbBar` with favored-team marker and lopsided
  pill; upset call-out logic generalizes (winner's predicted probability
  < 1/teams × 0.7).
- Weight (feature-flagged) and notes stay. Success panel shows per-team
  groups with rating deltas.

### 5.4 Session v2 — game-agnostic (posture: table)
- Setup: players, station count, **station noun** (Court / Table / Board /
  Station — chips, default Court), **format**: teams-per-station (2–4) ×
  team size (1–4), or **free-for-all of K players** (ranked finish).
- Station card: fill from bench (FIFO + matchmaking + variety penalty),
  shuffle, lopsided flag, per-team win %.
  - 2-team format → "Team A won / Draw / Team B won" (draws now supported).
  - 3+ teams / FFA → tap players/teams in finishing order to record.
- Bench queue, games-played fairness highlight, session record, and summary
  stay; all restyled. Session state schema versioned (`v2`) with migration
  from v1 (discard incompatible fields gracefully).

### 5.5 Leaderboard (posture: couch; home page)
- Top three rendered as a **podium strip** above the table (medal color,
  avatar, rating, record) — the payoff view for the group.
- Table: rank, player (avatar + provisional pill), rating (Plex Mono, bold),
  confidence bar, matches, W–L, win %. Sortable headers keep behavior.
- Controls (display mode, min-matches) become compact segmented/select row.
- League health + calibration verdict stay as quiet footers with the same
  wording rules.

### 5.6 Matchmaking (posture: mixed)
- Player multi-select becomes chip grid (tap to toggle) with search.
- Team count 2–4 plus optional uneven `team_sizes` later (non-goal for now).
- Result cards: fairness meter, lopsided pill, per-team columns with win %,
  "Send to Record" passes **all** teams via router state (works for N teams
  after 5.3).
- Constraints UI (together/apart) kept, restyled as chip pairs.

### 5.7 Matches (posture: couch)
- Each match: score strip (if `team_scores`), team columns with outcome
  pills (win/loss/draw/rank), rating deltas, session badge when
  `session_id` present, relative time + absolute on hover.
- Delete keeps two-step confirm via `ConfirmButton`; note about replay stays.
- Filter: current game (global), player filter later (non-goal).

### 5.8 Player profile (posture: couch)
- Header: avatar (lg), name, cross-game totals; game tabs restyled as
  segmented chips.
- Stat row: rating ± RD, matches, record, win % (StatCards, Plex Mono).
- Rating chart: keep fog-of-war band; restyle axes/grid to tokens; ember
  line.
- Recent matches: outcome pill + opponents + delta (restyled).
- Chemistry: shrunk win-rate bars (thin meter per row) instead of bare
  percentages; keep raw-on-hover and the shrinkage caption.

### 5.9 Games (posture: couch, admin)
- Game cards: name, strategy pill, description, season badge + new-season
  flow, delete confirm — restyled; rating-config summary line (tau, preset,
  season reset) read-only.
- Create form: Field components; strategy as segmented control.

## 6. Rollout plan (loop iterations)

Each phase: implement → `npm run build` + oxlint green → commit → next.

- [x] **P0 — this PRD** (`docs`)
- [x] **P1 — Foundation**: fonts, `@theme` tokens, component kit v2, app
  shell with global game switcher, all pages mechanically migrated to tokens
  (no page restructures yet). (`feat`)
- [x] **P2 — Record match v2**: N teams, FFA, finishing-order entry,
  per-team scores, backdating, N-team odds. (`feat`)
- [x] **P3 — Session v2**: formats, station nouns, draws, FFA ranking,
  restyle. (`feat`)
- [x] **P4 — Leaderboard + Matches redesign.** (`feat`)
- [x] **P5 — Profile + Games + Matchmaking polish**, N-team send-to-record.
  (`feat`)
- [ ] **P6 — E2E pass**: Chrome click-through against live data, mobile
  viewport check, fixes; lockfile cross-platform check (`docker build`).
  (`fix`/`chore`)

## 7. Non-goals (this cycle)

Backend changes (everything needed already exists); auth/multi-tenancy;
uneven team sizes in matchmaking UI; player-filter on Matches; PWA offline
session recording; drag-and-drop (tap interactions first — drag is
enhancement, not baseline).

## 8. Quality gates

`npm run build` (tsc + vite) and oxlint clean per phase; every phase leaves
the app fully usable; E2E click-through on live data before the cycle
closes; no rating-affecting writes to the live DB during testing.
