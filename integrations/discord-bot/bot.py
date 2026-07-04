# integrations/discord-bot/bot.py

"""RankForge Discord bot: /rank <game> [view] leaderboards in your server.

Reads the RankForge REST API — no database access, so it can run anywhere
that can reach your deployment. Configuration via environment variables:

    DISCORD_BOT_TOKEN   the bot token (Discord developer portal)
    RANKFORGE_API_URL   base URL of the RankForge API (default
                        http://localhost:8000)

Views:
    rating        raw Glicko-2 rating (default)
    conservative  rating - 2*RD: unproven players rank low until they
                  shrink their uncertainty
    season        current-season W-L records instead of career

Invite the bot with the ``applications.commands`` and ``bot`` scopes; it
needs no privileged intents.
"""

from __future__ import annotations

import os
from typing import Any

import discord
import httpx
from discord import app_commands

API_URL = os.getenv("RANKFORGE_API_URL", "http://localhost:8000").rstrip("/")
MAX_ROWS = 15

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


async def _get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=10) as http:
        response = await http.get(f"{API_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()


async def _find_game(name: str) -> dict | None:
    games = (await _get("/games/", {"limit": 100}))["items"]
    lowered = name.strip().lower()
    for game in games:
        if game["name"].lower() == lowered:
            return dict(game)
    for game in games:
        if game["name"].lower().startswith(lowered):
            return dict(game)
    return None


def _format_board(game: dict, entries: list[dict], view: str, season: int) -> str:
    if view == "season":
        season_label = f"W-L (season {season})"
        header = f"{'#':>2}  {'Player':<18} {season_label:<16} {'Win %':>6}"
    else:
        label = "Rating*" if view == "conservative" else "Rating"
        header = f"{'#':>2}  {'Player':<18} {label:>8} {'±RD':>5} {'W-L':>9}"

    rows = [header, "-" * len(header)]
    ranked = []
    for entry in entries:
        rating = entry["rating_info"]["rating"]
        if view == "conservative":
            rating -= 2 * entry["rating_info"]["rd"]
        ranked.append((rating, entry))
    ranked.sort(key=lambda pair: -pair[0])

    for position, (rating, entry) in enumerate(ranked[:MAX_ROWS], start=1):
        stats = entry.get("stats") or {}
        name = entry["player"]["name"][:18]
        if view == "season":
            season_stats = stats.get("season") or {}
            record = f"{season_stats.get('wins', 0)}-{season_stats.get('losses', 0)}"
            win_rate = f"{season_stats.get('win_rate', 0) * 100:.0f}%"
            rows.append(f"{position:>2}  {name:<18} {record:<16} {win_rate:>6}")
        else:
            rd = entry["rating_info"]["rd"]
            record = f"{stats.get('wins', 0)}-{stats.get('losses', 0)}"
            rows.append(
                f"{position:>2}  {name:<18} {rating:>8.0f} {rd:>5.0f} {record:>9}"
            )

    if view == "conservative":
        rows.append("")
        rows.append("* rating - 2*RD (Glicko lower bound)")
    return "```\n" + "\n".join(rows) + "\n```"


@tree.command(name="rank", description="Show a game's RankForge leaderboard")
@app_commands.describe(game="Game name", view="Leaderboard view")
@app_commands.choices(
    view=[
        app_commands.Choice(name="rating", value="rating"),
        app_commands.Choice(name="conservative", value="conservative"),
        app_commands.Choice(name="season", value="season"),
    ]
)
async def rank(
    interaction: discord.Interaction, game: str, view: str = "rating"
) -> None:
    await interaction.response.defer()
    try:
        found = await _find_game(game)
        if found is None:
            await interaction.followup.send(f"No game matching “{game}”.")
            return
        board = (await _get(f"/games/{found['id']}/leaderboard", {"limit": 100}))[
            "items"
        ]
        if not board:
            await interaction.followup.send(
                f"**{found['name']}** has no rated players yet."
            )
            return
        seasons = await _get(f"/games/{found['id']}/seasons")
        message = f"**{found['name']}** — season {seasons['current_season']}\n"
        message += _format_board(found, board, view, seasons["current_season"])
        await interaction.followup.send(message)
    except httpx.HTTPError as error:
        await interaction.followup.send(f"RankForge API unreachable: {error}")


@client.event
async def on_ready() -> None:
    await tree.sync()
    print(f"Logged in as {client.user}; commands synced.")


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_BOT_TOKEN (never hardcode it).")
    client.run(token)


if __name__ == "__main__":
    main()
