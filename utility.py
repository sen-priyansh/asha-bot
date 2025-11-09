import discord
from discord.ext import commands
from discord import app_commands
import time
import platform
import psutil
import config
from typing import List, Tuple

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
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
    async def botinfo(self, interaction: discord.Interaction):
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
    async def serverinfo(self, interaction: discord.Interaction):
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
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
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
    async def help(self, interaction: discord.Interaction, command: str = None):
        """Display help information with a complete list of slash commands and usage.

        - Without arguments: lists all commands (including group subcommands) with usage.
        - With an argument: supports full-path lookup like "level admin setxp" or a single command name.
        """

        def _format_usage(cmd: app_commands.Command, path: str) -> str:
            if getattr(cmd, "parameters", None):
                parts = []
                for p in cmd.parameters:
                    parts.append(f"<{p.name}>" if p.required else f"[{p.name}]")
                return f"/{path} {' '.join(parts)}".strip()
            return f"/{path}"

        def _flatten(cmds: List[app_commands.Command], parents: List[str]) -> List[Tuple[str, app_commands.Command]]:
            out: List[Tuple[str, app_commands.Command]] = []
            for c in cmds:
                if isinstance(c, app_commands.Group):
                    # Recurse into group
                    out.extend(_flatten(c.commands, parents + [c.name]))
                else:
                    full_path = " ".join(parents + [c.name])
                    out.append((full_path, c))
            return out

        all_top = self.bot.tree.get_commands()

        # If a specific command was requested, try to resolve it smartly
        if command:
            query = command.lower().strip()
            # Try full-path match first
            flat = _flatten(all_top, [])
            target = None
            for path, c in flat:
                if path.lower() == query or c.name.lower() == query:
                    target = (path, c)
                    break
            if not target:
                await interaction.response.send_message(f"Command `{command}` not found.", ephemeral=True)
                return

            path, cmd_obj = target
            embed = discord.Embed(
                title=f"Help: /{path}",
                description=cmd_obj.description or "(no description)",
                color=discord.Color.blue()
            )
            embed.add_field(name="Usage", value=_format_usage(cmd_obj, path), inline=False)

            # List choices/hints if available
            hints = []
            if getattr(cmd_obj, "parameters", None):
                for p in cmd_obj.parameters:
                    hint = f"- {p.name}: {'required' if p.required else 'optional'}"
                    if getattr(p, "description", None):
                        hint += f" — {p.description}"
                    hints.append(hint)
            if hints:
                embed.add_field(name="Parameters", value="\n".join(hints), inline=False)
            embed.set_footer(text="<> = required, [] = optional")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # No specific command: produce a complete listing (chunked if needed)
        flat = _flatten(all_top, [])
        # Sort by path for stable display
        flat.sort(key=lambda t: t[0])

        # Build lines and chunk into multiple embeds if necessary
        lines: List[str] = []
        for path, c in flat:
            usage = _format_usage(c, path)
            desc = c.description or "(no description)"
            lines.append(f"• {usage}\n  — {desc}")

        header = (
            "Here are all available slash commands. "
            "Tip: use `/help <command>` (e.g., `/help level admin setxp`) for focused details."
        )

        chunks: List[List[str]] = []
        current: List[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 3800:  # keep well below 4096 desc limit
                chunks.append(current)
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            chunks.append(current)

        # Send one or multiple embeds
        first = True
        for idx, part in enumerate(chunks, start=1):
            embed = discord.Embed(
                title="All Commands" + (f" (Page {idx}/{len(chunks)})" if len(chunks) > 1 else ""),
                description=(header + "\n\n" if first else "") + "\n".join(part),
                color=discord.Color.blue()
            )
            if first:
                await interaction.response.send_message(embed=embed, ephemeral=True)
                first = False
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="sync", description="Sync bot commands with Discord")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
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