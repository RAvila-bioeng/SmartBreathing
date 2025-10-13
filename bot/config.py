"""
SmartBreathing Telegram bot configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

class BotConfig:
    """Bot configuration"""
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # API Backend
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Validation
    @classmethod
    def validate(cls) -> bool:
        """Validates that all required configurations are present"""
        required_vars = [
            ("TELEGRAM_BOT_TOKEN", cls.TELEGRAM_BOT_TOKEN),
        ]
        
        missing_vars = []
        for var_name, var_value in required_vars:
            if not var_value:
                missing_vars.append(var_name)
        
        if missing_vars:
            raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")
        
        return True
    
    @classmethod
    def get_api_url(cls, endpoint: str = "") -> str:
        """Builds complete API URL"""
        base_url = cls.API_BASE_URL.rstrip('/')
        endpoint = endpoint.lstrip('/')
        return f"{base_url}/{endpoint}" if endpoint else base_url
