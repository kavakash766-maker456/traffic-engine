"""
bot.py
Discord bot entry point — discord.py v2.x with slash command tree sync.
"""

import os
import logging
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TOKEN      = os.getenv("DISCORD_BOT_TOKEN", "")
GUILD_IDS  = [int(g) for g in os.getenv("DISCORD_GUILD_IDS", "").split(",") if g.strip().isdigit()]


class FilmFeedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load cogs
        await self.load_extension("cogs.movie_commands")
        log.info("Cogs loaded.")

        # Sync slash commands
        if GUILD_IDS:
            for guild_id in GUILD_IDS:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info(f"Synced commands to guild {guild_id}")
        else:
            await self.tree.sync()
            log.info("Synced commands globally.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="4K Movies Free | /watch",
            )
        )


async def main():
    if not TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN is not set in .env")
    bot = FilmFeedBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
