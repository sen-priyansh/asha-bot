import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
PREFIX = "/"  # Changed to slash for traditional commands
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Default to 0 if not set

# MongoDB configuration
MONGODB_URI = os.getenv("MONGODB_URI")
USE_MONGODB = bool(MONGODB_URI)  # Enable MongoDB if URI is provided

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

# Gemini AI settings (loaded from env with fallback defaults)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
TOP_P = float(os.getenv("TOP_P", "0.95"))
TOP_K = int(os.getenv("TOP_K", "40"))

# Bot activity status (loaded from env with fallback defaults)
BOT_ACTIVITY = os.getenv("BOT_ACTIVITY", "Moderating & Chatting")
BOT_STATUS = os.getenv("BOT_STATUS", "online")  # online, idle, dnd, invisible

# AI Chat settings (loaded from env with fallback defaults)
REPLY_TO_PINGS = os.getenv("REPLY_TO_PINGS", "true").lower() in ("true", "1", "yes")
REPLY_TO_REPLIES = os.getenv("REPLY_TO_REPLIES", "true").lower() in ("true", "1", "yes") 