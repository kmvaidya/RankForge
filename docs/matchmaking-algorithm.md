# The RankForge Matchmaking Algorithm

*Balanced team generation via skill-distribution superposition and simulated annealing.*

## Problem

Given `N` players with Glicko-2 ratings, partition them into `M` teams
(of given sizes) so the match outcome is as uncertain as possible — a fair
match is one nobody can call in advance.

A rating alone is a point estimate. Glicko-2 also gives us each player's
**rating deviation (RD)** — how uncertain the system is about that estimate.
RankForge uses both: a new player with rating 1500 ± 350 is a very different
matchmaking proposition from a veteran at 1500 ± 50.

## Step 1 — Players as distributions

Each player *i* is modeled as a Gaussian random variable:

```
Sᵢ ~ N(μᵢ, σᵢ²),   μᵢ = rating,  σᵢ = RD
```

Players with no profile for the game get the default prior
(μ = 1500, σ = 350).

## Step 2 — Teams as superpositions

A team's skill is the sum of independent member skills. Sums of independent
Gaussians are Gaussian:

```
T = Σᵢ Sᵢ  ~  N( Σᵢ μᵢ ,  Σᵢ σᵢ² )
```

so a team's mean is the sum of member ratings, and its standard deviation is
`sqrt(Σ σᵢ²)` — uncertain players make a team's performance less predictable,
which the fairness score accounts for naturally.

## Step 3 — Fairness of a matchup

For teams A and B, consider the difference:

```
D = T_A − T_B ~ N( μ_A − μ_B ,  σ_A² + σ_B² )
```

The probability that A outrates B is:

```
P(A > B) = Φ( (μ_A − μ_B) / sqrt(σ_A² + σ_B²) )
```

where Φ is the standard normal CDF. A perfectly fair match is a coin flip
(P = 0.5), so we define:

```
fairness(A, B) = 1 − |2·P(A > B) − 1|    ∈ (0, 1]
```

- `1.0` — dead even
- `0.5` — the favorite wins ~3 times out of 4
- `→ 0` — a foregone conclusion

For `M > 2` teams, a configuration's fairness is the **minimum pairwise
fairness** — the worst matchup bounds the experience.

Note how RD enters: the same 100-point rating gap between two teams of
high-RD players yields a higher fairness than between two low-RD teams,
because the outcome genuinely is less certain.

## Step 4 — Searching the partition space

The number of ways to split N players into labeled teams of sizes
`(s₁, …, s_M)` is the multinomial coefficient `N! / (s₁!·…·s_M!)`.

**Exhaustive (small N).** Up to 20,000 partitions, we enumerate everything,
filter by constraints, score each, and keep the top-K distinct
configurations (same-size team permutations are deduplicated via canonical
forms). Typical friendly sessions (≤ 12 players, 2 teams → 924 partitions)
are solved exactly in milliseconds.

**Simulated annealing (large N).** Beyond that:

```
repeat R restarts:
    x ← random valid partition;  T ← T_max
    while T > T_min:
        repeat k times:
            x' ← swap two players between random teams
            if x' violates constraints: skip
            Δ ← fairness(x') − fairness(x)
            accept x' if Δ ≥ 0, else with probability exp(Δ / T)
        T ← T · cooling_rate
```

Defaults: `T_max = 1.0`, `T_min = 0.001`, `cooling_rate = 0.99`,
`k = 10`, `R = 4` — roughly 27k evaluations, well under the 2-second
budget for any realistic pool. A top-K set of distinct configurations is
maintained across all restarts. A `seed` can be supplied for reproducible
output.

Fairness lives in `[0, 1]`, so `T_max = 1.0` means the initial phase accepts
almost any move (exploration) while the final phase is nearly greedy
(exploitation).

## Constraints

Two hard constraint types, enforced identically in both search modes:

- **together** — groups that must share a team (friends, parent + child).
- **apart** — groups whose members must all be on different teams
  (rivals, "don't stack the two best").

Infeasible combinations (e.g. a together-group larger than the largest team,
or contradictory together/apart) are rejected with a 422 before or during
search.

## API

```
POST /matchmaking/generate
{
  "game_id": 1,
  "player_ids": [1, 2, 3, 4, 5, 6, 7, 8],
  "team_count": 2,
  "num_results": 5,
  "constraints": { "together": [[1, 2]], "apart": [[3, 4]] }
}
```

Response: configurations ranked by fairness, each with per-team
distributions `(μ, σ)`, per-team win probabilities, and member ratings.

## Limitations & future work

- Team skill as a pure sum ignores synergy/chemistry; a learned interaction
  model (see MASTER_PLAN "ML-Enhanced Rating System") could replace the
  superposition step without changing the search.
- Fairness is the only objective. Multi-objective search (variety across
  sessions, fatigue, role coverage) fits naturally into the annealing
  energy function.
- The pairwise-product "win probability" for M > 2 teams is an
  approximation (team distributions are not independent across pairings).
