import discord
from discord.ext import commands
import asyncio
import os
import logging
import config
import sys

# Set up logging with proper encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(stream=sys.stdout)  # Use stdout to handle Unicode properly
    ]
)
logger = logging.getLogger("bot")

# Initialize bot with intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True
intents.messages = True
intents.guild_messages = True
intents.dm_messages = True
intents.message_content = True
intents.reactions = True  # Added for potential future features
intents.voice_states = True  # Added for potential future features

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            case_insensitive=True,
            help_command=None  # Disable default help command
        )
    
    async def setup_hook(self):
        """Called when the bot is setting up"""
        # Load extensions
        await load_extensions(self)
        
        # Sync slash commands with Discord
        logger.info("Syncing slash commands...")
        for guild in self.guilds:
            try:
                await self.tree.sync(guild=guild)
            except Exception as e:
                logger.error(f"Failed to sync commands for guild {guild.id}: {e}")
        await self.tree.sync()
        logger.info("Slash commands synced")

    async def on_message(self, message):
        """Handle message events including mentions"""
        # Ignore messages from self
        if message.author == self.user:
            return

        # Process commands first
        await self.process_commands(message)

        # Handle mentions and replies
        if message.content.strip() == f'<@{self.user.id}>' or message.content.strip() == f'<@!{self.user.id}>':
            # If the message is just a mention, send a help message
            embed = discord.Embed(
                title="Hello! 👋",
                description="I'm a bot with moderation, auto-role, and AI chat capabilities.\nUse `/help` to see my commands!",
                color=discord.Color.blue()
            )
            await message.reply(embed=embed)
            return

# Create bot instance
bot = Bot()

# Bot events
@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Set bot status
    activity_type = discord.ActivityType.watching
    activity_name = config.BOT_ACTIVITY
    activity = discord.Activity(type=activity_type, name=activity_name)
    
    await bot.change_presence(status=getattr(discord.Status, config.BOT_STATUS), activity=activity)
    
    logger.info(f"Bot is ready! Serving {len(bot.guilds)} guilds.")

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Bad argument: {error}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"I don't have the required permissions: {', '.join(error.missing_permissions)}")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"An error occurred: {error}")

@bot.event
async def on_guild_join(guild):
    """Called when the bot joins a guild"""
    try:
        # Use a safe version of the guild name to avoid Unicode encoding issues
        safe_guild_name = repr(guild.name)
        logger.info(f"Joined guild: {safe_guild_name} (ID: {guild.id})")
        
        # Sync slash commands for the new guild
        try:
            await bot.tree.sync(guild=guild)
            logger.info(f"Synced slash commands for guild {guild.id}")
        except Exception as e:
            logger.error(f"Failed to sync commands for guild {guild.id}: {e}")
        
        # Find a suitable channel to send welcome message
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="Thanks for adding me!",
                    description="I'm a Discord bot with moderation, auto-role, and AI chat capabilities.",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Getting Started",
                    value=f"Use `/help` to see available commands."
                )
                embed.set_footer(text="Made with ❤️")
                
                await channel.send(embed=embed)
                break
    except Exception as e:
        logger.error(f"Error in on_guild_join: {e}")

# Load cogs
async def load_extensions(bot):
    """Load all cog extensions"""
    # List of cogs to load
    cogs = [
        "moderation",
        "autorole",
        "aichat",
        "utility",
        "leveling",
        "reactionroles"
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded extension: {cog}")
        except Exception as e:
            logger.error(f"Failed to load extension {cog}: {e}")

# Run the bot
if __name__ == "__main__":
    try:
        asyncio.run(bot.start(config.DISCORD_TOKEN))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Bot crashed: {e}") 