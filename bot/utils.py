"""
Utilities for the Telegram bot
"""
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class MessageFormatter:
    """Message formatter for the bot"""
    
    @staticmethod
    def format_user_profile(user_data: Dict) -> str:
        """Formats user profile"""
        return f"""
👤 **User Profile**

• **Name:** {user_data.get('name', 'N/A')}
• **Age:** {user_data.get('age', 'N/A')} years
• **Weight:** {user_data.get('weight', 'N/A')} kg
• **Gender:** {user_data.get('gender', 'N/A')}
• **Sport:** {user_data.get('sport_preference', 'N/A')}
• **Level:** {user_data.get('fitness_level', 'N/A')}
• **Registered:** {user_data.get('created_at', 'N/A')}
        """
    
    @staticmethod
    def format_sensor_reading(reading: Dict) -> str:
        """Formats sensor reading"""
        timestamp = reading.get('timestamp', 'N/A')
        if isinstance(timestamp, str):
            timestamp = timestamp[:16]  # Only date and time
        
        return f"""
📊 **Reading from {timestamp}**

• **SpO₂:** {reading.get('spo2', 'N/A')}%
• **CO₂:** {reading.get('co2', 'N/A')} ppm
• **Heart Rate:** {reading.get('heart_rate', 'N/A')} bpm
• **Temperature:** {reading.get('temperature', 'N/A')}°C
• **Respiratory Rate:** {reading.get('respiratory_rate', 'N/A')} rpm
        """
    
    @staticmethod
    def format_analysis_summary(analysis: Dict) -> str:
        """Formats analysis summary"""
        return f"""
🔍 **Performance Analysis**

**Summary:**
{analysis.get('analysis_summary', 'Insufficient data')}

**Trends:**
{MessageFormatter._format_list(analysis.get('trends', []), '•')}

**Alerts:**
{MessageFormatter._format_alerts(analysis.get('alerts', []))}

**Recommendations:**
{MessageFormatter._format_recommendations(analysis.get('recommendations', []))}

**Next Steps:**
{analysis.get('next_steps', 'Continue with regular training')}

**Confidence:** {analysis.get('confidence_score', 0) * 100:.0f}%
        """
    
    @staticmethod
    def format_routine(routine: Dict) -> str:
        """Formats exercise routine"""
        text = f"""
🏋️‍♂️ **{routine.get('name', 'Personalized Routine')}**

⏱️ **Duration:** {routine.get('total_duration', 'N/A')} minutes
🎯 **Difficulty:** {routine.get('difficulty', 'N/A')}
📝 **Description:** {routine.get('description', 'No description')}

**Exercises:**
"""
        
        for i, exercise in enumerate(routine.get('exercises', [])[:10], 1):
            text += f"""
{i}. **{exercise.get('name', 'Exercise')}**
   • Duration: {exercise.get('duration', 'N/A')} min
   • Intensity: {exercise.get('intensity', 'N/A')}
   • Description: {exercise.get('description', 'No description')}
"""
        
        return text
    
    @staticmethod
    def _format_list(items: List[str], prefix: str = "•") -> str:
        """Formats list of items"""
        if not items:
            return "No items."
        return "\n".join([f"{prefix} {item}" for item in items])
    
    @staticmethod
    def _format_alerts(alerts: List[str]) -> str:
        """Formats alerts"""
        if not alerts:
            return "✅ No alerts."
        return "\n".join([f"⚠️ {alert}" for alert in alerts])
    
    @staticmethod
    def _format_recommendations(recommendations: List[Dict]) -> str:
        """Formats recommendations"""
        if not recommendations:
            return "No specific recommendations."
        
        text = ""
        for i, rec in enumerate(recommendations[:5], 1):
            priority = rec.get('priority', 'medium')
            emoji = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
            text += f"{emoji} {rec.get('message', 'Recommendation')}\n"
        
        return text

class ValidationHelper:
    """Validation utilities"""
    
    @staticmethod
    def validate_age(age: str) -> tuple[bool, int]:
        """Validates age"""
        try:
            age_int = int(age)
            if 10 <= age_int <= 100:
                return True, age_int
            return False, 0
        except ValueError:
            return False, 0
    
    @staticmethod
    def validate_weight(weight: str) -> tuple[bool, float]:
        """Validates weight"""
        try:
            weight_float = float(weight)
            if 30 <= weight_float <= 200:
                return True, weight_float
            return False, 0.0
        except ValueError:
            return False, 0.0
    
    @staticmethod
    def validate_gender(gender_text: str) -> str:
        """Validates and normalizes gender"""
        gender_lower = gender_text.lower()
        if any(word in gender_lower for word in ['male', 'masculino', 'hombre', 'm']):
            return "male"
        elif any(word in gender_lower for word in ['female', 'femenino', 'mujer', 'f']):
            return "female"
        else:
            return "other"
    
    @staticmethod
    def validate_fitness_level(level_text: str) -> str:
        """Validates and normalizes fitness level"""
        level_lower = level_text.lower()
        if any(word in level_lower for word in ['beginner', 'principiante', 'básico']):
            return "beginner"
        elif any(word in level_lower for word in ['intermediate', 'intermedio', 'medio']):
            return "intermediate"
        else:
            return "advanced"

class ErrorHandler:
    """Error handling"""
    
    @staticmethod
    def get_user_friendly_error(error: Exception) -> str:
        """Converts technical errors to user-friendly messages"""
        error_type = type(error).__name__
        
        if "ConnectionError" in error_type:
            return "❌ Can't connect to server. Try again in a few minutes."
        elif "TimeoutError" in error_type:
            return "⏰ Operation took too long. Try again."
        elif "ValueError" in error_type:
            return "❌ Invalid data. Check information and try again."
        elif "KeyError" in error_type:
            return "❌ Missing information. Use /start to configure your profile."
        else:
            return "❌ An unexpected error occurred. Try again or use /help for more information."

class ConversationState:
    """Conversation state management"""
    
    def __init__(self):
        self.user_states = {}
    
    def set_user_state(self, user_id: int, state: str, data: Dict = None):
        """Sets user state"""
        self.user_states[user_id] = {
            'state': state,
            'data': data or {},
            'timestamp': datetime.utcnow()
        }
    
    def get_user_state(self, user_id: int) -> Optional[Dict]:
        """Gets user state"""
        return self.user_states.get(user_id)
    
    def clear_user_state(self, user_id: int):
        """Clears user state"""
        if user_id in self.user_states:
            del self.user_states[user_id]
    
    def is_state_expired(self, user_id: int, max_minutes: int = 30) -> bool:
        """Checks if state has expired"""
        state = self.get_user_state(user_id)
        if not state:
            return True
        
        time_diff = datetime.utcnow() - state['timestamp']
        return time_diff.total_seconds() > (max_minutes * 60)
