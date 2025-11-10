"""
Database utility module for MongoDB operations.
Handles connection management and provides common database operations.
"""
import motor.motor_asyncio
import logging
from typing import Optional, Dict, Any, List
import config

logger = logging.getLogger("bot")

class Database:
    """MongoDB database handler using motor for async operations."""
    
    def __init__(self):
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db = None
        self._connected = False
        
    async def connect(self):
        """Initialize MongoDB connection."""
        if not config.MONGODB_URI:
            logger.warning("MongoDB URI not configured. Using JSON file fallback.")
            return False
            
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                config.MONGODB_URI,
                serverSelectionTimeoutMS=5000
            )
            # Test connection
            await self.client.admin.command('ping')
            self.db = self.client.get_database()
            self._connected = True
            logger.info("Successfully connected to MongoDB")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self._connected = False
            return False
    
    async def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("MongoDB connection closed")
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connected
    
    def get_collection(self, collection_name: str):
        """Get a collection from the database."""
        if not self.db:
            raise RuntimeError("Database not connected")
        return self.db[collection_name]
    
    async def find_one(self, collection: str, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document."""
        if not self.is_connected:
            return None
        coll = self.get_collection(collection)
        return await coll.find_one(filter_dict)
    
    async def find_many(self, collection: str, filter_dict: Dict[str, Any] = None, 
                       limit: int = 0, sort: List[tuple] = None) -> List[Dict[str, Any]]:
        """Find multiple documents."""
        if not self.is_connected:
            return []
        coll = self.get_collection(collection)
        cursor = coll.find(filter_dict or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit > 0:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)
    
    async def insert_one(self, collection: str, document: Dict[str, Any]) -> Optional[str]:
        """Insert a single document."""
        if not self.is_connected:
            return None
        coll = self.get_collection(collection)
        result = await coll.insert_one(document)
        return str(result.inserted_id)
    
    async def update_one(self, collection: str, filter_dict: Dict[str, Any], 
                        update_dict: Dict[str, Any], upsert: bool = False) -> bool:
        """Update a single document."""
        if not self.is_connected:
            return False
        coll = self.get_collection(collection)
        result = await coll.update_one(filter_dict, {'$set': update_dict}, upsert=upsert)
        return result.modified_count > 0 or (upsert and result.upserted_id is not None)
    
    async def delete_one(self, collection: str, filter_dict: Dict[str, Any]) -> bool:
        """Delete a single document."""
        if not self.is_connected:
            return False
        coll = self.get_collection(collection)
        result = await coll.delete_one(filter_dict)
        return result.deleted_count > 0
    
    async def delete_many(self, collection: str, filter_dict: Dict[str, Any]) -> int:
        """Delete multiple documents."""
        if not self.is_connected:
            return 0
        coll = self.get_collection(collection)
        result = await coll.delete_many(filter_dict)
        return result.deleted_count

# Global database instance
db = Database()
