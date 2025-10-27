import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
import aiohttp
import logging
from database import connect_to_mongo, close_mongo_connection, find_user_by_credentials, is_database_connected

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# Conversation states for authentication
AUTH_ASK_NAME, AUTH_ASK_LAST_NAME, AUTH_ASK_PASSWORD = range(3)
# Other states

MAIN_MENU, VIEWING_DATA, CREATING_ROUTINE, CHAT_MODE = range(3, 7)

class SmartBreathingBot:
    def __init__(self):
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.user_sessions = {}  # Store user sessions
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Starts the authentication conversation."""
        await update.message.reply_text(
            "Welcome to SmartBreathing! Please enter your name to log in."
        )
        return AUTH_ASK_NAME

    async def auth_ask_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Saves the name and asks for the last name."""
        name = update.message.text
        if not name[0].isupper():
            await update.message.reply_text("The name must start with a capital letter. Please try again.")
            return AUTH_ASK_NAME

        context.user_data['name'] = name
        await update.message.reply_text("Great. Now, what is your last name?")
        return AUTH_ASK_LAST_NAME

    async def auth_ask_last_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Saves the last name and asks for the password."""
        last_name = update.message.text
        if not last_name[0].isupper():
            await update.message.reply_text("The last name must start with a capital letter. Please try again.")
            return AUTH_ASK_LAST_NAME

        context.user_data['last_name'] = last_name
        await update.message.reply_text("Got it. Please enter your password.")
        return AUTH_ASK_PASSWORD

    async def auth_ask_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Saves the password, authenticates the user, and ends the conversation."""
        password = update.message.text
        if not (password.isdigit() and len(password) == 4):
            await update.message.reply_text("The password must be a four-digit number. Please try again.")
            return AUTH_ASK_PASSWORD

        name = context.user_data.get('name')
        last_name = context.user_data.get('last_name')

        user = await find_user_by_credentials(name, last_name, password)

        if user:
            context.user_data['user'] = user
            await update.message.reply_text(
                "Authentication successful! Welcome back."
            )
            await self._show_main_menu(update, context, user)
            return MAIN_MENU
        else:
            await update.message.reply_text(
                "Authentication failed. Please check your credentials and start again with /start."
            )
            context.user_data.clear()
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels the current conversation."""
        await update.message.reply_text("Registration has been canceled.")
        context.user_data.clear()
        return ConversationHandler.END

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Help command - Shows help"""
        help_text = """
🤖 **SmartBreathing - Your AI Personal Trainer**

**Main commands:**
/start - Login or registration
/help - Show this help
/menu - Go to main menu
/status - View current status
/data - View my training data
/routine - Create new routine
/analysis - Performance analysis
/register - Register your data

**Features:**
• 📊 Real-time physiological monitoring
• 🏃‍♂️ AI-powered personalized routines
• 💬 Natural conversation with your trainer
• 📈 Performance and progress analysis
• ⚠️ Automatic safety alerts

**Need help?** Just write your question and I'll respond in a personalized way.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Menu command - Go to main menu"""
        user_data = context.user_data.get('user')
        
        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return ConversationHandler.END
        
        await self._show_main_menu(update, context, user_data)
        return MAIN_MENU
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Status command - View current status"""
        user_data = context.user_data.get('user')

        if not user_data:
            await update.message.reply_text("You are not logged in. Please use /start to log in.")
            return
        
        # Get recent analysis
        analysis = await self._get_user_analysis(str(user_data["_id"]))
        
        status_text = f"""
📊 **Your Current Status**

**Profile:**
• Name: {user_data.get('name', 'N/A')}
• Age: {user_data.get('age', 'N/A')} years
• Weight: {user_data.get('weight', 'N/A')} kg
• Sport: {user_data.get('sport_preference', 'N/A')}
• Level: {user_data.get('fitness_level', 'N/A')}

**Recent Analysis:**
{analysis.get('analysis_summary', 'No recent data')}

