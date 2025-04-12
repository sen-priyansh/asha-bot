# Discord Bot Project Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [Features](#features)
3. [Setup Instructions](#setup-instructions)
4. [Configuration](#configuration)
5. [Deployment Guide](#deployment-guide)
6. [Command Reference](#command-reference)
7. [Troubleshooting](#troubleshooting)
8. [Maintenance](#maintenance)

## Project Overview

This Discord bot is a feature-rich moderation and utility bot built using Python and the discord.py library. It includes various modules for moderation, leveling, reaction roles, and utility functions.

### Core Components
- `bot.py`: Main bot file handling initialization and core functionality
- `moderation.py`: Moderation commands and functionality
- `leveling.py`: Leveling system with XP tracking and role rewards
- `reactionroles.py`: Reaction role management system
- `utility.py`: Utility commands and helper functions
- `sync_commands.py`: Command synchronization utility

## Features

### 1. Moderation System
- Ban/Kick members
- Mute/Unmute functionality
- Warning system
- Message purging
- Role management

### 2. Leveling System
- XP tracking
- Level progression
- Role rewards
- Level cards
- Leaderboard
- Custom level-up messages

### 3. Reaction Roles
- Message-based role assignment
- Emoji-based reactions
- Role management
- Persistent role storage

### 4. Utility Commands
- Server information
- User information
- Bot statistics
- Help system
- Ping command

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git (optional, for version control)
- Discord Developer Account

### Installation Steps

1. Clone the repository (if using Git):
```bash
git clone <repository-url>
cd discord-bot
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file:
```env
DISCORD_TOKEN=your_bot_token_here
```

5. Configure the bot:
- Copy `.env.example` to `.env`
- Fill in your bot token
- Adjust other settings as needed

## Configuration

### Environment Variables
- `DISCORD_TOKEN`: Your bot's token from Discord Developer Portal
- Additional variables can be added as needed

### Bot Settings
- Prefix: Configurable in `bot.py`
- Default permissions: Set in Discord Developer Portal
- Command cooldowns: Configured in respective cog files

## Deployment Guide

### Local Deployment
1. Ensure all prerequisites are installed
2. Configure the `.env` file
3. Run the bot:
```bash
python bot.py
```

### Server Deployment
1. Set up a server (VPS, cloud instance, etc.)
2. Install Python and required dependencies
3. Clone the repository
4. Configure the `.env` file
5. Use a process manager (like PM2 or systemd) to keep the bot running

### PM2 Deployment Example
```bash
# Install PM2
npm install -g pm2

# Start the bot
pm2 start bot.py --interpreter python

# Save the process list
pm2 save

# Set up auto-start
pm2 startup
```

### systemd Deployment Example
Create a service file at `/etc/systemd/system/discord-bot.service`:
```ini
[Unit]
Description=Discord Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/bot
ExecStart=/path/to/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
```

## Command Reference

### Moderation Commands
- `/ban`: Ban a member
- `/kick`: Kick a member
- `/mute`: Mute a member
- `/unmute`: Unmute a member
- `/warn`: Warn a member
- `/warnings`: View member warnings
- `/purge`: Delete messages

### Leveling Commands
- `/level check`: Check your or another user's level
- `/level leaderboard`: View server leaderboard
- `/level setrole`: Set a role reward for a level
- `/level setxp`: Set a user's XP
- `/level addxp`: Add XP to a user

### Reaction Role Commands
- `/reactionrole add`: Add a reaction role
- `/reactionrole remove`: Remove a reaction role
- `/reactionrole list`: List all reaction roles

### Utility Commands
- `/help`: Show help information
- `/ping`: Check bot latency
- `/botinfo`: Show bot information
- `/serverinfo`: Show server information
- `/userinfo`: Show user information

## Troubleshooting

### Common Issues

1. **Bot Not Starting**
   - Check token validity
   - Verify Python version
   - Check for missing dependencies

2. **Commands Not Working**
   - Verify bot permissions
   - Check command registration
   - Ensure proper role hierarchy

3. **Database Issues**
   - Check file permissions
   - Verify JSON file integrity
   - Ensure proper data structure

### Error Logging
- Logs are stored in the `logs` directory
- Enable debug mode for detailed logging
- Check system logs for process-related issues

## Maintenance

### Regular Tasks
1. Update dependencies:
```bash
pip install -r requirements.txt --upgrade
```

2. Backup data files:
- `leveling.json`
- `level_roles.json`
- `autoroles.json`

3. Monitor logs for errors

### Security Considerations
- Keep bot token secure
- Regular dependency updates
- Monitor for suspicious activity
- Implement rate limiting
- Use proper error handling

### Performance Optimization
- Implement caching where appropriate
- Optimize database queries
- Use proper cooldowns
- Monitor resource usage

## Support

For issues and support:
1. Check the documentation
2. Review error logs
3. Contact the development team
4. Check GitHub issues (if applicable)

## License

[Specify your license here]

---

This documentation is a living document and should be updated as the project evolves. Last updated: [Current Date] 