import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
from typing import Dict, List, Optional, Union, Literal
import logging
import io

logger = logging.getLogger("bot")

# Data structure for reaction roles:
# {
#   guild_id: {
#     message_id: {
#       emoji_id/name: {
#         role_id: int,
#         mode: str (normal, unique, or exclusive),
#       },
#       settings: {
#         limit: int or None,
#         required_roles: List[int] or None,
#         max_roles: int or None,
#         embed_data: dict or None
#       }
#     }
#   }
# }

class ReactionRoles(commands.GroupCog, name="reaction"):
    def __init__(self, bot):
        self.bot = bot
        self.reaction_roles = {}  # Guild ID -> Message ID -> Emoji -> Role ID
        self.data_file = 'reaction_roles.json'
        self.load_data()
        self.save_task.start()
        # Register persistent button view handlers
        bot.loop.create_task(self.register_persistent_views())
        super().__init__()
        
    def cog_unload(self):
        self.save_task.cancel()
        
    def load_data(self):
        """Load reaction role data from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    self.reaction_roles = json.load(f)
        except Exception as e:
            logger.error(f"Error loading reaction role data: {e}")
            
    async def save_data(self):
        """Save reaction role data to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.reaction_roles, f)
        except Exception as e:
            logger.error(f"Error saving reaction role data: {e}")
            
    @tasks.loop(minutes=5)
    async def save_task(self):
        """Periodically save data"""
        await self.save_data()
        
    @save_task.before_loop
    async def before_save(self):
        await self.bot.wait_until_ready()
        
    @app_commands.command(name="create", description="Create a reaction role message")
    @app_commands.describe(
        title="Title for the embed",
        description="Description for the embed",
        channel="Channel to send the reaction role message to",
        color="Color for the embed (hex code like #FF0000)",
        style="Style of the reaction role message (reactions or buttons)"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="Traditional Reactions", value="reactions"),
        app_commands.Choice(name="Modern Buttons UI", value="buttons")
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_create(
        self, 
        interaction: discord.Interaction, 
        title: str, 
        description: str, 
        channel: discord.TextChannel, 
        color: Optional[str] = None,
        style: str = "reactions"
    ):
        """Create a reaction role message with a customized embed"""
        # Validate color input
        embed_color = discord.Color.blue()
        if color:
            try:
                color = color.strip('#')
                embed_color = discord.Color.from_rgb(
                    int(color[0:2], 16),
                    int(color[2:4], 16),
                    int(color[4:6], 16)
                )
            except:
                await interaction.response.send_message("Invalid color format. Please use a hex code like #FF0000.", ephemeral=True)
                return
        
        # Create and send embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color
        )
        
        if style == "reactions":
            embed.set_footer(text="React to get roles")
        else:
            embed.set_footer(text="Click buttons below to get roles")
        
        try:
            # Check if bot has permissions
            if not channel.permissions_for(interaction.guild.me).send_messages or not channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.response.send_message(f"I don't have permission to send messages or embeds in {channel.mention}.", ephemeral=True)
                return
            
            # For button style, we'll create a view later when roles are added
            reaction_message = await channel.send(embed=embed)
            
            # Initialize data structure for this message
            guild_id = str(interaction.guild.id)
            message_id = str(reaction_message.id)
            
            if guild_id not in self.reaction_roles:
                self.reaction_roles[guild_id] = {}
                
            self.reaction_roles[guild_id][message_id] = {
                "settings": {
                    "limit": None,
                    "required_roles": None,
                    "max_roles": None,
                    "style": style,  # Store the style
                    "embed_data": {
                        "title": title,
                        "description": description,
                        "color": color or "blue"
                    }
                }
            }
            
            await self.save_data()
            
            if style == "reactions":
                await interaction.response.send_message(
                    f"Reaction role message created in {channel.mention}. Use `/reaction add` to add roles to it.", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Button role message created in {channel.mention}. Use `/reaction add` to add roles with buttons.", 
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error creating reaction role message: {e}")
            await interaction.response.send_message(f"Error creating reaction role message: {e}", ephemeral=True)
    
    @app_commands.command(name="add", description="Add a reaction role")
    @app_commands.describe(
        message_id="The ID of the message to add the reaction role to",
        emoji="The emoji to use for the reaction role",
        role="The role to give when the emoji is reacted"
    )
    async def add_reaction_role(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        """Add a reaction role command"""
        try:
            message = await interaction.channel.fetch_message(int(message_id))
            await message.add_reaction(emoji)
            
            guild_id = str(interaction.guild.id)
            if guild_id not in self.reaction_roles:
                self.reaction_roles[guild_id] = {}
                
            if message_id not in self.reaction_roles[guild_id]:
                self.reaction_roles[guild_id][message_id] = {}
                
            self.reaction_roles[guild_id][message_id][emoji] = role.id
            self.save_reaction_roles()
            
            await interaction.response.send_message(
                f"Added reaction role: {emoji} -> {role.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error adding reaction role: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="remove", description="Remove a reaction role from a message")
    @app_commands.describe(
        message_id="ID of the message to remove reaction from",
        emoji="Emoji to remove"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_remove(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        emoji: str
    ):
        """Remove a reaction role from a message"""
        guild_id = str(interaction.guild.id)
        
        # Check if this reaction role exists
        if (guild_id in self.reaction_roles and 
            message_id in self.reaction_roles[guild_id] and 
            emoji in self.reaction_roles[guild_id][message_id]):
            
            # Get the style
            style = self.reaction_roles[guild_id][message_id]["settings"].get("style", "reactions")
            
            # Try to find the message to remove reaction
            try:
                message_found = False
                message = None
                message_channel = None
                
                for channel in interaction.guild.text_channels:
                    try:
                        message = await channel.fetch_message(int(message_id))
                        message_found = True
                        message_channel = channel
                        
                        # Remove the reaction for reaction style
                        if style == "reactions":
                            await message.clear_reaction(emoji)
                        break
                    except:
                        continue
            except Exception as e:
                logger.error(f"Could not remove reaction from message: {e}")
            
            # Remove from data
            role_id = self.reaction_roles[guild_id][message_id][emoji]["role_id"]
            role = interaction.guild.get_role(int(role_id))
            role_name = role.name if role else f"Unknown Role ({role_id})"
            
            del self.reaction_roles[guild_id][message_id][emoji]
            
            # Update buttons for button style
            if style == "buttons" and message and message_channel:
                await self.update_button_message(guild_id, message_id, message, message_channel)
            
            await self.save_data()
            
            await interaction.response.send_message(
                f"Removed reaction role: {emoji} → {role_name}", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "This reaction role does not exist.", 
                ephemeral=True
            )
    
    @app_commands.command(name="list", description="List all reaction roles in the server")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_list(self, interaction: discord.Interaction):
        """List all reaction roles in the server"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.reaction_roles or not self.reaction_roles[guild_id]:
            await interaction.response.send_message("No reaction roles set up in this server.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="Reaction Roles",
            description="All reaction roles set up in this server",
            color=discord.Color.blue()
        )
        
        for message_id, data in self.reaction_roles[guild_id].items():
            # Skip the settings entry
            message_text = []
            for emoji, role_data in data.items():
                if emoji == "settings":
                    continue
                    
                role_id = role_data["role_id"]
                mode = role_data["mode"]
                role = interaction.guild.get_role(int(role_id))
                role_name = role.name if role else f"Unknown Role ({role_id})"
                
                message_text.append(f"{emoji} → {role_name} ({mode})")
            
            if message_text:
                embed.add_field(
                    name=f"Message ID: {message_id}",
                    value="\n".join(message_text),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="settings", description="Configure settings for a reaction role message")
    @app_commands.describe(
        message_id="ID of the message to configure",
        max_roles="Maximum number of roles a user can have from this message",
        required_role="Role required to use these reaction roles"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_settings(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        max_roles: Optional[int] = None,
        required_role: Optional[discord.Role] = None
    ):
        """Configure settings for a reaction role message"""
        guild_id = str(interaction.guild.id)
        
        # Check if this message exists in our data
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message(
                "This message does not have any reaction roles set up.", 
                ephemeral=True
            )
            return
            
        # Update settings
        settings = self.reaction_roles[guild_id][message_id]["settings"]
        
        if max_roles is not None:
            settings["max_roles"] = max_roles
            
        if required_role is not None:
            if "required_roles" not in settings or settings["required_roles"] is None:
                settings["required_roles"] = []
            if str(required_role.id) not in settings["required_roles"]:
                settings["required_roles"].append(str(required_role.id))
        
        await self.save_data()
        
        # Prepare response message
        response = ["Updated reaction role settings:"]
        if max_roles is not None:
            response.append(f"Max roles: {max_roles}")
        if required_role is not None:
            response.append(f"Added required role: {required_role.mention}")
            
        await interaction.response.send_message("\n".join(response), ephemeral=True)
    
    @app_commands.command(name="edit", description="Edit the embed for a reaction role message")
    @app_commands.describe(
        message_id="ID of the message to edit",
        title="New title for the embed",
        description="New description for the embed",
        color="New color for the embed (hex code like #FF0000)"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_edit(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None
    ):
        """Edit the embed for a reaction role message"""
        guild_id = str(interaction.guild.id)
        
        # Check if this message exists in our data
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message(
                "This message does not have any reaction roles set up.", 
                ephemeral=True
            )
            return
            
        # Try to find the message
        message_found = False
        for channel in interaction.guild.text_channels:
            try:
                message = await channel.fetch_message(int(message_id))
                message_found = True
                break
            except:
                continue
                
        if not message_found:
            await interaction.response.send_message(
                "Message not found in any channel. It may have been deleted.",
                ephemeral=True
            )
            return
            
        # Get current embed data
        settings = self.reaction_roles[guild_id][message_id]["settings"]
        if "embed_data" not in settings or settings["embed_data"] is None:
            settings["embed_data"] = {
                "title": "Reaction Roles",
                "description": "React to get roles",
                "color": "blue"
            }
            
        embed_data = settings["embed_data"]
        
        # Update embed data
        if title is not None:
            embed_data["title"] = title
        if description is not None:
            embed_data["description"] = description
        if color is not None:
            try:
                # Validate color
                color = color.strip('#')
                int(color[0:2], 16)
                int(color[2:4], 16)
                int(color[4:6], 16)
                embed_data["color"] = color
            except:
                await interaction.response.send_message(
                    "Invalid color format. Please use a hex code like #FF0000.",
                    ephemeral=True
                )
                return
                
        # Create updated embed
        embed_color = discord.Color.blue()
        if embed_data["color"] != "blue":
            try:
                color = embed_data["color"]
                embed_color = discord.Color.from_rgb(
                    int(color[0:2], 16),
                    int(color[2:4], 16),
                    int(color[4:6], 16)
                )
            except:
                pass
                
        embed = discord.Embed(
            title=embed_data["title"],
            description=embed_data["description"],
            color=embed_color
        )
        embed.set_footer(text="React to get roles")
        
        # Update message
        try:
            await message.edit(embed=embed)
            await self.save_data()
            
            await interaction.response.send_message(
                "Updated reaction role message embed.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error updating reaction role message: {e}")
            await interaction.response.send_message(
                f"Error updating reaction role message: {e}",
                ephemeral=True
            )
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction add event"""
        # Skip bot reactions
        if payload.user_id == self.bot.user.id:
            return
            
        guild_id = str(payload.guild_id)
        message_id = str(payload.message_id)
        emoji = payload.emoji.name
        
        # Check if this is a reaction role
        if (guild_id in self.reaction_roles and 
            message_id in self.reaction_roles[guild_id] and 
            emoji in self.reaction_roles[guild_id][message_id]):
            
            try:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                    
                member = guild.get_member(payload.user_id)
                if not member:
                    return
                    
                # Check settings
                settings = self.reaction_roles[guild_id][message_id]["settings"]
                
                # Check required roles
                if settings["required_roles"]:
                    has_required_role = False
                    for role_id in settings["required_roles"]:
                        role = guild.get_role(int(role_id))
                        if role and role in member.roles:
                            has_required_role = True
                            break
                            
                    if not has_required_role:
                        # Remove reaction if they don't have required role
                        channel = guild.get_channel(payload.channel_id)
                        message = await channel.fetch_message(payload.message_id)
                        await message.remove_reaction(payload.emoji, member)
                        
                        # Try to DM user
                        try:
                            roles_str = ", ".join([f"<@&{role_id}>" for role_id in settings["required_roles"]])
                            await member.send(f"You need one of these roles to use this reaction role: {roles_str}")
                        except:
                            pass
                            
                        return
                
                # Check max roles
                if settings["max_roles"]:
                    # Count how many roles from this message the user has
                    role_count = 0
                    for emoji_data in self.reaction_roles[guild_id][message_id].values():
                        if isinstance(emoji_data, dict) and "role_id" in emoji_data:
                            role = guild.get_role(int(emoji_data["role_id"]))
                            if role and role in member.roles:
                                role_count += 1
                                
                    if role_count >= settings["max_roles"]:
                        # Remove reaction if they've reached the limit
                        channel = guild.get_channel(payload.channel_id)
                        message = await channel.fetch_message(payload.message_id)
                        await message.remove_reaction(payload.emoji, member)
                        
                        # Try to DM user
                        try:
                            await member.send(f"You can only have {settings['max_roles']} roles from this reaction role message.")
                        except:
                            pass
                            
                        return
                
                # Get role to add
                role_data = self.reaction_roles[guild_id][message_id][emoji]
                role = guild.get_role(int(role_data["role_id"]))
                
                if not role:
                    # Role doesn't exist anymore
                    return
                    
                # Handle different modes
                if role_data["mode"] == "unique":
                    # Remove other roles from this message
                    for emoji_key, other_role_data in self.reaction_roles[guild_id][message_id].items():
                        if emoji_key != emoji and emoji_key != "settings" and "role_id" in other_role_data:
                            other_role = guild.get_role(int(other_role_data["role_id"]))
                            if other_role and other_role in member.roles:
                                await member.remove_roles(other_role)
                                
                                # Also remove the user's reaction
                                channel = guild.get_channel(payload.channel_id)
                                message = await channel.fetch_message(payload.message_id)
                                try:
                                    await message.remove_reaction(emoji_key, member)
                                except:
                                    pass
                elif role_data["mode"] == "exclusive":
                    # Remove ALL other reaction roles from this server
                    for other_msg_id, msg_data in self.reaction_roles[guild_id].items():
                        for emoji_key, other_role_data in msg_data.items():
                            if emoji_key != "settings" and "role_id" in other_role_data:
                                if other_msg_id == message_id and emoji_key == emoji:
                                    continue
                                    
                                other_role = guild.get_role(int(other_role_data["role_id"]))
                                if other_role and other_role in member.roles:
                                    await member.remove_roles(other_role)
                
                # Add the role
                await member.add_roles(role)
                
            except Exception as e:
                logger.error(f"Error handling reaction add: {e}")
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle reaction remove event"""
        # Skip bot reactions
        if payload.user_id == self.bot.user.id:
            return
            
        guild_id = str(payload.guild_id)
        message_id = str(payload.message_id)
        emoji = payload.emoji.name
        
        # Check if this is a reaction role
        if (guild_id in self.reaction_roles and 
            message_id in self.reaction_roles[guild_id] and 
            emoji in self.reaction_roles[guild_id][message_id]):
            
            try:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                    
                member = guild.get_member(payload.user_id)
                if not member:
                    return
                    
                # Get role to remove
                role_data = self.reaction_roles[guild_id][message_id][emoji]
                role = guild.get_role(int(role_data["role_id"]))
                
                if role and role in member.roles:
                    await member.remove_roles(role)
                    
            except Exception as e:
                logger.error(f"Error handling reaction remove: {e}")

    async def update_button_message(self, guild_id, message_id, message, channel):
        """Update a button style reaction role message with current buttons"""
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            return
        
        message_data = self.reaction_roles[guild_id][message_id]
        
        # Create a view with buttons for each role
        view = discord.ui.View(timeout=None)
        
        # Parse custom emoji ID if needed
        for emoji, role_data in message_data.items():
            # Skip the settings entry
            if emoji == "settings":
                continue
            
            # Get role info
            role_id = role_data["role_id"]
            mode = role_data["mode"]
            label = role_data.get("label", None)
            
            # Handle custom emoji format
            button_emoji = emoji
            if emoji.startswith('<:') and emoji.endswith('>'):
                try:
                    # Extract emoji ID from format <:name:id>
                    emoji_parts = emoji.strip('<>').split(':')
                    if len(emoji_parts) >= 2:
                        emoji_id = emoji_parts[-1]
                        emoji_name = emoji_parts[1] if len(emoji_parts) > 2 else emoji_parts[0]
                        button_emoji = discord.PartialEmoji(name=emoji_name, id=int(emoji_id))
                except Exception as e:
                    logger.error(f"Error parsing custom emoji {emoji}: {e}")
                    # Fallback to text label if emoji can't be parsed
                    button_emoji = None
                    if not label:
                        guild = self.bot.get_guild(int(guild_id))
                        if guild:
                            role = guild.get_role(int(role_id))
                            label = role.name if role else f"Role {role_id}"
            
            # Create a button for this role
            try:
                button = RoleButton(
                    emoji=button_emoji,
                    role_id=role_id,
                    message_id=message_id,
                    guild_id=guild_id,
                    mode=mode,
                    label=label,
                    cog=self
                )
                
                view.add_item(button)
            except Exception as e:
                logger.error(f"Error creating button for role {role_id}: {e}")
        
        # Update the message with the view
        try:
            await message.edit(view=view)
        except Exception as e:
            logger.error(f"Error updating button message: {e}")
            
    @app_commands.command(name="verify", description="Verify all reaction role configurations and fix any issues")
    @app_commands.checks.has_permissions(administrator=True)
    async def reaction_verify(self, interaction: discord.Interaction):
        """Verify all reaction role configurations and fix any issues"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.reaction_roles or not self.reaction_roles[guild_id]:
            await interaction.response.send_message("No reaction roles set up in this server.", ephemeral=True)
            return
            
        # Defer response since it might take time
        await interaction.response.defer(ephemeral=True)
        
        issues_found = 0
        issues_fixed = 0
        missing_messages = 0
        missing_roles = 0
        invalid_emojis = 0
        
        # Check all messages and roles
        for message_id, message_data in list(self.reaction_roles[guild_id].items()):
            # Try to find the message
            message_found = False
            
            try:
                for channel in interaction.guild.text_channels:
                    try:
                        message = await channel.fetch_message(int(message_id))
                        message_found = True
                        break
                    except:
                        continue
            except Exception as e:
                logger.error(f"Error finding message {message_id}: {e}")
            
            if not message_found:
                issues_found += 1
                missing_messages += 1
                logger.warning(f"Message {message_id} not found in any channel")
                continue
                
            # Check all roles
            for emoji, role_data in list(message_data.items()):
                if emoji == "settings":
                    continue
                    
                issues_found += 1
                
                # Check if role exists
                try:
                    role_id = role_data["role_id"]
                    role = interaction.guild.get_role(int(role_id))
                    
                    if not role:
                        missing_roles += 1
                        # Remove invalid role
                        del self.reaction_roles[guild_id][message_id][emoji]
                        issues_fixed += 1
                        logger.warning(f"Role {role_id} not found, removed from reaction roles")
                        continue
                        
                    # Check if role is manageable
                    if role.position >= interaction.guild.me.top_role.position:
                        logger.warning(f"Role {role.name} ({role_id}) is higher than bot's highest role, cannot be managed")
                except Exception as e:
                    logger.error(f"Error checking role {role_data.get('role_id')}: {e}")
                
                # Validate emoji
                try:
                    if emoji.startswith('<:') and emoji.endswith('>'):
                        # Custom emoji, check if it exists
                        emoji_parts = emoji.strip('<>').split(':')
                        if len(emoji_parts) >= 2:
                            emoji_id = emoji_parts[-1]
                            emoji_obj = None
                            
                            # Check if emoji exists
                            for e in interaction.guild.emojis:
                                if str(e.id) == emoji_id:
                                    emoji_obj = e
                                    break
                                    
                            if not emoji_obj:
                                logger.warning(f"Custom emoji {emoji} not found in guild")
                                invalid_emojis += 1
                    else:
                        # Unicode emoji, just check if it's a single character
                        if len(emoji) > 2 and not emoji.startswith('<:'):
                            logger.warning(f"Invalid emoji format: {emoji}")
                            invalid_emojis += 1
                except Exception as e:
                    logger.error(f"Error validating emoji {emoji}: {e}")
        
        # Save changes
        if issues_fixed > 0:
            await self.save_data()
            
        # Generate report
        report = [
            f"# Reaction Roles Verification Report",
            f"Issues found: {issues_found}",
            f"Issues fixed: {issues_fixed}",
            f"",
            f"## Details",
            f"- Missing messages: {missing_messages}",
            f"- Missing roles: {missing_roles}",
            f"- Invalid emojis: {invalid_emojis}",
            f"",
            f"Use `/reaction rebuild` to refresh all reaction role messages."
        ]
        
        await interaction.followup.send("\n".join(report), ephemeral=True)

    async def register_persistent_views(self):
        """Register persistent views for button-based reaction roles"""
        await self.bot.wait_until_ready()
        
        logger.info("Registering persistent reaction role views...")
        # Create a counter to track registered views
        registered_count = 0
        
        try:
            # Iterate through all guilds, messages with button style
            for guild_id, guild_data in self.reaction_roles.items():
                for message_id, message_data in guild_data.items():
                    # Skip if not a button or menu style message
                    style = message_data.get("settings", {}).get("style", "reactions")
                    if style == "reactions":
                        continue
                    
                    # For button style, create and register the view
                    if style == "buttons":
                        view = discord.ui.View(timeout=None)
                        
                        # Add buttons for each role
                        for emoji, role_data in message_data.items():
                            if emoji == "settings":
                                continue
                                
                            # Create and add button
                            role_id = role_data["role_id"]
                            mode = role_data["mode"]
                            label = role_data.get("label")
                            
                            button = RoleButton(
                                emoji=emoji,
                                role_id=role_id,
                                message_id=message_id,
                                guild_id=guild_id,
                                mode=mode,
                                label=label,
                                cog=self
                            )
                            
                            view.add_item(button)
                        
                        # Register the view if it has buttons
                        if view.children:
                            self.bot.add_view(view, message_id=int(message_id))
                            registered_count += 1
                    
                    # For menu style, create and register select menus
                    elif style == "menu":
                        view = discord.ui.View(timeout=None)
                        
                        # Add select menus for each category with roles
                        for category_id, category_data in message_data["settings"]["categories"].items():
                            if not category_data["roles"]:
                                continue
                                
                            # Create a select menu for this category
                            select_menu = RoleSelectMenu(
                                guild_id=guild_id,
                                message_id=message_id,
                                category_id=category_id,
                                category_name=category_data["name"],
                                category_emoji=category_data.get("emoji"),
                                roles=category_data["roles"],
                                cog=self
                            )
                            
                            view.add_item(select_menu)
                        
                        # Register the view if it has select menus
                        if view.children:
                            self.bot.add_view(view, message_id=int(message_id))
                            registered_count += 1
            
            logger.info(f"Registered {registered_count} persistent reaction role views.")
        except Exception as e:
            logger.error(f"Error registering persistent views: {e}")

    @app_commands.command(name="rebuild", description="Rebuild and fix all reaction role messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def reaction_rebuild(self, interaction: discord.Interaction):
        """Rebuild all reaction role messages in the server"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.reaction_roles or not self.reaction_roles[guild_id]:
            await interaction.response.send_message("No reaction roles set up in this server.", ephemeral=True)
            return
            
        # Track statistics
        found_count = 0
        updated_count = 0
        missing_count = 0
        missing_messages = []
        
        await interaction.response.send_message("Starting to rebuild all reaction role messages...", ephemeral=True)
        
        # Iterate through all messages in this guild
        for message_id, message_data in list(self.reaction_roles[guild_id].items()):
            found_count += 1
            
            # Try to find the message
            message_found = False
            message = None
            message_channel = None
            
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(int(message_id))
                    message_found = True
                    message_channel = channel
                    break
                except:
                    continue
                    
            if not message_found:
                missing_count += 1
                missing_messages.append(message_id)
                continue
                
            # Update the message based on its style
            style = message_data.get("settings", {}).get("style", "reactions")
            
            if style == "reactions":
                # For reaction style, clear all reactions and re-add them
                try:
                    await message.clear_reactions()
                    
                    # Add all reactions back
                    for emoji in message_data.keys():
                        if emoji != "settings":
                            try:
                                await message.add_reaction(emoji)
                                await asyncio.sleep(0.5)  # Avoid rate limits
                            except Exception as e:
                                logger.error(f"Error adding reaction {emoji}: {e}")
                                
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Error updating reaction message {message_id}: {e}")
            
            elif style == "buttons":
                # For button style, update the message view
                try:
                    await self.update_button_message(guild_id, message_id, message, message_channel)
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Error updating button message {message_id}: {e}")
            
            elif style == "menu":
                # For menu style, update the message
                try:
                    await self.update_menu_message(guild_id, message_id, message)
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Error updating menu message {message_id}: {e}")
        
        # Re-register persistent views
        await self.register_persistent_views()
        
        # Send summary
        summary = f"Rebuild complete!\n"
        summary += f"- Found: {found_count} reaction role messages\n"
        summary += f"- Updated: {updated_count} messages\n"
        summary += f"- Missing: {missing_count} messages\n"
        
        if missing_messages:
            summary += "\nMissing message IDs (these were not found in any channel):\n"
            summary += ", ".join(missing_messages[:10])
            if len(missing_messages) > 10:
                summary += f" and {len(missing_messages) - 10} more..."
                
        await interaction.followup.send(summary, ephemeral=True)

    @app_commands.command(name="clone", description="Clone a reaction role message to another channel")
    @app_commands.describe(
        message_id="ID of the message to clone",
        channel="Channel to clone the message to"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_clone(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        channel: discord.TextChannel
    ):
        """Clone a reaction role message to another channel"""
        guild_id = str(interaction.guild.id)
        
        # Check if this reaction role exists
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message("Reaction role message not found.", ephemeral=True)
            return
            
        # Check permissions in target channel
        if not channel.permissions_for(interaction.guild.me).send_messages or not channel.permissions_for(interaction.guild.me).embed_links:
            await interaction.response.send_message(f"I don't have permission to send messages or embeds in {channel.mention}.", ephemeral=True)
            return
            
        # Get original message data
        message_data = self.reaction_roles[guild_id][message_id]
        style = message_data.get("settings", {}).get("style", "reactions")
        
        # Find original message to clone content
        original_message = None
        for ch in interaction.guild.text_channels:
            try:
                original_message = await ch.fetch_message(int(message_id))
                break
            except:
                continue
                
        if not original_message:
            await interaction.response.send_message("Could not find the original message to clone.", ephemeral=True)
            return
            
        # Clone the message
        try:
            # Create new embed matching the original
            if original_message.embeds:
                new_embed = original_message.embeds[0].copy()
            else:
                # Create default embed if original has none
                new_embed = discord.Embed(
                    title="Reaction Roles",
                    description="React to get roles",
                    color=discord.Color.blue()
                )
                
            # Send new message based on style
            if style == "reactions":
                # For reaction style, send embed then add reactions
                new_message = await channel.send(embed=new_embed)
                
                # Add all reactions
                for emoji in message_data.keys():
                    if emoji != "settings":
                        try:
                            await new_message.add_reaction(emoji)
                            await asyncio.sleep(0.5)  # Avoid rate limits
                        except Exception as e:
                            logger.error(f"Error adding reaction {emoji}: {e}")
            
            elif style == "buttons":
                # For button style, create view with buttons
                view = discord.ui.View(timeout=None)
                
                for emoji, role_data in message_data.items():
                    if emoji == "settings":
                        continue
                        
                    # Get role info
                    role_id = role_data["role_id"]
                    mode = role_data["mode"]
                    label = role_data.get("label")
                    
                    # Create button
                    button = RoleButton(
                        emoji=emoji,
                        role_id=role_id,
                        message_id="temp_id",  # Will be updated after sending
                        guild_id=guild_id,
                        mode=mode,
                        label=label,
                        cog=self
                    )
                    
                    view.add_item(button)
                
                # Send message with buttons
                new_message = await channel.send(embed=new_embed, view=view)
                
                # Update button message_ids
                for child in view.children:
                    child.message_id = str(new_message.id)
                
                # Register the view
                self.bot.add_view(view, message_id=new_message.id)
            
            elif style == "menu":
                # For menu style, update the message
                new_message = await channel.send(embed=new_embed, view=discord.ui.View())
                
                # Create data structure for the new message
                new_message_id = str(new_message.id)
                
                # Clone the data
                self.reaction_roles[guild_id][new_message_id] = {
                    "settings": message_data["settings"].copy()
                }
                
                # Update the menu message
                await self.update_menu_message(guild_id, new_message_id, new_message)
                await self.save_data()
                
                await interaction.response.send_message(
                    f"Cloned role menu to {channel.mention}.", 
                    ephemeral=True
                )
                return
            
            # Create data structure for the new message
            new_message_id = str(new_message.id)
            
            self.reaction_roles[guild_id][new_message_id] = {}
            
            # Copy settings
            self.reaction_roles[guild_id][new_message_id]["settings"] = message_data["settings"].copy()
            
            # Copy role mappings
            for emoji, role_data in message_data.items():
                if emoji != "settings":
                    self.reaction_roles[guild_id][new_message_id][emoji] = role_data.copy()
            
            await self.save_data()
            
            await interaction.response.send_message(
                f"Cloned reaction role message to {channel.mention}.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error cloning reaction role message: {e}")
            await interaction.response.send_message(f"Error cloning message: {e}", ephemeral=True)

    @app_commands.command(name="cleanup", description="Clean up invalid reaction role entries")
    @app_commands.checks.has_permissions(administrator=True)
    async def reaction_cleanup(self, interaction: discord.Interaction):
        """Clean up invalid reaction role entries"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.reaction_roles or not self.reaction_roles[guild_id]:
            await interaction.response.send_message("No reaction roles set up in this server.", ephemeral=True)
            return
            
        # Defer response since it might take time
        await interaction.response.defer(ephemeral=True)
        
        initial_messages = 0
        initial_roles = 0
        removed_messages = 0
        removed_roles = 0
        
        # Count initial entries
        for message_id, message_data in self.reaction_roles[guild_id].items():
            initial_messages += 1
            for emoji in message_data:
                if emoji != "settings":
                    initial_roles += 1
        
        # Clean up invalid messages
        for message_id in list(self.reaction_roles[guild_id].keys()):
            # Try to find the message
            message_found = False
            
            try:
                for channel in interaction.guild.text_channels:
                    try:
                        message = await channel.fetch_message(int(message_id))
                        message_found = True
                        break
                    except:
                        continue
            except Exception as e:
                logger.error(f"Error finding message {message_id}: {e}")
            
            if not message_found:
                del self.reaction_roles[guild_id][message_id]
                removed_messages += 1
                continue
            
            # Clean up invalid roles
            for emoji in list(self.reaction_roles[guild_id][message_id].keys()):
                if emoji == "settings":
                    continue
                    
                # Check if role exists
                try:
                    role_id = self.reaction_roles[guild_id][message_id][emoji]["role_id"]
                    role = interaction.guild.get_role(int(role_id))
                    
                    if not role:
                        del self.reaction_roles[guild_id][message_id][emoji]
                        removed_roles += 1
                except Exception as e:
                    logger.error(f"Error checking role: {e}")
                    # Remove invalid entry
                    try:
                        del self.reaction_roles[guild_id][message_id][emoji]
                        removed_roles += 1
                    except:
                        pass
        
        # Remove empty messages
        for message_id in list(self.reaction_roles[guild_id].keys()):
            if len(self.reaction_roles[guild_id][message_id]) == 1 and "settings" in self.reaction_roles[guild_id][message_id]:
                del self.reaction_roles[guild_id][message_id]
                removed_messages += 1
        
        # If guild dict is empty, remove it
        if not self.reaction_roles[guild_id]:
            del self.reaction_roles[guild_id]
        
        # Save changes
        await self.save_data()
        
        # Generate report
        remaining_messages = initial_messages - removed_messages
        remaining_roles = initial_roles - removed_roles
        
        report = [
            "# Reaction Roles Cleanup Report",
            f"Before cleanup: {initial_messages} messages, {initial_roles} roles",
            f"Removed: {removed_messages} messages, {removed_roles} roles",
            f"Remaining: {remaining_messages} messages, {remaining_roles} roles",
            "",
            "Cleanup completed successfully."
        ]
        
        await interaction.followup.send("\n".join(report), ephemeral=True)

    @app_commands.command(name="export", description="Export reaction roles configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def reaction_export(self, interaction: discord.Interaction):
        """Export reaction roles configuration for backup"""
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.reaction_roles or not self.reaction_roles[guild_id]:
            await interaction.response.send_message("No reaction roles set up in this server.", ephemeral=True)
            return
        
        # Create export data
        export_data = {
            "guild_id": guild_id,
            "guild_name": interaction.guild.name,
            "timestamp": discord.utils.utcnow().isoformat(),
            "reaction_roles": self.reaction_roles[guild_id]
        }
        
        # Convert to JSON
        export_json = json.dumps(export_data, indent=2)
        
        # Create file
        file = discord.File(
            io.BytesIO(export_json.encode('utf-8')),
            filename=f"reaction_roles_export_{guild_id}.json"
        )
        
        await interaction.response.send_message(
            "📤 Here's your reaction roles configuration export. Keep this file safe for backup purposes.",
            file=file,
            ephemeral=True
        )

    @app_commands.command(name="create_menu", description="Create an advanced role menu with categories")
    @app_commands.describe(
        title="Title for the role menu",
        description="Description for the role menu",
        channel="Channel to send the role menu to",
        color="Color for the embed (hex code like #FF0000)"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create_menu(
        self, 
        interaction: discord.Interaction, 
        title: str, 
        description: str, 
        channel: discord.TextChannel, 
        color: Optional[str] = None
    ):
        """Create an advanced role menu with categories support"""
        # Validate color input
        embed_color = discord.Color.blue()
        if color:
            try:
                color = color.strip('#')
                embed_color = discord.Color.from_rgb(
                    int(color[0:2], 16),
                    int(color[2:4], 16),
                    int(color[4:6], 16)
                )
            except:
                await interaction.response.send_message("Invalid color format. Please use a hex code like #FF0000.", ephemeral=True)
                return
        
        # Create and send embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color
        )
        embed.set_footer(text="Premium Role Menu | Click the buttons below to select roles")
        
        try:
            # Check if bot has permissions
            if not channel.permissions_for(interaction.guild.me).send_messages or not channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.response.send_message(f"I don't have permission to send messages or embeds in {channel.mention}.", ephemeral=True)
                return
                
            # Create and send the embed with an empty view for now
            menu_message = await channel.send(embed=embed, view=discord.ui.View())
            
            # Initialize data structure for this menu
            guild_id = str(interaction.guild.id)
            message_id = str(menu_message.id)
            
            if guild_id not in self.reaction_roles:
                self.reaction_roles[guild_id] = {}
                
            self.reaction_roles[guild_id][message_id] = {
                "settings": {
                    "limit": None,
                    "required_roles": None,
                    "max_roles": None,
                    "style": "menu",  # Special style for advanced menus
                    "embed_data": {
                        "title": title,
                        "description": description,
                        "color": color or "blue"
                    },
                    "categories": {}  # Store categories for this menu
                }
            }
            
            await self.save_data()
            
            await interaction.response.send_message(
                f"Advanced role menu created in {channel.mention}. Use `/reaction add_category` to add role categories.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creating role menu: {e}")
            await interaction.response.send_message(f"Error creating role menu: {e}", ephemeral=True)

    @app_commands.command(name="add_category", description="Add a category to a role menu")
    @app_commands.describe(
        message_id="ID of the role menu message",
        category_name="Name of the category to add",
        description="Description of this category (optional)",
        emoji="Emoji for this category (optional)"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_category(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        category_name: str,
        description: Optional[str] = None,
        emoji: Optional[str] = None
    ):
        """Add a category to an advanced role menu"""
        guild_id = str(interaction.guild.id)
        
        # Verify the message exists and is a menu
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message("Role menu not found.", ephemeral=True)
            return
            
        message_data = self.reaction_roles[guild_id][message_id]
        if message_data["settings"].get("style") != "menu":
            await interaction.response.send_message("This message is not an advanced role menu.", ephemeral=True)
            return
            
        # Make the category ID by slugifying the name
        category_id = category_name.lower().replace(" ", "_")
        
        # Check if category already exists
        if category_id in message_data["settings"]["categories"]:
            await interaction.response.send_message(f"Category '{category_name}' already exists in this menu.", ephemeral=True)
            return
            
        # Add the category
        message_data["settings"]["categories"][category_id] = {
            "name": category_name,
            "description": description,
            "emoji": emoji,
            "roles": []
        }
        
        await self.save_data()
        
        # Update the menu message
        try:
            # Find the message
            message = None
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(int(message_id))
                    break
                except:
                    continue
                    
            if message:
                await self.update_menu_message(guild_id, message_id, message)
                
            await interaction.response.send_message(
                f"Added category '{category_name}' to the role menu. Use `/reaction add_menu_role` to add roles to this category.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error adding category: {e}")
            await interaction.response.send_message(f"Error adding category: {e}", ephemeral=True)
            
    @app_commands.command(name="add_menu_role", description="Add a role to a menu category")
    @app_commands.describe(
        message_id="ID of the role menu message",
        category_name="Name of the category to add the role to",
        role="Role to add",
        description="Description of this role (optional)",
        emoji="Emoji for this role (optional)",
        mode="Role assignment mode"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Normal - User can have multiple roles", value="normal"),
        app_commands.Choice(name="Unique - User can only have one role from this category", value="unique"),
        app_commands.Choice(name="Exclusive - This role removes all roles from other categories", value="exclusive")
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_menu_role(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        category_name: str,
        role: discord.Role,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        mode: str = "normal"
    ):
        """Add a role to a category in an advanced role menu"""
        guild_id = str(interaction.guild.id)
        
        # Verify the message exists and is a menu
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message("Role menu not found.", ephemeral=True)
            return
            
        message_data = self.reaction_roles[guild_id][message_id]
        if message_data["settings"].get("style") != "menu":
            await interaction.response.send_message("This message is not an advanced role menu.", ephemeral=True)
            return
            
        # Find the category
        category_id = category_name.lower().replace(" ", "_")
        if category_id not in message_data["settings"]["categories"]:
            await interaction.response.send_message(f"Category '{category_name}' not found in this menu.", ephemeral=True)
            return
            
        # Check if the bot can manage this role
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                "I cannot assign this role as it's higher than or equal to my highest role.", 
                ephemeral=True
            )
            return
            
        # Check if role already exists in any category
        for cat_id, cat_data in message_data["settings"]["categories"].items():
            for existing_role in cat_data["roles"]:
                if existing_role["role_id"] == str(role.id):
                    await interaction.response.send_message(
                        f"Role {role.mention} already exists in category '{cat_data['name']}'.", 
                        ephemeral=True
                    )
                    return
                    
        # Add the role to the category
        role_data = {
            "role_id": str(role.id),
            "description": description,
            "emoji": emoji,
            "mode": mode
        }
        
        message_data["settings"]["categories"][category_id]["roles"].append(role_data)
        
        await self.save_data()
        
        # Update the menu message
        try:
            # Find the message
            message = None
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(int(message_id))
                    break
                except:
                    continue
                    
            if message:
                await self.update_menu_message(guild_id, message_id, message)
                
            await interaction.response.send_message(
                f"Added role {role.mention} to category '{category_name}' in the role menu.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error adding role to menu: {e}")
            await interaction.response.send_message(f"Error adding role to menu: {e}", ephemeral=True)

    async def update_menu_message(self, guild_id, message_id, message):
        """Update an advanced role menu message with current categories and roles"""
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            return
        
        message_data = self.reaction_roles[guild_id][message_id]
        if message_data["settings"].get("style") != "menu":
            return
            
        # Get embed data
        embed_data = message_data["settings"]["embed_data"]
        
        # Create a new embed with categories and roles
        try:
            # Parse color
            embed_color = discord.Color.blue()
            if embed_data["color"] != "blue":
                try:
                    color = embed_data["color"]
                    embed_color = discord.Color.from_rgb(
                        int(color[0:2], 16),
                        int(color[2:4], 16),
                        int(color[4:6], 16)
                    )
                except:
                    pass
                    
            embed = discord.Embed(
                title=embed_data["title"],
                description=embed_data["description"],
                color=embed_color
            )
            
            # Add categories and roles to the embed
            for category_id, category_data in message_data["settings"]["categories"].items():
                category_text = []
                
                # Add category description if present
                if category_data.get("description"):
                    category_text.append(category_data["description"])
                
                # Add roles in this category
                for role_data in category_data["roles"]:
                    role_id = role_data["role_id"]
                    emoji = role_data.get("emoji", "")
                    description = role_data.get("description", "")
                    
                    role_line = f"{emoji} <@&{role_id}>"
                    if description:
                        role_line += f" - {description}"
                        
                    category_text.append(role_line)
                
                # Add field for this category
                if category_text:
                    category_name = category_data["name"]
                    if category_data.get("emoji"):
                        category_name = f"{category_data['emoji']} {category_name}"
                        
                    embed.add_field(
                        name=category_name,
                        value="\n".join(category_text),
                        inline=False
                    )
            
            embed.set_footer(text="Premium Role Menu | Use the dropdown menus below to select roles")
            
            # Create dropdown menus for each category with roles
            view = discord.ui.View(timeout=None)
            
            for category_id, category_data in message_data["settings"]["categories"].items():
                if not category_data["roles"]:
                    continue
                    
                # Create a select menu for this category
                select_menu = RoleSelectMenu(
                    guild_id=guild_id,
                    message_id=message_id,
                    category_id=category_id,
                    category_name=category_data["name"],
                    category_emoji=category_data.get("emoji"),
                    roles=category_data["roles"],
                    cog=self
                )
                
                view.add_item(select_menu)
            
            # Update the message
            await message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error updating menu message: {e}")

    @app_commands.command(name="remove_menu_role", description="Remove a role from a menu category")
    @app_commands.describe(
        message_id="ID of the role menu message",
        role="Role to remove"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_menu_role(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        role: discord.Role
    ):
        """Remove a role from a menu category"""
        guild_id = str(interaction.guild.id)
        
        # Verify the message exists and is a menu
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message("Role menu not found.", ephemeral=True)
            return
            
        message_data = self.reaction_roles[guild_id][message_id]
        if message_data["settings"].get("style") != "menu":
            await interaction.response.send_message("This message is not an advanced role menu.", ephemeral=True)
            return
            
        # Find the role in categories
        role_id = str(role.id)
        found = False
        
        for category_id, category_data in message_data["settings"]["categories"].items():
            # Find and remove the role from this category
            for i, role_data in enumerate(category_data["roles"]):
                if role_data["role_id"] == role_id:
                    category_data["roles"].pop(i)
                    found = True
                    break
            
            if found:
                break
                
        if not found:
            await interaction.response.send_message(f"Role {role.mention} not found in any menu category.", ephemeral=True)
            return
            
        await self.save_data()
        
        # Update the menu message
        try:
            # Find the message
            message = None
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(int(message_id))
                    break
                except:
                    continue
                    
            if message:
                await self.update_menu_message(guild_id, message_id, message)
                
            await interaction.response.send_message(
                f"Removed role {role.mention} from the role menu.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error removing role from menu: {e}")
            await interaction.response.send_message(f"Error removing role from menu: {e}", ephemeral=True)

    @app_commands.command(name="remove_category", description="Remove a category from a role menu")
    @app_commands.describe(
        message_id="ID of the role menu message",
        category_name="Name of the category to remove"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_category(
        self, 
        interaction: discord.Interaction, 
        message_id: str, 
        category_name: str
    ):
        """Remove a category from an advanced role menu"""
        guild_id = str(interaction.guild.id)
        
        # Verify the message exists and is a menu
        if guild_id not in self.reaction_roles or message_id not in self.reaction_roles[guild_id]:
            await interaction.response.send_message("Role menu not found.", ephemeral=True)
            return
            
        message_data = self.reaction_roles[guild_id][message_id]
        if message_data["settings"].get("style") != "menu":
            await interaction.response.send_message("This message is not an advanced role menu.", ephemeral=True)
            return
            
        # Find the category
        category_id = category_name.lower().replace(" ", "_")
        if category_id not in message_data["settings"]["categories"]:
            await interaction.response.send_message(f"Category '{category_name}' not found in this menu.", ephemeral=True)
            return
            
        # Remove the category
        del message_data["settings"]["categories"][category_id]
        
        await self.save_data()
        
        # Update the menu message
        try:
            # Find the message
            message = None
            for channel in interaction.guild.text_channels:
                try:
                    message = await channel.fetch_message(int(message_id))
                    break
                except:
                    continue
                    
            if message:
                await self.update_menu_message(guild_id, message_id, message)
                
            await interaction.response.send_message(
                f"Removed category '{category_name}' from the role menu.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error removing category: {e}")
            await interaction.response.send_message(f"Error removing category: {e}", ephemeral=True)

# Button class for role assignment
class RoleButton(discord.ui.Button):
    def __init__(self, emoji, role_id, message_id, guild_id, mode, label, cog):
        # Set up the button
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label or None,
            emoji=emoji,
            custom_id=f"role_{role_id}_{message_id}"
        )
        self.role_id = role_id
        self.message_id = message_id
        self.guild_id = guild_id
        self.mode = mode
        self.cog = cog
    
    async def callback(self, interaction: discord.Interaction):
        """Called when the button is clicked"""
        if interaction.guild_id != int(self.guild_id):
            return
        
        member = interaction.user
        guild = interaction.guild
        role = guild.get_role(int(self.role_id))
        
        if not role:
            await interaction.response.send_message("This role no longer exists.", ephemeral=True)
            return
        
        message_data = self.cog.reaction_roles[self.guild_id][self.message_id]
        settings = message_data["settings"]
        
        # Check required roles
        if settings["required_roles"]:
            has_required_role = False
            for role_id in settings["required_roles"]:
                req_role = guild.get_role(int(role_id))
                if req_role and req_role in member.roles:
                    has_required_role = True
                    break
            
            if not has_required_role:
                roles_str = ", ".join([f"<@&{role_id}>" for role_id in settings["required_roles"]])
                await interaction.response.send_message(
                    f"You need one of these roles to use this button: {roles_str}",
                    ephemeral=True
                )
                return
        
        # Check max roles
        if settings["max_roles"]:
            # Count how many roles from this message the user has
            role_count = 0
            for emoji_data in message_data.values():
                if isinstance(emoji_data, dict) and "role_id" in emoji_data:
                    role = guild.get_role(int(emoji_data["role_id"]))
                    if role and role in member.roles:
                        role_count += 1
            
            if role_count >= settings["max_roles"] and role not in member.roles:
                await interaction.response.send_message(
                    f"You can only have {settings['max_roles']} roles from this message.",
                    ephemeral=True
                )
                return
        
        # Handle different modes
        if self.mode == "unique":
            # Remove other roles from this message
            roles_to_remove = []
            for emoji, other_role_data in message_data.items():
                if emoji != "settings" and "role_id" in other_role_data:
                    if other_role_data["role_id"] != self.role_id:
                        other_role = guild.get_role(int(other_role_data["role_id"]))
                        if other_role and other_role in member.roles:
                            roles_to_remove.append(other_role)
            
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove)
        
        elif self.mode == "exclusive":
            # Remove ALL other reaction roles
            roles_to_remove = []
            for other_msg_id, msg_data in self.cog.reaction_roles[self.guild_id].items():
                for emoji, other_role_data in msg_data.items():
                    if emoji != "settings" and "role_id" in other_role_data:
                        if other_msg_id == self.message_id and other_role_data["role_id"] == self.role_id:
                            continue
                        
                        other_role = guild.get_role(int(other_role_data["role_id"]))
                        if other_role and other_role in member.roles:
                            roles_to_remove.append(other_role)
            
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove)
        
        # Toggle the role
        try:
            if role in member.roles:
                await member.remove_roles(role)
                await interaction.response.send_message(f"Removed role: {role.mention}", ephemeral=True)
            else:
                await member.add_roles(role)
                await interaction.response.send_message(f"Added role: {role.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to manage that role.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

# Dropdown menu for role selection within a category
class RoleSelectMenu(discord.ui.Select):
    def __init__(self, guild_id, message_id, category_id, category_name, category_emoji, roles, cog):
        self.guild_id = guild_id
        self.message_id = message_id
        self.category_id = category_id
        self.cog = cog
        
        # Determine if the menu should be single or multi-select
        self.is_unique = any(role.get("mode") == "unique" for role in roles)
        
        # Create select menu options
        options = []
        for role_data in roles:
            role_id = role_data["role_id"]
            emoji = role_data.get("emoji")
            description = role_data.get("description", "Click to toggle this role")
            
            # Truncate description if too long
            if description and len(description) > 100:
                description = description[:97] + "..."
                
            # Create the option
            option = discord.SelectOption(
                label=f"Role: {role_id}", # Will be replaced with actual role name in the callback
                value=role_id,
                description=description,
                emoji=emoji
            )
            
            options.append(option)
        
        # Initialize the select menu
        placeholder = f"Select {category_name} roles"
        if category_emoji:
            placeholder = f"{category_emoji} {placeholder}"
            
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=1 if self.is_unique else len(options),
            options=options,
            custom_id=f"menu_{message_id}_{category_id}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle role selection"""
        if str(interaction.guild_id) != self.guild_id:
            return
            
        guild = interaction.guild
        member = interaction.user
        
        # Get menu data
        message_data = self.cog.reaction_roles[self.guild_id][self.message_id]
        category_data = message_data["settings"]["categories"][self.category_id]
        
        # Get selected and unselected role IDs
        selected_role_ids = self.values
        
        # Map of role IDs to their data
        role_data_map = {role["role_id"]: role for role in category_data["roles"]}
        
        # Process selections
        added_roles = []
        removed_roles = []
        
        for role_id, role_data in role_data_map.items():
            role = guild.get_role(int(role_id))
            if not role:
                continue
                
            # Check if this role was selected or deselected
            if role_id in selected_role_ids:
                # Role was selected - add it if not already there
                if role not in member.roles:
                    # Check exclusive mode
                    if role_data.get("mode") == "exclusive":
                        # Remove all other reaction roles
                        for other_msg_id, msg_data in self.cog.reaction_roles[self.guild_id].items():
                            if msg_data["settings"].get("style") == "menu":
                                for other_cat_id, other_cat_data in msg_data["settings"]["categories"].items():
                                    for other_role_data in other_cat_data["roles"]:
                                        if other_msg_id == self.message_id and other_cat_id == self.category_id and other_role_data["role_id"] == role_id:
                                            continue
                                            
                                        other_role = guild.get_role(int(other_role_data["role_id"]))
                                        if other_role and other_role in member.roles:
                                            try:
                                                await member.remove_roles(other_role)
                                                removed_roles.append(other_role)
                                            except:
                                                pass
                            elif "settings" in msg_data and emoji != "settings":
                                for emoji, emoji_data in msg_data.items():
                                    if emoji != "settings" and "role_id" in emoji_data:
                                        other_role = guild.get_role(int(emoji_data["role_id"]))
                                        if other_role and other_role in member.roles:
                                            try:
                                                await member.remove_roles(other_role)
                                                removed_roles.append(other_role)
                                            except:
                                                pass
                    
                    # Add the role
                    try:
                        await member.add_roles(role)
                        added_roles.append(role)
                    except:
                        pass
            elif role in member.roles:
                # Role was deselected - remove it
                try:
                    await member.remove_roles(role)
                    removed_roles.append(role)
                except:
                    pass
        
        # Send response
        response_parts = []
        if added_roles:
            response_parts.append(f"Added roles: {', '.join(role.mention for role in added_roles)}")
        if removed_roles:
            response_parts.append(f"Removed roles: {', '.join(role.mention for role in removed_roles)}")
            
        if response_parts:
            await interaction.response.send_message("\n".join(response_parts), ephemeral=True)
        else:
            await interaction.response.send_message("No role changes were made.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ReactionRoles(bot)) 