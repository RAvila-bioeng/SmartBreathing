import os
import logging
from typing import Dict, Any
import motor.motor_asyncio
from dotenv import load_dotenv
from telegram.ext import Application

load_dotenv()

logger = logging.getLogger(__name__)

class DBContext:
    client: motor.motor_asyncio.AsyncIOMotorClient = None
    db: motor.motor_asyncio.AsyncIOMotorDatabase = None
    is_connected: bool = False

db = DBContext()

async def connect_to_mongo(application: Application):
    """Connects to MongoDB and updates connection status."""
    mongodb_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "bot_database")
    
    if not mongodb_uri or mongodb_uri == "YOUR_MONGODB_URI":
        logger.warning("MONGODB_URI is not configured or is set to the default placeholder.")
        db.is_connected = False
        return

    try:
        db.client = motor.motor_asyncio.AsyncIOMotorClient(mongodb_uri)
        await db.client.admin.command('ismaster')
        db.db = db.client[db_name]
        db.is_connected = True
        logger.info(f"Successfully connected to MongoDB and using database '{db_name}'.")
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        db.client = None
        db.db = None
        db.is_connected = False

async def close_mongo_connection(application: Application):
    """Closes MongoDB connection."""
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed.")
    db.is_connected = False

async def update_user(user_id: int, user_data: Dict[str, Any]):
    """
    Updates or inserts a user's profile in the database and logs the result.
    """
    if not db.is_connected or not db.db:
        logger.error("Database is not connected. Cannot update user data.")
        return
    
    try:
        users_collection = db.db.users
        result = await users_collection.update_one(
            {'user_id': user_id},
            {'$set': user_data},
            upsert=True
        )
        
        logger.info(
            f"MongoDB update result for user {user_id}: "
            f"Matched: {result.matched_count}, "
            f"Modified: {result.modified_count}, "
            f"Upserted ID: {result.upserted_id}"
        )
        
    except Exception as e:
        logger.error(f"Failed to save user {user_id} data: {e}")

def is_database_connected() -> bool:
    """Returns the current status of the database connection."""
    return db.is_connected
