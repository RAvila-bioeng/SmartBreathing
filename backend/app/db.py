import os
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database


load_dotenv()


_mongo_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://root:example@localhost:27017")
    _mongo_client = MongoClient(mongo_uri)
    return _mongo_client


def get_database() -> Database:
    db_name = os.getenv("MONGODB_DB", "SmartBreathing")
    return get_mongo_client()[db_name]


