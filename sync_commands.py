import discord
from discord.ext import commands
import asyncio
import logging
import sys
import config

# Set up logging with proper encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sync.log", encoding='utf-8'),
        logging.StreamHandler(stream=sys.stdout)  # Use stdout to handle Unicode properly
    ]
)
logger = logging.getLogger("sync")

# Initialize bot with necessary intents
intents = discord.Intents.default()
intents.members = True

# Create bot instance - we don't need to load all the cogs
# We just need to sync the commands that are already registered
bot = commands.Bot(
    command_prefix=config.PREFIX,
    intents=intents,
    case_insensitive=True,
    help_command=None
)

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot is ready! Serving {len(bot.guilds)} guilds.")
    
    try:
        # First check if any args were specified
        if len(sys.argv) > 1 and sys.argv[1] == "--guild":
            if len(sys.argv) > 2:
                guild_id = int(sys.argv[2])
                guild = bot.get_guild(guild_id)
                if guild:
                    # Use repr for safe handling of guild names with emoji
                    safe_guild_name = repr(guild.name)
                    logger.info(f"Syncing for specific guild: {safe_guild_name} ({guild.id})")
                    await bot.tree.sync(guild=guild)
                    logger.info(f"Successfully synced commands for guild {safe_guild_name}")
                else:
                    logger.error(f"Guild with ID {guild_id} not found")
            else:
                logger.error("Guild ID not provided. Usage: python sync_commands.py --guild <guild_id>")
        else:
            # Sync globally
            logger.info("Syncing commands globally")
            await bot.tree.sync()
            logger.info("Successfully synced commands globally")
            
            # Also sync for each guild individually
            logger.info("Syncing commands for each guild")
            for guild in bot.guilds:
                try:
                    # Use repr for safe handling of guild names with emoji
                    safe_guild_name = repr(guild.name)
                    await bot.tree.sync(guild=guild)
                    logger.info(f"Successfully synced commands for guild {safe_guild_name}")
                except Exception as e:
                    logger.error(f"Failed to sync commands for guild {guild.id}: {e}")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")
    finally:
        # Exit once we're done
        await bot.close()

# Run the bot
if __name__ == "__main__":
    try:
        asyncio.run(bot.start(config.DISCORD_TOKEN))
    except KeyboardInterrupt:
        logger.info("Sync stopped by user.")
    except Exception as e:
        logger.error(f"Sync failed: {e}") 