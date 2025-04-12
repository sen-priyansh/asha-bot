import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
import json
import os
import asyncio
from aiohttp import web

class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_roles = {}  # {guild_id: role_id}
        self.roles_file = 'autoroles.json'
        self.load_roles()  # Load saved roles when the cog starts
        self.save_roles_task.start()  # Start the background task
        self.web_server_task.start()  # Start the web server
        self.port = int(os.getenv('PORT', 8080))  # Use PORT env variable or default to 8080
    
    def cog_unload(self):
        """Called when the cog is unloaded"""
        self.save_roles_task.cancel()  # Stop the background task
        self.web_server_task.cancel()  # Stop the web server
    
    def load_roles(self):
        """Load saved roles from file"""
        try:
            if os.path.exists(self.roles_file):
                with open(self.roles_file, 'r') as f:
                    self.custom_roles = json.load(f)
        except Exception as e:
            print(f"Error loading roles: {e}")
            
    @tasks.loop(minutes=5)  # Run every 5 minutes
    async def save_roles_task(self):
        """Background task to save roles periodically"""
        try:
            with open(self.roles_file, 'w') as f:
                json.dump(self.custom_roles, f)
        except Exception as e:
            print(f"Error saving roles: {e}")
            
    @save_roles_task.before_loop
    async def before_save_roles(self):
        """Wait until the bot is ready before starting the task"""
        await self.bot.wait_until_ready()
            
    async def save_roles(self):
        """Save roles immediately"""
        try:
            with open(self.roles_file, 'w') as f:
                json.dump(self.custom_roles, f)
        except Exception as e:
            print(f"Error saving roles: {e}")
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Assign a role to a new member when they join"""
        guild_id = str(member.guild.id)
        
        # Check if there's a custom role set for this guild
        if guild_id in self.custom_roles:
            role_id = self.custom_roles[guild_id]
            role = member.guild.get_role(int(role_id))
            
            if role:
                try:
                    await member.add_roles(role)
                    
                    # Send welcome message
                    for channel in member.guild.text_channels:
                        if channel.permissions_for(member.guild.me).send_messages:
                            embed = discord.Embed(
                                title="Welcome!",
                                description=f"Welcome {member.mention} to {member.guild.name}!",
                                color=discord.Color.green()
                            )
                            embed.add_field(name="Auto-Role", value=f"You've been given the {role.name} role.")
                            embed.set_thumbnail(url=member.display_avatar.url)
                            
                            await channel.send(embed=embed)
                            break
                except discord.Forbidden:
                    print(f"Failed to assign role to {member} in {member.guild}: Missing permissions")
                except Exception as e:
                    print(f"Error assigning role to {member} in {member.guild}: {e}")
        
        # Check if there's a default role in config
        elif config.DEFAULT_ROLE_ID:
            role = member.guild.get_role(int(config.DEFAULT_ROLE_ID))
            
            if role:
                try:
                    await member.add_roles(role)
                    
                    # Send welcome message
                    for channel in member.guild.text_channels:
                        if channel.permissions_for(member.guild.me).send_messages:
                            embed = discord.Embed(
                                title="Welcome!",
                                description=f"Welcome {member.mention} to {member.guild.name}!",
                                color=discord.Color.green()
                            )
                            embed.add_field(name="Auto-Role", value=f"You've been given the {role.name} role.")
                            embed.set_thumbnail(url=member.display_avatar.url)
                            
                            await channel.send(embed=embed)
                            break
                except discord.Forbidden:
                    print(f"Failed to assign default role to {member} in {member.guild}: Missing permissions")
                except Exception as e:
                    print(f"Error assigning default role to {member} in {member.guild}: {e}")
    
    @app_commands.command(name="setautorole", description="Set a role to be automatically assigned to new members")
    @app_commands.describe(role="The role to automatically assign to new members")
    @app_commands.checks.has_permissions(administrator=True)
    async def setautorole(self, interaction: app_commands.Interaction, role: discord.Role):
        """Set the auto-role for this server"""
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message("I cannot assign a role that is higher than or equal to my highest role.", ephemeral=True)
            return
            
        guild_id = str(interaction.guild.id)
        self.custom_roles[guild_id] = str(role.id)
        await self.save_roles()  # Save immediately when a role is set
        
        await interaction.response.send_message(f"Auto-role has been set to {role.mention}. New members will receive this role when they join.")
    
    @app_commands.command(name="removeautorole", description="Remove the auto-role for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def removeautorole(self, interaction: app_commands.Interaction):
        """Remove the auto-role for this server"""
        guild_id = str(interaction.guild.id)
        
        if guild_id in self.custom_roles:
            del self.custom_roles[guild_id]
            await self.save_roles()  # Save immediately when a role is removed
            await interaction.response.send_message("Auto-role has been removed. New members will no longer receive an automatic role.")
        else:
            await interaction.response.send_message("No auto-role is set for this server.", ephemeral=True)
    
    @app_commands.command(name="getautorole", description="Show the current auto-role for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def getautorole(self, interaction: app_commands.Interaction):
        """Get the current auto-role for this server"""
        guild_id = str(interaction.guild.id)
        
        if guild_id in self.custom_roles:
            role_id = self.custom_roles[guild_id]
            role = interaction.guild.get_role(int(role_id))
            
            if role:
                await interaction.response.send_message(f"The current auto-role is {role.mention}.")
            else:
                await interaction.response.send_message("The auto-role is set but the role no longer exists. Please set a new auto-role.", ephemeral=True)
                del self.custom_roles[guild_id]
        elif config.DEFAULT_ROLE_ID:
            role = interaction.guild.get_role(int(config.DEFAULT_ROLE_ID))
            
            if role:
                await interaction.response.send_message(f"Using default auto-role from config: {role.mention}.")
            else:
                await interaction.response.send_message("The default auto-role from config is set but the role doesn't exist in this server.", ephemeral=True)
        else:
            await interaction.response.send_message("No auto-role is set for this server.", ephemeral=True)
    
    @app_commands.command(name="roleall", description="Apply a role to all current members")
    @app_commands.describe(role="The role to apply to all members")
    @app_commands.checks.has_permissions(administrator=True)
    async def roleall(self, interaction: app_commands.Interaction, role: discord.Role):
        """Assign a role to all members in the server"""
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message("I cannot assign a role that is higher than or equal to my highest role.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        success_count = 0
        fail_count = 0
        
        for member in interaction.guild.members:
            if not member.bot and role not in member.roles:
                try:
                    await member.add_roles(role)
                    success_count += 1
                except:
                    fail_count += 1
        
        await interaction.followup.send(f"Role assignment complete. Successfully assigned to {success_count} members. Failed for {fail_count} members.")

    async def handle_status(self, request):
        """Handle status check requests"""
        return web.Response(text=json.dumps({
            "status": "online",
            "guilds_with_autorole": len(self.custom_roles),
            "bot_latency": round(self.bot.latency * 1000, 2)
        }), content_type='application/json')

    @tasks.loop()
    async def web_server_task(self):
        """Background task to run the web server"""
        app = web.Application()
        app.router.add_get('/status', self.handle_status)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        while True:
            await asyncio.sleep(3600)  # Keep the server running
    
    @web_server_task.before_loop
    async def before_web_server(self):
        """Wait until the bot is ready before starting the web server"""
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(AutoRole(bot))
