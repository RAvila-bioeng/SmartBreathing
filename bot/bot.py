import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from bson import ObjectId

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import aiohttp
import logging

from database import (
    connect_to_mongo,
    close_mongo_connection,
    find_user_by_credentials,
    is_database_connected,
    db,  # DBContext para acceder a las colecciones
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown



# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
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
        self.user_sessions: Dict[int, Dict] = {}

    # -------------------------------------------------------------------------
    # AUTH
    # -------------------------------------------------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Starts the authentication conversation."""
        await update.message.reply_text(
            "Welcome to SmartBreathing! Please enter your name to log in."
        )
        return AUTH_ASK_NAME

    async def auth_ask_name(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Saves the name and asks for the last name."""
        name = update.message.text.strip()
        if not name or not name[0].isupper():
            await update.message.reply_text(
                "The name must start with a capital letter. Please try again."
            )
            return AUTH_ASK_NAME

        context.user_data["name"] = name
        await update.message.reply_text("Great. Now, what is your last name?")
        return AUTH_ASK_LAST_NAME

    async def auth_ask_last_name(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Saves the last name and asks for the password."""
        last_name = update.message.text.strip()
        if not last_name or not last_name[0].isupper():
            await update.message.reply_text(
                "The last name must start with a capital letter. Please try again."
            )
            return AUTH_ASK_LAST_NAME

        context.user_data["last_name"] = last_name
        await update.message.reply_text("Got it. Please enter your password.")
        return AUTH_ASK_PASSWORD

    async def auth_ask_password(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Saves the password, authenticates the user, and ends the conversation."""
        password = update.message.text.strip()
        if not (password.isdigit() and len(password) == 4):
            await update.message.reply_text(
                "The password must be a four-digit number. Please try again."
            )
            return AUTH_ASK_PASSWORD

        name = context.user_data.get("name")
        last_name = context.user_data.get("last_name")

        user = await find_user_by_credentials(name, last_name, password)

        if user:
            context.user_data["user"] = user

            # 1) Cargar contexto del usuario desde la DB
            full_context = await self._load_user_full_context(user)
            context.user_data["full_context"] = full_context

            # 2) Enviar resumen amigable (Markdown V2 seguro)
            summary_text = self._build_user_summary(full_context)
            if not summary_text:
                summary_text = "Login successful."
            await update.message.reply_text(
                summary_text, parse_mode=ParseMode.MARKDOWN_V2
            )

            # 3) Preguntar por condición limitante si procede
            await self._ask_condition_if_needed(update, context, user)

            # 4) Mostrar menú principal
            await self._show_main_menu(update, context, user)
            return MAIN_MENU
        else:
            await update.message.reply_text(
                "Authentication failed. Please check your credentials and start again with /start."
            )
            context.user_data.clear()
            return ConversationHandler.END

    async def cancel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Cancels the current conversation."""
        await update.message.reply_text("Registration has been canceled.")
        context.user_data.clear()
        return ConversationHandler.END

    # -------------------------------------------------------------------------
    # HELP / MENU / STATUS / DATA / ANALYSIS / ROUTINE
    # -------------------------------------------------------------------------
    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Help command - Shows help"""
        help_text = """
🤖 *SmartBreathing - Your AI Personal Trainer*

*Main commands:*
/start - Login or registration
/help - Show this help
/menu - Go to main menu
/status - View current status
/data - View my training data
/routine - Create new routine
/analysis - Performance analysis
/register - Register your data

*Features:*
• Real-time physiological monitoring
• AI-powered personalized routines
• Natural conversation with your trainer
• Performance and progress analysis
• Automatic safety alerts

Need help? Just write your question and I'll respond in a personalized way.
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def menu_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Menu command - Go to main menu"""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return ConversationHandler.END

        await self._show_main_menu(update, context, user_data)
        return MAIN_MENU

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Status command - View current status"""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        # Get recent analysis
        analysis = await self._get_user_analysis(str(user_data["_id"]))

        name = user_data.get("nombre") or user_data.get("name", "N/A")
        age = user_data.get("edad", user_data.get("age", "N/A"))
        weight = user_data.get("peso", user_data.get("weight", "N/A"))

        status_text = f"""
📊 Your Current Status

Profile:
• Name: {name}
• Age: {age} years
• Weight: {weight} kg
• Sport: {user_data.get('sport_preference', 'N/A')}
• Level: {user_data.get('fitness_level', 'N/A')}

Recent Analysis:
{analysis.get('analysis_summary', 'No recent data')}

Recommendations:
{self._format_recommendations(analysis.get('recommendations', []))}
        """

        # Aquí NO uso parse_mode para evitar líos de Markdown con texto dinámico
        await update.message.reply_text(status_text)

    async def data_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Data command - View training data"""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        # Get recent readings desde el backend
        readings = await self._get_user_readings(str(user_data["_id"]))

        if not readings:
            await update.message.reply_text("📊 No recent training data available.")
            return

        data_text = self._format_sensor_data(readings[:10])  # Last 10 readings

        keyboard = [
            [InlineKeyboardButton("📈 View Full Analysis", callback_data="full_analysis")],
            [InlineKeyboardButton("📊 Export Data", callback_data="export_data")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📊 Your Training Data\n\n{data_text}",
            reply_markup=reply_markup,
        )

    async def routine_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Routine command - Create new routine"""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        keyboard = [
            [InlineKeyboardButton("🏃‍♂️ Cardio", callback_data="routine_cardio")],
            [InlineKeyboardButton("💪 Strength", callback_data="routine_strength")],
            [InlineKeyboardButton("🧘‍♂️ Breathing", callback_data="routine_breathing")],
            [InlineKeyboardButton("🎯 Custom", callback_data="routine_custom")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🏋️‍♂️ Create New Routine\n\n"
            "What type of routine would you like to create?",
            reply_markup=reply_markup,
        )

    async def analysis_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Analysis command - Performance analysis"""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        await update.message.reply_text(
            "🔍 Analyzing your data... This may take a few seconds."
        )

        analysis = await self._get_user_analysis(str(user_data["_id"]))

        analysis_text = f"""
🔍 Performance Analysis with AI

Summary:
{analysis.get('analysis_summary', 'Insufficient data for analysis')}

Trends:
{self._format_trends(analysis.get('trends', []))}

Alerts:
{self._format_alerts(analysis.get('alerts', []))}

Recommendations:
{self._format_recommendations(analysis.get('recommendations', []))}

Next Steps:
{analysis.get('next_steps', 'Continue with regular training')}

Analysis Confidence: {analysis.get('confidence_score', 0) * 100:.0f}%
        """

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Analysis", callback_data="refresh_analysis")],
            [InlineKeyboardButton("📊 View Detailed Data", callback_data="detailed_data")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            analysis_text, reply_markup=reply_markup
        )

    # -------------------------------------------------------------------------
    # GENERAL MESSAGE HANDLER (chat + condición limitante)
    # -------------------------------------------------------------------------
    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles general text messages with AI or condition detail."""
        # 1) Si estamos esperando el detalle de la condición limitante
        if context.user_data.get("awaiting_condition_detail"):
            detail = update.message.text.strip()
            user_data = context.user_data.get("user")

            if user_data and db.is_connected and db.db is not None:
                try:
                    users_col = db.db.users
                    await users_col.update_one(
                        {"_id": user_data["_id"]},
                        {"$set": {"condicion_limitante_detalle": detail}},
                    )
                    user_data["condicion_limitante_detalle"] = detail
                    context.user_data["user"] = user_data
                    logger.info(
                        f"Saved limiting condition detail for user {user_data['_id']}"
                    )
                except Exception as e:
                    logger.error(f"Error saving limiting condition detail: {e}")

            context.user_data["awaiting_condition_detail"] = False
            safe_detail = escape_markdown(detail, version=2)
            await update.message.reply_text(
                f"Thanks! I'll take your condition into account from now on: *{safe_detail}*",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        # 2) Chat normal con el entrenador
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        message_text = update.message.text

        # Show processing message
        processing_msg = await update.message.reply_text("🤔 Processing your query...")

        try:
            response = await self._generate_ai_response(message_text, user_data)
            await processing_msg.delete()
            # No usamos parse_mode aquí para evitar errores por Markdown raro del modelo
            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            await processing_msg.edit_text(
                "❌ Sorry, there was an error processing your query. "
                "Try again or use /menu to see available options."
            )

    # -------------------------------------------------------------------------
    # CALLBACK QUERIES (inline buttons)
    # -------------------------------------------------------------------------
    async def handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles inline button callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data
        user_data = context.user_data.get("user")

        if not user_data:
            await query.edit_message_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        if data == "main_menu":
            await self._show_main_menu(update, context, user_data)

        elif data == "status":
            await self.status_command(update, context)

        elif data == "data":
            await self.data_command(update, context)

        elif data == "routines":
            await self.routine_command(update, context)

        elif data == "analysis":
            await self.analysis_command(update, context)

        elif data == "full_analysis":
            await self.analysis_command(update, context)

        elif data.startswith("routine_"):
            routine_type = data.split("_", 1)[1]
            await self._create_routine_by_type(update, context, routine_type)

        elif data == "refresh_analysis":
            await self.analysis_command(update, context)

        elif data == "detailed_data":
            await self.data_command(update, context)

        elif data == "chat":
            await query.edit_message_text(
                "You can now chat with the AI. Just send a message."
            )

        elif data == "settings":
            await query.edit_message_text(
                "The settings section is currently under development. Please check back later."
            )

        elif data == "register_exercises":
            await self._register_exercises(update, context)

        elif data.startswith("toggle_exercise_"):
            ex_id = data.split("_", 2)[2]
            await self._toggle_exercise_status(update, context, ex_id)

        elif data == "all_exercises_done":
            await self._handle_all_exercises_done(update, context)

    # -------------------------------------------------------------------------
    # MENÚ PRINCIPAL
    # -------------------------------------------------------------------------
    async def _show_main_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_data: Dict,
    ) -> None:
        """Shows main menu"""
        keyboard = [
            [InlineKeyboardButton("🏋️‍♂️ Routines", callback_data="routines")],
            [
                InlineKeyboardButton(
                    "✅ Register Exercises", callback_data="register_exercises"
                )
            ],
            [InlineKeyboardButton("💬 Chat with AI", callback_data="chat")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        name = user_data.get("nombre") or user_data.get("name", "User")

        welcome_text = f"""
🧘‍♂️ Hello {name}!

I'm your intelligent personal trainer. How can I help you today?

Your profile:
• Sport: {user_data.get('sport_preference', 'N/A')}
• Level: {user_data.get('fitness_level', 'N/A')}
        """

        if update.callback_query:
            await update.callback_query.edit_message_text(
                welcome_text, reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                welcome_text, reply_markup=reply_markup
            )

    # -------------------------------------------------------------------------
    # RUTINAS: creación y guardado en DB
    # -------------------------------------------------------------------------
    async def _create_routine_by_type(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        routine_type: str,
    ) -> None:
        """Creates routine by selected type, saves it in DB and warns about overwrite."""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.callback_query.edit_message_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        # Aviso de que se sobreescribe la última rutina
        await update.callback_query.edit_message_text(
            "⚠️ Generating a new routine. Your previous assigned routine "
            "will be replaced and only the latest one will be used.\n\n"
            "Generating with AI...",
        )

        routine_goals = {
            "cardio": ["cardiovascular", "endurance"],
            "strength": ["muscle_gain", "strength"],
            "breathing": ["breathing", "relaxation"],
            "custom": ["general_fitness"],
        }
        goals = routine_goals.get(routine_type, ["general_fitness"])

        try:
            routine = await self._generate_ai_routine(str(user_data["_id"]), goals)

            if routine:
                # Guardar rutina en la colección ejercicios_asignados
                await self._save_assigned_routine(user_data, routine, routine_type)

                routine_text = self._format_routine(routine)

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔙 Main Menu", callback_data="main_menu"
                        )
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.callback_query.edit_message_text(
                    routine_text, reply_markup=reply_markup
                )
            else:
                await update.callback_query.edit_message_text(
                    "❌ Error generating routine. Try again."
                )

        except Exception as e:
            logger.error(f"Error creating routine: {e}")
            await update.callback_query.edit_message_text(
                "❌ Error generating routine. Try again."
            )

    async def _save_assigned_routine(
        self, user_data: Dict, routine: Dict, routine_type: str
    ) -> None:
        """Save routine as assigned exercises in ejercicios_asignados."""
        if not db.is_connected or db.db is None:
            logger.error("Database not connected. Cannot save assigned routine.")
            return

        try:
            col = db.db.ejercicios_asignados
            user_oid = user_data["_id"]
            now = datetime.utcnow()

            # Por simplicidad, asociamos todos los ejercicios a la misma rutina/fecha
            docs = []
            for ex in routine.get("exercises", []):
                docs.append(
                    {
                        "idUsuario": user_oid,
                        "tipo": routine_type,
                        "nombre_rutina": routine.get("name"),
                        "fecha_creacion_rutina": now,
                        "fecha_ejercicio": now,  # se podría hacer calendario más tarde
                        "dias_semana": routine.get("dias_semana", []),
                        "nombre": ex.get("name"),
                        "descripcion": ex.get("description"),
                        "duracion": ex.get("duration"),
                        "intensidad": ex.get("intensity"),
                        "resultado": "por_hacer",
                    }
                )

            if docs:
                # Borramos rutinas anteriores del usuario para dejar solo la última
                await col.delete_many({"idUsuario": user_oid})
                await col.insert_many(docs)
                logger.info(
                    f"Saved {len(docs)} assigned exercises for user {user_oid}"
                )

        except Exception as e:
            logger.error(f"Error saving assigned routine: {e}")

    # -------------------------------------------------------------------------
    # REGISTRAR EJERCICIOS
    # -------------------------------------------------------------------------
    async def _register_exercises(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Allows the user to mark assigned exercises as completed."""
        user_data = context.user_data.get("user")
        if not user_data:
            await update.callback_query.edit_message_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        if not db.is_connected or db.db is None:
            await update.callback_query.edit_message_text(
                "Database not available at the moment. Try again later."
            )
            return

        col = db.db.ejercicios_asignados
        user_oid = user_data["_id"]

        # Buscar la rutina más reciente por fecha_creacion_rutina
        latest_doc_cursor = (
            col.find({"idUsuario": user_oid})
            .sort("fecha_creacion_rutina", -1)
            .limit(1)
        )
        latest_docs = await latest_doc_cursor.to_list(length=1)
        if not latest_docs:
            await update.callback_query.edit_message_text(
                "You don't have any assigned routine yet. Use Routines to create one.",
            )
            return

        latest_date = latest_docs[0]["fecha_creacion_rutina"]
        routine_cursor = col.find(
            {"idUsuario": user_oid, "fecha_creacion_rutina": latest_date}
        )
        routine = await routine_cursor.to_list(length=100)

        context.user_data["current_routine_date"] = latest_date

        text = "📝 These are your latest assigned exercises:\n\n"
        keyboard: List[List[InlineKeyboardButton]] = []

        for ex in routine:
            ex_id = str(ex["_id"])
            status = ex.get("resultado", "por_hacer")
            status_emoji = "✅" if status == "finalizado" else "⏳"
            nombre = ex.get("nombre", "Exercise")
            text += f"{status_emoji} {nombre} - {status}\n"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{status_emoji} {nombre}",
                        callback_data=f"toggle_exercise_{ex_id}",
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "✔️ I have completed ALL exercises",
                    callback_data="all_exercises_done",
                )
            ]
        )
        keyboard.append(
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        )

        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _toggle_exercise_status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        exercise_id: str,
    ) -> None:
        """Mark one exercise as completed."""
        user_data = context.user_data.get("user")
        if not user_data:
            await update.callback_query.edit_message_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        if not db.is_connected or db.db is None:
            await update.callback_query.edit_message_text(
                "Database not available at the moment. Try again later."
            )
            return

        try:
            col = db.db.ejercicios_asignados
            oid = ObjectId(exercise_id)
            await col.update_one({"_id": oid}, {"$set": {"resultado": "finalizado"}})
        except Exception as e:
            logger.error(f"Error updating exercise result: {e}")

        # Refrescar la vista
        await self._register_exercises(update, context)

    async def _handle_all_exercises_done(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Check if all exercises in latest routine are done and reward the user."""
        user_data = context.user_data.get("user")
        if not user_data:
            await update.callback_query.edit_message_text(
                "You are not logged in. Please use /start to log in."
            )
            return

        if not db.is_connected or db.db is None:
            await update.callback_query.edit_message_text(
                "Database not available at the moment. Try again later."
            )
            return

        col = db.db.ejercicios_asignados
        user_oid = user_data["_id"]
        latest_date = context.user_data.get("current_routine_date")

        # Contar ejercicios aún no finalizados
        pending = await col.count_documents(
            {
                "idUsuario": user_oid,
                "fecha_creacion_rutina": latest_date,
                "resultado": {"$ne": "finalizado"},
            }
        )

        if pending > 0:
            await update.callback_query.edit_message_text(
                "There are still exercises marked as pending. "
                "Mark them as completed first by tapping on each one."
            )
            return

        reward_pref = user_data.get("sistema_recompensas", "mensaje_motivador")
        if reward_pref == "menos_ejercicio":
            msg = (
                "🎉 Great job! As a reward, tomorrow you can take a lighter training day."
            )
        elif reward_pref == "mas_descanso":
            msg = "😌 Awesome! You earned an extra rest break in your next session."
        else:
            msg = (
                "🏆 Amazing work! Keep it up, you're progressing really well. 💪"
            )

        await update.callback_query.edit_message_text(
            msg
            + "\n\nYour routine is fully completed. I'm really proud of your effort! 🙌",
        )

    # -------------------------------------------------------------------------
    # CARGA DE CONTEXTO DESDE LA DB
    # -------------------------------------------------------------------------
    async def _load_user_full_context(self, user: Dict) -> Dict:
        """
        Carga:
          - usuario (users)
          - último RegistroUsuarioEjercicio
          - Mediciones solo de las 2 fechas más recientes
        """
        result: Dict[str, Optional[Dict]] = {
            "user": user,
            "latest_exercise_record": None,
            "latest_measurements": [],
        }

        if not db.is_connected or db.db is None:
            return result

        try:
            user_oid = user["_id"]

            # Último registro de ejercicio
            reg_col = db.db.RegistroUsuarioEjercicio
            last_ex_cursor = (
                reg_col.find({"idUsuario": user_oid})
                .sort("fecha_interaccion", -1)
                .limit(1)
            )
            last_ex_docs = await last_ex_cursor.to_list(length=1)
            if last_ex_docs:
                result["latest_exercise_record"] = last_ex_docs[0]

            # Mediciones: solo 2 fechas más recientes
            med_col = db.db.Mediciones
            med_cursor = (
                med_col.find({"idUsuario": user_oid})
                .sort("fecha_medicion", -1)
            )
            all_med = await med_cursor.to_list(length=200)

            dates_seen = []
            selected = []
            for m in all_med:
                fecha = m.get("fecha_medicion")
                if isinstance(fecha, datetime):
                    key = fecha.date()
                else:
                    key = str(fecha)[:10]

                if key not in dates_seen:
                    dates_seen.append(key)
                if len(dates_seen) <= 2:
                    selected.append(m)
                else:
                    break

            result["latest_measurements"] = selected

        except Exception as e:
            logger.error(f"Error loading full user context: {e}")

        return result

    def _build_user_summary(self, full_context: Dict) -> str:
        user = full_context.get("user") or {}
        latest_ex = full_context.get("latest_exercise_record")
        measurements = full_context.get("latest_measurements", [])

        # Escapar campos dinámicos para Markdown V2
        name = escape_markdown(str(user.get("nombre", "User")), version=2)
        edad = escape_markdown(str(user.get("edad", "N/A")), version=2)
        peso = escape_markdown(str(user.get("peso", "N/A")), version=2)
        sport = escape_markdown(str(user.get("sport_preference", "N/A")), version=2)
        level = escape_markdown(str(user.get("fitness_level", "N/A")), version=2)
        objetivo = escape_markdown(str(user.get("objetivo_deportivo", "N/A")), version=2)

        # OJO: el "!" va escapado como \! para MarkdownV2
        text = (
            f"👋 Welcome back, *{name}*\\!\n\n"
            f"*Profile:*\n"
            f"• Age: {edad} years\n"
            f"• Weight: {peso} kg\n"
            f"• Sport: {sport}\n"
            f"• Level: {level}\n"
            f"• Goal: {objetivo}\n"
        )

        if latest_ex:
            fecha = escape_markdown(str(latest_ex.get("fecha_interaccion", "N/A")), version=2)
            resultados = escape_markdown(str(latest_ex.get("resultados", "N/A")), version=2)
            text += "\n*Last exercise interaction:*\n"
            text += f"• Date: {fecha}\n"
            text += f"• Results: {resultados}\n"

        if measurements:
            text += "\n*Recent measurements (last 2 dates):*\n"
            for m in measurements:
                fecha_m = escape_markdown(str(m.get("fecha_medicion", "N/A")), version=2)
                tipo = escape_markdown(str(m.get("tipoDeMedicion", "N/A")), version=2)
                valor = escape_markdown(str(m.get("valor", "N/A")), version=2)
                text += f"• {fecha_m} - {tipo}: {valor}\n"

        return text


    # -------------------------------------------------------------------------
    # API BACKEND METHODS
    # -------------------------------------------------------------------------
    async def _get_user_analysis(self, user_id: str) -> Dict:
        """Gets user analysis from backend"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base_url}/api/analysis/{user_id}"
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {"analysis_summary": "No data available"}
        except Exception as e:
            logger.error(f"Error getting analysis: {e}")
            return {"analysis_summary": "Error getting analysis"}

    async def _get_user_readings(self, user_id: str) -> List[Dict]:
        """Gets user readings from backend"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base_url}/api/sensors/readings/{user_id}"
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
        except Exception as e:
            logger.error(f"Error getting readings: {e}")
            return []

    async def _generate_ai_routine(
        self, user_id: str, goals: List[str]
    ) -> Optional[Dict]:
        """Generates routine with AI via backend"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base_url}/api/ai/generate-routine/{user_id}",
                    json=goals,
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            logger.error(f"Error generating routine: {e}")
            return None

    async def _generate_ai_response(
        self,
        message: str,
        user_data: Dict,
    ) -> str:
        """Generates AI response using ChatGPT with style based on grado_exigencia"""
        try:
            # Estilo según grado_exigencia
            grado = (user_data.get("grado_exigencia") or "").lower()
            if "exigente" in grado:
                style_instruction = (
                    "Your tone is like a strict military coach: very demanding, "
                    "direct and intense. You push the user hard, use short, firm "
                    "sentences and tough-love motivation, but you NEVER insult, "
                    "humiliate or are abusive."
                )
            elif "moderado" in grado:
                style_instruction = (
                    "Your tone is like a serious teacher: neutral, precise and "
                    "professional. You are not very emotional, not too kind and "
                    "not rude. You avoid emojis, focus on clear, concrete guidance."
                )
            else:  # bajo u otros
                style_instruction = (
                    "Your tone is warm, friendly and encouraging. You support the "
                    "user with empathy, positive reinforcement and some emojis."
                )

            # Obtener condición limitante si existe
            limiting_condition = user_data.get('condicion_limitante_detalle')
            condition_note = ""
            if limiting_condition:
                condition_note = (
                    f"\n- IMPORTANT: User has a limiting medical condition: "
                    f"{limiting_condition}. Always adapt recommendations and exercises "
                    f"to respect this condition and prioritize safety."
                )

            prompt = f"""
USER INFORMATION:
- Name: {user_data.get('nombre', user_data.get('name', 'User'))}
- Age: {user_data.get('edad', user_data.get('age', 'N/A'))} years
- Weight: {user_data.get('peso', user_data.get('weight', 'N/A'))} kg
- Sport: {user_data.get('sport_preference', 'N/A')}
- Level: {user_data.get('fitness_level', 'N/A')}
- Effort preference (grado_exigencia): {user_data.get('grado_exigencia', 'N/A')}{condition_note}

USER QUERY: {message}

RESPOND ACCORDING TO THIS STYLE:
{style_instruction}

ADDITIONAL RULES:
- Answer in the same language as the user if possible.
- Be technically accurate but accessible.
- Maximum 500 characters.
- If the user has a limiting condition, always consider it in your recommendations.
"""

            if self.openai_api_key:
                import openai

                client = openai.OpenAI(api_key=self.openai_api_key)

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert personal trainer and coach.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=300,
                )

                return response.choices[0].message.content
            else:
                return self._generate_basic_response(message, user_data)

        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            return self._generate_basic_response(message, user_data)

    # -------------------------------------------------------------------------
    # FORMATTING HELPERS
    # -------------------------------------------------------------------------
    def _generate_basic_response(self, message: str, user_data: Dict) -> str:
        """Generates basic response without AI, respecting grado_exigencia"""
        name = user_data.get("nombre", user_data.get("name", "User"))
        grado = (user_data.get("grado_exigencia") or "").lower()

        # Frases base según estilo
        if "exigente" in grado:
            hello = f"{name}, focus. 💥"
            routine_hint = "Use /routine and we’ll build a tough session. No excuses."
            data_hint = "Track your effort with /register after each workout."
            generic = (
                f"{name}, stay disciplined. Choose an option in /menu and execute."
            )
        elif "moderado" in grado:
            hello = f"Hello {name}."
            routine_hint = "Use /routine to generate a structured training plan."
            data_hint = "Use /register to record which exercises you have completed."
            generic = (
                f"{name}, you can use /menu to see the available training options."
            )
        else:  # bajo u otros
            hello = f"Hello {name}! 👋"
            routine_hint = (
                f"Perfect {name}! 💪 Use /routine to create a personalized routine."
            )
            data_hint = (
                "📊 Use /register to tell me which exercises you have completed."
            )
            generic = (
                f"I understand, {name}. 😊 Use /menu to see all available options or "
                "/help for more information."
            )

        text_lower = message.lower()

        if any(word in text_lower for word in ["hello", "hi", "hola"]):
            return hello
        elif any(
            word in text_lower
            for word in ["routine", "exercise", "workout", "rutina", "ejercicio"]
        ):
            return routine_hint
        elif any(
            word in text_lower
            for word in ["data", "metrics", "analysis", "datos", "métricas", "registro"]
        ):
            return data_hint
        else:
            return generic

    def _format_sensor_data(self, readings: List[Dict]) -> str:
        """Formats sensor data"""
        if not readings:
            return "No data available."

        text = "Latest measurements:\n"
        for reading in readings[:5]:
            timestamp = reading.get("timestamp", "N/A")
            if isinstance(timestamp, str):
                timestamp = timestamp[:16]

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
        for rec in recommendations[:3]:
            priority = rec.get("priority", "medium")
            emoji = (
                "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
            )
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
🏋️‍♂️ {routine.get('name', 'Personalized Routine')}

Duration: {routine.get('total_duration', 'N/A')} minutes
Difficulty: {routine.get('difficulty', 'N/A')}

Exercises:
"""

        for i, exercise in enumerate(routine.get("exercises", [])[:5], 1):
            text += f"""
{i}. {exercise.get('name', 'Exercise')}
   • Duration: {exercise.get('duration', 'N/A')} min
   • Intensity: {exercise.get('intensity', 'N/A')}
   • {exercise.get('description', 'No description')}
"""

        return text


# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
def main() -> None:
    """Main bot function"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured in .env")

    bot = SmartBreathingBot()

    app = Application.builder().token(token).build()

    # Conexión a MongoDB gestionada por Application
    app.post_init = connect_to_mongo
    app.post_shutdown = close_mongo_connection

    # Authentication conversation handler
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            AUTH_ASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.auth_ask_name)
            ],
            AUTH_ASK_LAST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.auth_ask_last_name)
            ],
            AUTH_ASK_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.auth_ask_password)
            ],
            MAIN_MENU: [
                CommandHandler("menu", bot.menu_command),
                CallbackQueryHandler(bot.handle_callback_query),
            ],
        },
        fallbacks=[CommandHandler("cancel", bot.cancel)],
    )

    app.add_handler(auth_handler)
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("status", bot.status_command))
    app.add_handler(CommandHandler("data", bot.data_command))
    app.add_handler(CommandHandler("routine", bot.routine_command))
    app.add_handler(CommandHandler("analysis", bot.analysis_command))
    # Mensajes de texto generales (chat / condición limitante)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message)
    )
    # Callbacks inline (botones)
    app.add_handler(CallbackQueryHandler(bot.handle_callback_query))

    logger.info("Starting SmartBreathing Bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
