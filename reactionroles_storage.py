"""
Storage abstraction layer for reaction roles data.
Supports both MongoDB and JSON file storage with automatic fallback.
"""
import json
import os
import logging
from typing import Dict, Optional, Any
import config

logger = logging.getLogger("bot")

class ReactionRolesStorage:
    """Hybrid storage for reaction roles - MongoDB or JSON fallback."""
    
    def __init__(self):
        self.use_db = config.USE_MONGODB
        self.json_file = 'reaction_roles.json'
        self.data = {}  # guild_id -> message_id -> emoji -> role_data
        
        if not self.use_db:
            self._load_json()
    
    def _load_json(self):
        """Load data from JSON file."""
        try:
            if os.path.exists(self.json_file):
                with open(self.json_file, 'r') as f:
                    self.data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading reaction roles JSON data: {e}")
    
    async def save_json(self):
        """Save data to JSON file."""
        if self.use_db:
            return  # Don't save to JSON if using MongoDB
        try:
            with open(self.json_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reaction roles JSON data: {e}")
    
    async def get_guild_data(self, guild_id: str) -> Dict[str, Any]:
        """Get all reaction role data for a guild."""
        if self.use_db:
            from database import db
            results = await db.find_many('reaction_roles', {'guild_id': guild_id})
            # Reconstruct the nested structure
            guild_data = {}
            for doc in results:
                message_id = doc.get('message_id')
                if message_id:
                    guild_data[message_id] = doc.get('data', {})
            return guild_data
        else:
            return self.data.get(guild_id, {})
    
    async def set_guild_data(self, guild_id: str, guild_data: Dict[str, Any]):
        """Set all reaction role data for a guild."""
        if self.use_db:
            from database import db
            # Delete existing and insert new
            await db.delete_many('reaction_roles', {'guild_id': guild_id})
            for message_id, message_data in guild_data.items():
                await db.insert_one('reaction_roles', {
                    'guild_id': guild_id,
                    'message_id': message_id,
                    'data': message_data
                })
        else:
            self.data[guild_id] = guild_data
    
    async def get_message_data(self, guild_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        """Get reaction role data for a specific message."""
        if self.use_db:
            from database import db
            result = await db.find_one('reaction_roles', 
                                      {'guild_id': guild_id, 'message_id': message_id})
            return result.get('data') if result else None
        else:
            return self.data.get(guild_id, {}).get(message_id)
    
    async def set_message_data(self, guild_id: str, message_id: str, message_data: Dict[str, Any]):
        """Set reaction role data for a specific message."""
        if self.use_db:
            from database import db
            await db.update_one('reaction_roles', 
                              {'guild_id': guild_id, 'message_id': message_id},
                              {'guild_id': guild_id, 'message_id': message_id, 'data': message_data},
                              upsert=True)
        else:
            if guild_id not in self.data:
                self.data[guild_id] = {}
            self.data[guild_id][message_id] = message_data
    
    async def delete_message_data(self, guild_id: str, message_id: str):
        """Delete reaction role data for a specific message."""
        if self.use_db:
            from database import db
            await db.delete_one('reaction_roles', 
                              {'guild_id': guild_id, 'message_id': message_id})
        else:
            if guild_id in self.data and message_id in self.data[guild_id]:
                del self.data[guild_id][message_id]
    
    async def delete_guild_data(self, guild_id: str):
        """Delete all reaction role data for a guild."""
        if self.use_db:
            from database import db
            await db.delete_many('reaction_roles', {'guild_id': guild_id})
        else:
            if guild_id in self.data:
                del self.data[guild_id]
