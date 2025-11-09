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

# Change GroupCog to Cog
class Leveling(commands.Cog):
    # Keep group definitions inside for now, they will become top-level groups
    admin_group = app_commands.Group(name="admin", description="Admin level commands")
    role_group = app_commands.Group(name="role", description="Role management commands")
    settings_group = app_commands.Group(name="settings", description="Leveling system settings")
    card_group = app_commands.Group(name="card", description="Level card commands")
    advanced_group = app_commands.Group(name="advanced", description="Advanced level commands")

    def __init__(self, bot):
        self.bot = bot
        self.xp_data = {}  # {guild_id: {user_id: {"xp": xp, "level": level, "last_message": timestamp}}}
        self.level_roles = {}  # {guild_id: {level: role_id}}
        self.message_cooldowns = {} # Deprecated? last_message in xp_data seems to handle this.
        self.level_messages = {}  # {guild_id: {level?: message_template}}
        self.background_images = {}  # {guild_id: {user_id?: image_url}}
        self.leveling_data = {} # Stores server settings like level_up_channel, enabled status

        # Default settings (Consider moving to a config file or making them per-server settings)
        self.xp_cooldown = 60
        self.min_xp = 10
        self.max_xp = 20

        # File paths
        self.data_file = 'leveling.json'
        self.roles_file = 'level_roles.json'
        self.messages_file = 'level_messages.json'
        self.backgrounds_file = 'level_backgrounds.json'
        self.settings_file = 'leveling_settings.json' # Added for server settings

        self.fonts_dir = 'fonts'
        self.images_dir = 'level_images' # Unused?

        # Create directories if they don't exist
        os.makedirs(self.fonts_dir, exist_ok=True)
        # os.makedirs(self.images_dir, exist_ok=True) # Not currently used

        self.load_data()
        self.save_task.start()

        # --- IMPORTANT: Link groups to this cog instance ---
        # This makes them appear as /level admin, /level role etc.
        # We need to do this AFTER the cog is initialized but BEFORE it's added
        # A good place might be the setup function or dynamically upon cog_load
        # For simplicity, we'll assume the registration process handles this
        # OR we can explicitly add them to the bot's tree in setup if needed.
        # Let's try relying on the standard registration first.
        Leveling.admin_group.cog = self
        Leveling.role_group.cog = self
        Leveling.settings_group.cog = self
        Leveling.card_group.cog = self
        Leveling.advanced_group.cog = self


    def cog_unload(self):
        self.save_task.cancel()

    # --- Basic Level Commands (Directly under /level) ---

    @app_commands.command(name="check", description="Check your current level and XP")
    @app_commands.describe(member="The member to check (defaults to yourself)")
    async def check(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
       # ... (check command implementation) ...
        member = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)

        if guild_id not in self.xp_data or user_id not in self.xp_data[guild_id]:
            await interaction.response.send_message(f"{member.mention} hasn't earned any XP yet!", ephemeral=True)
            return

        data = self.xp_data[guild_id][user_id]
        current_level = data["level"]
        current_xp = data["xp"]

        # Calculate XP needed for the next level
        total_xp_next = self.get_total_xp_for_level(current_level + 1)
        # Calculate XP needed to reach the current level
        total_xp_current = self.get_total_xp_for_level(current_level)
        # Calculate XP earned within the current level
        progress = current_xp - total_xp_current
        # Calculate total XP required for the current level span
        level_span_xp = total_xp_next - total_xp_current
        if level_span_xp <= 0: level_span_xp = 1 # Avoid division by zero

        embed = discord.Embed(
            title=f"{member.display_name}'s Level",
            color=member.color or discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"`{current_level}`")
        embed.add_field(name="Total XP", value=f"`{current_xp}`")
        embed.add_field(name="Progress", value=f"`{progress} / {level_span_xp}` XP to Level {current_level + 1}", inline=False)

        # Add progress bar visualization
        bar_length = 20
        filled_length = int(bar_length * progress // level_span_xp)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        embed.add_field(name="Level Progress", value=f"`{bar}`", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Show the server XP leaderboard")
    @app_commands.describe(page="The page of the leaderboard to show")
    async def level_leaderboard(self, interaction: discord.Interaction, page: int = 1):
       # ... (leaderboard command implementation) ...
        guild_id = str(interaction.guild.id)

        if guild_id not in self.xp_data or not self.xp_data[guild_id]:
            await interaction.response.send_message("No XP data available for this server yet!", ephemeral=True)
            return

        # Sort users by XP
        sorted_users = sorted(
            self.xp_data[guild_id].items(),
            key=lambda item: item[1].get("xp", 0), # Use .get for safety
            reverse=True
        )

        # Paginate results (10 per page)
        per_page = 10
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        total_pages = (len(sorted_users) + per_page - 1) // per_page
        if total_pages == 0: total_pages = 1 # Ensure at least one page

        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"Invalid page number. Please specify a page between 1 and {total_pages}.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🏆 XP Leaderboard - {interaction.guild.name}",
            description=f"Page {page}/{total_pages}",
            color=discord.Color.gold()
        )

        # Get current page users
        page_users = sorted_users[start_idx:end_idx]

        lb_text = ""
        if not page_users:
            lb_text = "No users on this page."
        else:
            for idx, (user_id, data) in enumerate(page_users, start=start_idx + 1):
                try:
                    member = interaction.guild.get_member(int(user_id))
                    if not member:
                         try:
                             member = await interaction.guild.fetch_member(int(user_id))
                             member_name = member.display_name
                         except discord.NotFound:
                             member_name = f"Unknown User (ID: {user_id})"
                         except discord.HTTPException:
                              member_name = f"User Fetch Error (ID: {user_id})"
                    else:
                         member_name = member.display_name

                    level = data.get("level", 0)
                    xp = data.get("xp", 0)

                    lb_text += f"**{idx}. {member_name}**\n"
                    lb_text += f"   Level: `{level}` | XP: `{xp}`\n"

                except Exception as e:
                     logger.warning(f"Error processing user {user_id} for leaderboard: {e}")
                     lb_text += f"**{idx}. Error processing user**\n"


        embed.add_field(name="Rankings", value=lb_text, inline=False)
        embed.set_footer(text=f"Showing users {start_idx+1}-{min(end_idx, len(sorted_users))} of {len(sorted_users)}")

        await interaction.response.send_message(embed=embed)


    # --- Admin Subcommands (/level admin ...) ---

    # Decorate methods with the subgroup command decorator
    @admin_group.command(name="setxp", description="Set a user's XP directly")
    @app_commands.describe(member="The member to set XP for", xp="The amount of XP to set")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_setxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
       # ... (setxp implementation) ...
        if xp < 0:
            await interaction.response.send_message("XP cannot be negative!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        user_id = str(member.id)

        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}

        current_level = self.get_level_from_xp(xp)
        self.xp_data[guild_id][user_id] = {
            "xp": xp,
            "level": current_level,
            "last_message": int(time.time()) # Initialize last_message
        }
        await self.save_data() # Save user data

        await interaction.response.send_message(f"Set {member.mention}'s XP to {xp} (Level {current_level}).")
        await self.check_level_roles(member, current_level, assign_all_below=True) # Check roles after setting

    @admin_group.command(name="addxp", description="Add XP to a user")
    @app_commands.describe(member="The member to add XP to", xp="The amount of XP to add")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_addxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
       # ... (addxp implementation) ...
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)

        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}
        if user_id not in self.xp_data[guild_id]:
            self.xp_data[guild_id][user_id] = {"xp": 0, "level": 0, "last_message": int(time.time())}

        current_xp = self.xp_data[guild_id][user_id]["xp"]
        current_level = self.xp_data[guild_id][user_id]["level"]

        new_xp = max(0, current_xp + xp)
        new_level = self.get_level_from_xp(new_xp)

        self.xp_data[guild_id][user_id]["xp"] = new_xp
        self.xp_data[guild_id][user_id]["level"] = new_level

        await self.save_data()

        await interaction.response.send_message(f"Added {xp} XP to {member.mention}. They are now level {new_level}.")

        if new_level > current_level:
            announce_channel = self._get_level_up_channel(interaction.guild) or interaction.channel
            await self.handle_level_up(member, new_level, announce_channel, announce=False)

    @admin_group.command(name="setlevel", description="Set a user's level")
    @app_commands.describe(member="The member to set the level for", level="The level to set for the member")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level(self, interaction: discord.Interaction, member: discord.Member, level: int):
       # ... (setlevel implementation) ...
        if level < 0:
            await interaction.response.send_message("Level cannot be negative", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        user_id = str(member.id)

        if guild_id not in self.xp_data:
            self.xp_data[guild_id] = {}

        xp_required = self.get_total_xp_for_level(level)

        self.xp_data[guild_id][user_id] = {
            "xp": xp_required,
            "level": level,
            "last_message": int(time.time())
        }

        await self.save_data()

        await interaction.response.send_message(f"Set {member.mention}'s level to {level} (XP set to {xp_required}).")
        await self.check_level_roles(member, level, assign_all_below=True)

    # --- Role Management Subcommands (/level role ...) ---
    @role_group.command(name="add", description="Add a role reward for reaching a specific level")
    @app_commands.describe(level="The level at which to award the role", role="The role to award at the specified level")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        if level < 1:
            await interaction.response.send_message("Level must be at least 1!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"I cannot assign the role {role.mention} as it's higher than or equal to my highest role.",
                ephemeral=True
            )
            return

        if role.is_default() or role.is_integration() or role.is_premium_subscriber():
            await interaction.response.send_message(
                f"Cannot assign the role {role.mention} as a level reward (it's @everyone, a bot role, or a booster role).",
                ephemeral=True
            )
            return

        if guild_id not in self.level_roles:
            self.level_roles[guild_id] = {}

        level_str = str(level)
        self.level_roles[guild_id][level_str] = str(role.id)

        await self.save_level_roles()

        await interaction.response.send_message(
            f"✅ Role {role.mention} will now be awarded when members reach level {level}.",
            ephemeral=True
        )

    @role_group.command(name="remove", description="Remove a role reward from the level system")
    @app_commands.describe(level="The level to remove the role reward from")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_level_role(self, interaction: discord.Interaction, level: int):
       # ... (remove_level_role implementation) ...
        guild_id = str(interaction.guild.id)
        level_str = str(level)

        if guild_id not in self.level_roles or level_str not in self.level_roles[guild_id]:
            await interaction.response.send_message(
                f"There is no role reward set for level {level}.",
                ephemeral=True
            )
            return

        role_id = self.level_roles[guild_id][level_str]
        role = interaction.guild.get_role(int(role_id))
        role_mention = role.mention if role else f"Unknown Role (ID: {role_id})"

        del self.level_roles[guild_id][level_str]

        if not self.level_roles[guild_id]:
            del self.level_roles[guild_id]

        await self.save_level_roles()

        await interaction.response.send_message(
            f"✅ Removed {role_mention} as a reward for level {level}.",
            ephemeral=True
        )

    @role_group.command(name="list", description="List all role rewards in the level system")
    async def list_level_roles(self, interaction: discord.Interaction):
       # ... (list_level_roles implementation) ...
        guild_id = str(interaction.guild.id)

        if guild_id not in self.level_roles or not self.level_roles[guild_id]:
            await interaction.response.send_message(
                "No role rewards have been set up for this server.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📜 Level Role Rewards",
            description="Roles automatically assigned at specific levels:",
            color=discord.Color.blue()
        )

        try:
            sorted_levels = sorted(self.level_roles[guild_id].keys(), key=int)
        except ValueError:
            logger.error(f"Non-integer level keys found in level_roles for guild {guild_id}")
            await interaction.response.send_message("Error retrieving level roles due to invalid data.", ephemeral=True)
            return

        level_role_text = ""
        if not sorted_levels:
            level_role_text = "No roles configured."
        else:
            for level_key in sorted_levels:
                level_str = str(level_key)
                role_id = self.level_roles[guild_id].get(level_str)
                if role_id:
                    role = interaction.guild.get_role(int(role_id))
                    role_mention = role.mention if role else f"Unknown Role (ID: {role_id})"
                    level_role_text += f"**Level {level_key}:** {role_mention}\n"
                else:
                     level_role_text += f"**Level {level_key}:** Error fetching role\n"

        embed.add_field(name="Configured Rewards", value=level_role_text, inline=False)
        await interaction.response.send_message(embed=embed)

    # --- Settings Subcommands (/level settings ...) ---
    @settings_group.command(name="xprate", description="Change the XP gain rate (Admin only)")
    @app_commands.describe(min_xp="Minimum XP to award", max_xp="Maximum XP to award", cooldown="Cooldown in seconds between XP awards")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_xprate(self, interaction: discord.Interaction, min_xp: Optional[int] = None, max_xp: Optional[int] = None, cooldown: Optional[int] = None):
       # ... (level_xprate implementation) ...
        guild_id = str(interaction.guild.id)
        if guild_id not in self.leveling_data:
            self.leveling_data[guild_id] = {}
        if "settings" not in self.leveling_data[guild_id]:
            self.leveling_data[guild_id]["settings"] = {
                "min_xp": self.min_xp, "max_xp": self.max_xp, "xp_cooldown": self.xp_cooldown,
                 "level_up_channel": None, "enabled": True, "level_up_messages": True
             }

        settings = self.leveling_data[guild_id]["settings"]
        updated_settings = []

        if min_xp is not None:
            if min_xp < 0:
                await interaction.response.send_message("Minimum XP cannot be negative.", ephemeral=True)
                return
            current_max_xp = settings["max_xp"] if max_xp is None else max_xp # Use new max_xp if provided
            if min_xp > current_max_xp:
                 await interaction.response.send_message(f"Minimum XP ({min_xp}) cannot be greater than Maximum XP ({current_max_xp}).", ephemeral=True)
                 return
            settings["min_xp"] = min_xp
            updated_settings.append(f"Minimum XP: `{min_xp}`")

        if max_xp is not None:
            current_min_xp = settings["min_xp"] # Use potentially updated min_xp
            if max_xp < current_min_xp:
                 await interaction.response.send_message(f"Maximum XP ({max_xp}) cannot be less than Minimum XP ({current_min_xp}).", ephemeral=True)
                 return
            settings["max_xp"] = max_xp
            updated_settings.append(f"Maximum XP: `{max_xp}`")

        if cooldown is not None:
            if cooldown < 0:
                await interaction.response.send_message("Cooldown cannot be negative.", ephemeral=True)
                return
            settings["xp_cooldown"] = cooldown
            updated_settings.append(f"XP Cooldown: `{cooldown}` seconds")

        if not updated_settings:
             current_settings = self.leveling_data[guild_id]["settings"]
             await interaction.response.send_message(
                 f"No settings changed. Current settings:\n"
                 f"Minimum XP: `{current_settings['min_xp']}`\n"
                 f"Maximum XP: `{current_settings['max_xp']}`\n"
                 f"Cooldown: `{current_settings['xp_cooldown']}` seconds",
                 ephemeral=True
             )
             return

        await self.save_leveling_settings()
        await interaction.response.send_message(
            f"✅ Updated XP settings:\n" + "\n".join(updated_settings),
            ephemeral=True
        )

    @settings_group.command(name="setmessage", description="Set a custom level-up message")
    @app_commands.describe(level="Level for this message (0 for default)", message="Template: {user}, {level}, {server}")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_setmessage(self, interaction: discord.Interaction, level: int, message: str):
       # ... (level_setmessage implementation) ...
        guild_id = str(interaction.guild.id)

        if guild_id not in self.level_messages:
            self.level_messages[guild_id] = {}

        level_key = str(level)
        self.level_messages[guild_id][level_key] = message

        await self.save_level_messages()

        preview = message.replace("{user}", interaction.user.mention)
        preview = preview.replace("{level}", str(level if level > 0 else "X"))
        preview = preview.replace("{server}", interaction.guild.name)

        embed = discord.Embed(
            title="✅ Level-up Message Set",
            description=f"Set custom message for **Level {level if level > 0 else 'Default'}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Template", value="```\n" + message + "\n```", inline=False)
        embed.add_field(name="Preview", value=preview, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="clearmessage", description="Clear a custom level-up message")
    @app_commands.describe(level="Level to clear message for (0 for default)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_clearmessage(self, interaction: discord.Interaction, level: int):
       # ... (level_clearmessage implementation) ...
        guild_id = str(interaction.guild.id)
        level_str = str(level)

        if guild_id not in self.level_messages or level_str not in self.level_messages[guild_id]:
            await interaction.response.send_message(f"No custom message set for level {level if level > 0 else 'default'}.", ephemeral=True)
            return

        del self.level_messages[guild_id][level_str]

        if not self.level_messages[guild_id]:
            del self.level_messages[guild_id]

        await self.save_level_messages()

        await interaction.response.send_message(f"✅ Cleared custom message for level {level if level > 0 else 'default'}.", ephemeral=True)

    @settings_group.command(name="listmessages", description="List all custom level-up messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_listmessages(self, interaction: discord.Interaction):
       # ... (level_listmessages implementation) ...
        guild_id = str(interaction.guild.id)

        if guild_id not in self.level_messages or not self.level_messages[guild_id]:
            await interaction.response.send_message("No custom level-up messages are set for this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title="💬 Custom Level-up Messages",
            description=f"Custom messages for {interaction.guild.name}",
            color=discord.Color.blue()
        )

        sorted_levels = sorted(
             self.level_messages[guild_id].keys(),
             key=lambda x: int(x) if x != '0' else -1
         )

        message_list = ""
        for level_key in sorted_levels:
            message = self.level_messages[guild_id][level_key]
            level_display = f"Level {level_key}" if level_key != '0' else "Default"
            display_message = (message[:70] + '...') if len(message) > 70 else message
            message_list += "**" + level_display + ":** ```\n" + display_message + "\n```\n"

        if not message_list:
             message_list = "No messages configured."

        embed.add_field(name="Configured Messages", value=message_list, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="levelupchannel", description="Set the channel where level up messages will be sent")
    @app_commands.describe(channel="The channel for level up messages, or none to use the same channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level_up_channel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
       # ... (set_level_up_channel implementation) ...
        guild_id = str(interaction.guild.id)
        if guild_id not in self.leveling_data:
            self.leveling_data[guild_id] = {}
        if "settings" not in self.leveling_data[guild_id]:
             self.leveling_data[guild_id]["settings"] = {} # Initialize if needed

        settings = self.leveling_data[guild_id]["settings"]

        if channel:
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                 await interaction.response.send_message(
                     f"I need 'Send Messages' and 'Embed Links' permissions in {channel.mention} to send level up messages there.",
                     ephemeral=True
                 )
                 return

            settings["level_up_channel"] = channel.id
            await self.save_leveling_settings()
            await interaction.response.send_message(f"✅ Level up messages will now be sent to {channel.mention}.", ephemeral=True)
        else:
            if settings.get("level_up_channel") is not None:
                 settings["level_up_channel"] = None
                 await self.save_leveling_settings()
                 await interaction.response.send_message("✅ Level up messages will now be sent in the channel where the user leveled up.", ephemeral=True)
            else:
                 await interaction.response.send_message("Level up messages are already being sent in the channel where the user leveled up.", ephemeral=True)

    @settings_group.command(name="toggleleveling", description="Enable or disable the leveling system in this server")
    @app_commands.describe(enabled="Whether to enable (True) or disable (False) leveling")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_leveling(self, interaction: discord.Interaction, enabled: bool):
       # ... (toggle_leveling implementation) ...
        guild_id = str(interaction.guild.id)
        if guild_id not in self.leveling_data:
            self.leveling_data[guild_id] = {}
        if "settings" not in self.leveling_data[guild_id]:
             self.leveling_data[guild_id]["settings"] = {}

        settings = self.leveling_data[guild_id]["settings"]
        settings["enabled"] = enabled
        await self.save_leveling_settings()

        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            f"✅ Leveling system has been **{status}** for this server.",
            ephemeral=True
        )

    @settings_group.command(name="togglemessages", description="Enable or disable level up messages")
    @app_commands.describe(enabled="Whether level up messages are enabled")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_level_up_messages(self, interaction: discord.Interaction, enabled: bool):
       # ... (toggle_level_up_messages implementation) ...
        guild_id = str(interaction.guild.id)
        if guild_id not in self.leveling_data:
            self.leveling_data[guild_id] = {}
        if "settings" not in self.leveling_data[guild_id]:
             self.leveling_data[guild_id]["settings"] = {}

        settings = self.leveling_data[guild_id]["settings"]
        settings["level_up_messages"] = enabled
        await self.save_leveling_settings()

        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            f"✅ Level up announcements have been **{status}** for this server.",
            ephemeral=True
        )

    # --- Card Subcommands (/level card ...) ---
    @card_group.command(name="show", description="Show your level card or another user's")
    @app_commands.describe(member="Member to show card for", theme="Card theme")
    @app_commands.choices(theme=[
        app_commands.Choice(name="Default", value="default"),
        # ... other theme choices ...
        app_commands.Choice(name="Gold", value="gold")
    ])
    async def level_card(self, interaction: discord.Interaction, member: Optional[discord.Member] = None, theme: str = "default"):
       # ... (level_card implementation) ...
        target_member = member or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(target_member.id)

        await interaction.response.defer() # Defer as card generation takes time

        if guild_id not in self.xp_data or user_id not in self.xp_data[guild_id]:
            await interaction.followup.send(f"{target_member.mention} hasn't earned any XP yet!")
            return

        data = self.xp_data[guild_id][user_id]
        current_level = data.get("level", 0)
        current_xp = data.get("xp", 0)

        # Calculate progress
        total_xp_next = self.get_total_xp_for_level(current_level + 1)
        total_xp_current = self.get_total_xp_for_level(current_level)
        level_span_xp = total_xp_next - total_xp_current
        if level_span_xp <= 0 : level_span_xp = 1
        progress = current_xp - total_xp_current
        percentage = max(0, min(100, int((progress / level_span_xp) * 100)))

        try:
            rank = await self.get_user_rank(guild_id, user_id)
            card_bytes = await self.generate_level_card(
                member=target_member, guild_id=guild_id, user_id=user_id,
                level=current_level, xp=current_xp, next_level_xp=total_xp_next,
                percentage=percentage, rank=rank, theme=theme
            )
            file = discord.File(fp=card_bytes, filename=f"{target_member.name}_level_card.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            logger.error(f"Error generating level card for {target_member.id}: {e}", exc_info=True)
            await interaction.followup.send(f"Sorry, there was an error generating the level card for {target_member.mention}.")

    @card_group.command(name="background", description="Set a custom background for your level card")
    @app_commands.describe(image_url="Image URL (PNG/JPG, <8MB). Leave empty to reset.", member="Member to set for (Admin only)")
    async def level_setbackground(self, interaction: discord.Interaction, image_url: Optional[str] = None, member: Optional[discord.Member] = None):
       # ... (level_setbackground implementation) ...
        target_member = member or interaction.user
        is_admin_setting_for_other = member and member != interaction.user

        if is_admin_setting_for_other and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need admin permissions to set backgrounds for others.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        user_id = str(target_member.id)

        if guild_id not in self.background_images:
            self.background_images[guild_id] = {}

        # Resetting
        if not image_url:
            if user_id in self.background_images.get(guild_id, {}):
                del self.background_images[guild_id][user_id]
                if not self.background_images[guild_id]: del self.background_images[guild_id]
                await self.save_backgrounds()
                await interaction.response.send_message(f"✅ Reset background for {target_member.mention}'s level card.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{target_member.mention} doesn't have a custom background.", ephemeral=True)
            return

        # Setting new
        await interaction.response.defer(ephemeral=True)
        try:
            result = urlparse(image_url)
            if not all([result.scheme, result.netloc]):
                await interaction.followup.send("Invalid URL format.", ephemeral=True); return
        except ValueError:
             await interaction.followup.send("Invalid URL format.", ephemeral=True); return

        try:
            async with aiohttp.ClientSession() as session:
                 async with session.head(image_url, timeout=10) as head_resp:
                     # ... (HEAD request checks) ...
                     if head_resp.status != 200: await interaction.followup.send(f"URL inaccessible (Status: {head_resp.status}).", ephemeral=True); return
                     content_type = head_resp.headers.get('Content-Type', '').lower()
                     if not content_type.startswith('image/'): await interaction.followup.send("URL is not an image.", ephemeral=True); return
                     content_length = int(head_resp.headers.get('Content-Length', -1))
                     if content_length > 8 * 1024 * 1024: await interaction.followup.send("Image too large (>8MB).", ephemeral=True); return

                 async with session.get(image_url, timeout=15) as resp:
                    if resp.status != 200: await interaction.followup.send(f"Download failed (Status: {resp.status}).", ephemeral=True); return
                    image_data = await resp.read()
                    try:
                        with Image.open(io.BytesIO(image_data)) as img:
                             img.verify()
                             if img.format not in ['PNG', 'JPEG', 'WEBP']: await interaction.followup.send("Unsupported format (Use PNG/JPG/WEBP).", ephemeral=True); return

                        self.background_images[guild_id][user_id] = image_url
                        await self.save_backgrounds()
                        try:
                            card_bytes = await self.generate_preview_card(target_member, guild_id, user_id)
                            file = discord.File(fp=card_bytes, filename="level_card_preview.png")
                            await interaction.followup.send(f"✅ Background set for {target_member.mention}. Preview:", file=file, ephemeral=True)
                        except Exception as card_err:
                             logger.error(f"Error generating preview card: {card_err}")
                             await interaction.followup.send(f"✅ Background set for {target_member.mention}. Preview failed.", ephemeral=True)

                    except (IOError, SyntaxError) as pillow_err:
                        logger.warning(f"Pillow verification failed for {image_url}: {pillow_err}")
                        await interaction.followup.send("Invalid or corrupted image file.", ephemeral=True)

        except asyncio.TimeoutError:
             await interaction.followup.send("Download timed out.", ephemeral=True)
        except aiohttp.ClientError as http_err:
            await interaction.followup.send(f"Network error: {http_err}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting background: {e}", exc_info=True)
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

    @card_group.command(name="resetbackgrounds", description="Reset all custom backgrounds (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_resetbackgrounds(self, interaction: discord.Interaction):
       # ... (level_resetbackgrounds implementation) ...
        guild_id = str(interaction.guild.id)
        if guild_id in self.background_images and self.background_images[guild_id]:
            backgrounds_count = len(self.background_images[guild_id])
            self.background_images[guild_id] = {}
            await self.save_backgrounds()
            await interaction.response.send_message(f"✅ Reset {backgrounds_count} custom backgrounds.", ephemeral=True)
        else:
            await interaction.response.send_message("No custom backgrounds to reset.", ephemeral=True)

    # --- Advanced Subcommands (/level advanced ...) ---
    @advanced_group.command(name="topleaderboard", description="Show a visual leaderboard of top members")
    @app_commands.describe(page="The page of the leaderboard to show", theme="The theme to use for the leaderboard")
    async def level_topleaderboard(self, interaction: discord.Interaction, page: int = 1, theme: str = "default"):
       # ... (level_topleaderboard implementation) ...
        guild_id = str(interaction.guild.id)

        if guild_id not in self.xp_data or not self.xp_data[guild_id]:
            await interaction.response.send_message("No XP data available!", ephemeral=True); return

        sorted_users = sorted(self.xp_data[guild_id].items(), key=lambda item: item[1].get("xp", 0), reverse=True)
        per_page = 5
        total_pages = (len(sorted_users) + per_page - 1) // per_page
        if total_pages == 0: total_pages = 1

        if page < 1 or page > total_pages:
            await interaction.response.send_message(f"Invalid page (1-{total_pages}).", ephemeral=True); return

        await interaction.response.defer()
        try:
            leaderboard_bytes = await self.generate_leaderboard_image(
                guild=interaction.guild, sorted_users=sorted_users,
                page=page, total_pages=total_pages, per_page=per_page, theme=theme
            )
            file = discord.File(fp=leaderboard_bytes, filename=f"leaderboard_page_{page}.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            logger.error(f"Error generating leaderboard image: {e}", exc_info=True)
            await interaction.followup.send("Error generating leaderboard image.")

    @advanced_group.command(name="resetuser", description="Reset a user's level and XP")
    @app_commands.describe(member="The member to reset")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_resetuser(self, interaction: discord.Interaction, member: discord.Member):
       # ... (level_resetuser implementation) ...
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)

        if guild_id not in self.xp_data or user_id not in self.xp_data[guild_id]:
            await interaction.response.send_message(f"{member.mention} has no data to reset.", ephemeral=True); return

        confirm_view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(f"⚠️ **WARNING**: Reset all XP/level data for {member.mention}?", view=confirm_view, ephemeral=True)
        await confirm_view.wait()

        if confirm_view.value is None: await interaction.edit_original_response(content="Reset cancelled (timed out).", view=None); return
        if not confirm_view.value: await interaction.edit_original_response(content="Reset cancelled.", view=None); return

        try:
             await interaction.edit_original_response(content="Processing reset...", view=None)
             del self.xp_data[guild_id][user_id]
             if not self.xp_data[guild_id]: del self.xp_data[guild_id]
             await self.save_data()
             await interaction.edit_original_response(content=f"✅ Reset data for {member.mention}.")
        except Exception as e:
             logger.error(f"Error resetting user {user_id}: {e}")
             await interaction.edit_original_response(content=f"Error during reset: {e}")

    @advanced_group.command(name="resetall", description="Reset all levels and XP (dangerous!)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_resetall(self, interaction: discord.Interaction):
       # ... (level_resetall implementation) ...
        guild_id = str(interaction.guild.id)
        confirm_view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"🔥🔥 **EXTREME WARNING** 🔥🔥\n"
            f"Reset **ALL** leveling data (XP, roles, settings) for **{interaction.guild.name}**? This **CANNOT** be undone.",
            view=confirm_view,
            ephemeral=True
        )
        await confirm_view.wait()

        if confirm_view.value is None: await interaction.edit_original_response(content="Reset cancelled (timed out).", view=None); return
        if not confirm_view.value: await interaction.edit_original_response(content="Reset cancelled.", view=None); return

        await interaction.edit_original_response(content="Processing server data reset...", view=None)
        try:
            reset_count = 0
            if guild_id in self.xp_data: reset_count = len(self.xp_data[guild_id]); del self.xp_data[guild_id]
            if guild_id in self.level_roles: del self.level_roles[guild_id]
            if guild_id in self.level_messages: del self.level_messages[guild_id]
            if guild_id in self.background_images: del self.background_images[guild_id]
            if guild_id in self.leveling_data: del self.leveling_data[guild_id]

            await self.save_all_data()
            await interaction.edit_original_response(content=f"✅✅ Successfully reset all leveling data for {reset_count} users and all settings.")
        except Exception as e:
             logger.error(f"Error resetting all data for guild {guild_id}: {e}")
             await interaction.edit_original_response(content=f"Error during reset: {e}")

    @advanced_group.command(name="syncfonts", description="Sync font files for level cards")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_syncfonts(self, interaction: discord.Interaction):
       # ... (level_syncfonts implementation) ...
        await interaction.response.defer(ephemeral=True)
        fonts = [
            ("Roboto-Regular.ttf", "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf"),
            ("Roboto-Bold.ttf", "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"),
         ]
        success, failed, skipped = 0, 0, 0
        os.makedirs(self.fonts_dir, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            for font_file, font_url in fonts:
                font_path = os.path.join(self.fonts_dir, font_file)
                if os.path.exists(font_path): skipped += 1; continue
                try:
                    async with session.get(font_url, timeout=10) as resp:
                        if resp.status == 200:
                            with open(font_path, 'wb') as f: f.write(await resp.read()); success += 1
                        else: logger.error(f"Font DL fail {font_file}: HTTP {resp.status}"); failed += 1
                except asyncio.TimeoutError: logger.error(f"Font DL timeout {font_file}"); failed += 1
                except Exception as e: logger.error(f"Font DL error {font_file}: {e}"); failed += 1

        report = [f"## Font Sync Report", f"- Success: `{success}`", f"- Failed: `{failed}`", f"- Skipped: `{skipped}`"]
        await interaction.followup.send("\n".join(report), ephemeral=True)

    @advanced_group.command(name="resetcards", description="Reset all level cards to default style")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_resetcards(self, interaction: discord.Interaction):
       # ... (level_resetcards implementation) ...
        guild_id = str(interaction.guild.id)
        confirm_view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(f"⚠️ **WARNING**: Reset ALL custom backgrounds for **{interaction.guild.name}**?", view=confirm_view, ephemeral=True)
        await confirm_view.wait()

        if confirm_view.value is None:
            await interaction.edit_original_response(content="Reset cancelled (timed out).", view=None)
            return
        if not confirm_view.value:
            await interaction.edit_original_response(content="Reset cancelled.", view=None)
            return

        reset_count = 0
        if guild_id in self.background_images:
            reset_count = len(self.background_images[guild_id])
            del self.background_images[guild_id]
            await self.save_backgrounds()
            await interaction.edit_original_response(content=f"✅ Reset {reset_count} custom backgrounds.", view=None)
        else:
            await interaction.edit_original_response(content="No custom backgrounds to reset.", view=None)

    @advanced_group.command(name="diagnose", description="Run diagnostics on the leveling system")
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnose_leveling(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        issues_found, issues_fixed = 0, 0
        report = ["## Leveling System Diagnostic Report", ""]
        guild_id = str(interaction.guild.id)

        try: # Basic structure checks
            if guild_id not in self.xp_data:
                self.xp_data[guild_id] = {}
                report.append("✅ Created missing XP data entry.")
                issues_found += 1
                issues_fixed += 1
            if guild_id not in self.level_roles:
                self.level_roles[guild_id] = {}
                report.append("✅ Created missing Level Roles entry.")
                issues_found += 1
                issues_fixed += 1
            if guild_id not in self.level_messages:
                self.level_messages[guild_id] = {}
                report.append("✅ Created missing Level Messages entry.")
                issues_found += 1
                issues_fixed += 1
            if guild_id not in self.background_images:
                self.background_images[guild_id] = {}
                report.append("✅ Created missing Backgrounds entry.")
                issues_found += 1
                issues_fixed += 1
            if guild_id not in self.leveling_data:
                self.leveling_data[guild_id] = {}
                report.append("✅ Created missing Settings entry.")
                issues_found += 1
                issues_fixed += 1
            if "settings" not in self.leveling_data.get(guild_id, {}):
                self.leveling_data[guild_id]["settings"] = {
                    "min_xp": self.min_xp,
                    "max_xp": self.max_xp,
                    "xp_cooldown": self.xp_cooldown,
                    "level_up_channel": None,
                    "enabled": True,
                    "level_up_messages": True
                }
                report.append("✅ Initialized server settings.")
                issues_found += 1
                issues_fixed += 1
        except Exception as e:
            report.append(f"❌ CRITICAL ERROR initializing guild data: {e}")
            await interaction.followup.send("\n".join(report), ephemeral=True)
            return

        # Check Level Roles
        invalid_roles = []
        roles_dict = self.level_roles.get(guild_id, {})
        for level_str, role_id_str in list(roles_dict.items()):
            role = interaction.guild.get_role(int(role_id_str)) if role_id_str.isdigit() else None
            if not role:
                invalid_roles.append(level_str)
                issues_found += 1
        
        if invalid_roles:
            fixed_count = 0
            for lvl in invalid_roles:
                if lvl in roles_dict:
                    del roles_dict[lvl]
                    fixed_count += 1
            issues_fixed += fixed_count
            report.append(f"✅ Removed {fixed_count} invalid level roles.")
        
        if not roles_dict and guild_id in self.level_roles:
            del self.level_roles[guild_id]

        # Check Users
        invalid_users = []
        fixed_entries = 0
        users_dict = self.xp_data.get(guild_id, {})
        users_to_check = list(users_dict.keys())
        report.append(f"\nChecking {len(users_to_check)} users...")
        start_time = time.time()
        
        for i, user_id_str in enumerate(users_to_check):
            if i % 100 == 0 and i > 0:
                report.append(f"...checked {i}/{len(users_to_check)} users ({(time.time() - start_time):.1f}s)... ")
            
            user_data = users_dict.get(user_id_str)
            if not isinstance(user_data, dict):
                invalid_users.append(user_id_str)
                issues_found += 1
                report.append(f"❌ User {user_id_str} invalid data format.")
                continue
            
            member = interaction.guild.get_member(int(user_id_str))
            if not member:
                try:
                    await asyncio.sleep(0.05)
                    await interaction.guild.fetch_member(int(user_id_str))
                except discord.NotFound:
                    invalid_users.append(user_id_str)
                    issues_found += 1
                    continue
                except discord.HTTPException as e:
                    report.append(f"⚠️ HTTP Error fetch user {user_id_str}: {e.status}")
                    continue
                except Exception as e:
                    report.append(f"⚠️ Error fetch user {user_id_str}: {e}")
                    continue
            
            updated = False
            req_fields = {"xp": 0, "level": 0, "last_message": 0}
            for f, dv in req_fields.items():
                if f not in user_data or not isinstance(user_data[f], int):
                    user_data[f] = dv
                    updated = True
                    issues_found += 1
            
            calc_lvl = self.get_level_from_xp(user_data["xp"])
            if user_data["level"] != calc_lvl:
                user_data["level"] = calc_lvl
                updated = True
                issues_found += 1
                report.append(f"⚠️ Corrected level {user_id_str} ({user_data['level']} -> {calc_lvl})")
            
            if updated:
                fixed_entries += 1
                issues_fixed += 1
                self.xp_data[guild_id][user_id_str] = user_data
        
        if invalid_users:
            fixed_count = 0
            for uid in invalid_users:
                if uid in users_dict:
                    del users_dict[uid]
                    fixed_count += 1
            issues_fixed += fixed_count
            report.append(f"✅ Removed data for {fixed_count} users not in server.")
        
        if not users_dict and guild_id in self.xp_data:
            del self.xp_data[guild_id]
        
        if fixed_entries > 0:
            report.append(f"✅ Corrected fields for {fixed_entries} users.")

        # Check Settings Channel
        settings = self.leveling_data.get(guild_id, {}).get("settings", {})
        chan_id = settings.get("level_up_channel")
        if chan_id:
            channel = interaction.guild.get_channel(chan_id)
        else:
            channel = None
        
        if chan_id and (not channel or not isinstance(channel, discord.TextChannel)):
            report.append(f"⚠️ Level-up channel (ID: {chan_id}) invalid/missing. Resetting.")
            settings["level_up_channel"] = None
            issues_found += 1
            issues_fixed += 1
        elif channel:
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                report.append(f"⚠️ Missing Send/Embed perms in {channel.mention}.")
                issues_found += 1

        # Save and Final Report
        if issues_fixed > 0:
            report.append(f"\nSaving {issues_fixed} fixes...")
            await self.save_all_data()
            report.append("✅ Data saved.")
        
        report.append(f"\n--- Diagnosis Summary ---")
        if issues_found == 0:
            report.append("✨ No issues found!")
        else:
            report.append(f"🔍 Found {issues_found} issues.\n🛠️ Automatically fixed {issues_fixed} issues.")

        report_text = "\n".join(report)
        
        # Send report (handle length)
        if len(report_text) > 1900:
            chunks = [report_text[i:i+1900] for i in range(0, len(report_text), 1900)]
            await interaction.followup.send("Diagnostic report too long, sending chunks:", ephemeral=True)
            for chunk in chunks:
                await interaction.followup.send(f"```markdown\n{chunk}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"```markdown\n{report_text}\n```", ephemeral=True)

    @advanced_group.command(name="backup", description="Create a backup of all leveling data")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_leveling(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_data = {
                "version": 1,
                "timestamp": timestamp,
                "guild_id": guild_id,
                "guild_name": interaction.guild.name,
                "data": {
                    "xp_data": self.xp_data.get(guild_id, {}),
                    "level_roles": self.level_roles.get(guild_id, {}),
                    "level_messages": self.level_messages.get(guild_id, {}),
                    "background_images": self.background_images.get(guild_id, {}),
                    "settings": self.leveling_data.get(guild_id, {}).get("settings", {})
                 }
            }
            try: export_json = json.dumps(backup_data, indent=2)
            except TypeError as json_err: logger.error(f"Backup serialize error G:{guild_id}: {json_err}"); await interaction.followup.send("Backup Error: Failed to serialize data.", ephemeral=True); return

            file = discord.File(io.BytesIO(export_json.encode('utf-8')), filename=f"leveling_backup_{guild_id}_{timestamp}.json")
            await interaction.followup.send("📤 Here's your leveling system backup file.", file=file, ephemeral=True)
        except Exception as e:
             logger.error(f"Backup error G:{guild_id}: {e}", exc_info=True)
             await interaction.followup.send(f"Error creating backup: {e}", ephemeral=True)

    # --- Utility & Internal Methods ---
    # ... (get_xp_for_level, get_total_xp_for_level, get_level_from_xp) ...
    # ... (check_level_roles, generate_preview_card) ...
    # ... (load_data, _load_json_data, save_all_data, save_data, save_level_roles, etc.)...
    # ... (save_task, before_save_task) ...
    # ... (_is_leveling_enabled, _should_announce, _get_level_up_channel) ...
    # ... (on_message, handle_level_up, get_level_up_message) ...
    # ... (generate_level_card, get_user_rank, generate_leaderboard_image) ...

    def get_xp_for_level(self, level: int) -> int:
        if level <= 0:
            return 100 # Base XP for level 0 to 1
        total_xp_for_level = 5 * (level ** 2) + 50 * level + 100
        total_xp_for_prev_level = 5 * ((level-1) ** 2) + 50 * (level-1) + 100 if level > 0 else 0
        return total_xp_for_level - total_xp_for_prev_level

    def get_total_xp_for_level(self, level: int) -> int:
         if level < 0: return 0
         return 5 * (level ** 2) + 50 * level + 100

    def get_level_from_xp(self, xp: int) -> int:
        level = 0
        xp_needed = 100
        while xp >= xp_needed:
            level += 1
            xp_needed = self.get_total_xp_for_level(level + 1)
        return level

    async def check_level_roles(self, member: discord.Member, level: int, assign_all_below: bool = False):
        guild_id = str(member.guild.id)
        if guild_id not in self.level_roles: return
        roles_to_add = []
        current_roles = member.roles
        levels_to_check = range(1, level + 1) if assign_all_below else [level]
        for check_level in levels_to_check:
             level_str = str(check_level)
             if level_str in self.level_roles[guild_id]:
                 role_id_str = self.level_roles[guild_id][level_str]
                 try:
                      role = member.guild.get_role(int(role_id_str))
                      if role and role not in current_roles and role.position < member.guild.me.top_role.position and not role.is_integration() and not role.is_default() and not role.is_premium_subscriber():
                           roles_to_add.append(role)
                      elif role and role in current_roles:
                           pass # Already has role
                      elif role:
                           logger.warning(f"Cannot assign level role {role.name} G:{guild_id}: Higher than bot or managed.")
                 except ValueError: logger.error(f"Invalid role ID {role_id_str} L:{level_str} G:{guild_id}")
                 except Exception as e: logger.error(f"Error checking role {role_id_str} L:{level_str} G:{guild_id}: {e}")
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason=f"Level {level} reward(s)")
                logger.info(f"Awarded roles {[r.name for r in roles_to_add]} to {member.name} L:{level} G:{guild_id}")
            except discord.Forbidden: logger.error(f"Failed add roles to {member.name} G:{guild_id}: Missing Permissions")
            except discord.HTTPException as e: logger.error(f"Failed add roles to {member.name} G:{guild_id}: HTTP {e.status} - {e.text}")
            except Exception as e: logger.error(f"Failed add roles to {member.name} G:{guild_id}: {e}", exc_info=True)

    async def generate_preview_card(self, member: discord.Member, guild_id: str, user_id: str) -> io.BytesIO:
         if guild_id in self.xp_data and user_id in self.xp_data[guild_id]:
             data = self.xp_data[guild_id][user_id]
             level = data.get("level", 1); xp = data.get("xp", 50)
             total_xp_next = self.get_total_xp_for_level(level + 1)
             total_xp_current = self.get_total_xp_for_level(level)
             level_span_xp = total_xp_next - total_xp_current
             if level_span_xp <= 0: level_span_xp = 1
             progress = xp - total_xp_current
             percentage = max(0, min(100, int((progress / level_span_xp) * 100)))
         else: level = 1; xp = 50; total_xp_next = self.get_total_xp_for_level(2); percentage = 50
         rank = await self.get_user_rank(guild_id, user_id)
         return await self.generate_level_card(member=member, guild_id=guild_id, user_id=user_id, level=level, xp=xp, next_level_xp=total_xp_next, percentage=percentage, rank=rank)

    def load_data(self):
        self._load_json_data(self.data_file, "XP data", "xp_data")
        self._load_json_data(self.roles_file, "Level roles", "level_roles")
        self._load_json_data(self.messages_file, "Level messages", "level_messages")
        self._load_json_data(self.backgrounds_file, "Background images", "background_images")
        self._load_json_data(self.settings_file, "Leveling settings", "leveling_data")

    def _load_json_data(self, file_path: str, data_name: str, attribute_name: str):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                     content = f.read()
                     if not content.strip(): setattr(self, attribute_name, {}); return
                     f.seek(0)
                     setattr(self, attribute_name, json.load(f))
                     # logger.info(f"Loaded {data_name} from {file_path}")
            else: setattr(self, attribute_name, {})
        except json.JSONDecodeError as e: logger.error(f"JSON Decode Error {data_name} ({file_path}): {e}"); setattr(self, attribute_name, {})
        except Exception as e: logger.error(f"Load Error {data_name} ({file_path}): {e}", exc_info=True); setattr(self, attribute_name, {})

    async def save_all_data(self):
         await self._save_json_data(self.data_file, "XP data", self.xp_data)
         await self._save_json_data(self.roles_file, "Level roles", self.level_roles)
         await self._save_json_data(self.messages_file, "Level messages", self.level_messages)
         await self._save_json_data(self.backgrounds_file, "Background images", self.background_images)
         await self._save_json_data(self.settings_file, "Leveling settings", self.leveling_data)

    async def save_data(self):
         await self._save_json_data(self.data_file, "XP data", self.xp_data)
    async def save_level_roles(self):
        await self._save_json_data(self.roles_file, "Level roles", self.level_roles)
    async def save_level_messages(self):
        await self._save_json_data(self.messages_file, "Level messages", self.level_messages)
    async def save_backgrounds(self):
        await self._save_json_data(self.backgrounds_file, "Background images", self.background_images)
    async def save_leveling_settings(self):
         await self._save_json_data(self.settings_file, "Leveling settings", self.leveling_data)

    async def _save_json_data(self, file_path: str, data_name: str, data: dict):
        try:
             temp_file = f"{file_path}.tmp"
             with open(temp_file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)
             os.replace(temp_file, file_path)
        except Exception as e:
            logger.error(f"Save Error {data_name} ({file_path}): {e}", exc_info=True)
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as rm_err:
                    logger.error(f"Temp remove error {temp_file}: {rm_err}")

    @tasks.loop(minutes=5)
    async def save_task(self):
        logger.info("Running periodic save task for leveling data...")
        await self.save_all_data()
        logger.info("Periodic save task completed.")

    @save_task.before_loop
    async def before_save_task(self):
        await self.bot.wait_until_ready()

    def _is_leveling_enabled(self, guild_id: str) -> bool:
         return self.leveling_data.get(guild_id, {}).get("settings", {}).get("enabled", True)
    def _should_announce(self, guild_id: str) -> bool:
          return self.leveling_data.get(guild_id, {}).get("settings", {}).get("level_up_messages", True)
    def _get_level_up_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
         guild_id = str(guild.id)
         settings = self.leveling_data.get(guild_id, {}).get("settings", {})
         channel_id = settings.get("level_up_channel")
         if channel_id: return guild.get_channel(channel_id)
         return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.is_system() or not message.content: return
        guild_id = str(message.guild.id)
        if not self._is_leveling_enabled(guild_id): return
        user_id = str(message.author.id)
        current_time = int(time.time())
        if guild_id not in self.xp_data: self.xp_data[guild_id] = {}
        if user_id not in self.xp_data[guild_id]: self.xp_data[guild_id][user_id] = {"xp": 0, "level": 0, "last_message": 0}
        user_data = self.xp_data[guild_id][user_id]
        guild_settings = self.leveling_data.get(guild_id, {}).get("settings", {})
        cooldown = guild_settings.get("xp_cooldown", self.xp_cooldown)
        last_message_time = user_data.get("last_message", 0)
        if current_time - last_message_time < cooldown: return
        user_data["last_message"] = current_time
        min_xp = guild_settings.get("min_xp", self.min_xp)
        max_xp = guild_settings.get("max_xp", self.max_xp)
        xp_gained = random.randint(min_xp, max_xp)
        user_data["xp"] += xp_gained
        current_level = user_data["level"]
        new_level = self.get_level_from_xp(user_data["xp"])
        if new_level > current_level:
            user_data["level"] = new_level
            logger.info(f"User {message.author.name} ({user_id}) G:{guild_id} leveled up to {new_level} (XP: {user_data['xp']})")
            announce_channel = self._get_level_up_channel(message.guild) or message.channel
            await self.handle_level_up(message.author, new_level, announce_channel, announce=self._should_announce(guild_id))
        await self.save_data()

    async def handle_level_up(self, member: discord.Member, new_level: int, target_channel: discord.TextChannel, announce: bool = True):
        guild_id = str(member.guild.id)
        user_id = str(member.id)
        await self.check_level_roles(member, new_level)
        if announce:
            try:
                 message_template = self.get_level_up_message(guild_id, new_level)
                 level_message = message_template.replace("{user}", member.mention).replace("{level}", str(new_level)).replace("{server}", member.guild.name)
                 embed = discord.Embed(title="🎉 Level Up!", description=level_message, color=member.color or discord.Color.green())
                 embed.set_thumbnail(url=member.display_avatar.url)
                 embed.set_footer(text=f"Keep up the great work!")
                 perms = target_channel.permissions_for(member.guild.me)
                 if perms.send_messages and perms.embed_links:
                      await target_channel.send(content=f"{member.mention}", embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
                 else: logger.warning(f"Missing Send/Embed perms in LvlUp channel {target_channel.id} G:{guild_id}.")
            except Exception as e: logger.error(f"LvlUp announce error U:{user_id} G:{guild_id}: {e}", exc_info=True)

    def get_level_up_message(self, guild_id: str, level: int) -> str:
        default_message = "🎉 Congratulations {user}! You've reached level **{level}** in {server}!"
        guild_messages = self.level_messages.get(guild_id, {})
        level_str = str(level)
        return guild_messages.get(level_str, guild_messages.get("0", default_message))

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
        """Generate a simple level card image with optional custom background.

        Returns a BytesIO PNG image.
        """
        # Canvas
        width, height = 800, 240
        card = Image.new("RGB", (width, height), (25, 29, 35))
        draw = ImageDraw.Draw(card)

        # Background handling
        bg_url = self.background_images.get(guild_id, {}).get(user_id)
        if bg_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(bg_url, timeout=10) as resp:
                        if resp.status == 200:
                            bg_data = await resp.read()
                            with Image.open(io.BytesIO(bg_data)).convert("RGB") as bg:
                                bg = bg.resize((width, height), Image.LANCZOS)
                                # Subtle blur for readability
                                bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
                                card.paste(bg)
            except Exception as e:
                logger.warning(f"Failed to load background for {user_id}: {e}")

        # Theme overlay for readability and style
        theme_colors = {
            "default": (0, 0, 0, 110),
            "dark": (0, 0, 0, 140),
            "light": (255, 255, 255, 90),
            "blue": (30, 64, 175, 110),
            "green": (16, 95, 66, 110),
            "red": (136, 19, 55, 110),
            "purple": (88, 28, 135, 110),
            "gold": (146, 64, 14, 110),
        }
        overlay_color = theme_colors.get(theme, theme_colors["default"])
        overlay = Image.new("RGBA", (width, height), overlay_color)
        card = Image.alpha_composite(card.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(card)

        # Avatar
        avatar_size = 128
        avatar_x, avatar_y = 24, (height - avatar_size) // 2
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(member.display_avatar.replace(format='png', size=256).url), timeout=10) as resp:
                    if resp.status == 200:
                        av_bytes = await resp.read()
                        with Image.open(io.BytesIO(av_bytes)).convert("RGBA") as av:
                            av = av.resize((avatar_size, avatar_size), Image.LANCZOS)
                            # Make circular avatar
                            mask = Image.new("L", (avatar_size, avatar_size), 0)
                            ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
                            card.paste(av, (avatar_x, avatar_y), mask)
        except Exception as e:
            logger.debug(f"Avatar load failed for {member.id}: {e}")

        # Fonts
        def _font(name: str, size: int):
            try:
                path = os.path.join(self.fonts_dir, name)
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
            except Exception:
                pass
            return ImageFont.load_default()

        font_title = _font("Roboto-Bold.ttf", 32)
        font_sub = _font("Roboto-Regular.ttf", 20)
        font_small = _font("Roboto-Regular.ttf", 16)

        # Text positions
        text_x = avatar_x + avatar_size + 24
        text_y = 32

        # Primary line: username
        name_text = member.display_name
        draw.text((text_x, text_y), name_text, fill=(255, 255, 255), font=font_title)

        # Secondary line: Level | Rank
        text_y += 44
        sec_text = f"Level {level}"
        if rank:
            sec_text += f"  •  Rank #{rank}"
        draw.text((text_x, text_y), sec_text, fill=(235, 235, 235), font=font_sub)

        # XP line
        text_y += 28
        xp_text = f"XP: {xp:,}"
        draw.text((text_x, text_y), xp_text, fill=(210, 210, 210), font=font_small)

        # Progress bar
        bar_x, bar_y = text_x, text_y + 36
        bar_w, bar_h = width - bar_x - 24, 24
        # Background bar
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=12, fill=(60, 65, 75))
        # Filled bar
        pct = max(0, min(100, percentage))
        filled_w = int(bar_w * (pct / 100.0))
        fill_color = (99, 102, 241)  # Indigo-ish
        draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_w, bar_y + bar_h], radius=12, fill=fill_color)
        # Percentage text
        pct_text = f"{pct}% to next level"
        tw, th = draw.textsize(pct_text, font=font_small)
        draw.text((bar_x + bar_w - tw, bar_y + (bar_h - th) // 2), pct_text, fill=(255, 255, 255), font=font_small)

        # Footer
        footer = f"Next level at {next_level_xp:,} XP"
        draw.text((text_x, bar_y + bar_h + 12), footer, fill=(180, 180, 180), font=font_small)

        # Export to bytes
        out = io.BytesIO()
        card.save(out, format="PNG", optimize=True)
        out.seek(0)
        return out

    async def get_user_rank(self, guild_id: str, user_id: str) -> int:
        """Return the 1-based rank of the user by XP in the guild, or 0 if not found."""
        users = self.xp_data.get(guild_id, {})
        if not users or user_id not in users:
            return 0
        try:
            sorted_users = sorted(users.items(), key=lambda item: item[1].get("xp", 0), reverse=True)
            for idx, (uid, _) in enumerate(sorted_users, start=1):
                if uid == user_id:
                    return idx
        except Exception as e:
            logger.warning(f"Rank computation failed for G:{guild_id} U:{user_id}: {e}")
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
        """Generate a simple visual leaderboard image for the page slice."""
        width, height = 900, 520
        img = Image.new("RGB", (width, height), (24, 26, 32))
        draw = ImageDraw.Draw(img)

        # Theme header bar
        theme_colors = {
            "default": (60, 65, 75),
            "dark": (40, 44, 52),
            "light": (210, 210, 210),
            "blue": (37, 99, 235),
            "green": (16, 95, 66),
            "red": (153, 27, 27),
            "purple": (126, 34, 206),
            "gold": (146, 64, 14),
        }
        header_color = theme_colors.get(theme, theme_colors["default"])
        draw.rectangle([0, 0, width, 76], fill=header_color)

        # Fonts
        def _font(name: str, size: int):
            try:
                path = os.path.join(self.fonts_dir, name)
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
            except Exception:
                pass
            return ImageFont.load_default()

        title_font = _font("Roboto-Bold.ttf", 28)
        row_font = _font("Roboto-Regular.ttf", 20)
        small_font = _font("Roboto-Regular.ttf", 16)

        title = f"{guild.name} • Leaderboard (Page {page}/{total_pages})"
        draw.text((24, 22), title, fill=(255, 255, 255), font=title_font)

        # Rows
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(sorted_users))
        y = 100
        row_h = 76
        for i in range(start_idx, end_idx):
            user_id, data = sorted_users[i]
            rank = i + 1
            xp = data.get("xp", 0)
            level = data.get("level", 0)

            # Background stripe
            stripe = (30, 34, 40) if (i % 2 == 0) else (36, 40, 46)
            draw.rounded_rectangle([16, y - 10, width - 16, y + row_h - 18], radius=12, fill=stripe)

            # Rank
            draw.text((32, y), f"#{rank}", fill=(255, 255, 255), font=row_font)

            # Name
            name = f"User {user_id}"
            member = guild.get_member(int(user_id))
            if member:
                name = member.display_name
            draw.text((110, y), name, fill=(235, 235, 235), font=row_font)

            # Level / XP
            draw.text((110, y + 28), f"Level {level} • {xp:,} XP", fill=(200, 200, 200), font=small_font)

            y += row_h

        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        out.seek(0)
        return out

# --- Confirmation View ---
# (Keep existing ConfirmView)
class ConfirmView(discord.ui.View):
    # ... (ConfirmView implementation) ...
    def __init__(self, user_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.value = None
        self.user_id = user_id
        self._interaction = None # Store interaction for editing on timeout

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        self._interaction = interaction # Store the interaction that passed the check
        return True

    async def _disable_and_edit(self, interaction: discord.Interaction, content: str):
        for item in self.children:
            item.disabled = True
        try:
            await interaction.response.edit_message(content=content, view=self)
        except discord.NotFound:
             # Original message might have been deleted
             try:
                  await interaction.followup.send(content + " (Original message deleted)", ephemeral=True)
             except: pass # Ignore if followup fails too
        except Exception as e:
             logger.warning(f"Error editing confirmation message: {e}")

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await self._disable_and_edit(interaction, "Confirmed. Processing...")
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await self._disable_and_edit(interaction, "Operation cancelled.")
        self.stop()

    async def on_timeout(self):
        if self._interaction: # If an interaction was stored
             await self._disable_and_edit(self._interaction, "Confirmation timed out.")
        self.stop()


async def setup(bot):
    # Instantiate the Cog
    cog = Leveling(bot)

    # Add the main cog to the bot first
    await bot.add_cog(cog)

    logger.info("Leveling Cog loaded and command groups registered.") 