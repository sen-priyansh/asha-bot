import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import config

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.warnings = {}  # {guild_id: {user_id: [warnings]}}
        self.muted_users = {}  # {guild_id: {user_id: unmute_time}}
        self._mute_task = None
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        self._mute_task = asyncio.create_task(self.check_mute_expiry())
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        if self._mute_task:
            self._mute_task.cancel()
    
    async def check_mute_expiry(self):
        """Check for expired mutes and unmute users"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            current_time = datetime.now()
            for guild_id in list(self.muted_users.keys()):
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue
                    
                # Get the mute role
                mute_role = discord.utils.get(guild.roles, name=config.MUTE_ROLE_NAME)
                if not mute_role:
                    continue
                    
                for user_id, unmute_time in list(self.muted_users[guild_id].items()):
                    if current_time >= unmute_time:
                        member = guild.get_member(int(user_id))
                        if member and mute_role in member.roles:
                            try:
                                await member.remove_roles(mute_role)
                                del self.muted_users[guild_id][user_id]
                                
                                # Send notification
                                for channel in guild.text_channels:
                                    if channel.permissions_for(guild.me).send_messages:
                                        await channel.send(f"{member.mention} has been unmuted.")
                                        break
                            except discord.Forbidden:
                                print(f"Failed to unmute {member} in {guild}: Missing permissions")
                            except Exception as e:
                                print(f"Error unmuting {member} in {guild}: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)
    
    async def create_mute_role(self, guild):
        """Create a mute role if it doesn't exist"""
        mute_role = discord.utils.get(guild.roles, name=config.MUTE_ROLE_NAME)
        if not mute_role:
            try:
                # Create the mute role
                mute_role = await guild.create_role(
                    name=config.MUTE_ROLE_NAME,
                    reason="Role for muted users"
                )
                
                # Set permissions for all channels
                for channel in guild.channels:
                    await channel.set_permissions(
                        mute_role,
                        send_messages=False,
                        add_reactions=False,
                        speak=False
                    )
                
                return mute_role
            except discord.Forbidden:
                return None
        return mute_role
    
    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="The member to ban", reason="The reason for the ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        """Ban a member from the server"""
        if interaction.user.top_role <= member.top_role:
            await interaction.response.send_message("You cannot ban someone with a higher or equal role.", ephemeral=True)
            return
            
        try:
            await member.ban(reason=reason)
            embed = discord.Embed(
                title="Member Banned",
                description=f"{member.mention} has been banned.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason)
            embed.set_footer(text=f"Banned by {interaction.user}")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to ban members.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    
    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="The reason for the kick")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        """Kick a member from the server"""
        if interaction.user.top_role <= member.top_role:
            await interaction.response.send_message("You cannot kick someone with a higher or equal role.", ephemeral=True)
            return
            
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                title="Member Kicked",
                description=f"{member.mention} has been kicked.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=reason)
            embed.set_footer(text=f"Kicked by {interaction.user}")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick members.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    
    @app_commands.command(name="mute", description="Mute a member for a specified duration")
    @app_commands.describe(
        member="The member to mute",
        duration="Duration of the mute (e.g., 30s, 5m, 1h, 1d)",
        reason="The reason for the mute"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str = "1h", reason: str = "No reason provided"):
        """Mute a member for a specified duration"""
        if interaction.user.top_role <= member.top_role:
            await interaction.response.send_message("You cannot mute someone with a higher or equal role.", ephemeral=True)
            return
            
        # Parse duration
        duration_seconds = config.DEFAULT_MUTE_DURATION
        try:
            time_unit = duration[-1].lower()
            time_value = int(duration[:-1])
            
            if time_unit == 's':
                duration_seconds = time_value
            elif time_unit == 'm':
                duration_seconds = time_value * 60
            elif time_unit == 'h':
                duration_seconds = time_value * 3600
            elif time_unit == 'd':
                duration_seconds = time_value * 86400
            else:
                await interaction.response.send_message("Invalid time unit. Use s (seconds), m (minutes), h (hours), or d (days).", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("Invalid duration format. Use a number followed by s, m, h, or d (e.g., 30m, 2h).", ephemeral=True)
            return
            
        # Get or create mute role
        mute_role = await self.create_mute_role(interaction.guild)
        if not mute_role:
            await interaction.response.send_message("I couldn't create or find the mute role. Please check my permissions.", ephemeral=True)
            return
            
        try:
            # Add role to member
            await member.add_roles(mute_role, reason=reason)
            
            # Calculate unmute time
            unmute_time = datetime.now() + timedelta(seconds=duration_seconds)
            
            # Store mute information
            guild_id = str(interaction.guild.id)
            user_id = str(member.id)
            
            if guild_id not in self.muted_users:
                self.muted_users[guild_id] = {}
                
            self.muted_users[guild_id][user_id] = unmute_time
            
            # Create embed
            embed = discord.Embed(
                title="Member Muted",
                description=f"{member.mention} has been muted.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Duration", value=duration)
            embed.add_field(name="Unmute Time", value=unmute_time.strftime("%Y-%m-%d %H:%M:%S"))
            embed.set_footer(text=f"Muted by {interaction.user}")
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    
    @app_commands.command(name="unmute", description="Unmute a muted member")
    @app_commands.describe(member="The member to unmute")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        """Unmute a muted member"""
        mute_role = discord.utils.get(interaction.guild.roles, name=config.MUTE_ROLE_NAME)
        if not mute_role:
            await interaction.response.send_message("Mute role not found.", ephemeral=True)
            return
            
        if mute_role not in member.roles:
            await interaction.response.send_message(f"{member.mention} is not muted.", ephemeral=True)
            return
            
        try:
            await member.remove_roles(mute_role)
            
            # Remove from muted users
            guild_id = str(interaction.guild.id)
            user_id = str(member.id)
            
            if guild_id in self.muted_users and user_id in self.muted_users[guild_id]:
                del self.muted_users[guild_id][user_id]
            
            await interaction.response.send_message(f"{member.mention} has been unmuted.")
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="The reason for the warning")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        """Warn a member"""
        if interaction.user.top_role <= member.top_role:
            await interaction.response.send_message("You cannot warn someone with a higher or equal role.", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.warnings:
            self.warnings[guild_id] = {}
            
        if user_id not in self.warnings[guild_id]:
            self.warnings[guild_id][user_id] = []
            
        warning = {
            "reason": reason,
            "timestamp": datetime.now(),
            "moderator": interaction.user.id
        }
        
        self.warnings[guild_id][user_id].append(warning)
        
        # Create embed
        embed = discord.Embed(
            title="Member Warned",
            description=f"{member.mention} has been warned.",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Warning Count", value=len(self.warnings[guild_id][user_id]))
        embed.set_footer(text=f"Warned by {interaction.user}")
        
        await interaction.response.send_message(embed=embed)
        
        # DM the user
        try:
            dm_embed = discord.Embed(
                title=f"Warning in {interaction.guild.name}",
                description=f"You have been warned.",
                color=discord.Color.yellow()
            )
            dm_embed.add_field(name="Reason", value=reason)
            dm_embed.add_field(name="Warning Count", value=len(self.warnings[guild_id][user_id]))
            
            await member.send(embed=dm_embed)
        except:
            await interaction.followup.send("Could not DM the user about their warning.", ephemeral=True)
    
    @app_commands.command(name="warnings", description="Show warnings for a member")
    @app_commands.describe(member="The member to check warnings for")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        """Show warnings for a member"""
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.warnings or user_id not in self.warnings[guild_id] or not self.warnings[guild_id][user_id]:
            await interaction.response.send_message(f"{member.mention} has no warnings.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title=f"Warnings for {member}",
            description=f"{member.mention} has {len(self.warnings[guild_id][user_id])} warnings.",
            color=discord.Color.yellow()
        )
        
        for i, warning in enumerate(self.warnings[guild_id][user_id], 1):
            moderator = interaction.guild.get_member(warning["moderator"])
            moderator_name = moderator.name if moderator else "Unknown Moderator"
            
            embed.add_field(
                name=f"Warning {i}",
                value=f"**Reason:** {warning['reason']}\n"
                      f"**Date:** {warning['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                      f"**Moderator:** {moderator_name}",
                inline=False
            )
            
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member")
    @app_commands.describe(member="The member to clear warnings for")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        """Clear all warnings for a member"""
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.warnings or user_id not in self.warnings[guild_id] or not self.warnings[guild_id][user_id]:
            await interaction.response.send_message(f"{member.mention} has no warnings to clear.", ephemeral=True)
            return
            
        warning_count = len(self.warnings[guild_id][user_id])
        self.warnings[guild_id][user_id] = []
        
        await interaction.response.send_message(f"Cleared {warning_count} warnings for {member.mention}")
    
    @app_commands.command(name="purge", description="Delete a specified number of messages")
    @app_commands.describe(amount="The number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        """Delete a specified number of messages"""
        if amount <= 0 or amount > 100:
            await interaction.response.send_message("Please provide a number between 1 and 100.", ephemeral=True)
            return
            
        try:
            # Defer the response since this might take a while
            await interaction.response.defer(ephemeral=True)
            
            # Delete messages
            deleted = await interaction.channel.purge(limit=amount)
            
            # Send confirmation
            await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to delete messages.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot)) 