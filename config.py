import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
PREFIX = "/"  # Changed to slash for traditional commands
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Auto-role configuration
DEFAULT_ROLE_ID = os.getenv("DEFAULT_ROLE_ID")

# Server-specific role configurations
# Format: {server_id: role_id}
SERVER_ROLES = {
    # Example: "123456789012345678": "987654321098765432"
}

# Moderation settings
MUTE_ROLE_NAME = "Muted"
DEFAULT_MUTE_DURATION = 3600  # 1 hour in seconds

# Gemini AI settings
GEMINI_MODEL = "gemini-2.0-flash"
MAX_TOKENS = 1024
TEMPERATURE = 0.7
TOP_P = 0.95
TOP_K = 40

# Bot activity status
BOT_ACTIVITY = "Moderating & Chatting"
BOT_STATUS = "online"  # online, idle, dnd, invisible

# AI Chat settings
REPLY_TO_PINGS = True  # Whether to respond to bot mentions
REPLY_TO_REPLIES = True  # Whether to respond to replies to bot messages 