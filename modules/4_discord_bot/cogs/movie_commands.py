"""
movie_commands.py
Slash command cog: /watch, /trending, /request
"""

import os
import re
import logging
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import requests
from pathlib import Path
import json

log = logging.getLogger(__name__)

TMDB_KEY    = os.getenv("TMDB_API_KEY", "b6524bb48fb309af7e940a074a363851")
TMDB_BASE   = "https://api.themoviedb.org/3"
IMG_W500    = "https://image.tmdb.org/t/p/w500"

SETTINGS_PATH = Path(__file__).parent.parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

TARGET_URL    = SETTINGS["target_url"]
EMBED_COLOR   = SETTINGS["discord"]["embed_color"]
QUALITY_TAGS  = SETTINGS["discord"]["stream_quality_tags"]


def _slug(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s


def _tmdb_search(query: str) -> dict | None:
    try:
        resp = requests.get(
            f"{TMDB_BASE}/search/multi",
            params={"api_key": TMDB_KEY, "query": query, "language": "en-US"},
            timeout=10,
        )
        results = resp.json().get("results", [])
        for r in results:
            if r.get("media_type") in ("movie", "tv"):
                return r
    except Exception as e:
        log.warning(f"TMDb search failed: {e}")
    return None


def _tmdb_trending() -> list[dict]:
    try:
        resp = requests.get(
            f"{TMDB_BASE}/trending/all/day",
            params={"api_key": TMDB_KEY, "language": "en-US"},
            timeout=10,
        )
        return resp.json().get("results", [])[:10]
    except Exception as e:
        log.warning(f"TMDb trending failed: {e}")
    return []


def _build_movie_embed(item: dict) -> tuple[discord.Embed, discord.ui.View]:
    title       = item.get("title") or item.get("name") or "Unknown"
    overview    = (item.get("overview") or "No description.")[:300]
    year        = (item.get("release_date") or item.get("first_air_date") or "")[:4]
    rating      = item.get("vote_average", 0)
    poster_path = item.get("poster_path")
    slug        = _slug(title)
    stream_url  = f"{TARGET_URL}/movie/{slug}"

    embed = discord.Embed(
        title       = f"🎬 {title} ({year})",
        description = overview + ("..." if len(item.get("overview", "")) > 300 else ""),
        color       = EMBED_COLOR,
        url         = stream_url,
    )
    embed.add_field(name="⭐ Rating",  value=f"{rating:.1f} / 10", inline=True)
    embed.add_field(name="📺 Quality", value=" | ".join(QUALITY_TAGS[:2]), inline=True)
    embed.add_field(name="💰 Cost",    value="**FREE**",             inline=True)
    embed.add_field(
        name  = "🔗 Stream Link",
        value = f"[Click to Watch Free in 4K]({stream_url})",
        inline=False,
    )
    if poster_path:
        embed.set_thumbnail(url=f"{IMG_W500}{poster_path}")
    embed.set_footer(text="FilmFeed • No Sign-up • Zero Ads • 4K Streaming")

    view = StreamView(stream_url, title)
    return embed, view


class StreamView(discord.ui.View):
    def __init__(self, url: str, title: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label = "▶ Stream in 4K Now",
                style = discord.ButtonStyle.danger,
                url   = url,
                emoji = "🎬",
            )
        )
        self.add_item(
            discord.ui.Button(
                label = "📋 Request via WhatsApp",
                style = discord.ButtonStyle.success,
                url   = f"https://wa.me/?text=I+want+to+watch+{requests.utils.quote(title)}",
                emoji = "📱",
            )
        )


class MovieCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="watch", description="Find and stream a movie or TV show for free in 4K")
    @app_commands.describe(title="Movie or TV show name")
    async def watch(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(thinking=True)

        item = _tmdb_search(title)
        if not item:
            await interaction.followup.send(
                f"❌ Couldn't find **{title}** on TMDb. Try a different spelling.",
                ephemeral=True,
            )
            return

        embed, view = _build_movie_embed(item)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="trending", description="Show the top 10 trending movies and shows right now")
    async def trending(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        items = _tmdb_trending()
        if not items:
            await interaction.followup.send("❌ Could not fetch trending titles right now.", ephemeral=True)
            return

        embed = discord.Embed(
            title       = "🔥 Trending Now — Top 10",
            description = "Stream all of these free in 4K on FilmFeed:",
            color       = EMBED_COLOR,
        )

        view = discord.ui.View(timeout=None)

        for i, item in enumerate(items, 1):
            title    = item.get("title") or item.get("name") or "Unknown"
            year     = (item.get("release_date") or item.get("first_air_date") or "")[:4]
            rating   = item.get("vote_average", 0)
            slug     = _slug(title)
            url      = f"{TARGET_URL}/movie/{slug}"
            mtype    = "🎬" if item.get("media_type") == "movie" else "📺"

            embed.add_field(
                name  = f"{i}. {mtype} {title} ({year})",
                value = f"⭐ {rating:.1f} | [Watch Free]({url})",
                inline=False,
            )

            if i <= 5:  # Add buttons for top 5
                view.add_item(
                    discord.ui.Button(
                        label = f"{i}. {title[:20]}",
                        style = discord.ButtonStyle.danger,
                        url   = url,
                        row   = (i - 1) // 3,
                    )
                )

        embed.set_footer(text="FilmFeed • No Sign-up • Zero Ads • 4K Streaming")
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="request", description="Request a movie or show to be added to FilmFeed")
    @app_commands.describe(title="Movie or TV show you want to request")
    async def request(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(thinking=True)

        item = _tmdb_search(title)
        found_title = (item.get("title") or item.get("name") or title) if item else title
        slug        = _slug(found_title)
        stream_url  = f"{TARGET_URL}/movie/{slug}"
        wa_url      = f"https://wa.me/?text=Hi!+I%27m+requesting+{requests.utils.quote(found_title)}+on+FilmFeed:+{stream_url}"

        embed = discord.Embed(
            title       = f"📋 Request: {found_title}",
            description = (
                f"Your request for **{found_title}** has been noted!\n\n"
                f"It may already be available here: [Check FilmFeed]({stream_url})\n\n"
                f"Or send a direct request via WhatsApp for priority processing."
            ),
            color       = 0x25D366,
        )

        if item and item.get("poster_path"):
            embed.set_thumbnail(url=f"{IMG_W500}{item['poster_path']}")

        embed.set_footer(text="FilmFeed • Free 4K Streaming • No Sign-up")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="▶ Check on FilmFeed", style=discord.ButtonStyle.danger, url=stream_url))
        view.add_item(discord.ui.Button(label="📱 WhatsApp Request", style=discord.ButtonStyle.success, url=wa_url))

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(MovieCommands(bot))
