"""
Storage abstraction layer for leveling data.
Supports both MongoDB and JSON file storage with automatic fallback.
"""
import json
import os
import logging
from typing import Dict, Optional, Any
import config

logger = logging.getLogger("bot")

class LevelingStorage:
    """Hybrid storage for leveling data - MongoDB or JSON fallback."""
    
    def __init__(self):
        self.use_db = config.USE_MONGODB
        self.json_file = 'leveling.json'
        self.settings_file = 'leveling_settings.json'
        self.roles_file = 'level_roles.json'
        self.messages_file = 'level_messages.json'
        self.backgrounds_file = 'level_backgrounds.json'
        
        # In-memory cache
        self.data = {}
        self.settings = {}
        self.roles = {}
        self.messages = {}
        self.backgrounds = {}
        
        if not self.use_db:
            self._load_json()
    
    def _load_json(self):
        """Load data from JSON files."""
        try:
            if os.path.exists(self.json_file):
                with open(self.json_file, 'r') as f:
                    self.data = json.load(f)
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
            if os.path.exists(self.roles_file):
                with open(self.roles_file, 'r') as f:
                    self.roles = json.load(f)
            if os.path.exists(self.messages_file):
                with open(self.messages_file, 'r') as f:
                    self.messages = json.load(f)
            if os.path.exists(self.backgrounds_file):
                with open(self.backgrounds_file, 'r') as f:
                    self.backgrounds = json.load(f)
        except Exception as e:
            logger.error(f"Error loading leveling JSON data: {e}")
    
    async def save_json(self):
        """Save data to JSON files."""
        if self.use_db:
            return  # Don't save to JSON if using MongoDB
        try:
            with open(self.json_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            with open(self.roles_file, 'w') as f:
                json.dump(self.roles, f, indent=2)
            with open(self.messages_file, 'w') as f:
                json.dump(self.messages, f, indent=2)
            with open(self.backgrounds_file, 'w') as f:
                json.dump(self.backgrounds, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving leveling JSON data: {e}")
    
    async def get_user_data(self, guild_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user leveling data."""
        if self.use_db:
            from database import db
            return await db.find_one('leveling', {'guild_id': guild_id, 'user_id': user_id})
        else:
            return self.data.get(guild_id, {}).get(user_id)
    
    async def set_user_data(self, guild_id: str, user_id: str, data: Dict[str, Any]):
        """Set user leveling data."""
        if self.use_db:
            from database import db
            data['guild_id'] = guild_id
            data['user_id'] = user_id
            await db.update_one('leveling', {'guild_id': guild_id, 'user_id': user_id}, data, upsert=True)
        else:
            if guild_id not in self.data:
                self.data[guild_id] = {}
            self.data[guild_id][user_id] = data
    
    async def get_guild_leaderboard(self, guild_id: str, limit: int = 10):
        """Get guild leaderboard."""
        if self.use_db:
            from database import db
            return await db.find_many('leveling', {'guild_id': guild_id}, limit=limit, 
                                     sort=[('xp', -1)])
        else:
            guild_data = self.data.get(guild_id, {})
            sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)
            return [{'user_id': uid, **data} for uid, data in sorted_users[:limit]]
    
    async def delete_user_data(self, guild_id: str, user_id: str):
        """Delete user data."""
        if self.use_db:
            from database import db
            await db.delete_one('leveling', {'guild_id': guild_id, 'user_id': user_id})
        else:
            if guild_id in self.data and user_id in self.data[guild_id]:
                del self.data[guild_id][user_id]
    
    async def get_settings(self, guild_id: str) -> Dict[str, Any]:
        """Get guild settings."""
        if self.use_db:
            from database import db
            result = await db.find_one('leveling_settings', {'guild_id': guild_id})
            return result or {}
        else:
            return self.settings.get(guild_id, {})
    
    async def set_settings(self, guild_id: str, settings: Dict[str, Any]):
        """Set guild settings."""
        if self.use_db:
            from database import db
            settings['guild_id'] = guild_id
            await db.update_one('leveling_settings', {'guild_id': guild_id}, settings, upsert=True)
        else:
            self.settings[guild_id] = settings
    
    async def get_roles(self, guild_id: str) -> Dict[str, Any]:
        """Get level roles."""
        if self.use_db:
            from database import db
            result = await db.find_one('level_roles', {'guild_id': guild_id})
            return result.get('roles', {}) if result else {}
        else:
            return self.roles.get(guild_id, {})
    
    async def set_roles(self, guild_id: str, roles: Dict[str, Any]):
        """Set level roles."""
        if self.use_db:
            from database import db
            await db.update_one('level_roles', {'guild_id': guild_id}, 
                              {'guild_id': guild_id, 'roles': roles}, upsert=True)
        else:
            self.roles[guild_id] = roles
    
    async def get_messages(self, guild_id: str) -> Dict[str, Any]:
        """Get level messages."""
        if self.use_db:
            from database import db
            result = await db.find_one('level_messages', {'guild_id': guild_id})
            return result.get('messages', {}) if result else {}
        else:
            return self.messages.get(guild_id, {})
    
    async def set_messages(self, guild_id: str, messages: Dict[str, Any]):
        """Set level messages."""
        if self.use_db:
            from database import db
            await db.update_one('level_messages', {'guild_id': guild_id}, 
                              {'guild_id': guild_id, 'messages': messages}, upsert=True)
        else:
            self.messages[guild_id] = messages
    
    async def get_background(self, user_id: str) -> Optional[str]:
        """Get user background URL."""
        if self.use_db:
            from database import db
            result = await db.find_one('level_backgrounds', {'user_id': user_id})
            return result.get('url') if result else None
        else:
            return self.backgrounds.get(user_id)
    
    async def set_background(self, user_id: str, url: str):
        """Set user background URL."""
        if self.use_db:
            from database import db
            await db.update_one('level_backgrounds', {'user_id': user_id}, 
                              {'user_id': user_id, 'url': url}, upsert=True)
        else:
            self.backgrounds[user_id] = url
    
    async def delete_background(self, user_id: str):
        """Delete user background."""
        if self.use_db:
            from database import db
            await db.delete_one('level_backgrounds', {'user_id': user_id})
        else:
            if user_id in self.backgrounds:
                del self.backgrounds[user_id]
