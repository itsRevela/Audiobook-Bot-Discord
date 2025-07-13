# Audiobook Bot by revela
# import discord
# from discord.ext import commands
import nextcord as discord
from nextcord.ext import commands
import os
import logging
import asyncio

from config import BOT_TOKEN
from logging_setup import setup_logging

setup_logging()
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
bot = commands.AutoShardedBot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.sync_all_application_commands()
        log.info("Synced slash commands.")
    except Exception as e:
        log.error(f"Failed to sync commands: {e}")
    log.info(f"Successfully loaded {len(bot.cogs)} cogs.")

def main():
    # Load cogs synchronously (nextcord style)
    for filename in os.listdir('./cogs'):
        if filename.endswith('_cog.py'):
            try:
                bot.load_extension(f'cogs.{filename[:-3]}')
                log.info(f"Successfully loaded cog: {filename}")
            except Exception as e:
                log.exception(f"Failed to load cog: {filename}", exc_info=e)

    if not BOT_TOKEN:
        log.critical("!!! BOT_TOKEN NOT FOUND !!! Check your .env and config.py file.")
    else:
        log.info("BOT_TOKEN found. Attempting to connect to Discord...")
        try:
            bot.run(BOT_TOKEN)
        except Exception:
            log.exception("A fatal error occurred during bot execution.")
        finally:
            log.info("================== BOT SHUTTING DOWN ==================")

if __name__ == "__main__":
    asyncio.run(main())