# Discord Bot

A feature-rich Discord bot with moderation, leveling, reaction roles, and utility commands.

## Features

### 1. Moderation Commands
- `/moderation ban` - Ban a member from the server
- `/moderation kick` - Kick a member from the server
- `/moderation mute` - Mute a member for a specified duration
- `/moderation unmute` - Unmute a muted member
- `/moderation warn` - Warn a member
- `/moderation warnings` - View a member's warnings
- `/moderation clearwarnings` - Clear all warnings for a member
- `/moderation purge` - Delete multiple messages from a channel

### 2. Leveling System
- `/level check` - Check your or another user's level
- `/level leaderboard` - View the server's XP leaderboard
- `/level admin setxp` - Set a user's XP (Admin only)
- `/level admin addxp` - Add XP to a user (Admin only)
- `/level role set` - Set a role to be assigned at a specific level
- `/level role remove` - Remove a role from being assigned at a level
- `/level settings xprate` - Configure XP gain settings

### 3. Reaction Roles
- `/reaction create` - Create a reaction role message
- `/reaction add` - Add a reaction role to a message
- `/reaction remove` - Remove a reaction role from a message
- `/reaction list` - List all reaction roles in the server
- `/reaction settings` - Configure reaction role settings
- `/reaction edit` - Edit a reaction role message
- `/reaction verify` - Verify and fix reaction role configurations
- `/reaction rebuild` - Rebuild all reaction role messages
- `/reaction clone` - Clone a reaction role message to another channel
- `/reaction cleanup` - Clean up invalid reaction role entries
- `/reaction export` - Export reaction roles configuration

### 4. Utility Commands
- `/utility ping` - Check the bot's latency
- `/utility botinfo` - Display information about the bot
- `/utility serverinfo` - Display information about the server
- `/utility userinfo` - Display information about a user
- `/utility help` - Display help information

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your bot token:
   ```
   TOKEN=your_bot_token_here
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

## Configuration

### Bot Permissions
The bot requires the following permissions:
- Manage Roles
- Manage Messages
- Ban Members
- Kick Members
- Send Messages
- Embed Links
- Add Reactions
- Read Message History

### Required Intents
- Server Members Intent
- Message Content Intent
- Presence Intent

## Features in Detail

### Moderation System
The moderation system provides comprehensive tools for server management:
- Automatic mute role creation and management
- Warning system with persistent storage
- Configurable mute durations
- Bulk message deletion with user filtering

### Leveling System
The leveling system includes:
- Automatic XP gain from messages
- Configurable XP rates and cooldowns
- Level-based role rewards
- Customizable level-up messages
- Server-wide leaderboard

### Reaction Roles
Advanced reaction role system with:
- Multiple role assignment modes (normal, unique, exclusive)
- Role limits and requirements
- Customizable embeds
- Persistent button views
- Category-based role menus
- Export/import functionality

### Utility Features
Various utility commands for:
- Server information
- User information
- Bot statistics
- Help documentation

## Support

For support, please open an issue in the repository or contact the bot owner.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 