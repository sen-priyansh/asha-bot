import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
import random
from typing import Dict, Optional, List, Union
import logging
import time
import aiohttp
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from urllib.parse import urlparse
import datetime

logger = logging.getLogger("bot")

class Leveling(commands.GroupCog, name="level"):
    def __init__(self, bot):
        self.bot = bot
        self.xp_data = {}  # {guild_id: {user_id: {"xp": xp, "level": level}}}
        self.level_roles = {}  # {guild_id: {level: role_id}}
        self.message_cooldowns = {}  # {guild_id: {user_id: last_time}}
        # Custom message templates
        self.level_messages = {}  # {guild_id: {level?: message_template}}
        # Background images for level cards
        self.background_images = {}  # {guild_id: {user_id?: image_url}}
        self.xp_cooldown = 60  # 1 minute cooldown between XP awards
        self.min_xp = 10  # Minimum XP awarded per message
        self.max_xp = 20  # Maximum XP awarded per message
        self.data_file = 'leveling.json'
        self.roles_file = 'level_roles.json'
        self.messages_file = 'level_messages.json'
        self.backgrounds_file = 'level_backgrounds.json'
        self.fonts_dir = 'fonts'
        self.images_dir = 'level_images'
        
        # Create directories if they don't exist
        os.makedirs(self.fonts_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        
        self.load_data()
        self.save_task.start()
        super().__init__()
        
    # Basic level commands group
    level_group = app_commands.Group(name="level", description="Basic level commands")
    
    @level_group.command(name="check", description="Check your or another user's level")
    @app_commands.describe(member="The member to check the level of (optional)")
    async def check(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Check level command"""
        member = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.xp_data or user_id not in self.xp_data[guild_id]:
            await interaction.response.send_message(f"{member.mention} hasn't earned any XP yet!", ephemeral=True)
            return
            
        data = self.xp_data[guild_id][user_id]
        current_level = data["level"]
        current_xp = data["xp"]
        next_level_xp = self.get_xp_for_level(current_level)
        progress = current_xp - sum(self.get_xp_for_level(l) for l in range(current_level))
        
        embed = discord.Embed(
            title=f"{member.name}'s Level",
            color=discord.Color.blue()
        )
        embed.add_field(name="Level", value=str(current_level))
        embed.add_field(name="XP", value=f"{current_xp}/{next_level_xp}")
        embed.add_field(name="Progress", value=f"{progress}/{next_level_xp - self.get_xp_for_level(current_level - 1) if current_level > 0 else next_level_xp}")
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)

    @level_group.command(name="leaderboard", description="Show the server's XP leaderboard")
    @app_commands.describe(page="Page number to view (optional)")
    async def level_leaderboard(self, interaction: discord.Interaction, page: int = 1):
        """Show top users by XP"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.xp_data or not self.xp_data[guild_id]:
            await interaction.response.send_message("No XP data available for this server yet!", ephemeral=True)
            return
            
        # Sort users by XP
        sorted_users = sorted(
            self.xp_data[guild_id].items(),
            key=lambda x: x[1]["xp"],
            reverse=True
        )
        
        # Paginate results (10 per page)
        per_page = 10
        total_pages = (len(sorted_users) + per_page - 1) // per_page
        
        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"Invalid page number. Please specify a page between 1 and {total_pages}.", ephemeral=True)
            return
            
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(sorted_users))
        
        embed = discord.Embed(
            title=f"XP Leaderboard - {interaction.guild.name}",
            description=f"Page {page}/{total_pages}",
            color=discord.Color.gold()
        )
        
        for idx, (user_id, data) in enumerate(sorted_users[start_idx:end_idx], start=start_idx + 1):
            try:
                member = await interaction.guild.fetch_member(int(user_id))
                member_name = member.display_name
            except:
                member_name = f"Unknown User ({user_id})"
                
            embed.add_field(
                name=f"#{idx}. {member_name}",
                value=f"Level: {data['level']} | XP: {data['xp']}",
                inline=False
            )
            
        await interaction.response.send_message(embed=embed)

    # Admin commands group
    admin_group = app_commands.Group(name="admin", description="Admin level commands")
    
    @admin_group.command(name="setxp", description="Set a user's XP (Admin only)")
    @app_commands.describe(member="The member to set XP for", xp="The amount of XP to set")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_setxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
        """Set XP command"""
        if xp < 0:
            await interaction.response.send_message("XP cannot be negative!", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}
            
        self.xp_data[guild_id][user_id] = {
            "xp": xp,
            "level": self.get_level_from_xp(xp)
        }
        await self.save_data()
        
        await interaction.response.send_message(f"Set {member.mention}'s XP to {xp} (Level {self.xp_data[guild_id][user_id]['level']}).")

    @admin_group.command(name="addxp", description="Add XP to a user (Admin only)")
    @app_commands.describe(member="The member to add XP to", xp="The amount of XP to add")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_addxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
        """Add XP command"""
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}
        if user_id not in self.xp_data[guild_id]:
            self.xp_data[guild_id][user_id] = {"xp": 0, "level": 0}
            
        current_xp = self.xp_data[guild_id][user_id]["xp"]
        current_level = self.xp_data[guild_id][user_id]["level"]
        
        new_xp = current_xp + xp
        new_level = self.get_level_from_xp(new_xp)
        
        self.xp_data[guild_id][user_id]["xp"] = new_xp
        self.xp_data[guild_id][user_id]["level"] = new_level
        
        await self.save_data()
        
        await interaction.response.send_message(f"Added {xp} XP to {member.mention}. They are now level {new_level}.")

    @admin_group.command(name="setlevel", description="Set a user's level")
    @app_commands.describe(member="The member to set the level for", level="The level to set for the member")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level(self, interaction: discord.Interaction, member: discord.Member, level: int):
        """Set a user's level"""
        if level < 0:
            await interaction.response.send_message("Level cannot be negative", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}
            
        xp_required = self.get_xp_for_level(level)
        
        # Update user's level data
        self.xp_data[guild_id][user_id] = {
            "xp": xp_required,
            "level": level,
            "last_message": int(time.time())
        }
        
        # Save updated data
        await self.save_data()
            
        await interaction.response.send_message(f"{member.mention}'s level has been set to {level}")
        
        # Check and assign any role rewards
        await self.check_level_roles(member, level)
    
    @admin_group.command(name="diagnose", description="Check and fix potential issues in the leveling system")
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnose_leveling(self, interaction: discord.Interaction):
        """Diagnose leveling system command"""
        await interaction.response.defer(ephemeral=True)
        
        issues_found = 0
        issues_fixed = 0
        results = []
        
        # Check for mismatched levels and XP
        for guild_id, guild_data in self.xp_data.items():
            for user_id, user_data in guild_data.items():
                current_xp = user_data["xp"]
                current_level = user_data["level"]
                calculated_level = self.get_level_from_xp(current_xp)
                
                if current_level != calculated_level:
                    issues_found += 1
                    results.append(f"User {user_id} in server {guild_id} has level {current_level} but should be {calculated_level} based on XP ({current_xp})")
                    
                    # Fix the issue
                    self.xp_data[guild_id][user_id]["level"] = calculated_level
                    issues_fixed += 1
                    results.append(f" - Fixed: Set level to {calculated_level}")
        
        # Check level roles for invalid entries
        for guild_id, guild_roles in self.level_roles.items():
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    issues_found += 1
                    results.append(f"Server {guild_id} not found but has level role data")
                    continue
                
                for level, role_id in list(guild_roles.items()):
                    role = guild.get_role(int(role_id))
                    if not role:
                        issues_found += 1
                        results.append(f"Role {role_id} for level {level} in server {guild_id} not found")
                        
                        # Fix the issue
                        del self.level_roles[guild_id][level]
                        issues_fixed += 1
                        results.append(f" - Fixed: Removed invalid role entry")
            except Exception as e:
                results.append(f"Error checking server {guild_id}: {e}")
        
        # Save any changes
        if issues_fixed > 0:
            await self.save_data()
            await self.save_level_roles()
        
        # Send report
        if issues_found == 0:
            await interaction.followup.send("✅ No issues found in the leveling system!", ephemeral=True)
        else:
            embed = discord.Embed(
                title="Leveling System Diagnostic",
                description=f"Found {issues_found} issues, fixed {issues_fixed}",
                color=discord.Color.gold()
            )
            
            # Split results into chunks if there are too many
            chunks = [results[i:i+10] for i in range(0, len(results), 10)]
            for i, chunk in enumerate(chunks):
                embed.add_field(
                    name=f"Issues {i*10+1}-{i*10+len(chunk)}",
                    value="\n".join(chunk),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @admin_group.command(name="backup", description="Create a backup of the leveling system data")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_leveling(self, interaction: discord.Interaction):
        """Backup leveling data command"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Create timestamp for filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create backup files
            xp_backup = f"leveling_backup_{timestamp}.json"
            roles_backup = f"level_roles_backup_{timestamp}.json"
            
            with open(self.data_file, 'r') as f:
                xp_data = f.read()
                
            with open(self.roles_file, 'r') as f:
                roles_data = f.read()
                
            # Create files to send
            xp_file = discord.File(io.BytesIO(xp_data.encode('utf-8')), filename=xp_backup)
            roles_file = discord.File(io.BytesIO(roles_data.encode('utf-8')), filename=roles_backup)
            
            # Send backup files
            await interaction.followup.send(
                content=f"📦 Here are your leveling system backup files for {interaction.guild.name}.\nKeep these files safe for future restoration if needed.",
                files=[xp_file, roles_file],
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Error creating backup: {e}", ephemeral=True)

    # Role management group
    role_group = app_commands.Group(name="role", description="Role management commands")
    
    @role_group.command(name="set", description="Set a role to be assigned at a specific level")
    @app_commands.describe(level="The level to assign the role at", role="The role to assign")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def level_setrole(self, interaction: discord.Interaction, level: int, role: discord.Role):
        """Set level role command"""
        if level < 1:
            await interaction.response.send_message("Level must be at least 1!", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        if guild_id not in self.level_roles:
            self.level_roles[guild_id] = {}
            
        self.level_roles[guild_id][str(level)] = str(role.id)
        await self.save_data()
        
        await interaction.response.send_message(f"Role {role.mention} will be assigned at level {level}.")

    @role_group.command(name="remove", description="Remove a role from being assigned at a level")
    @app_commands.describe(level="The level to remove the role from")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def level_removerole(self, interaction: discord.Interaction, level: int):
        """Remove level role command"""
        guild_id = str(interaction.guild.id)
        if guild_id in self.level_roles and str(level) in self.level_roles[guild_id]:
            del self.level_roles[guild_id][str(level)]
            await self.save_data()
            await interaction.response.send_message(f"Removed role assignment for level {level}.")
        else:
            await interaction.response.send_message(f"No role is set for level {level}.", ephemeral=True)
    
    @role_group.command(name="add", description="Add a role reward for reaching a specific level")
    @app_commands.describe(level="The level at which to award the role", role="The role to award at the specified level")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        """Add level role command"""
        if level < 1:
            await interaction.response.send_message("Level must be at least 1!", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        
        # Check if the bot can manage this role
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                "I cannot assign this role as it's higher than or equal to my highest role.", 
                ephemeral=True
            )
            return
            
        # Initialize level roles if needed
        if guild_id not in self.level_roles:
            self.level_roles[guild_id] = {}
            
        # Add the role
        self.level_roles[guild_id][str(level)] = str(role.id)
        
        # Save changes
        await self.save_level_roles()
        
        # Confirmation
        await interaction.response.send_message(
            f"✅ Role {role.mention} will now be awarded when members reach level {level}.",
            ephemeral=True
        )
    
    @role_group.command(name="delete", description="Remove a role reward from the level system")
    @app_commands.describe(level="The level to remove the role reward from")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_level_role(self, interaction: discord.Interaction, level: int):
        """Remove level role command"""
        guild_id = str(interaction.guild.id)
        
        # Check if this level has a role reward
        if guild_id not in self.level_roles or str(level) not in self.level_roles[guild_id]:
            await interaction.response.send_message(
                f"There is no role reward set for level {level}.",
                ephemeral=True
            )
            return
            
        # Get the role for display purposes
        role_id = self.level_roles[guild_id][str(level)]
        role = interaction.guild.get_role(int(role_id))
        role_mention = role.mention if role else f"Unknown Role (ID: {role_id})"
        
        # Remove the role
        del self.level_roles[guild_id][str(level)]
        
        # Clean up if empty
        if not self.level_roles[guild_id]:
            del self.level_roles[guild_id]
            
        # Save changes
        await self.save_level_roles()
        
        # Confirmation
        await interaction.response.send_message(
            f"✅ Removed {role_mention} as a reward for level {level}.",
            ephemeral=True
        )
    
    @role_group.command(name="list", description="List all role rewards in the level system")
    async def list_level_roles(self, interaction: discord.Interaction):
        """List level roles command"""
        guild_id = str(interaction.guild.id)
        
        # Check if there are any role rewards
        if guild_id not in self.level_roles or not self.level_roles[guild_id]:
            await interaction.response.send_message(
                "No role rewards have been set up for this server.",
                ephemeral=True
            )
            return
            
        # Create embed
        embed = discord.Embed(
            title="Level Role Rewards",
            description="Roles that are automatically assigned when members reach specific levels",
            color=discord.Color.blue()
        )
        
        # Sort levels
        sorted_levels = sorted([int(level) for level in self.level_roles[guild_id].keys()])
        
        # Add fields for each level
        for level in sorted_levels:
            role_id = self.level_roles[guild_id][str(level)]
            role = interaction.guild.get_role(int(role_id))
            
            if role:
                embed.add_field(
                    name=f"Level {level}",
                    value=role.mention,
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"Level {level}",
                    value=f"Unknown Role (ID: {role_id})",
                    inline=False
                )
        
        # Send the embed
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @role_group.command(name="reward", description="Set a role reward for reaching a specific level")
    @app_commands.default_permissions(manage_roles=True)
    async def role_reward(self, interaction: discord.Interaction, level: int, role: discord.Role):
        """Role reward command"""
        if level < 1:
            await interaction.response.send_message("Level must be at least 1!", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        
        # Check if the bot can manage this role
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                "I cannot assign this role as it's higher than or equal to my highest role.", 
                ephemeral=True
            )
            return
            
        # Initialize level roles if needed
        if guild_id not in self.level_roles:
            self.level_roles[guild_id] = {}
            
        # Add the role
        self.level_roles[guild_id][str(level)] = str(role.id)
        
        # Save changes
        await self.save_level_roles()
        
        # Confirmation
        await interaction.response.send_message(
            f"✅ Role {role.mention} will now be awarded when members reach level {level}.",
            ephemeral=True
        )

    # Settings group
    settings_group = app_commands.Group(name="settings", description="Leveling system settings")
    
    @settings_group.command(name="xprate", description="Change the XP gain rate (Admin only)")
    @app_commands.describe(min_xp="Minimum XP to award", max_xp="Maximum XP to award", cooldown="Cooldown in seconds between XP awards")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_xprate(self, interaction: discord.Interaction, min_xp: int, max_xp: int, cooldown: int):
        """Set XP rate command"""
        if min_xp < 0 or max_xp < min_xp or cooldown < 0:
            await interaction.response.send_message("Invalid values! Make sure min_xp >= 0, max_xp >= min_xp, and cooldown >= 0.", ephemeral=True)
            return
            
        self.min_xp = min_xp
        self.max_xp = max_xp
        self.xp_cooldown = cooldown
        
        await interaction.response.send_message(
            f"Updated XP settings:\n"
            f"Minimum XP: {min_xp}\n"
            f"Maximum XP: {max_xp}\n"
            f"Cooldown: {cooldown} seconds"
        )
    
    @settings_group.command(name="setmessage", description="Set a custom level-up message")
    @app_commands.describe(
        level="Specific level to set message for (0 for default message)",
        message="Custom message to display when users level up. Use {user} for username, {level} for level, {server} for server name"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def level_setmessage(self, interaction: discord.Interaction, level: int, message: str):
        """Set a custom level-up message"""
        guild_id = str(interaction.guild.id)
        
        # Initialize if needed
        if guild_id not in self.level_messages:
            self.level_messages[guild_id] = {}
            
        # Set the message template
        # Level 0 is the default message for all levels
        self.level_messages[guild_id][str(level)] = message
        
        # Save to disk
        await self.save_level_messages()
        
        # Confirmation and preview
        preview = message.replace("{user}", interaction.user.mention)
        preview = preview.replace("{level}", str(level if level > 0 else "X"))
        preview = preview.replace("{server}", interaction.guild.name)
        
        embed = discord.Embed(
            title="Level-up Message Set",
            description=f"Set custom level-up message for level {level if level > 0 else 'default'}",
            color=discord.Color.green()
        )
        embed.add_field(name="Message", value=message, inline=False)
        embed.add_field(name="Preview", value=preview, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @settings_group.command(name="clearmessage", description="Clear a custom level-up message")
    @app_commands.describe(level="Level to clear message for (0 for default message)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_clearmessage(self, interaction: discord.Interaction, level: int):
        """Clear a custom level-up message"""
        guild_id = str(interaction.guild.id)
        
        # Check if there are custom messages
        if guild_id not in self.level_messages:
            await interaction.response.send_message("No custom messages are set for this server.", ephemeral=True)
            return
            
        level_str = str(level)
        if level_str not in self.level_messages[guild_id]:
            await interaction.response.send_message(f"No custom message set for level {level}.", ephemeral=True)
            return
            
        # Remove the message
        del self.level_messages[guild_id][level_str]
        
        # Clean up empty dictionaries
        if not self.level_messages[guild_id]:
            del self.level_messages[guild_id]
            
        # Save to disk
        await self.save_level_messages()
        
        await interaction.response.send_message(f"Cleared custom message for level {level if level > 0 else 'default'}.", ephemeral=True)
        
    @settings_group.command(name="listmessages", description="List all custom level-up messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_listmessages(self, interaction: discord.Interaction):
        """List all custom level-up messages"""
        guild_id = str(interaction.guild.id)
        
        # Check if there are custom messages
        if guild_id not in self.level_messages or not self.level_messages[guild_id]:
            await interaction.response.send_message("No custom messages are set for this server.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="Custom Level-up Messages",
            description="All custom level-up messages for this server",
            color=discord.Color.blue()
        )
        
        for level, message in self.level_messages[guild_id].items():
            embed.add_field(
                name=f"Level {level if level != '0' else 'Default'}",
                value=message,
                inline=False
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @settings_group.command(name="levelupchannel", description="Set the channel where level up messages will be sent")
    @app_commands.describe(channel="The channel where level up messages will be sent")
    @app_commands.default_permissions(manage_guild=True)
    async def set_level_up_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            guild_id = str(interaction.guild.id)
            
            if guild_id not in self.leveling_data:
                self.leveling_data[guild_id] = {}
                
            self.leveling_data[guild_id]["level_up_channel"] = channel.id
            await self.save_data()
            
            await interaction.response.send_message(f"Level up messages will now be sent to {channel.mention}")
        except Exception as e:
            await interaction.response.send_message(f"Error setting level up channel: {str(e)}", ephemeral=True)

    @settings_group.command(name="toggleleveling", description="Enable or disable the leveling system in this server")
    @app_commands.describe(enabled="Whether to enable or disable leveling")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_leveling(self, interaction: discord.Interaction, enabled: bool):
        try:
            guild_id = str(interaction.guild.id)
            
            if guild_id not in self.leveling_data:
                self.leveling_data[guild_id] = {}
                
            # Create server section if it doesn't exist
            if "server" not in self.leveling_data[guild_id]:
                self.leveling_data[guild_id]["server"] = {}
                
            # Update the enabled status
            self.leveling_data[guild_id]["server"]["enabled"] = enabled
            
            # Save the updated data
            self.save_leveling_data()
            
            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(
                f"✅ Leveling system has been {status} for this server.",
                ephemeral=True
            )
        except discord.app_commands.errors.MissingPermissions:
            await interaction.response.send_message(
                "You need the 'Manage Server' permission to use this command.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while toggling the leveling system: {str(e)}",
                ephemeral=True
            )
            print(f"Error in toggle_leveling command: {e}")
            
    @settings_group.command(name="togglemessages", description="Enable or disable level up announcements")
    @app_commands.describe(enabled="Whether to enable or disable level up messages")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_level_up_messages(self, interaction: discord.Interaction, enabled: bool):
        try:
            guild_id = str(interaction.guild.id)
            
            if guild_id not in self.leveling_data:
                self.leveling_data[guild_id] = {}
                
            # Create server section if it doesn't exist
            if "server" not in self.leveling_data[guild_id]:
                self.leveling_data[guild_id]["server"] = {}
                
            # Update the level up messages status
            self.leveling_data[guild_id]["server"]["level_up_messages"] = enabled
            
            # Save the updated data
            self.save_leveling_data()
            
            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(
                f"✅ Level up announcements have been {status} for this server.",
                ephemeral=True
            )
        except discord.app_commands.errors.MissingPermissions:
            await interaction.response.send_message(
                "You need the 'Manage Server' permission to use this command.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while toggling level up messages: {str(e)}",
                ephemeral=True
            )
            print(f"Error in toggle_level_up_messages command: {e}")
    
    # Card commands group
    card_group = app_commands.Group(name="card", description="Level card commands")
    
    @card_group.command(name="view", description="View your or someone else's level card")
    @app_commands.describe(
        member="The member to check the level card of (optional)",
        theme="Card theme (default, dark, light, blue, green, red, purple, gold)"
    )
    @app_commands.choices(theme=[
        app_commands.Choice(name="Default", value="default"),
        app_commands.Choice(name="Dark", value="dark"),
        app_commands.Choice(name="Light", value="light"),
        app_commands.Choice(name="Blue", value="blue"),
        app_commands.Choice(name="Green", value="green"),
        app_commands.Choice(name="Red", value="red"),
        app_commands.Choice(name="Purple", value="purple"),
        app_commands.Choice(name="Gold", value="gold")
    ])
    async def level_card(self, interaction: discord.Interaction, member: Optional[discord.Member] = None, theme: str = "default"):
        """Generate and show a level card with background image and theme"""
        member = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        # Check if the user has XP data
        if guild_id not in self.xp_data or user_id not in self.xp_data[guild_id]:
            await interaction.response.send_message(f"{member.mention} hasn't earned any XP yet!", ephemeral=True)
            return
        
        # Defer response since image generation might take some time
        await interaction.response.defer()
        
        # Get user data
        data = self.xp_data[guild_id][user_id]
        current_level = data["level"]
        current_xp = data["xp"]
        
        # Calculate XP for next level
        total_xp_next = sum(self.get_xp_for_level(l) for l in range(current_level + 1))
        # Calculate XP for current level
        total_xp_current = sum(self.get_xp_for_level(l) for l in range(current_level))
        # Progress to next level
        level_xp = self.get_xp_for_level(current_level)
        progress = current_xp - total_xp_current
        percentage = min(100, int((progress / level_xp) * 100))
        
        try:
            # Get server rank
            rank = await self.get_user_rank(guild_id, user_id)
            
            # Generate level card image
            card_bytes = await self.generate_level_card(
                member=member,
                guild_id=guild_id,
                user_id=user_id,
                level=current_level,
                xp=current_xp,
                next_level_xp=total_xp_next,
                percentage=percentage,
                rank=rank,
                theme=theme
            )
            
            # Send the card
            file = discord.File(fp=card_bytes, filename="level_card.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            logger.error(f"Error generating level card: {e}")
            await interaction.followup.send(f"Sorry, there was an error generating the level card. Please try again later.")

    @card_group.command(name="background", description="Set a custom background for your level card")
    @app_commands.describe(
        image_url="URL of the image to use as background (leave empty to reset)",
        member="Member to set background for (admin only, leave empty for yourself)"
    )
    async def level_setbackground(
        self, 
        interaction: discord.Interaction, 
        image_url: Optional[str] = None,
        member: Optional[discord.Member] = None
    ):
        """Set a custom background for level cards"""
        # Check permissions if setting for someone else
        if member and member != interaction.user:
            # Only admins can set backgrounds for others
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("You need administrator permissions to set backgrounds for others.", ephemeral=True)
                return
        
        # Use the requester if no member specified
        target_member = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(target_member.id)
        
        # Initialize background images dict if needed
        if guild_id not in self.background_images:
            self.background_images[guild_id] = {}
        
        # Resetting background
        if not image_url:
            if user_id in self.background_images[guild_id]:
                del self.background_images[guild_id][user_id]
                
                # Clean up if guild dict is empty
                if not self.background_images[guild_id]:
                    del self.background_images[guild_id]
                
                await self.save_backgrounds()
                await interaction.response.send_message(f"Reset background for {target_member.mention}'s level card.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{target_member.mention} doesn't have a custom background.", ephemeral=True)
            return
        
        # Validate the URL
        try:
            # Check if it's a valid URL
            result = urlparse(image_url)
            if not all([result.scheme, result.netloc]):
                await interaction.response.send_message("Invalid URL. Please provide a valid image URL.", ephemeral=True)
                return
            
            # Try to download the image to validate it
            await interaction.response.defer(ephemeral=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("Failed to download the image. Make sure the URL is accessible.", ephemeral=True)
                        return
                    
                    image_data = await resp.read()
                    
                    # Check if it's a valid image
                    try:
                        img = Image.open(io.BytesIO(image_data))
                        img.verify()  # Verify it's a valid image
                        
                        # Save the URL
                        self.background_images[guild_id][user_id] = image_url
                        await self.save_backgrounds()
                        
                        # Generate a preview
                        if guild_id in self.xp_data and user_id in self.xp_data[guild_id]:
                            data = self.xp_data[guild_id][user_id]
                            level = data["level"]
                            xp = data["xp"]
                            
                            # Calculate progress for preview
                            total_xp_next = sum(self.get_xp_for_level(l) for l in range(level + 1))
                            total_xp_current = sum(self.get_xp_for_level(l) for l in range(level))
                            level_xp = self.get_xp_for_level(level)
                            progress = xp - total_xp_current
                            percentage = min(100, int((progress / level_xp) * 100))
                            
                            # Generate preview
                            card_bytes = await self.generate_level_card(
                                member=target_member,
                                guild_id=guild_id,
                                user_id=user_id,
                                level=level,
                                xp=xp,
                                next_level_xp=total_xp_next,
                                percentage=percentage
                            )
                            
                            # Send preview
                            file = discord.File(fp=card_bytes, filename="level_card_preview.png")
                            await interaction.followup.send(
                                content=f"Background set for {target_member.mention}'s level card. Preview:",
                                file=file,
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(f"Background set for {target_member.mention}'s level card. They need to earn some XP to see it in action!", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Invalid image format: {e}")
                        await interaction.followup.send("Invalid image format. Please provide a valid image (PNG, JPG, etc).", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting background: {e}")
            await interaction.followup.send(f"Error setting background: {e}", ephemeral=True)
    
    @card_group.command(name="resetbackgrounds", description="Reset all custom backgrounds (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_resetbackgrounds(self, interaction: discord.Interaction):
        """Reset all custom backgrounds for the server"""
        guild_id = str(interaction.guild.id)
        
        if guild_id in self.background_images:
            backgrounds_count = len(self.background_images[guild_id])
            del self.background_images[guild_id]
            await self.save_backgrounds()
            await interaction.response.send_message(f"Reset {backgrounds_count} custom backgrounds for this server.", ephemeral=True)
        else:
            await interaction.response.send_message("No custom backgrounds were set for this server.", ephemeral=True)
    
    # Additional groups for other commands
    advanced_group = app_commands.Group(name="advanced", description="Advanced level commands")
    
    @advanced_group.command(name="topleaderboard", description="Show the server's XP leaderboard as an image")
    @app_commands.describe(
        page="Page number to view (optional)",
        theme="Card theme (default, dark, light, blue, green, red, purple, gold)"
    )
    @app_commands.choices(theme=[
        app_commands.Choice(name="Default", value="default"),
        app_commands.Choice(name="Dark", value="dark"),
        app_commands.Choice(name="Light", value="light"),
        app_commands.Choice(name="Blue", value="blue"),
        app_commands.Choice(name="Green", value="green"),
        app_commands.Choice(name="Red", value="red"),
        app_commands.Choice(name="Purple", value="purple"),
        app_commands.Choice(name="Gold", value="gold")
    ])
    async def level_topleaderboard(self, interaction: discord.Interaction, page: int = 1, theme: str = "default"):
        """Generate and show a visual leaderboard"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.xp_data or not self.xp_data[guild_id]:
            await interaction.response.send_message("No XP data available for this server yet!", ephemeral=True)
            return
            
        # Sort users by XP
        sorted_users = sorted(
            self.xp_data[guild_id].items(),
            key=lambda x: x[1]["xp"],
            reverse=True
        )
        
        # Paginate results (5 per page for image)
        per_page = 5
        total_pages = (len(sorted_users) + per_page - 1) // per_page
        
        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"Invalid page number. Please specify a page between 1 and {total_pages}.", ephemeral=True)
            return
            
        # Defer response since image generation might take some time
        await interaction.response.defer()
        
        try:
            # Generate the leaderboard image
            leaderboard_bytes = await self.generate_leaderboard_image(
                guild=interaction.guild,
                sorted_users=sorted_users,
                page=page,
                total_pages=total_pages,
                per_page=per_page,
                theme=theme
            )
            
            # Send the image
            file = discord.File(fp=leaderboard_bytes, filename="leaderboard.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            logger.error(f"Error generating leaderboard image: {e}")
            await interaction.followup.send(f"Sorry, there was an error generating the leaderboard image. Please try again later or use `/level leaderboard` instead.")
            
    @advanced_group.command(name="syncfonts", description="Sync fonts for leveling cards (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_syncfonts(self, interaction: discord.Interaction):
        """Download and sync fonts for level cards"""
        await interaction.response.defer(ephemeral=True)
        
        # Ensure directory exists
        os.makedirs(self.fonts_dir, exist_ok=True)
        
        # Define font URLs to download
        fonts = {
            "Roboto-Regular.ttf": "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Regular.ttf",
            "Roboto-Bold.ttf": "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Bold.ttf",
            "Roboto-Italic.ttf": "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Italic.ttf"
        }
        
        success = 0
        failed = 0
        skipped = 0
        
        for font_file, font_url in fonts.items():
            font_path = os.path.join(self.fonts_dir, font_file)
            
            # Skip if already exists
            if os.path.exists(font_path):
                skipped += 1
                continue
                
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(font_url) as resp:
                        if resp.status == 200:
                            font_data = await resp.read()
                            with open(font_path, 'wb') as f:
                                f.write(font_data)
                            success += 1
                        else:
                            logger.error(f"Failed to download font {font_file}: HTTP {resp.status}")
                            failed += 1
            except Exception as e:
                logger.error(f"Error downloading font {font_file}: {e}")
                failed += 1
        
        # Generate report
        report = [
            "# Font Sync Report",
            f"Total fonts processed: {len(fonts)}",
            f"- Successfully downloaded: {success}",
            f"- Failed to download: {failed}",
            f"- Already exist (skipped): {skipped}",
            "",
            "Font synchronization completed."
        ]
        
        await interaction.followup.send("\n".join(report), ephemeral=True)
        
    @advanced_group.command(name="resetcards", description="Reset all level card settings (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_resetcards(self, interaction: discord.Interaction):
        """Reset all level card settings for the server"""
        guild_id = str(interaction.guild.id)
        
        # Initialize confirmation view
        confirm_view = ConfirmView(interaction.user.id)
        
        await interaction.response.send_message(
            "⚠️ **WARNING**: This will delete all custom backgrounds and card settings for this server. Are you sure?",
            view=confirm_view,
            ephemeral=True
        )
        
        # Wait for confirmation
        await confirm_view.wait()
        
        if confirm_view.value is None:
            await interaction.followup.send("Reset cancelled - you didn't respond in time.", ephemeral=True)
            return
            
        if not confirm_view.value:
            await interaction.followup.send("Reset cancelled.", ephemeral=True)
            return
        
        # Reset background images
        if guild_id in self.background_images:
            backgrounds_count = len(self.background_images[guild_id])
            del self.background_images[guild_id]
            await self.save_backgrounds()
            
            await interaction.followup.send(f"Reset {backgrounds_count} custom backgrounds for this server.", ephemeral=True)
        else:
            await interaction.followup.send("No custom backgrounds were set for this server.", ephemeral=True)

    @advanced_group.command(name="diagnose", description="Check and fix potential issues in the leveling system")
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnose_leveling(self, interaction: discord.Interaction):
        """Check for and fix potential issues in the leveling system"""
        await interaction.response.defer(ephemeral=True)
        
        issues_found = 0
        issues_fixed = 0
        report = ["# Leveling System Diagnostic Report", ""]
        
        # Check if the database exists
        try:
            guild_id = str(interaction.guild.id)
            if guild_id not in self.xp_data:
                self.xp_data[guild_id] = {}
                issues_found += 1
                issues_fixed += 1
                report.append("✅ Created missing guild entry in users database")
            
            # Check level roles
            if guild_id not in self.level_roles:
                self.level_roles[guild_id] = {}
                issues_found += 1
                issues_fixed += 1
                report.append("✅ Created missing guild entry in level roles database")
                
            # Check if level role entries are valid
            invalid_level_roles = []
            for level, role_id in self.level_roles.get(guild_id, {}).items():
                role = interaction.guild.get_role(int(role_id))
                if not role:
                    invalid_level_roles.append(level)
                    issues_found += 1
            
            if invalid_level_roles:
                for level in invalid_level_roles:
                    del self.level_roles[guild_id][level]
                    issues_fixed += 1
                
                report.append(f"✅ Removed {len(invalid_level_roles)} invalid level roles that no longer exist")
            
            # Check user entries
            invalid_users = []
            for user_id in list(self.xp_data[guild_id].keys()):
                try:
                    member = await interaction.guild.fetch_member(int(user_id))
                    if not member:
                        invalid_users.append(user_id)
                        issues_found += 1
                except discord.NotFound:
                    invalid_users.append(user_id)
                    issues_found += 1
                except Exception as e:
                    report.append(f"⚠️ Error checking user {user_id}: {e}")
            
            if invalid_users:
                for user_id in invalid_users:
                    if user_id in self.xp_data[guild_id]:
                        del self.xp_data[guild_id][user_id]
                        issues_fixed += 1
                
                report.append(f"✅ Removed {len(invalid_users)} users who are no longer in the server")
            
            # Check if any user entries have missing fields
            fixed_user_entries = 0
            for user_id, user_data in self.xp_data[guild_id].items():
                user_updated = False
                
                required_fields = ["xp", "level", "last_message"]
                for field in required_fields:
                    if field not in user_data:
                        if field == "xp":
                            self.xp_data[guild_id][user_id]["xp"] = 0
                        elif field == "level":
                            self.xp_data[guild_id][user_id]["level"] = 0
                        elif field == "last_message":
                            self.xp_data[guild_id][user_id]["last_message"] = 0
                        
                        user_updated = True
                        issues_found += 1
                
                if user_updated:
                    fixed_user_entries += 1
                    issues_fixed += 1
            
            if fixed_user_entries > 0:
                report.append(f"✅ Fixed {fixed_user_entries} user entries with missing fields")
            
            # Save changes
            await self.save_data()
            await self.save_level_roles()
            
            # Finalize report
            if issues_found == 0:
                report.append("✨ No issues found! The leveling system is in good condition.")
            else:
                report.append(f"Found {issues_found} issues and fixed {issues_fixed} issues.")
                
            await interaction.followup.send("\n".join(report), ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Error during diagnostic: {e}", ephemeral=True)
            
    @advanced_group.command(name="backup", description="Create a backup of the leveling system data")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_leveling(self, interaction: discord.Interaction):
        """Create a backup of all leveling system data"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Create timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create data to export
            export_data = {
                "users": self.xp_data,
                "level_roles": self.level_roles,
                "timestamp": timestamp,
                "server_info": {
                    "guild_id": interaction.guild.id,
                    "guild_name": interaction.guild.name
                }
            }
            
            # Convert to JSON
            export_json = json.dumps(export_data, indent=2)
            
            # Create file
            file = discord.File(
                io.BytesIO(export_json.encode('utf-8')),
                filename=f"leveling_backup_{timestamp}.json"
            )
            
            await interaction.followup.send(
                "📤 Here's your leveling system backup. Keep this file safe for backup purposes.",
                file=file,
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"Error creating backup: {e}", ephemeral=True)

    async def check_level_roles(self, member, level):
        """Check if the member should receive a role reward for their current level."""
        guild_id = str(member.guild.id)
        
        # Return if this guild has no level roles set up
        if guild_id not in self.level_roles:
            return
            
        try:
            # Sort the level roles by level requirement (ascending)
            sorted_roles = sorted(
                self.level_roles[guild_id].items(),
                key=lambda x: int(x[1]["level"])
            )
            
            # Find all roles the member should have based on their level
            roles_to_add = []
            for role_id, data in sorted_roles:
                if level >= int(data["level"]):
                    roles_to_add.append(role_id)
                else:
                    break  # No need to check higher levels
            
            # Get the actual role objects
            valid_roles = []
            for role_id in roles_to_add:
                try:
                    role = member.guild.get_role(int(role_id))
                    if role:
                        valid_roles.append(role)
                    else:
                        print(f"Role {role_id} not found in guild {guild_id}")
                except Exception as e:
                    print(f"Error getting role {role_id}: {e}")
            
            # Add missing roles
            try:
                missing_roles = [role for role in valid_roles if role not in member.roles]
                if missing_roles:
                    await member.add_roles(*missing_roles, reason="Level up role reward")
                    print(f"Added {len(missing_roles)} level roles to {member.name}")
            except discord.Forbidden:
                print(f"Missing permissions to add roles to {member.name} in {member.guild.name}")
            except Exception as e:
                print(f"Error adding roles to {member.name}: {e}")
                
        except Exception as e:
            print(f"Error checking level roles for {member.name}: {e}")

    @app_commands.command(name="addlevelrole", description="Add a role reward for reaching a specific level")
    @app_commands.describe(level="The level at which to award the role", role="The role to award at the specified level")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        """Add a role reward for reaching a specific level"""
        if level <= 0:
            await interaction.response.send_message("Level must be greater than 0", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.level_roles:
            self.level_roles[guild_id] = {}
            
        # Store the role ID for the specified level
        self.level_roles[guild_id][str(level)] = role.id
        
        # Save updated role rewards
        with open("level_roles.json", "w") as f:
            json.dump(self.level_roles, f, indent=4)
            
        await interaction.response.send_message(f"✅ {role.mention} will now be awarded at level {level}")

    @app_commands.command(name="remove_level_role", description="Remove a role reward from the level system")
    @app_commands.describe(
        level="The level to remove the role reward from"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_level_role(self, interaction: discord.Interaction, level: int):
        try:
            guild_id = str(interaction.guild.id)
            level_str = str(level)
            
            # Check if the guild has any level roles
            if guild_id not in self.level_roles:
                await interaction.response.send_message(
                    "This server has no level rewards set up.",
                    ephemeral=True
                )
                return
                
            # Check if the specified level has a role reward
            if level_str not in self.level_roles[guild_id]:
                await interaction.response.send_message(
                    f"There is no role reward set for level {level}.",
                    ephemeral=True
                )
                return
                
            # Get the role information before removing
            role_id = self.level_roles[guild_id][level_str]
            role = interaction.guild.get_role(int(role_id))
            role_mention = role.mention if role else f"role with ID {role_id}"
            
            # Remove the level-role association
            del self.level_roles[guild_id][level_str]
            
            # If the guild has no level roles left, remove the guild entry
            if not self.level_roles[guild_id]:
                del self.level_roles[guild_id]
                
            # Save the updated data
            self.save_level_roles()
            
            await interaction.response.send_message(
                f"✅ Removed {role_mention} from level {level} rewards.",
                ephemeral=True
            )
            
        except discord.app_commands.errors.MissingPermissions:
            await interaction.response.send_message(
                "You need the 'Administrator' permission to use this command.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while removing the level role: {str(e)}",
                ephemeral=True
            )
            print(f"Error in remove_level_role command: {e}")

    @app_commands.command(name="list_level_roles", description="List all role rewards in the level system")
    async def list_level_roles(self, interaction: discord.Interaction):
        try:
            guild_id = str(interaction.guild.id)
            
            # Check if the guild has any level roles
            if guild_id not in self.level_roles or not self.level_roles[guild_id]:
                await interaction.response.send_message(
                    "This server has no level rewards set up.",
                    ephemeral=True
                )
                return
                
            # Create an embed to display level roles
            embed = discord.Embed(
                title="Level Role Rewards",
                description="The following roles are awarded when members reach specific levels:",
                color=discord.Color.blue()
            )
            
            # Sort levels numerically for better display
            sorted_levels = sorted(self.level_roles[guild_id].keys(), key=int)
            
            for level in sorted_levels:
                role_id = self.level_roles[guild_id][level]
                role = interaction.guild.get_role(int(role_id))
                role_mention = role.mention if role else f"Unknown Role (ID: {role_id})"
            # Sort by level
            sorted_levels = sorted(self.level_roles[guild_id].items(), key=lambda x: int(x[0]))
            
            role_text = ""
            for level_str, role_id in sorted_levels:
                role = interaction.guild.get_role(role_id)
                if role:
                    role_text += f"Level {level_str}: {role.mention}\n"
                else:
                    role_text += f"Level {level_str}: Unknown Role (ID: {role_id})\n"
                    
            embed.add_field(name="Rewards", value=role_text, inline=False)
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while retrieving level roles: {str(e)}",
                ephemeral=True
            )
            print(f"Error in view_level_roles command: {e}")

    @app_commands.command(name="setlevel", description="Set a user's level")
    @app_commands.describe(member="The member to set the level for", level="The level to set for the member")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level(self, interaction: discord.Interaction, member: discord.Member, level: int):
        """Set a user's level"""
        if level < 0:
            await interaction.response.send_message("Level cannot be negative", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        
        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}
            
        xp_required = self.get_xp_for_level(level)
        
        # Update user's level data
        self.xp_data[guild_id][user_id] = {
            "xp": xp_required,
            "level": level,
            "last_message": int(time.time())
        }
        
        # Save updated data
        await self.save_data()
            
        await interaction.response.send_message(f"{member.mention}'s level has been set to {level}")
        
        # Check and assign any role rewards
        await self.check_level_roles(member, level)

    def load_data(self):
        """Load all data from files"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    self.xp_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading XP data: {e}")
            
        try:
            if os.path.exists(self.roles_file):
                with open(self.roles_file, 'r') as f:
                    self.level_roles = json.load(f)
        except Exception as e:
            logger.error(f"Error loading level roles: {e}")
            
        try:
            if os.path.exists(self.messages_file):
                with open(self.messages_file, 'r') as f:
                    self.level_messages = json.load(f)
        except Exception as e:
            logger.error(f"Error loading level messages: {e}")
            
        try:
            if os.path.exists(self.backgrounds_file):
                with open(self.backgrounds_file, 'r') as f:
                    self.background_images = json.load(f)
        except Exception as e:
            logger.error(f"Error loading background images: {e}")
            
    async def save_data(self):
        """Save XP and level role data to files"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.xp_data, f)
            with open(self.roles_file, 'w') as f:
                json.dump(self.level_roles, f)
            await self.save_level_messages()
            await self.save_backgrounds()
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            
    async def save_level_messages(self):
        """Save level message templates to file"""
        try:
            with open(self.messages_file, 'w') as f:
                json.dump(self.level_messages, f)
        except Exception as e:
            logger.error(f"Error saving level messages: {e}")
            
    async def save_backgrounds(self):
        """Save background image URLs to file"""
        try:
            with open(self.backgrounds_file, 'w') as f:
                json.dump(self.background_images, f)
        except Exception as e:
            logger.error(f"Error saving background images: {e}")
            
    def cog_unload(self):
        self.save_task.cancel()
        # No need to manually remove commands as discord.py handles this automatically
        # when using the GroupCog approach
        
    @tasks.loop(minutes=5)
    async def save_task(self):
        """Periodically save data"""
        await self.save_data()
        await self.save_level_messages()
        
    @save_task.before_loop
    async def before_save(self):
        await self.bot.wait_until_ready()
        
    def get_xp_for_level(self, level: int) -> int:
        """Calculate XP needed for a level"""
        return 5 * (level ** 2) + 50 * level + 100
        
    def get_level_from_xp(self, xp: int) -> int:
        """Calculate level from XP"""
        level = 0
        while xp >= self.get_xp_for_level(level):
            xp -= self.get_xp_for_level(level)
            level += 1
        return level
    
    def should_award_xp(self, guild_id: str, user_id: str) -> bool:
        """Check if a user should be awarded XP based on cooldown"""
        current_time = time.time()
        
        # Initialize cooldowns for guild if needed
        if guild_id not in self.message_cooldowns:
            self.message_cooldowns[guild_id] = {}
            
        # Check if the user is on cooldown
        if user_id in self.message_cooldowns[guild_id]:
            last_time = self.message_cooldowns[guild_id][user_id]
            if current_time - last_time < self.xp_cooldown:
                return False
                
        # Update last message time
        self.message_cooldowns[guild_id][user_id] = current_time
        return True
        
    @commands.Cog.listener()
    async def on_message(self, message):
        # Skip messages from bots, DMs, and system messages
        if message.author.bot or not message.guild or message.is_system():
            return

        try:
            # Get guild and user IDs as strings for dictionary keys
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)
            
            # Initialize dict entries if they don't exist
            if guild_id not in self.xp_data:
                self.xp_data[guild_id] = {}
            
            if user_id not in self.xp_data[guild_id]:
                self.xp_data[guild_id][user_id] = {"xp": 0, "level": 0, "last_message": 0}
            
            # Get the current time
            current_time = int(time.time())
            
            # Check if the cooldown has passed
            last_message_time = self.xp_data[guild_id][user_id].get("last_message", 0)
            if current_time - last_message_time < self.xp_cooldown:
                return
            
            # Update last message time
            self.xp_data[guild_id][user_id]["last_message"] = current_time
            
            # Add XP (random amount between min and max)
            xp_gained = random.randint(self.min_xp, self.max_xp)
            self.xp_data[guild_id][user_id]["xp"] += xp_gained
            
            # Calculate level threshold
            current_xp = self.xp_data[guild_id][user_id]["xp"]
            current_level = self.xp_data[guild_id][user_id]["level"]
            
            # Check if user should level up
            xp_needed = self.get_xp_for_level(current_level + 1)
            
            if current_xp >= xp_needed:
                # Level up!
                self.xp_data[guild_id][user_id]["level"] += 1
                new_level = self.xp_data[guild_id][user_id]["level"]
                
                # Check if we should send a level up message
                if self.should_announce(message.channel):
                    try:
                        # Create embed
                        embed = discord.Embed(
                            title="🎉 Level Up!",
                            description=f"{message.author.mention} has reached level **{new_level}**!",
                            color=0x5865F2
                        )
                        embed.set_thumbnail(url=message.author.display_avatar.url)
                        
                        # Send the message
                        await message.channel.send(embed=embed)
                    except Exception as e:
                        print(f"Error sending level up message: {e}")
                
                # Check if there's a role reward for this level
                await self.check_level_roles(message.author, new_level)
            
            # Save after every message to avoid data loss
            await self.save_data()
            
        except Exception as e:
            print(f"Error in leveling system: {e}")
            # Don't re-raise the exception to prevent the bot from crashing

    def get_level_up_message(self, guild_id: str, level: int, user) -> str:
        """Get the appropriate level up message for this guild and level"""
        default_message = "🎉 Congratulations {user}! You've reached level **{level}**!"
        
        if guild_id not in self.level_messages:
            return default_message
            
        # Check if there's a specific message for this level
        level_str = str(level)
        if level_str in self.level_messages[guild_id]:
            return self.level_messages[guild_id][level_str]
            
        # Check if there's a default message
        if "0" in self.level_messages[guild_id]:
            return self.level_messages[guild_id]["0"]
            
        return default_message
            
    async def handle_level_up(self, message: discord.Message, new_level: int):
        """Handle level up events"""
        try:
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)
            
            # Get appropriate level up message
            message_template = self.get_level_up_message(guild_id, new_level, message.author)
            
            # Format the message
            level_message = message_template.replace("{user}", message.author.mention)
            level_message = level_message.replace("{level}", str(new_level))
            level_message = level_message.replace("{server}", message.guild.name)
            
            # Create a more attractive level up message with ping
            embed = discord.Embed(
                title="🎉 Level Up! 🎉",
                description=level_message,
                color=discord.Color.green()
            )
            embed.add_field(name="Current XP", value=f"{self.xp_data[guild_id][user_id]['xp']}")
            embed.add_field(name="Next Level", value=f"{self.get_xp_for_level(new_level)} XP needed")
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.set_footer(text=f"Keep chatting to earn more XP! | {message.guild.name}")
            
            # Find a channel to send the message
            sent_message = False
            for channel in message.guild.text_channels:
                if channel.permissions_for(message.guild.me).send_messages:
                    try:
                        # Use plain text first with user ping to guarantee notification
                        notification_text = f"{message.author.mention} just reached level {new_level}!"
                        await channel.send(notification_text)
                        await channel.send(embed=embed)
                        sent_message = True
                        break
                    except Exception as e:
                        logger.error(f"Error sending level up message: {e}")
                        continue
            
            if not sent_message:
                logger.warning(f"Could not find a suitable channel to send level up notification in {message.guild.name}")
                
            # Check for role assignment
            if guild_id in self.level_roles and str(new_level) in self.level_roles[guild_id]:
                role_id = self.level_roles[guild_id][str(new_level)]
                role = message.guild.get_role(int(role_id))
                if role:
                    try:
                        await message.author.add_roles(role)
                        # Send additional message if role was awarded
                        if sent_message:  # Only try to send if we found a channel earlier
                            for channel in message.guild.text_channels:
                                if channel.permissions_for(message.guild.me).send_messages:
                                    try:
                                        await channel.send(f"🏆 {message.author.mention} has earned the **{role.name}** role for reaching level {new_level}!")
                                        break
                                    except Exception as e:
                                        logger.error(f"Error sending role award message: {e}")
                                        continue
                    except discord.Forbidden:
                        logger.error(f"Failed to assign level role to {message.author} in {message.guild}: Missing permissions")
        except Exception as e:
            logger.error(f"Error in handle_level_up: {e}")

    async def generate_level_card(
        self, 
        member: discord.Member,
        guild_id: str,
        user_id: str,
        level: int,
        xp: int,
        next_level_xp: int,
        percentage: int,
        rank: int = 0,
        theme: str = "default"
    ) -> io.BytesIO:
        """Generate a level card with custom background if available"""
        # Constants for card dimensions
        card_width = 800
        card_height = 250
        
        # Theme colors
        theme_colors = {
            "default": {
                "bg": (47, 49, 54, 255),
                "overlay": (0, 0, 0, 128),
                "progress_bg": (100, 100, 100, 128),
                "progress_fill": (88, 101, 242, 255),  # Discord blurple
                "text": (255, 255, 255, 255)
            },
            "dark": {
                "bg": (30, 30, 30, 255),
                "overlay": (0, 0, 0, 180),
                "progress_bg": (50, 50, 50, 180),
                "progress_fill": (100, 100, 100, 255),
                "text": (220, 220, 220, 255)
            },
            "light": {
                "bg": (240, 240, 240, 255),
                "overlay": (255, 255, 255, 180),
                "progress_bg": (200, 200, 200, 180),
                "progress_fill": (150, 150, 150, 255),
                "text": (30, 30, 30, 255)
            },
            "blue": {
                "bg": (53, 109, 187, 255),
                "overlay": (0, 0, 128, 120),
                "progress_bg": (70, 130, 180, 150),
                "progress_fill": (30, 144, 255, 255),
                "text": (255, 255, 255, 255)
            },
            "green": {
                "bg": (46, 139, 87, 255),
                "overlay": (0, 100, 0, 120),
                "progress_bg": (60, 179, 113, 150),
                "progress_fill": (34, 139, 34, 255),
                "text": (255, 255, 255, 255)
            },
            "red": {
                "bg": (178, 34, 34, 255),
                "overlay": (139, 0, 0, 120),
                "progress_bg": (205, 92, 92, 150),
                "progress_fill": (220, 20, 60, 255),
                "text": (255, 255, 255, 255)
            },
            "purple": {
                "bg": (106, 90, 205, 255),
                "overlay": (75, 0, 130, 120),
                "progress_bg": (147, 112, 219, 150),
                "progress_fill": (138, 43, 226, 255),
                "text": (255, 255, 255, 255)
            },
            "gold": {
                "bg": (184, 134, 11, 255),
                "overlay": (139, 69, 19, 120),
                "progress_bg": (218, 165, 32, 150),
                "progress_fill": (255, 215, 0, 255),
                "text": (255, 255, 255, 255)
            }
        }
        
        # Use default theme if specified theme doesn't exist
        if theme not in theme_colors:
            theme = "default"
            
        colors = theme_colors[theme]
        
        # Check if user has a custom background
        background_url = None
        if guild_id in self.background_images and user_id in self.background_images[guild_id]:
            background_url = self.background_images[guild_id][user_id]
        
        try:
            # Create base image
            if background_url:
                # Download custom background
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(background_url) as resp:
                            if resp.status == 200:
                                image_data = await resp.read()
                                background = Image.open(io.BytesIO(image_data)).convert("RGBA")
                                
                                # Resize and crop to fit card dimensions
                                bg_ratio = background.width / background.height
                                card_ratio = card_width / card_height
                                
                                if bg_ratio > card_ratio:
                                    # Image is wider than card
                                    new_width = int(card_height * bg_ratio)
                                    background = background.resize((new_width, card_height), Image.LANCZOS)
                                    # Crop center
                                    left = (background.width - card_width) // 2
                                    background = background.crop((left, 0, left + card_width, card_height))
                                else:
                                    # Image is taller than card
                                    new_height = int(card_width / bg_ratio)
                                    background = background.resize((card_width, new_height), Image.LANCZOS)
                                    # Crop center
                                    top = (background.height - card_height) // 2
                                    background = background.crop((0, top, card_width, top + card_height))
                            else:
                                # Fallback to default if download fails
                                background = Image.new("RGBA", (card_width, card_height), colors["bg"])
                except Exception as e:
                    logger.error(f"Error loading background image: {e}")
                    background = Image.new("RGBA", (card_width, card_height), colors["bg"])
            else:
                # Use default background
                background = Image.new("RGBA", (card_width, card_height), colors["bg"])
            
            # Create transparent overlay for better text readability
            overlay = Image.new("RGBA", (card_width, card_height), colors["overlay"])
            background = Image.alpha_composite(background, overlay)
            
            # Create a drawing context
            draw = ImageDraw.Draw(background)
            
            # Try to use a nice font if available
            font_path = os.path.join(self.fonts_dir, "Roboto-Regular.ttf")
            if not os.path.exists(font_path):
                # Download the font if it doesn't exist
                os.makedirs(self.fonts_dir, exist_ok=True)
                try:
                    async with aiohttp.ClientSession() as session:
                        font_url = "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Regular.ttf"
                        async with session.get(font_url) as resp:
                            if resp.status == 200:
                                font_data = await resp.read()
                                with open(font_path, 'wb') as f:
                                    f.write(font_data)
                except Exception as e:
                    logger.error(f"Error downloading font: {e}")
                    
            # Check again if font exists after download attempt
            if not os.path.exists(font_path):
                # Fallback to default
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            else:
                font_large = ImageFont.truetype(font_path, 36)
                font_medium = ImageFont.truetype(font_path, 24)
                font_small = ImageFont.truetype(font_path, 18)
            
            # Get user avatar
            try:
                avatar_url = member.display_avatar.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(str(avatar_url)) as resp:
                        if resp.status == 200:
                            avatar_data = await resp.read()
                            avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
                            
                            # Resize avatar
                            avatar = avatar.resize((150, 150), Image.LANCZOS)
                            
                            # Create circular mask for avatar
                            mask = Image.new("L", (150, 150), 0)
                            draw_mask = ImageDraw.Draw(mask)
                            draw_mask.ellipse((0, 0, 150, 150), fill=255)
                            
                            # Apply mask to avatar
                            avatar_circle = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
                            avatar_circle.putalpha(mask)
                            
                            # Paste avatar on card
                            background.paste(avatar_circle, (40, 50), avatar_circle)
            except Exception as e:
                logger.error(f"Error loading avatar: {e}")
                # Skip avatar if error
            
            # Draw username
            username = member.display_name
            if len(username) > 15:
                username = username[:12] + "..."
            draw.text((220, 60), username, fill=colors["text"], font=font_large)
            
            # Draw level and XP
            draw.text((220, 110), f"Level: {level}", fill=colors["text"], font=font_medium)
            draw.text((220, 140), f"XP: {xp}/{next_level_xp}", fill=colors["text"], font=font_medium)
            
            # Draw rank if available
            if rank > 0:
                draw.text((700, 60), f"Rank: #{rank}", fill=colors["text"], font=font_medium)
            
            # Draw progress bar background
            bar_width = card_width - 260
            bar_height = 30
            draw.rounded_rectangle(
                ((220, 180), (220 + bar_width, 180 + bar_height)),
                radius=15,
                fill=colors["progress_bg"]
            )
            
            # Draw progress bar fill
            if percentage > 0:
                fill_width = int((bar_width * percentage) / 100)
                draw.rounded_rectangle(
                    ((220, 180), (220 + fill_width, 180 + bar_height)),
                    radius=15,
                    fill=colors["progress_fill"]
                )
            
            # Draw percentage text
            draw.text((220 + (bar_width // 2), 185), f"{percentage}%", fill=colors["text"], font=font_small, anchor="mm")
            
            # Save image to bytes
            output_buffer = io.BytesIO()
            background.save(output_buffer, format="PNG")
            output_buffer.seek(0)
            
            return output_buffer
        except Exception as e:
            logger.error(f"Error generating level card: {e}")
            # Create a simple fallback card
            fallback = Image.new("RGBA", (card_width, card_height), (47, 49, 54, 255))
            draw = ImageDraw.Draw(fallback)
            draw.text((50, 50), f"Error generating card: {str(e)[:100]}", fill=(255, 0, 0, 255))
            draw.text((50, 100), f"Username: {member.display_name}", fill=(255, 255, 255, 255))
            draw.text((50, 150), f"Level: {level} | XP: {xp}/{next_level_xp}", fill=(255, 255, 255, 255))
            
            output_buffer = io.BytesIO()
            fallback.save(output_buffer, format="PNG")
            output_buffer.seek(0)
            
            return output_buffer
    
    async def get_user_rank(self, guild_id: str, user_id: str) -> int:
        """Get user's rank in the server based on XP"""
        if guild_id not in self.xp_data:
            return 0
            
        # Sort users by XP
        sorted_users = sorted(
            self.xp_data[guild_id].items(),
            key=lambda x: x[1]["xp"],
            reverse=True
        )
        
        # Find user's position
        for i, (uid, _) in enumerate(sorted_users, 1):
            if uid == user_id:
                return i
                
        return 0

    async def generate_leaderboard_image(
        self,
        guild: discord.Guild,
        sorted_users: list,
        page: int,
        total_pages: int,
        per_page: int,
        theme: str = "default"
    ) -> io.BytesIO:
        """Generate a visual leaderboard image"""
        # Constants for image dimensions
        image_width = 800
        image_height = 600
        
        # Theme colors
        theme_colors = {
            "default": {
                "bg": (47, 49, 54, 255),
                "header_bg": (32, 34, 37, 255),
                "entry_bg": (54, 57, 63, 255),
                "highlight": (88, 101, 242, 255),  # Discord blurple
                "text": (255, 255, 255, 255),
                "subtext": (185, 187, 190, 255)
            },
            "dark": {
                "bg": (30, 30, 30, 255),
                "header_bg": (20, 20, 20, 255),
                "entry_bg": (40, 40, 40, 255),
                "highlight": (100, 100, 100, 255),
                "text": (220, 220, 220, 255),
                "subtext": (150, 150, 150, 255)
            },
            "light": {
                "bg": (240, 240, 240, 255),
                "header_bg": (230, 230, 230, 255),
                "entry_bg": (250, 250, 250, 255),
                "highlight": (150, 150, 150, 255),
                "text": (30, 30, 30, 255),
                "subtext": (100, 100, 100, 255)
            },
            "blue": {
                "bg": (53, 109, 187, 255),
                "header_bg": (41, 84, 144, 255),
                "entry_bg": (65, 121, 199, 255),
                "highlight": (30, 144, 255, 255),
                "text": (255, 255, 255, 255),
                "subtext": (220, 230, 242, 255)
            },
            "green": {
                "bg": (46, 139, 87, 255),
                "header_bg": (36, 107, 67, 255),
                "entry_bg": (56, 157, 101, 255),
                "highlight": (34, 139, 34, 255),
                "text": (255, 255, 255, 255),
                "subtext": (220, 240, 220, 255)
            },
            "red": {
                "bg": (178, 34, 34, 255),
                "header_bg": (139, 26, 26, 255),
                "entry_bg": (205, 51, 51, 255),
                "highlight": (220, 20, 60, 255),
                "text": (255, 255, 255, 255),
                "subtext": (255, 220, 220, 255)
            },
            "purple": {
                "bg": (106, 90, 205, 255),
                "header_bg": (85, 72, 164, 255),
                "entry_bg": (122, 104, 220, 255),
                "highlight": (138, 43, 226, 255),
                "text": (255, 255, 255, 255),
                "subtext": (230, 220, 250, 255)
            },
            "gold": {
                "bg": (184, 134, 11, 255),
                "header_bg": (139, 101, 8, 255),
                "entry_bg": (205, 149, 12, 255),
                "highlight": (255, 215, 0, 255),
                "text": (255, 255, 255, 255),
                "subtext": (255, 248, 220, 255)
            }
        }
        
        # Use default theme if specified theme doesn't exist
        if theme not in theme_colors:
            theme = "default"
            
        colors = theme_colors[theme]
        
        try:
            # Create base image
            image = Image.new("RGBA", (image_width, image_height), colors["bg"])
            draw = ImageDraw.Draw(image)
            
            # Try to use a nice font if available
            font_path = os.path.join(self.fonts_dir, "Roboto-Regular.ttf")
            if not os.path.exists(font_path):
                # Fallback to default
                font_title = ImageFont.load_default()
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            else:
                font_title = ImageFont.truetype(font_path, 36)
                font_large = ImageFont.truetype(font_path, 28)
                font_medium = ImageFont.truetype(font_path, 24)
                font_small = ImageFont.truetype(font_path, 18)
            
            # Draw header
            header_height = 80
            draw.rectangle(
                ((0, 0), (image_width, header_height)),
                fill=colors["header_bg"]
            )
            
            # Draw title
            title = f"{guild.name} Leaderboard"
            draw.text((image_width // 2, header_height // 2), title, fill=colors["text"], font=font_title, anchor="mm")
            
            # Draw page info
            page_info = f"Page {page}/{total_pages}"
            draw.text((image_width - 20, header_height - 20), page_info, fill=colors["subtext"], font=font_small, anchor="rb")
            
            # Get users for current page
            start_idx = (page - 1) * per_page
            end_idx = min(start_idx + per_page, len(sorted_users))
            users_to_display = sorted_users[start_idx:end_idx]
            
            # Draw leaderboard entries
            entry_height = 100
            entry_padding = 10
            y_offset = header_height + entry_padding
            
            for rank, (user_id, data) in enumerate(users_to_display, start=start_idx + 1):
                # Draw entry background
                entry_bg_color = colors["entry_bg"]
                if rank == 1:  # First place highlight
                    entry_bg_color = tuple(int(c * 1.2) if c < 200 else c for c in colors["highlight"])
                elif rank == 2:  # Second place
                    entry_bg_color = tuple(int(c * 1.1) if c < 220 else c for c in colors["entry_bg"])
                elif rank == 3:  # Third place
                    entry_bg_color = tuple(int(c * 1.05) if c < 230 else c for c in colors["entry_bg"])
                    
                draw.rounded_rectangle(
                    ((entry_padding, y_offset), (image_width - entry_padding, y_offset + entry_height)),
                    radius=10,
                    fill=entry_bg_color
                )
                
                # Draw rank
                rank_size = 40
                rank_bg_color = colors["highlight"]
                draw.ellipse(
                    ((entry_padding + 10, y_offset + (entry_height - rank_size) // 2),
                     (entry_padding + 10 + rank_size, y_offset + (entry_height + rank_size) // 2)),
                    fill=rank_bg_color
                )
                draw.text(
                    (entry_padding + 10 + rank_size // 2, y_offset + entry_height // 2),
                    f"#{rank}",
                    fill=colors["text"],
                    font=font_medium,
                    anchor="mm"
                )
                
                # Try to get member info
                try:
                    member = guild.get_member(int(user_id))
                    username = member.display_name if member else f"Unknown User ({user_id})"
                    
                    # Get avatar if possible
                    if member and member.display_avatar:
                        avatar_url = member.display_avatar.url
                        async with aiohttp.ClientSession() as session:
                            async with session.get(str(avatar_url)) as resp:
                                if resp.status == 200:
                                    avatar_data = await resp.read()
                                    avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
                                    
                                    # Resize avatar
                                    avatar_size = 80
                                    avatar = avatar.resize((avatar_size, avatar_size), Image.LANCZOS)
                                    
                                    # Create circular mask for avatar
                                    mask = Image.new("L", (avatar_size, avatar_size), 0)
                                    draw_mask = ImageDraw.Draw(mask)
                                    draw_mask.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                                    
                                    # Apply mask to avatar
                                    avatar_circle = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
                                    avatar_circle.putalpha(mask)
                                    
                                    # Paste avatar on card
                                    avatar_x = entry_padding + 80
                                    avatar_y = y_offset + (entry_height - avatar_size) // 2
                                    image.paste(avatar_circle, (avatar_x, avatar_y), avatar_circle)
                
                except Exception as e:
                    logger.error(f"Error loading user data for leaderboard: {e}")
                    username = f"Unknown User ({user_id})"
                
                # Draw username (truncate if too long)
                if len(username) > 20:
                    username = username[:17] + "..."
                draw.text(
                    (entry_padding + 180, y_offset + entry_height // 3),
                    username,
                    fill=colors["text"],
                    font=font_large
                )
                
                # Draw level and XP
                level = data["level"]
                xp = data["xp"]
                level_text = f"Level: {level}"
                xp_text = f"XP: {xp}"
                
                draw.text(
                    (entry_padding + 180, y_offset + entry_height * 2 // 3),
                    level_text,
                    fill=colors["subtext"],
                    font=font_medium
                )
                
                draw.text(
                    (image_width - entry_padding - 20, y_offset + entry_height // 2),
                    xp_text,
                    fill=colors["text"],
                    font=font_large,
                    anchor="rm"
                )
                
                # Update y position for next entry
                y_offset += entry_height + entry_padding
            
            # Draw footer with server info
            footer_height = 40
            draw.rectangle(
                ((0, image_height - footer_height), (image_width, image_height)),
                fill=colors["header_bg"]
            )
            
            # Member count
            member_count = guild.member_count
            member_text = f"Server Members: {member_count}"
            timestamp = f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            
            draw.text(
                (entry_padding, image_height - footer_height // 2),
                member_text,
                fill=colors["subtext"],
                font=font_small,
                anchor="lm"
            )
            
            draw.text(
                (image_width - entry_padding, image_height - footer_height // 2),
                timestamp,
                fill=colors["subtext"],
                font=font_small,
                anchor="rm"
            )
            
            # Save image to bytes
            output_buffer = io.BytesIO()
            image.save(output_buffer, format="PNG")
            output_buffer.seek(0)
            
            return output_buffer
        except Exception as e:
            logger.error(f"Error generating leaderboard image: {e}")
            # Create a simple fallback
            fallback = Image.new("RGBA", (image_width, image_height), (47, 49, 54, 255))
            draw = ImageDraw.Draw(fallback)
            
            draw.text((50, 50), f"Error generating leaderboard: {str(e)[:100]}", fill=(255, 0, 0, 255))
            draw.text((50, 100), f"Server: {guild.name}", fill=(255, 255, 255, 255))
            draw.text((50, 150), f"Page: {page}/{total_pages}", fill=(255, 255, 255, 255))
            
            # Attempt to still list some users in text format
            y_pos = 200
            for rank, (user_id, data) in enumerate(sorted_users[start_idx:end_idx], start=start_idx + 1):
                try:
                    member = guild.get_member(int(user_id))
                    username = member.display_name if member else f"Unknown User ({user_id})"
                    text = f"#{rank}: {username} - Level {data['level']} (XP: {data['xp']})"
                    draw.text((50, y_pos), text, fill=(255, 255, 255, 255))
                    y_pos += 40
                except:
                    pass
            
            output_buffer = io.BytesIO()
            fallback.save(output_buffer, format="PNG")
            output_buffer.seek(0)
            
            return output_buffer

    async def save_level_roles(self):
        try:
            # Ensure the data is properly formatted
            with open('level_roles.json', 'w') as f:
                json.dump(self.level_roles, f, indent=4)
            print("Level roles data saved successfully")
        except Exception as e:
            print(f"Error saving level roles data: {e}")

    @app_commands.command(name="rolereward", description="Set a role reward for reaching a specific level")
    @app_commands.default_permissions(manage_roles=True)
    async def role_reward(self, interaction: discord.Interaction, level: int, role: discord.Role):
        """Set a role reward for reaching a specific level"""
        try:
            # Validate input
            if level < 1:
                await interaction.response.send_message("Level must be a positive number", ephemeral=True)
                return
                
            # Check bot permissions
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.response.send_message("I need 'Manage Roles' permission to set role rewards", ephemeral=True)
                return
                
            # Check if the role is higher than bot's highest role
            if role.position >= interaction.guild.me.top_role.position:
                await interaction.response.send_message("I cannot assign roles higher than my highest role", ephemeral=True)
                return
                
            # Initialize guild in level_roles if not exists
            guild_id = str(interaction.guild.id)
            if guild_id not in self.level_roles:
                self.level_roles[guild_id] = {}
                
            # Add or update the role reward
            self.level_roles[guild_id][str(level)] = role.id
            await self.save_level_roles()
            
            embed = discord.Embed(
                title="Level Reward Set",
                description=f"Members will receive the role {role.mention} when they reach level {level}",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Server: {interaction.guild.name}")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
            print(f"Error in role_reward command: {e}")

    def calculate_xp_for_level(self, level):
        return 5 * (level ** 2) + 50 * level + 100

    async def check_role_rewards(self, member, level):
        guild_id = str(member.guild.id)
        if guild_id in self.level_roles and str(level) in self.level_roles[guild_id]:
            role_id = self.level_roles[guild_id][str(level)]
            role = member.guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role)
                    print(f"Added role {role.name} to {member.name}")
                except Exception as e:
                    print(f"Error adding role {role.name} to {member.name}: {e}")

# Confirmation view for dangerous operations
class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.value = None
        self.user_id = user_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.send_message("Confirmed. Processing...", ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.send_message("Operation cancelled.", ephemeral=True)
        self.stop()

async def setup(bot):
    await bot.add_cog(Leveling(bot)) 