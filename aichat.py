import discord
from discord.ext import commands
from discord import app_commands
from gemini_ai import GeminiAI
import config

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.gemini = GeminiAI()
        self.chat_channels = {}  # {channel_id: is_active}
    
    @app_commands.command(name="chat", description="Chat with the AI using Gemini API")
    async def chat(self, interaction: discord.Interaction, message: str):
        """Chat with the AI using Gemini API"""
        await interaction.response.defer()
        
        try:
            # Get response from Gemini
            response = await self.gemini.get_response(str(interaction.user.id), message)
            
            # Create embed
            embed = discord.Embed(
                title="AI Response",
                description=response,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")
    
    @app_commands.command(name="resetchat", description="Reset your chat history with the AI")
    async def resetchat(self, interaction: discord.Interaction):
        """Reset your chat history with the AI"""
        success = self.gemini.reset_chat(str(interaction.user.id))
        
        if success:
            await interaction.response.send_message("Your chat history has been reset.")
        else:
            await interaction.response.send_message("You don't have any chat history to reset.")
    
    @app_commands.command(name="toggleaichannel", description="Toggle AI chat for the current channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def toggleaichannel(self, interaction: discord.Interaction):
        """Toggle AI chat for the current channel"""
        channel_id = str(interaction.channel.id)
        
        if channel_id in self.chat_channels and self.chat_channels[channel_id]:
            self.chat_channels[channel_id] = False
            await interaction.response.send_message("AI chat has been disabled for this channel.")
        else:
            self.chat_channels[channel_id] = True
            await interaction.response.send_message("AI chat has been enabled for this channel. I will respond to all messages in this channel.")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages that should trigger AI responses"""
        # Ignore messages from bots (including self)
        if message.author.bot:
            return
            
        should_respond = False
        message_content = message.content
        
        # Check if the message is in an AI chat channel
        channel_id = str(message.channel.id)
        if channel_id in self.chat_channels and self.chat_channels[channel_id]:
            should_respond = True
        
        # Check if the bot was mentioned
        elif config.REPLY_TO_PINGS and self.bot.user in message.mentions:
            should_respond = True
            # Remove the bot mention from the message
            message_content = message_content.replace(f'<@{self.bot.user.id}>', '').strip()
            message_content = message_content.replace(f'<@!{self.bot.user.id}>', '').strip()
            
            # If it's just a mention with no content, let the bot's on_message handle it
            if not message_content:
                return
        
        # Check if the message is a reply to the bot
        elif config.REPLY_TO_REPLIES and message.reference:
            referenced_message = await message.channel.fetch_message(message.reference.message_id)
            if referenced_message.author.id == self.bot.user.id:
                should_respond = True
        
        if should_respond and message_content:
            # Don't respond to commands
            ctx = await self.bot.get_context(message)
            if ctx.valid:
                return
                
            async with message.channel.typing():
                try:
                    # Get response from Gemini
                    response = await self.gemini.get_response(str(message.author.id), message_content)
                    
                    # Create embed
                    embed = discord.Embed(
                        description=response,
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text=f"Responding to {message.author}")
                    
                    # Send the response
                    await message.reply(embed=embed)
                except Exception as e:
                    await message.channel.send(f"Error: {str(e)}")

async def setup(bot):
    # Sync slash commands
    await bot.add_cog(AIChat(bot))
    await bot.tree.sync() 