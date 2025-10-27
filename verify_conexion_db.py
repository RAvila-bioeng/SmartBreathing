import os
import asyncio
import logging
import motor.motor_asyncio
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def check_mongo_connection():
    """Checks the connection to MongoDB and prints the status."""
    load_dotenv(dotenv_path='.env')
    mongodb_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "bot_database")

    if not mongodb_uri or mongodb_uri == "YOUR_MONGODB_URI":
        logger.error("❌ MONGODB_URI is not configured. Please check your bot/.env file.")
        return

    client = None
    try:
        logger.info(f"Attempting to connect to MongoDB at {mongodb_uri}...")
        client = motor.motor_asyncio.AsyncIOMotorClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        
        # The ismaster command is cheap and does not require auth.
        await client.admin.command('ismaster')
        
        db = client[db_name]
        logger.info(f"✅ Successfully connected to MongoDB.")
        logger.info(f"✅ Using database: '{db_name}'")
        
        # Optional: Check collections
        collections = await db.list_collection_names()
        if collections:
            logger.info(f"✅ Found collections: {', '.join(collections)}")
        else:
            logger.warning("🟡 No collections found in the database.")

    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
    finally:
        if client:
            client.close()
            logger.info("Connection closed.")

if __name__ == "__main__":
    asyncio.run(check_mongo_connection())
