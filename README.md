# Discord Moderation Bot with Gemini AI

A Discord bot that provides moderation capabilities, auto-role assignment, and AI-powered chat using Google's Gemini API.

## Features

- **Moderation Commands**: Ban, kick, mute, and warn users
- **Auto-Role Assignment**: Automatically assign roles to new members
- **AI Chat**: Chat with the bot using Google's Gemini API
- **Utility Commands**: Help, ping, and other utility commands

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory with the following variables:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   GEMINI_API_KEY=your_gemini_api_key
   ```
4. Run the bot:
   ```
   python bot.py
   ```

## Commands

- `!help` - Display help information
- `!ping` - Check if the bot is online
- `!ban @user [reason]` - Ban a user
- `!kick @user [reason]` - Kick a user
- `!mute @user [duration] [reason]` - Mute a user
- `!warn @user [reason]` - Warn a user
- `!chat [message]` - Chat with the AI

## Auto-Role Configuration

Edit the `config.py` file to set up auto-roles for your server.

## License

MIT 