**Recommendations:**
{self._format_recommendations(analysis.get('recommendations', []))}
        """
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def data_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Data command - View training data"""
        user_data = context.user_data.get('user')

        if not user_data:
            await update.message.reply_text("You are not logged in. Please use /start to log in.")
            return
        
        # Get recent readings
        readings = await self._get_user_readings(str(user_data["_id"]))
        
        if not readings:
            await update.message.reply_text("📊 No recent training data available.")
            return
        
        # Create data chart
        data_text = self._format_sensor_data(readings[:10])  # Last 10 readings
        
        keyboard = [
            [InlineKeyboardButton("📈 View Full Analysis", callback_data="full_analysis")],
            [InlineKeyboardButton("📊 Export Data", callback_data="export_data")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📊 **Your Training Data**\n\n{data_text}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def routine_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Routine command - Create new routine"""
        user_data = context.user_data.get('user')

        if not user_data:
            await update.message.reply_text("You are not logged in. Please use /start to log in.")
            return
        
        keyboard = [
            [InlineKeyboardButton("🏃‍♂️ Cardio", callback_data="routine_cardio")],
            [InlineKeyboardButton("💪 Strength", callback_data="routine_strength")],
            [InlineKeyboardButton("🧘‍♂️ Breathing", callback_data="routine_breathing")],
            [InlineKeyboardButton("🎯 Custom", callback_data="routine_custom")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏋️‍♂️ **Create New Routine**\n\n"
            "What type of routine would you like to create?",
            reply_markup=reply_markup
        )
    
    async def analysis_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Analysis command - Performance analysis"""
        user_data = context.user_data.get('user')

        if not user_data:
            await update.message.reply_text("You are not logged in. Please use /start to log in.")
            return
        
        await update.message.reply_text("🔍 Analyzing your data... This may take a few seconds.")
        
        # Get analysis with AI
        analysis = await self._get_user_analysis(str(user_data["_id"]))
        
        analysis_text = f"""
🔍 **Performance Analysis with AI**

**Summary:**
{analysis.get('analysis_summary', 'Insufficient data for analysis')}

**Trends:**
{self._format_trends(analysis.get('trends', []))}

**Alerts:**
{self._format_alerts(analysis.get('alerts', []))}

**Recommendations:**
{self._format_recommendations(analysis.get('recommendations', []))}

**Next Steps:**
{analysis.get('next_steps', 'Continue with regular training')}

**Analysis Confidence:** {analysis.get('confidence_score', 0) * 100:.0f}%
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Analysis", callback_data="refresh_analysis")],
            [InlineKeyboardButton("📊 View Detailed Data", callback_data="detailed_data")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            analysis_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles general text messages with AI"""
        user_data = context.user_data.get('user')
        
        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        message_text = update.message.text
        
        # Show processing message
        processing_msg = await update.message.reply_text("🤔 Processing your query...")
        
        try:
            # Generate AI response
            response = await self._generate_ai_response(message_text, user_data)
            
            # Delete processing message
            await processing_msg.delete()
            
            # Send response
            await update.message.reply_text(response, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            await processing_msg.edit_text(
                "❌ Sorry, there was an error processing your query. "
                "Try again or use /menu to see available options."
            )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_data = context.user_data.get('user')
        
        if not user_data:
            await query.edit_message_text("You are not logged in. Please use /start to log in.")
            return
            
        if data == "main_menu":
            await self._show_main_menu(update, context, user_data)
        
        elif data == "full_analysis":
            await self.analysis_command(update, context)
        
        elif data.startswith("routine_"):
            routine_type = data.split("_")[1]
            await self._create_routine_by_type(update, context, routine_type)
        
        elif data == "refresh_analysis":
            await self.analysis_command(update, context)
        
        elif data == "detailed_data":
            await self.data_command(update, context)
    
    async def _show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: Dict) -> None:
        """Shows main menu"""
        keyboard = [
            [InlineKeyboardButton("📊 My Status", callback_data="status")],
            [InlineKeyboardButton("📈 My Data", callback_data="data")],
            [InlineKeyboardButton("🏋️‍♂️ Routines", callback_data="routines")],
            [InlineKeyboardButton("🔍 AI Analysis", callback_data="analysis")],
            [InlineKeyboardButton("💬 Chat with AI", callback_data="chat")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"""
🧘‍♂️ **Hello {user_data.get('name', 'User')}!**

I'm your intelligent personal trainer. How can I help you today?

**Your profile:**
• Sport: {user_data.get('sport_preference', 'N/A')}
• Level: {user_data.get('fitness_level', 'N/A')}
• Last update: {user_data.get('updated_at', 'N/A')}
        """
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                welcome_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                welcome_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    
    async def _create_routine_by_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE, routine_type: str) -> None:
        """Creates routine by selected type"""
        user_data = context.user_data.get('user')
        
        if not user_data:
            await update.callback_query.edit_message_text("You are not logged in. Please use /start to log in.")
            return
        
        # Map routine types
        routine_goals = {
            "cardio": ["cardiovascular", "endurance"],
            "strength": ["muscle_gain", "strength"],
            "breathing": ["breathing", "relaxation"],
            "custom": ["general_fitness"]
        }
        
        goals = routine_goals.get(routine_type, ["general_fitness"])
        
        await update.callback_query.edit_message_text("🤖 Generating personalized routine with AI...")
        
        try:
            # Generate routine with AI
            routine = await self._generate_ai_routine(str(user_data["_id"]), goals)
            
            if routine:
                routine_text = self._format_routine(routine)
                
                keyboard = [
                    [InlineKeyboardButton("✅ Accept Routine", callback_data=f"accept_routine_{routine.get('id', '')}")],
                    [InlineKeyboardButton("🔄 Generate Another", callback_data="routine_menu")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.callback_query.edit_message_text(
                    routine_text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await update.callback_query.edit_message_text("❌ Error generating routine. Try again.")
                
        except Exception as e:
            logger.error(f"Error creating routine: {e}")
            await update.callback_query.edit_message_text("❌ Error generating routine. Try again.")
    
    # API methods
    async def _get_user_analysis(self, user_id: str) -> Dict:
        """Gets user analysis"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base_url}/api/analysis/{user_id}") as response:
                    if response.status == 200:
                        return await response.json()
                    return {"analysis_summary": "No data available"}
        except Exception as e:
            logger.error(f"Error getting analysis: {e}")
            return {"analysis_summary": "Error getting analysis"}
    
    async def _get_user_readings(self, user_id: str) -> List[Dict]:
        """Gets user readings"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base_url}/api/sensors/readings/{user_id}") as response:
                    if response.status == 200:
                        return await response.json()
                    return []
        except Exception as e:
            logger.error(f"Error getting readings: {e}")
            return []
    
    async def _generate_ai_routine(self, user_id: str, goals: List[str]) -> Optional[Dict]:
        """Generates routine with AI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base_url}/api/ai/generate-routine/{user_id}",
                    json=goals
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            logger.error(f"Error generating routine: {e}")
            return None
    
    async def _generate_ai_response(self, message: str, user_data: Dict) -> str:
        """Generates AI response using ChatGPT"""
        try:
            # Create contextual prompt
            prompt = f"""
            You are an expert and friendly personal trainer. Respond to the user's query in a personalized and helpful way.
            
            USER INFORMATION:
            - Name: {user_data.get('name', 'User')}
            - Age: {user_data.get('age', 'N/A')} years
            - Weight: {user_data.get('weight', 'N/A')} kg
            - Sport: {user_data.get('sport_preference', 'N/A')}
            - Level: {user_data.get('fitness_level', 'N/A')}
            
            USER QUERY: {message}
            
            Respond in a way that is:
            - Friendly and motivating
            - Specific to their profile
            - Technically accurate but accessible
            - Include appropriate emojis
            - Maximum 500 characters
            """
            
            # Call ChatGPT
            if self.openai_api_key:
                import openai
                client = openai.OpenAI(api_key=self.openai_api_key)
                
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are an expert and motivating personal trainer."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=300
                )
                
                return response.choices[0].message.content
            else:
                # Basic response if no API key
                return self._generate_basic_response(message, user_data)
                
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            return self._generate_basic_response(message, user_data)
    
    def _generate_basic_response(self, message: str, user_data: Dict) -> str:
        """Generates basic response without AI"""
        name = user_data.get('name', 'User')
        
        if any(word in message.lower() for word in ['hello', 'hi', 'hola']):
            return f"Hello {name}! 👋 How can I help you with your training?"
        elif any(word in message.lower() for word in ['routine', 'exercise', 'workout', 'rutina', 'ejercicio']):
            return f"Perfect {name}! 💪 Use /routine to create a personalized routine."
        elif any(word in message.lower() for word in ['data', 'metrics', 'analysis', 'datos', 'métricas']):
            return f"📊 Use /data to view your data or /analysis for a complete AI analysis."
        else:
            return f"I understand {name}. 🤔 Use /menu to see all available options or /help for more information."
    
    # Formatting methods
    def _format_sensor_data(self, readings: List[Dict]) -> str:
        """Formats sensor data"""
        if not readings:
            return "No data available."
        
        text = "**Latest measurements:**\n"
        for reading in readings[:5]:  # Show only last 5
            timestamp = reading.get('timestamp', 'N/A')
            if isinstance(timestamp, str):
                timestamp = timestamp[:16]  # Only date and time
            
            text += f"""
📅 {timestamp}
• SpO₂: {reading.get('spo2', 'N/A')}%
• CO₂: {reading.get('co2', 'N/A')} ppm
• HR: {reading.get('heart_rate', 'N/A')} bpm
---
"""
        return text
    
    def _format_recommendations(self, recommendations: List[Dict]) -> str:
        """Formats recommendations"""
        if not recommendations:
            return "No specific recommendations."
        
        text = ""
        for i, rec in enumerate(recommendations[:3], 1):  # Maximum 3 recommendations
            priority = rec.get('priority', 'medium')
            emoji = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
            text += f"{emoji} {rec.get('message', 'Recommendation')}\n"
        
        return text
    
    def _format_trends(self, trends: List[str]) -> str:
        """Formats trends"""
        if not trends:
            return "No trends identified."
        
        return "\n".join([f"• {trend}" for trend in trends[:5]])
    
    def _format_alerts(self, alerts: List[str]) -> str:
        """Formats alerts"""
        if not alerts:
            return "✅ No alerts."
        
        return "\n".join([f"⚠️ {alert}" for alert in alerts])
    
    def _format_routine(self, routine: Dict) -> str:
        """Formats routine"""
        text = f"""
🏋️‍♂️ **{routine.get('name', 'Personalized Routine')}**

⏱️ **Duration:** {routine.get('total_duration', 'N/A')} minutes
🎯 **Difficulty:** {routine.get('difficulty', 'N/A')}

**Exercises:**
"""
        
        for i, exercise in enumerate(routine.get('exercises', [])[:5], 1):
            text += f"""
{i}. **{exercise.get('name', 'Exercise')}**
   • Duration: {exercise.get('duration', 'N/A')} min
   • Intensity: {exercise.get('intensity', 'N/A')}
   • {exercise.get('description', 'No description')}
"""
        
        return text


def main() -> None:
    """Main bot function"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured in .env")
    
    bot = SmartBreathingBot()
    
    app = Application.builder().token(token).build()

    app.post_init = connect_to_mongo
    app.post_shutdown = close_mongo_connection
    
    # Authentication conversation handler
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            AUTH_ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.auth_ask_name)],
            AUTH_ASK_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.auth_ask_last_name)],
            AUTH_ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.auth_ask_password)],
            MAIN_MENU: [
                CommandHandler("menu", bot.menu_command),
                CallbackQueryHandler(bot.handle_callback_query)
            ]
        },
        fallbacks=[CommandHandler("cancel", bot.cancel)],
    )

    app.add_handler(auth_handler)
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("status", bot.status_command))
    app.add_handler(CommandHandler("data", bot.data_command))
    app.add_handler(CommandHandler("routine", bot.routine_command))
    app.add_handler(CommandHandler("analysis", bot.analysis_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    app.add_handler(CallbackQueryHandler(bot.handle_callback_query))
    
    logger.info("Starting SmartBreathing Bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
