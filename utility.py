import discord
from discord.ext import commands
from discord import app_commands
import time
import platform
import psutil
import config

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: app_commands.Interaction):
        """Check the bot's latency"""
        start_time = time.time()
        await interaction.response.defer()
        end_time = time.time()
        
        api_latency = round(self.bot.latency * 1000)
        response_time = round((end_time - start_time) * 1000)
        
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="API Latency", value=f"{api_latency}ms", inline=True)
        embed.add_field(name="Response Time", value=f"{response_time}ms", inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="botinfo", description="Display information about the bot")
    async def botinfo(self, interaction: app_commands.Interaction):
        """Display information about the bot"""
        # Get bot information
        bot_version = "1.0.0"
        python_version = platform.python_version()
        discord_py_version = discord.__version__
        
        # Get system information
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        
        # Create embed
        embed = discord.Embed(
            title=f"{self.bot.user.name} Info",
            description="A Discord bot with moderation, auto-role, and AI chat capabilities.",
            color=discord.Color.blue()
        )
        
        # Add bot fields
        embed.add_field(name="Bot Version", value=bot_version, inline=True)
        embed.add_field(name="Python Version", value=python_version, inline=True)
        embed.add_field(name="Discord.py Version", value=discord_py_version, inline=True)
        
        # Add system fields
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=True)
        embed.add_field(name="Memory Usage", value=f"{memory_usage}%", inline=True)
        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=True)
        
        # Add bot stats
        embed.add_field(name="Commands", value=len(self.bot.tree.get_commands()), inline=True)
        embed.add_field(name="Users", value=len(self.bot.users), inline=True)
        embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
        
        # Set thumbnail and footer
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="serverinfo", description="Display information about the server")
    async def serverinfo(self, interaction: app_commands.Interaction):
        """Display information about the server"""
        guild = interaction.guild
        
        # Get member counts
        total_members = guild.member_count
        online_members = len([m for m in guild.members if m.status != discord.Status.offline])
        bot_count = len([m for m in guild.members if m.bot])
        
        # Get channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        # Create embed
        embed = discord.Embed(
            title=f"{guild.name} Info",
            description=guild.description or "No description",
            color=discord.Color.gold()
        )
        
        # Add server fields
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        
        # Add member fields
        embed.add_field(name="Total Members", value=total_members, inline=True)
        embed.add_field(name="Online Members", value=online_members, inline=True)
        embed.add_field(name="Bot Count", value=bot_count, inline=True)
        
        # Add channel fields
        embed.add_field(name="Text Channels", value=text_channels, inline=True)
        embed.add_field(name="Voice Channels", value=voice_channels, inline=True)
        embed.add_field(name="Categories", value=categories, inline=True)
        
        # Add role count
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Emojis", value=len(guild.emojis), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
        
        # Set server icon and footer
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="userinfo", description="Display information about a user")
    @app_commands.describe(member="The user to get information about (leave empty for yourself)")
    async def userinfo(self, interaction: app_commands.Interaction, member: discord.Member = None):
        """Display information about a user"""
        member = member or interaction.user
        
        # Get user information
        roles = [role.mention for role in member.roles if role != interaction.guild.default_role]
        roles_str = ", ".join(roles) if roles else "None"
        
        # Create embed
        embed = discord.Embed(
            title=f"{member} Info",
            color=member.color
        )
        
        # Add user fields
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        
        # Add date fields
        embed.add_field(name="Created At", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name="Joined At", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name="Boosting Since", value=member.premium_since.strftime("%Y-%m-%d %H:%M:%S") if member.premium_since else "Not boosting", inline=True)
        
        # Add role information
        embed.add_field(name=f"Roles [{len(roles)}]", value=roles_str, inline=False)
        
        # Set user avatar and footer
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="help", description="Display help information")
    @app_commands.describe(command="The command to get help for")
    async def help(self, interaction: app_commands.Interaction, command: str = None):
        """Display help information"""
        if command is None:
            # Create main help embed
            embed = discord.Embed(
                title="Bot Help",
                description="Here are all my available commands:",
                color=discord.Color.blue()
            )
            
            # Get all commands grouped by cog
            for cog_name, cog in self.bot.cogs.items():
                # Skip hidden cogs
                if cog_name.startswith("_"):
                    continue
                
                # Get commands for this cog
                commands_list = cog.app_commands if hasattr(cog, 'app_commands') else []
                if not commands_list:
                    continue
                
                # Add field for this category
                command_list = "\n".join([f"`/{cmd.name}` - {cmd.description}" for cmd in commands_list])
                embed.add_field(name=cog_name, value=command_list, inline=False)
            
            # Set footer
            embed.set_footer(text="Use /help <command> for more info on a command.")
            
        else:
            # Find the command
            cmd = discord.utils.get(self.bot.tree.get_commands(), name=command.lower())
            if cmd is None:
                await interaction.response.send_message(f"Command `{command}` not found.", ephemeral=True)
                return
            
            # Create command help embed
            embed = discord.Embed(
                title=f"Help: /{cmd.name}",
                description=cmd.description,
                color=discord.Color.blue()
            )
            
            # Add parameters if any
            if cmd.parameters:
                params = []
                for param in cmd.parameters:
                    if param.required:
                        params.append(f"<{param.name}>")
                    else:
                        params.append(f"[{param.name}]")
                usage = f"/{cmd.name} {' '.join(params)}"
                embed.add_field(name="Usage", value=usage, inline=False)
            
            # Set footer
            embed.set_footer(text="<> = required, [] = optional")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sync", description="Sync bot commands with Discord")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: app_commands.Interaction):
        """Sync slash commands with Discord"""
        await interaction.response.defer(ephemeral=True)
        
        # Only allow bot owner to use
        if interaction.user.id != config.OWNER_ID:
            await interaction.followup.send("This command can only be used by the bot owner.", ephemeral=True)
            return
            
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"Successfully synced {len(synced)} command(s).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error syncing commands: {str(e)}", ephemeral=True)
    
    def get_uptime(self):
        """Get the bot's uptime"""
        # This would normally calculate uptime from bot start time
        # For simplicity, we'll just return a placeholder
        return "Coming soon"

async def setup(bot):
    await bot.add_cog(Utility(bot)) 