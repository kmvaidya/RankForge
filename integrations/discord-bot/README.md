# RankForge Discord bot

A minimal bot exposing `/rank <game> [view]` — your RankForge leaderboards
inside Discord. It talks to the REST API only, so it can run anywhere that
can reach your deployment (no database access needed).

## Setup

1. Create an application + bot at <https://discord.com/developers/applications>.
2. Invite it with the `bot` and `applications.commands` scopes (no
   privileged intents needed).
3. Run:

   ```bash
   pip install -r requirements.txt
   export DISCORD_BOT_TOKEN=...            # from the developer portal
   export RANKFORGE_API_URL=http://localhost:8000
   python bot.py
   ```

## Views

| View | Shows |
|---|---|
| `rating` (default) | raw Glicko-2 rating, ±RD, career W-L |
| `conservative` | rating − 2·RD — unproven players rank low until their uncertainty shrinks |
| `season` | current-season W-L records |

## Security note

Keep the token in the environment — never commit it. If you previously ran
a bot with a token hardcoded in source (e.g. an older leaderboards script),
treat that token as exposed and **regenerate it** in the developer portal.
