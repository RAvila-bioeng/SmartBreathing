import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_message:
         await update.effective_message.reply_text("❌ Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo más tarde.")

class SmartBreathingBot:
    def __init__(self):
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.user_sessions: Dict[int, Dict] = {}
        logger.info(f"Initialized SmartBreathingBot with API_BASE_URL: {self.api_base_url}")

    def _get_message_by_tone(self, key: str, user_data: Dict) -> str:
        """Returns a localized message based on the user's 'grado_exigencia'."""
        grado = (user_data.get("grado_exigencia") or "").lower()
        
        # Determine tone category
        tone = "moderado" # default
        if "bajo" in grado: tone = "bajo"
        elif "exigente" in grado: tone = "exigente"
        
        messages = {
            "login_success": {
                "bajo": "¡Inicio de sesión exitoso! 🎉 Qué alegría verte de nuevo.",
                "moderado": "Inicio de sesión exitoso. Bienvenido.",
                "exigente": "Sesión iniciada. Vamos a trabajar."
            },
            "welcome_menu": {
                "bajo": "¡Hola {name}! 😊 Estoy aquí para ayudarte a brillar hoy.",
                "moderado": "Hola {name}. Soy tu entrenador personal inteligente.",
                "exigente": "{name}, concéntrate. Estoy aquí para maximizar tu rendimiento."
            },
            "session_complete": {
                "bajo": "¡Brutal trabajo hoy! 💥 Has completado toda la sesión, sigue así 🙌",
                "moderado": "Sesión completada correctamente. Buen progreso.",
                "exigente": "Sesión completada. Esto es lo mínimo para acercarte a tus objetivos, seguimos."
            },
            "session_incomplete": {
                "bajo": "No pasa nada, hoy también has avanzado. Mañana lo retomamos con calma 💪",
                "moderado": "Sesión guardada como incompleta. Intenta completar la rutina la próxima vez.",
                "exigente": "Sesión de hoy incompleta. Si quieres progresar, necesitas más constancia. La próxima vez vamos a por todo."
            },
            # Rewards
            "reward_menos_ejercicio": {
                "bajo": "🎉 ¡Gran trabajo! Como recompensa, mañana puedes tomarte un día de entrenamiento más ligero.",
                "moderado": "Buen trabajo. Mañana puedes reducir la carga de entrenamiento.",
                "exigente": "Bien hecho. Mañana reduce la intensidad para recuperar."
            },
            "reward_mas_descanso": {
                "bajo": "😌 ¡Impresionante! Te has ganado un descanso extra en tu próxima sesión.",
                "moderado": "Has cumplido. Tienes un descanso extra en la próxima sesión.",
                "exigente": "Objetivo cumplido. Te permito un descanso extra la próxima vez."
            },
            "reward_comida": {
                "bajo": "🍏 ¡Buen trabajo! Te has ganado una pequeña recompensa: ¡disfruta de ese snack saludable!",
                "moderado": "Sesión terminada. Si encaja en tu dieta, puedes tomar un snack de recuperación.",
                "exigente": "Entrenamiento finalizado. Nútrete correctamente para recuperar."
            },
            "reward_generic": {
                "bajo": "🏆 ¡Trabajo asombroso! Sigue así, estás progresando muy bien. 💪",
                "moderado": "Sesión registrada. Buen trabajo.",
                "exigente": "Hecho. Mantén el ritmo."
            }
        }
        
        template = messages.get(key, {}).get(tone, messages.get(key, {}).get("moderado", ""))
        return template

    # -------------------------------------------------------------------------
    # AUTH
    # -------------------------------------------------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Starts the authentication conversation."""
        await update.message.reply_text(
            "¡Bienvenido a SmartBreathing! Por favor, introduce tu nombre para iniciar sesión."
        )
        return AUTH_ASK_NAME

    async def auth_ask_name(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Saves the name and asks for the last name."""
        name = update.message.text.strip()
        if not name or not name[0].isupper():
            await update.message.reply_text(
                "El nombre debe comenzar con mayúscula. Por favor, inténtalo de nuevo."
            )
            return AUTH_ASK_NAME

        context.user_data["name"] = name
        await update.message.reply_text("Genial. Ahora, ¿cuál es tu apellido?")
        return AUTH_ASK_LAST_NAME

    async def auth_ask_last_name(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Saves the last name and asks for the password."""
        last_name = update.message.text.strip()
        if not last_name or not last_name[0].isupper():
            await update.message.reply_text(
                "El apellido debe comenzar con mayúscula. Por favor, inténtalo de nuevo."
            )
            return AUTH_ASK_LAST_NAME

        context.user_data["last_name"] = last_name
        await update.message.reply_text("Entendido. Por favor, introduce tu código de 4 dígitos.")
        return AUTH_ASK_PASSWORD

    async def auth_ask_password(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Saves the password, authenticates the user, and ends the conversation."""
        password = update.message.text.strip()
        if not (password.isdigit() and len(password) == 4):
            await update.message.reply_text(
                "El código debe ser un número de 4 dígitos. Por favor, inténtalo de nuevo."
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
                summary_text = self._get_message_by_tone("login_success", user)
            
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
                "Autenticación fallida. Por favor, verifica tus credenciales y comienza de nuevo con /start."
            )
            context.user_data.clear()
            return ConversationHandler.END

    async def _ask_condition_if_needed(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: Dict,
    ) -> None:
        """
        Checks if the user has a limiting condition but no details yet.
        If so, asks for details and sets a flag in user_data.
        """
        cond = user.get("condiciones_limitantes", "")
        # Normalize: check if it looks like "yes"
        has_condition = False
        if isinstance(cond, bool):
            has_condition = cond
        elif isinstance(cond, str):
            cond_lower = cond.lower().strip()
            if cond_lower in ["si", "sí", "yes", "true", "1", "s"]:
                has_condition = True
        
        detail = user.get("condicion_limitante_detalle")
        
        if has_condition and not detail:
            context.user_data["awaiting_condition_detail"] = True
            text = (
                "⚠️ Veo que indicaste una condición limitante en tu perfil.\n\n"
                "¿Podrías describirla brevemente? (ej. 'Lesión de rodilla', 'Asma', 'Dolor de espalda')\n"
                "Esto me ayuda a adaptar los ejercicios para tu seguridad."
            )
            await update.message.reply_text(text)
        else:
            context.user_data["awaiting_condition_detail"] = False

    async def cancel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Cancels the current conversation."""
        await update.message.reply_text("El registro ha sido cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

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

            # Mediciones: solo 2 fechas más recientes, ordenadas por fecha
            med_col = db.db.Mediciones
            try:
                # Intento 1: ObjectId
                med_cursor = med_col.find({"idUsuario": user_oid}).sort("fecha", -1).limit(2)
                readings = await med_cursor.to_list(length=2)
                if not readings:
                    # Intento 2: String
                    med_cursor = med_col.find({"idUsuario": str(user_oid)}).sort("fecha", -1).limit(2)
                    readings = await med_cursor.to_list(length=2)
            except:
                 readings = []

            result["latest_measurements"] = readings

        except Exception as e:
            logger.error(f"Error loading full user context: {e}")

        return result

    def _build_user_summary(self, full_context: Dict) -> str:
        user = full_context.get("user") or {}
        latest_ex = full_context.get("latest_exercise_record")
        measurements = full_context.get("latest_measurements", [])

        # Escapar campos dinámicos para Markdown V2
        name = escape_markdown(str(user.get("nombre", "Usuario")), version=2)
        edad = escape_markdown(str(user.get("edad", "N/A")), version=2)
        peso = escape_markdown(str(user.get("peso", "N/A")), version=2)
        sport = escape_markdown(str(user.get("sport_preference", "N/A")), version=2)
        level = escape_markdown(str(user.get("fitness_level", "N/A")), version=2)
        objetivo = escape_markdown(str(user.get("objetivo_deportivo", "N/A")), version=2)

        text = (
            f"👋 ¡Bienvenido de nuevo, *{name}*\\!\n\n"
            f"*Perfil:*\n"
            f"• Edad: {edad} años\n"
            f"• Peso: {peso} kg\n"
            f"• Deporte: {sport}\n"
            f"• Nivel: {level}\n"
            f"• Objetivo: {objetivo}\n"
        )

        if latest_ex:
            fecha = escape_markdown(str(latest_ex.get("fecha_interaccion", "N/A")), version=2)
            resultados = escape_markdown(str(latest_ex.get("resultados", "N/A")), version=2)
            text += "\n*Última actividad:*\n"
            text += f"• Fecha: {fecha}\n"
            text += f"• Resultados: {resultados}\n"

        if measurements:
            text += "\n*Mediciones recientes:*\n"
            for m in measurements:
                fecha_raw = m.get("fecha", "N/A")
                fecha_m = escape_markdown(str(fecha_raw), version=2)
                valores = m.get("valores", {})
                
                # Resumen de valores clave
                val_str = ""
                # Priorizar mostrar peso, spo2 y co2 si existen
                if "peso" in valores:
                    val_str += f"Peso: {valores['peso']} "
                if "spo2" in valores:
                    val_str += f"SpO2: {valores['spo2']}% "
                
                # Si no hay claves específicas, mostrar las primeras 2
                if not val_str:
                    items = list(valores.items())[:2]
                    for k, v in items:
                        val_str += f"{k}: {v} "
                
                val_esc = escape_markdown(val_str.strip(), version=2)
                text += f"• {fecha_m}: {val_esc}\n"

        return text

    # -------------------------------------------------------------------------
    # HELP / MENU / STATUS / DATA / ANALYSIS / ROUTINE
    # -------------------------------------------------------------------------
    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Help command - Shows help"""
        help_text = """
🤖 *SmartBreathing - Tu Entrenador Personal con IA*

*Comandos principales:*
/start - Iniciar sesión o registro
/help - Mostrar esta ayuda
/menu - Volver al menú principal
/status - Ver estado actual
/data - Ver mis datos de entrenamiento
/routine - Crear nueva rutina
/analysis - Análisis de rendimiento
/register - Registrar tus datos

*Funciones:*
• Monitoreo fisiológico en tiempo real
• Rutinas personalizadas con IA
• Conversación natural con tu entrenador
• Análisis de rendimiento y progreso
• Alertas automáticas de seguridad

Puedes usar /menu en cualquier momento para volver a las opciones principales.

¿Necesitas ayuda? Simplemente escribe tu pregunta y te responderé de forma personalizada.
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def menu_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Menu command - Go to main menu"""
        user_data = context.user_data.get("user")

        if not user_data:
            await update.message.reply_text(
                "No has iniciado sesión. Usa /start para entrar."
            )
            return ConversationHandler.END

        await self._show_main_menu(update, context, user_data)
        return MAIN_MENU

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Status command - View current status"""
        user_data = context.user_data.get("user")
        query = getattr(update, "callback_query", None)

        if not user_data:
            msg = "No has iniciado sesión. Usa /start para entrar."
            if query:
                await query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        # Get recent analysis
        analysis = await self._get_user_analysis(str(user_data["_id"]))

        name = user_data.get("nombre") or user_data.get("name", "N/A")
        age = user_data.get("edad", user_data.get("age", "N/A"))
        weight = user_data.get("peso", user_data.get("weight", "N/A"))

        # Check for health risks in latest measurements
        full_context = await self._load_user_full_context(user_data) # Ensure context is fresh
        latest_measurements = full_context.get("latest_measurements", [])
        warnings = self._check_health_risks(latest_measurements)
        
        warning_text = ""
        if warnings:
            warning_text = "\n\n⚠️ ALERTA DE SEGURIDAD:\n" + "\n".join(warnings) + "\n\n(Recuerda: soy una IA, esto no es consejo médico. Consulta a un profesional)."

        no_data_msg = ""
        if not latest_measurements:
            no_data_msg = "\n\n⚠️ Aún no tengo mediciones registradas para ti. Puedo generarte una rutina igualmente, pero si registras tus datos (peso, pulsaciones, CO₂, etc.), podré personalizar mucho mejor tus recomendaciones."

        status_text = f"""
📊 Tu Estado Actual

Perfil:
• Nombre: {name}
• Edad: {age} años
• Peso: {weight} kg
• Deporte: {user_data.get('sport_preference', 'N/A')}
• Nivel: {user_data.get('fitness_level', 'N/A')}

Análisis Reciente:
{analysis.get('analysis_summary', 'Sin datos recientes')}

Recomendaciones:
{self._format_recommendations(analysis.get('recommendations', []))}
{warning_text}{no_data_msg}
        """

        if query:
            keyboard = [[InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]]
            await query.edit_message_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(status_text)

    async def data_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Data command - View training data"""
        user_data = context.user_data.get("user")
        query = getattr(update, "callback_query", None)

        if not user_data:
            msg = "No has iniciado sesión. Usa /start para entrar."
            if query:
                await query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        # Get recent readings desde el backend
        readings = await self._get_user_readings(str(user_data["_id"]))

        if not readings:
            msg = "📊 No hay datos de entrenamiento recientes disponibles."
            if query:
                await query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        data_text = self._format_sensor_data(readings[:10])  # Last 10 readings

        keyboard = [
            [InlineKeyboardButton("📈 Ver Análisis Completo", callback_data="full_analysis")],
            [InlineKeyboardButton("📊 Exportar Datos", callback_data="export_data")],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(
                f"📊 Tus Datos de Entrenamiento\n\n{data_text}",
                reply_markup=reply_markup,
            )
        else:
            await update.message.reply_text(
                f"📊 Tus Datos de Entrenamiento\n\n{data_text}",
                reply_markup=reply_markup,
            )

    async def routine_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Routine command - Create new routine"""
        user_data = context.user_data.get("user")
        query = getattr(update, "callback_query", None)

        if not user_data:
            msg = "No has iniciado sesión. Usa /start para iniciar sesión.\n\nEn cualquier momento puedes escribir /menu para volver al menú principal."
            if query:
                await query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        keyboard = [
            [InlineKeyboardButton("🏃‍♂️ Aeróbico", callback_data="routine_aerobico")],
            [InlineKeyboardButton("⚡ Anaeróbico", callback_data="routine_anaerobico")],
            [InlineKeyboardButton("💪 Fuerza", callback_data="routine_fuerza")],
            [InlineKeyboardButton("🫁 Respiración", callback_data="routine_respiracion")],
            [InlineKeyboardButton("🔀 Mixto", callback_data="routine_mixto")],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = """
🏋️‍♂️ *Crear nueva rutina*

¿Qué tipo de rutina te gustaría generar?

También puedes escribir /menu en cualquier momento para volver a este menú principal.
"""
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    async def analysis_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Analysis command - Performance analysis"""
        user_data = context.user_data.get("user")
        query = getattr(update, "callback_query", None)

        if not user_data:
            msg = "No has iniciado sesión. Usa /start para entrar."
            if query:
                await query.edit_message_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        wait_msg_text = "🔍 Analizando tus datos... Esto puede tomar unos segundos."
        if query:
            await query.edit_message_text(wait_msg_text)
            wait_msg = None
        else:
            wait_msg = await update.message.reply_text(wait_msg_text)

        analysis = await self._get_user_analysis(str(user_data["_id"]))

        # Check for health risks
        full_context = context.user_data.get("full_context", {})
        latest_measurements = full_context.get("latest_measurements", [])
        warnings = self._check_health_risks(latest_measurements)
        
        warning_text = ""
        if warnings:
            warning_text = "\n\n⚠️ ALERTAS:\n" + "\n".join(warnings)

        no_data_msg = ""
        if not latest_measurements:
            no_data_msg = "\n\n⚠️ Aún no tengo mediciones registradas para ti. Puedo generarte una rutina igualmente, pero si registras tus datos (peso, pulsaciones, CO₂, etc.), podré personalizar mucho mejor tus recomendaciones."

        analysis_text = f"""
🔍 Análisis de Rendimiento con IA

Resumen:
{analysis.get('analysis_summary', 'Datos insuficientes para el análisis')}

Tendencias:
{self._format_trends(analysis.get('trends', []))}

Alertas:
{self._format_alerts(analysis.get('alerts', []))}

Recomendaciones:
{self._format_recommendations(analysis.get('recommendations', []))}

Próximos Pasos:
{analysis.get('next_steps', 'Continúa con el entrenamiento regular')}

Confianza del Análisis: {analysis.get('confidence_score', 0) * 100:.0f}%
{warning_text}{no_data_msg}

(Nota: Este bot es una IA, no un médico. Contrasta siempre con un profesional).
        """

        keyboard = [
            [InlineKeyboardButton("🔄 Actualizar Análisis", callback_data="refresh_analysis")],
            [InlineKeyboardButton("📊 Ver Datos Detallados", callback_data="detailed_data")],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(
                analysis_text, reply_markup=reply_markup
            )
        else:
            if wait_msg:
                await wait_msg.edit_text(analysis_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(analysis_text, reply_markup=reply_markup)

    # -------------------------------------------------------------------------
    # GENERAL MESSAGE HANDLER (chat + condición limitante + extra exercise + settings)
    # -------------------------------------------------------------------------
    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles general text messages."""
        user_data = context.user_data.get("user")
        if not user_data:
            await update.message.reply_text(
                "No has iniciado sesión. Usa /start para entrar."
            )
            return

        text_input = (update.message.text or "").strip()

        # 1) Waiting for Limiting Condition Detail
        if context.user_data.get("awaiting_condition_detail"):
            try:
                if db.is_connected and db.db is not None:
                    users_col = db.db.users
                    await users_col.update_one(
                        {"_id": user_data["_id"]},
                        {"$set": {"condicion_limitante_detalle": text_input}},
                    )
                    user_data["condicion_limitante_detalle"] = text_input
                    context.user_data["user"] = user_data
                    logger.info(
                        f"Saved limiting condition for user {user_data['_id']}: {text_input}"
                    )

                context.user_data["awaiting_condition_detail"] = False
                await update.message.reply_text(
                    f"✅ Entendido. Tendré en cuenta tu condición a partir de ahora:\n- {text_input}"
                )
                return
            except Exception as e:
                logger.error(f"Error saving limiting condition: {e}", exc_info=True)
                context.user_data["awaiting_condition_detail"] = False
                await update.message.reply_text(
                    "⚠️ Hubo un problema guardando tu condición, pero la recordaré para esta sesión."
                )
                return

        # 2) Waiting for Extra Exercise Detail
        if context.user_data.get("awaiting_extra_exercise_detail"):
            try:
                if db.is_connected and db.db is not None:
                    col = db.db.RegistroUsuarioEjercicio
                    doc = {
                        "idUsuario": user_data["_id"],
                        "fecha_interaccion": datetime.utcnow(),
                        "tipo": "extra",
                        "resultados": text_input,
                        "completado": True,
                        "fuente": "telegram_bot"
                    }
                    await col.insert_one(doc)
                    logger.info(f"Saved extra exercise for user {user_data['_id']}")

                context.user_data["awaiting_extra_exercise_detail"] = False
                
                # Log the full session completion including the extra exercise event
                try:
                    completed_ids = context.user_data.get("session_completed_exercises", [])
                    latest_date = context.user_data.get("current_routine_date")
                    
                    if latest_date:
                        col_routines = db.db.ejercicios_asignados
                        exercises_cursor = col_routines.find({"idUsuario": user_data["_id"], "fecha_creacion_rutina": latest_date})
                        exercises = await exercises_cursor.to_list(length=100)
                        
                        await self._log_session_completion(user_data, "completa", exercises, completed_ids)
                except Exception as log_e:
                    logger.error(f"Error logging session after extra exercise: {log_e}")

                # Reset session flags
                context.user_data["has_extra_exercise"] = False 
                context.user_data["session_completed_exercises"] = []
                
                # Send reward message
                await self._send_reward_message(update, context, has_extra=True)
                return
            except Exception as e:
                logger.error(f"Error saving extra exercise: {e}", exc_info=True)
                context.user_data["awaiting_extra_exercise_detail"] = False
                await update.message.reply_text(
                    "⚠️ Problema guardando el ejercicio extra, ¡pero sigue así con el buen trabajo!"
                )
                return

        # 3) Waiting for Settings Update (Profile Field)
        pending_field = context.user_data.get("pending_update_field")
        if pending_field:
            try:
                new_value = text_input
                valid = True
                error_msg = "Formato inválido."

                if pending_field == "edad":
                    if not text_input.isdigit() or not (10 <= int(text_input) <= 100):
                        valid = False
                        error_msg = "Por favor introduce una edad válida (10-100)."
                    else:
                        new_value = int(text_input)

                elif pending_field == "peso":
                    try:
                        val = float(text_input)
                        if not (0 < val < 400):
                            valid = False
                            error_msg = "Por favor introduce un peso válido (0-400)."
                        else:
                            new_value = val
                    except ValueError:
                        valid = False
                        error_msg = "Por favor introduce un número válido para el peso."

                elif pending_field == "frecuencia_entrenamiento":
                    if not text_input.isdigit() or not (1 <= int(text_input) <= 14):
                        valid = False
                        error_msg = "Por favor introduce una frecuencia válida (1-14)."
                    else:
                        new_value = int(text_input)

                elif pending_field == "tiempo_dedicable_diario":
                    if not text_input.isdigit() or not (5 <= int(text_input) <= 300):
                        valid = False
                        error_msg = "Por favor introduce minutos válidos (5-300)."
                    else:
                        new_value = int(text_input)

                elif pending_field == "codigo":
                    if not (text_input.isdigit() and len(text_input) == 4):
                        valid = False
                        error_msg = "El código debe ser exactamente de 4 dígitos."
                    else:
                        new_value = text_input

                elif pending_field in [
                    "equipamiento", "sport_preference", "objetivo_deportivo",
                    "grado_exigencia", "sistema_recompensas"
                ]:
                    if not text_input:
                        valid = False
                        error_msg = "Por favor introduce un valor."
                    else:
                        new_value = text_input

                if not valid:
                    await update.message.reply_text(f"❌ {error_msg} Inténtalo de nuevo.")
                    return

                # Update DB
                if db.is_connected and db.db is not None:
                    users_col = db.db.users
                    await users_col.update_one(
                        {"_id": user_data["_id"]},
                        {"$set": {pending_field: new_value}}
                    )
                    user_data[pending_field] = new_value
                    context.user_data["user"] = user_data
                    
                    del context.user_data["pending_update_field"]
                    
                    field_name_es = pending_field.replace('_', ' ')
                    
                    await update.message.reply_text(
                        f"✅ Tu {field_name_es} ha sido actualizado a: {new_value}"
                    )
                    return
                else:
                    await update.message.reply_text("⚠️ Base de datos no disponible.")
                    return

            except Exception as e:
                logger.error(f"Error updating profile field: {e}", exc_info=True)
                await update.message.reply_text("❌ Ocurrió un error al actualizar.")
                return

        # 4) Intent Detection and Chat
        text_lower = text_input.lower()
        
        # Intent: Rutina
        if any(kw in text_lower for kw in ["mi rutina", "rutina actual", "qué rutina tengo", "recordar mi rutina", "qué tengo que entrenar"]):
            await self._answer_current_routine(user_data, update)
            return

        # Intent: Mediciones
        if any(kw in text_lower for kw in ["mis mediciones", "mis resultados", "últimos tests", "últimos resultados", "spo2", "co2", "frecuencia cardiaca", "bpm"]):
            await self._answer_measurements(user_data, update)
            return

        # Default AI Chat
        message_text = update.message.text
        processing_msg = await update.message.reply_text("🤔 Procesando tu consulta...")

        try:
            response = await self._generate_ai_response(message_text, user_data, context)
            await processing_msg.delete()
            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            await processing_msg.edit_text(
                "❌ Lo siento, hubo un error procesando tu consulta. "
                "Inténtalo de nuevo o usa /menu para ver las opciones."
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
                "No has iniciado sesión. Usa /start para entrar."
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
                "Ya puedes chatear con la IA. Simplemente envía un mensaje."
            )

        # --- SETTINGS MENU ---
        elif data == "settings":
            await self._show_settings_menu(update, context)

        elif data == "settings_update_profile":
            await self._show_settings_profile(update, context)
        
        elif data == "settings_change_code":
            await self._initiate_field_update(update, context, "codigo", "Por favor introduce tu nuevo código de acceso de 4 dígitos.")

        elif data == "settings_change_training":
            await self._show_settings_training(update, context)

        elif data == "settings_change_rewards":
            await self._initiate_field_update(update, context, "sistema_recompensas", "Por favor introduce tu sistema de recompensas preferido (ej. 'menos_ejercicio', 'mas_descanso', 'comida', 'mensaje_motivador').")

        elif data.startswith("update_field_"):
            field = data.replace("update_field_", "")
            msg = f"Por favor introduce tu nuevo {field.replace('_', ' ')}."
            if field == "edad": msg = "Por favor introduce tu nueva edad."
            if field == "peso": msg = "Por favor introduce tu nuevo peso (kg)."
            if field == "frecuencia_entrenamiento": msg = "Por favor introduce tu nueva frecuencia de entrenamiento (sesiones/semana)."
            if field == "tiempo_dedicable_diario": msg = "Por favor introduce tu nuevo tiempo diario disponible (minutos)."
            
            await self._initiate_field_update(update, context, field, msg)

        # --- EXERCISE REGISTRATION ---
        elif data == "register_exercises":
            await self._register_exercises(update, context)

        elif data.startswith("toggle_exercise_"):
            ex_id = data.split("_", 2)[2]
            await self._toggle_exercise_status(update, context, ex_id)

        elif data == "all_exercises_done":
            await self._finish_session(update, context)
            
        elif data == "finish_session":
            await self._finish_session(update, context)
        
        elif data == "close_session_anyway":
            await self._close_session_incomplete(update, context, abandoned=True)
            
        elif data == "session_incomplete_planned":
            await self._close_session_incomplete(update, context, abandoned=False)

        elif data == "extra_exercise":
            context.user_data["has_extra_exercise"] = True
            await query.edit_message_text(
                "Perfecto, apuntado que has hecho algo extra. Cuando termines la sesión te preguntaré qué fue exactamente."
            )
            # Re-show checklist to continue
            await asyncio.sleep(2)
            await self._register_exercises(update, context)

        elif data == "continue_session":
            await self._register_exercises(update, context)

    # -------------------------------------------------------------------------
    # INTENT HELPERS
    # -------------------------------------------------------------------------
    async def _answer_current_routine(self, user_data: Dict, update: Update) -> None:
        """Answers questions about current routine using real DB data."""
        if not db.is_connected or db.db is None:
            await update.message.reply_text("Base de datos no disponible.")
            return

        try:
            col = db.db.ejercicios_asignados
            user_oid = user_data["_id"]
            
            latest_doc = await col.find_one({"idUsuario": user_oid}, sort=[("fecha_creacion_rutina", -1)])
            
            if not latest_doc:
                await update.message.reply_text(
                    "No tienes ninguna rutina asignada actualmente. "
                    "Puedes crear una nueva desde el menú 'Rutinas'."
                )
                return

            latest_date = latest_doc["fecha_creacion_rutina"]
            exercises_cursor = col.find({"idUsuario": user_oid, "fecha_creacion_rutina": latest_date})
            exercises = await exercises_cursor.to_list(length=100)

            routine_name = exercises[0].get("nombre_rutina", "Rutina Personalizada")
            routine_type = exercises[0].get("tipo", "General")
            
            msg = f"🏋️‍♂️ *Tu Rutina Actual: {routine_name}*\n"
            msg += f"Tipo: {routine_type}\n"
            msg += f"Ejercicios ({len(exercises)}):\n"
            
            for ex in exercises:
                msg += f"• {ex.get('nombre', 'Ejercicio')} ({ex.get('duracion', 0)} min, {ex.get('intensidad', 'Medio')})\n"
            
            days = exercises[0].get("dias_semana", [])
            if days:
                msg += f"\nDías recomendados: {', '.join(days)}"

            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error answering current routine: {e}")
            await update.message.reply_text("Hubo un error al consultar tu rutina.")

    async def _answer_measurements(self, user_data: Dict, update: Update) -> None:
        """Answers questions about measurements using real DB data."""
        full_context = await self._load_user_full_context(user_data)
        measurements = full_context.get("latest_measurements", [])

        if not measurements:
            await update.message.reply_text(
                "Aún no tengo mediciones registradas para ti. "
                "Si registras tus mediciones con la mascarilla, podré personalizar mucho mejor tus recomendaciones."
            )
            return

        msg = "📊 *Tus Últimas Mediciones*\n\n"
        
        for m in measurements:
            fecha = m.get("fecha", "N/A")
            msg += f"📅 Fecha: {fecha}\n"
            valores = m.get("valores", {})
            for k, v in valores.items():
                if k.startswith("co2") or k in ["peso", "spo2", "bpm", "grasa_porc"]:
                    msg += f"• {k}: {v}\n"
            msg += "\n"

        warnings = self._check_health_risks(measurements)
        if warnings:
            msg += "⚠️ *Alertas:*\n" + "\n".join(warnings) + "\n\n"

        msg += "(Recuerda: soy una IA, no un médico.)"
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

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
                    json={"goals": goals},
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except aiohttp.ClientConnectorError as e:
            raise e
        except Exception as e:
            logger.error(f"Error generating routine: {e}")
            return None

    async def _generate_ai_response(
        self,
        message: str,
        user_data: Dict,
        context: ContextTypes.DEFAULT_TYPE = None
    ) -> str:
        """Generates AI response using ChatGPT with style based on grado_exigencia"""
        try:
            grado = (user_data.get("grado_exigencia") or "").lower()
            if "exigente" in grado:
                style_instruction = (
                    "Tu tono es como un entrenador militar estricto: muy exigente, directo e intenso. "
                    "Empujas al usuario al límite, usas frases cortas y firmes, "
                    "pero NUNCA insultas, humillas ni eres abusivo."
                )
            elif "moderado" in grado:
                style_instruction = (
                    "Tu tono es como un profesor serio: neutral, preciso y profesional. "
                    "No eres muy emocional, ni demasiado amable ni grosero. Evitas emojis, te centras en guías claras."
                )
            else:  # bajo u otros
                style_instruction = (
                    "Tu tono es cálido, amigable y alentador. Apoyas al usuario con empatía, "
                    "refuerzo positivo y algunos emojis."
                )

            limiting_condition = user_data.get('condicion_limitante_detalle')
            condition_note = ""
            if limiting_condition:
                condition_note = (
                    f"\n- IMPORTANTE: El usuario tiene una condición médica limitante: "
                    f"{limiting_condition}. Adapta siempre las recomendaciones y ejercicios "
                    f"para respetar esta condición y priorizar la seguridad."
                )

            measurements_note = ""
            routine_note = ""
            
            if db.is_connected and db.db is not None:
                user_oid = user_data["_id"]
                med_col = db.db.Mediciones
                
                try:
                    med_cursor = med_col.find({"idUsuario": user_oid}).sort("fecha", -1).limit(2)
                    readings = await med_cursor.to_list(length=2)
                    if not readings:
                        med_cursor = med_col.find({"idUsuario": str(user_oid)}).sort("fecha", -1).limit(2)
                        readings = await med_cursor.to_list(length=2)
                except:
                    readings = []
                
                if readings:
                    latest = readings[0]
                    valores = latest.get("valores", {})
                    measurements_note = f"\n- MEDICIONES RECIENTES: {json.dumps(valores)}"
                    warnings = self._check_health_risks(readings)
                    if warnings:
                        measurements_note += f"\n- ALERTAS DE SEGURIDAD ACTIVAS: {'; '.join(warnings)}. Sé conservador y prioriza la salud."

                rout_col = db.db.ejercicios_asignados
                latest_rout = await rout_col.find_one({"idUsuario": user_oid}, sort=[("fecha_creacion_rutina", -1)])
                if latest_rout:
                    create_date = latest_rout.get("fecha_creacion_rutina")
                    exs_cursor = rout_col.find({"idUsuario": user_oid, "fecha_creacion_rutina": create_date})
                    exs = await exs_cursor.to_list(length=50)
                    
                    routine_note = f"\n- RUTINA ACTUAL ({latest_rout.get('nombre_rutina')}): "
                    ex_list = []
                    for e in exs:
                        status = "(Hecho)" if e.get("resultado") == "finalizado" else ""
                        ex_list.append(f"{e.get('nombre')} {status}")
                    routine_note += ", ".join(ex_list)

            prompt = f"""
INFORMACIÓN DEL USUARIO:
- Nombre: {user_data.get('nombre', user_data.get('name', 'Usuario'))}
- Edad: {user_data.get('edad', user_data.get('age', 'N/A'))} años
- Peso: {user_data.get('peso', user_data.get('weight', 'N/A'))} kg
- Deporte: {user_data.get('sport_preference', 'N/A')}
- Nivel: {user_data.get('fitness_level', 'N/A')}
- Preferencia de esfuerzo (grado_exigencia): {user_data.get('grado_exigencia', 'N/A')}{condition_note}{measurements_note}{routine_note}

CONSULTA DEL USUARIO: {message}

RESPONDE SIGUIENDO ESTE ESTILO:
{style_instruction}

REGLAS ADICIONALES:
- Responde siempre en Español.
- Sé técnicamente preciso pero accesible.
- Máximo 500 caracteres.
- Si hay alertas de seguridad o condiciones limitantes, siempre considéralas.
- Recuerda que eres una IA, no un médico.
"""

            if self.openai_api_key:
                import openai
                client = openai.OpenAI(api_key=self.openai_api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Eres un entrenador personal experto.",
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
            return "Lo siento, no puedo procesar tu solicitud ahora."

    def _generate_basic_response(self, message: str, user_data: Dict) -> str:
        """Fallback response if OpenAI is not configured."""
        return "Modo básico (sin IA): He recibido tu mensaje. Configura OPENAI_API_KEY para respuestas inteligentes."

    # -------------------------------------------------------------------------
    # EXERCISE FLOW HELPERS
    # -------------------------------------------------------------------------
    async def _finish_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles session completion logic."""
        user_data = context.user_data.get("user")
        if not db.is_connected or db.db is None: return

        # Use session state instead of persistent DB status
        completed_ids = context.user_data.get("session_completed_exercises", [])
        
        col = db.db.ejercicios_asignados
        user_oid = user_data["_id"]
        latest_date = context.user_data.get("current_routine_date")

        exercises_cursor = col.find({"idUsuario": user_oid, "fecha_creacion_rutina": latest_date})
        exercises = await exercises_cursor.to_list(length=100)
        
        total = len(exercises)
        completed_count = len(completed_ids)
        pending = total - completed_count

        # Case A: All done
        if pending == 0:
            if context.user_data.get("has_extra_exercise") and not context.user_data.get("awaiting_extra_exercise_detail"):
                context.user_data["awaiting_extra_exercise_detail"] = True
                msg = "¡Genial que hayas hecho ejercicios extra! Cuéntame brevemente qué ejercicio extra hiciste (ej. ‘15 min correr extra’, ‘Rutina de core adicional’)."
                if update.callback_query:
                    await update.callback_query.edit_message_text(msg)
                return
            
            # Send final reward and log session
            await self._log_session_completion(user_data, "completa", exercises, completed_ids)
            await self._send_reward_message(update, context, has_extra=False)
            # Reset session
            context.user_data["session_completed_exercises"] = []
            context.user_data["has_extra_exercise"] = False

        # Case B: Pending > 0
        else:
            msg = f"Te quedan {pending} ejercicios sin marcar como completados.\n¿Qué quieres hacer?"
            keyboard = [
                [InlineKeyboardButton("🔁 Seguir intentando", callback_data="continue_session")],
                [InlineKeyboardButton("🗓️ Terminar otro día", callback_data="session_incomplete_planned")],
                [InlineKeyboardButton("🛑 Hoy no termino", callback_data="close_session_anyway")],
                [InlineKeyboardButton("🔙 Menú principal", callback_data="main_menu")]
            ]
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

    async def _close_session_incomplete(self, update: Update, context: ContextTypes.DEFAULT_TYPE, abandoned: bool) -> None:
        """Closes an incomplete session."""
        user_data = context.user_data.get("user")
        if not db.is_connected or db.db is None: return
        
        status = "incompleta_abandonada" if abandoned else "incompleta_planeada"
        
        completed_ids = context.user_data.get("session_completed_exercises", [])
        col = db.db.ejercicios_asignados
        user_oid = user_data["_id"]
        latest_date = context.user_data.get("current_routine_date")
        exercises_cursor = col.find({"idUsuario": user_oid, "fecha_creacion_rutina": latest_date})
        exercises = await exercises_cursor.to_list(length=100)
        
        await self._log_session_completion(user_data, status, exercises, completed_ids)
        
        context.user_data["session_completed_exercises"] = []
        context.user_data["has_extra_exercise"] = False
        
        msg = self._get_message_by_tone("session_incomplete", user_data)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)

    async def _log_session_completion(self, user_data: Dict, status: str, exercises: List[Dict], completed_ids: List[str]) -> None:
        """Logs the session summary and individual exercise status to DB."""
        if not db.is_connected or db.db is None: return
        
        try:
            reg_col = db.db.RegistroUsuarioEjercicio
            now = datetime.utcnow()
            
            session_doc = {
                "idUsuario": user_data["_id"],
                "fecha_interaccion": now,
                "tipo": "sesion",
                "estado_sesion": status,
                "ejercicios_completados": len(completed_ids),
                "total_ejercicios": len(exercises),
                "fuente": "telegram_bot"
            }
            await reg_col.insert_one(session_doc)
            
            exercise_docs = []
            for ex in exercises:
                ex_id_str = str(ex["_id"])
                state = "completado" if ex_id_str in completed_ids else "pendiente"
                if status == "incompleta_abandonada" and state == "pendiente":
                    state = "saltado"
                
                doc = {
                    "idUsuario": user_data["_id"],
                    "fecha_interaccion": now,
                    "tipo": "ejercicio_sesion",
                    "id_ejercicio_asignado": ex.get("_id"),
                    "nombre_ejercicio": ex.get("nombre"),
                    "estado_ejercicio": state,
                    "sesion_id": session_doc.get("_id")
                }
                exercise_docs.append(doc)
            
            if exercise_docs:
                await reg_col.insert_many(exercise_docs)
                
            logger.info(f"Logged session {status} for user {user_data['_id']}")
            
        except Exception as e:
            logger.error(f"Error logging session: {e}")

    async def _send_reward_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, has_extra: bool) -> None:
        user_data = context.user_data.get("user")
        reward_pref = user_data.get("sistema_recompensas", "mensaje_motivador")
        
        base_msg = ""
        if reward_pref == "menos_ejercicio":
            base_msg = self._get_message_by_tone("reward_menos_ejercicio", user_data)
        elif reward_pref == "mas_descanso":
            base_msg = self._get_message_by_tone("reward_mas_descanso", user_data)
        elif reward_pref == "comida":
            base_msg = self._get_message_by_tone("reward_comida", user_data)
        else:
            base_msg = self._get_message_by_tone("reward_generic", user_data)

        if has_extra:
            base_msg = "🔥 ¡Increíble! Has hecho ejercicios extra. " + base_msg

        closing = self._get_message_by_tone("session_complete", user_data)
        full_msg = f"{closing}\n\n{base_msg}"

        if update.callback_query:
            await update.callback_query.edit_message_text(full_msg)
        else:
            await update.message.reply_text(full_msg)

    # -------------------------------------------------------------------------
    # SETTINGS HELPERS
    # -------------------------------------------------------------------------
    async def _show_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        keyboard = [
            [InlineKeyboardButton("👤 Actualizar perfil", callback_data="settings_update_profile")],
            [InlineKeyboardButton("🔑 Cambiar código acceso", callback_data="settings_change_code")],
            [InlineKeyboardButton("🎯 Preferencias entrenamiento", callback_data="settings_change_training")],
            [InlineKeyboardButton("🏅 Sistema recompensas", callback_data="settings_change_rewards")],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")],
        ]
        await update.callback_query.edit_message_text(
            "⚙️ Configuración\nElige una opción para actualizar tu perfil:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_settings_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        keyboard = [
            [InlineKeyboardButton("Edad", callback_data="update_field_edad")],
            [InlineKeyboardButton("Peso", callback_data="update_field_peso")],
            [InlineKeyboardButton("🔙 Atrás", callback_data="settings")],
        ]
        await update.callback_query.edit_message_text(
            "👤 Actualizar Datos de Perfil:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_settings_training(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        keyboard = [
            [InlineKeyboardButton("Frecuencia", callback_data="update_field_frecuencia_entrenamiento")],
            [InlineKeyboardButton("Tiempo Disponible", callback_data="update_field_tiempo_dedicable_diario")],
            [InlineKeyboardButton("Equipamiento", callback_data="update_field_equipamiento")],
            [InlineKeyboardButton("Preferencia Deporte", callback_data="update_field_sport_preference")],
            [InlineKeyboardButton("Objetivo", callback_data="update_field_objetivo_deportivo")],
            [InlineKeyboardButton("Intensidad", callback_data="update_field_grado_exigencia")],
            [InlineKeyboardButton("🔙 Atrás", callback_data="settings")],
        ]
        await update.callback_query.edit_message_text(
            "🎯 Actualizar Preferencias de Entrenamiento:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _initiate_field_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, message: str) -> None:
        context.user_data["pending_update_field"] = field
        await update.callback_query.edit_message_text(message)

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
            [InlineKeyboardButton("🏋️‍♂️ Rutinas", callback_data="routines")],
            [
                InlineKeyboardButton(
                    "✅ Registrar Ejercicios", callback_data="register_exercises"
                )
            ],
            [InlineKeyboardButton("💬 Chatear con IA", callback_data="chat")],
            [InlineKeyboardButton("⚙️ Configuración", callback_data="settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_text = self._get_message_by_tone("welcome_menu", user_data).format(name=user_data.get("nombre", "Usuario"))
        
        welcome_text += f"\n\nTu perfil:\n• Deporte: {user_data.get('sport_preference', 'N/A')}\n• Nivel: {user_data.get('fitness_level', 'N/A')}"
        welcome_text += "\n\nTambién puedes escribir /menu en cualquier momento para volver a este menú principal."

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
                "No has iniciado sesión. Usa /start para entrar."
            )
            return

        await update.callback_query.edit_message_text(
            "⚠️ Generando nueva rutina. Tu rutina asignada anterior "
            "será reemplazada y solo se usará la más reciente.\n\n"
            "Generando con IA...",
        )

        goals = [routine_type]

        try:
            routine = await self._generate_ai_routine(str(user_data["_id"]), goals)

            if routine:
                await self._save_assigned_routine(user_data, routine, routine_type)

                routine_text = self._format_routine(routine)

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔙 Menú Principal", callback_data="main_menu"
                        )
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.callback_query.edit_message_text(
                    routine_text, reply_markup=reply_markup
                )
            else:
                await update.callback_query.edit_message_text(
                    "❌ No he podido generar tu rutina. Inténtalo de nuevo."
                )

        except aiohttp.ClientConnectorError:
            logger.error(f"Backend no disponible en {self.api_base_url}")
            await update.callback_query.edit_message_text(
                "❌ No he podido generar tu rutina porque el servidor está fuera de línea.\n"
                "Asegúrate de que el backend de SmartBreathing está iniciado y vuelve a intentarlo."
            )
        except Exception as e:
            logger.error(f"Error creating routine: {e}")
            await update.callback_query.edit_message_text(
                "❌ Error generando la rutina. Inténtalo de nuevo."
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

            docs = []
            for ex in routine.get("exercises", []):
                docs.append(
                    {
                        "idUsuario": user_oid,
                        "tipo": routine_type,
                        "nombre_rutina": routine.get("name"),
                        "fecha_creacion_rutina": now,
                        "fecha_ejercicio": now,
                        "dias_semana": routine.get("dias_semana", []),
                        "nombre": ex.get("name"),
                        "descripcion": ex.get("description"),
                        "duracion": ex.get("duration"),
                        "intensidad": ex.get("intensity"),
                        "resultado": "por_hacer",
                        "id_ejercicio": ex.get("id_ejercicio")
                    }
                )

            if docs:
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
                "No has iniciado sesión. Usa /start para entrar."
            )
            return

        if not db.is_connected or db.db is None:
            await update.callback_query.edit_message_text(
                "Base de datos no disponible. Inténtalo más tarde."
            )
            return

        col = db.db.ejercicios_asignados
        user_oid = user_data["_id"]

        latest_doc_cursor = (
            col.find({"idUsuario": user_oid})
            .sort("fecha_creacion_rutina", -1)
            .limit(1)
        )
        latest_docs = await latest_doc_cursor.to_list(length=1)
        if not latest_docs:
            await update.callback_query.edit_message_text(
                "No tienes rutinas asignadas aún. Usa Rutinas para crear una.",
            )
            return

        latest_date = latest_docs[0]["fecha_creacion_rutina"]
        routine_cursor = col.find(
            {"idUsuario": user_oid, "fecha_creacion_rutina": latest_date}
        )
        routine = await routine_cursor.to_list(length=100)

        context.user_data["current_routine_date"] = latest_date
        
        if "session_completed_exercises" not in context.user_data:
            context.user_data["session_completed_exercises"] = []

        text = "📝 Marcando ejercicios para la sesión de hoy:\n\n"
        keyboard: List[List[InlineKeyboardButton]] = []

        completed_ids = context.user_data["session_completed_exercises"]

        for ex in routine:
            ex_id = str(ex["_id"])
            status_emoji = "✅" if ex_id in completed_ids else "⬜"
            nombre = ex.get("nombre", "Exercise")
            text += f"{status_emoji} {nombre}\n"
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
                    "➕ He hecho ejercicios EXTRA",
                    callback_data="extra_exercise",
                )
            ]
        )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "✅ Terminar por hoy",
                    callback_data="finish_session",
                )
            ]
        )
        keyboard.append(
            [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]
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
        """Mark one exercise as completed locally for the session."""
        user_data = context.user_data.get("user")
        if not user_data: return

        if "session_completed_exercises" not in context.user_data:
            context.user_data["session_completed_exercises"] = []
            
        completed_ids = context.user_data["session_completed_exercises"]
        
        if exercise_id in completed_ids:
            completed_ids.remove(exercise_id)
        else:
            completed_ids.append(exercise_id)
            
        context.user_data["session_completed_exercises"] = completed_ids

        await self._register_exercises(update, context)

    def _check_health_risks(self, measurements: List[Dict]) -> List[str]:
        """Checks for health risks in the latest measurement."""
        if not measurements:
            return []
        
        latest = measurements[0]
        valores = latest.get("valores", {})
        warnings = []

        max_co2 = 0
        for k, v in valores.items():
            if k.startswith("co2") and isinstance(v, (int, float)):
                if v > max_co2:
                    max_co2 = v
        
        if max_co2 > 2000:
            warnings.append("⚠️ CO₂ muy alto (>2000 ppm). Ventila la habitación y evita esfuerzos intensos.")
        elif max_co2 > 1000:
            warnings.append("⚠️ CO₂ elevado (>1000 ppm). Se recomienda ventilar.")

        spo2 = valores.get("spo2")
        if spo2 is not None and isinstance(spo2, (int, float)):
            if spo2 < 92:
                warnings.append("⚠️ SpO₂ bajo (<92%). Evita el ejercicio intenso y consulta a un médico si persiste.")
            elif spo2 < 95:
                warnings.append("⚠️ SpO₂ ligeramente bajo (92-94%). Modera la intensidad.")

        bpm = valores.get("bpm") or valores.get("heart_rate")
        if bpm is not None and isinstance(bpm, (int, float)):
            if bpm < 50:
                warnings.append("⚠️ Pulso en reposo bajo (<50 bpm). Precaución.")
            elif bpm > 100:
                warnings.append("⚠️ Pulso en reposo alto (>100 bpm). Precaución.")

        return warnings

    def _format_recommendations(self, recommendations: List[Dict]) -> str:
        """Formats recommendations"""
        if not recommendations:
            return "Sin recomendaciones específicas."

        text = ""
        for rec in recommendations[:3]:
            priority = rec.get("priority", "medium")
            emoji = (
                "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
            )
            text += f"{emoji} {rec.get('message', 'Recomendación')}\n"

        return text

    def _format_trends(self, trends: List[str]) -> str:
        """Formats trends"""
        if not trends:
            return "No hay tendencias identificadas."

        return "\n".join([f"• {trend}" for trend in trends[:5]])

    def _format_alerts(self, alerts: List[str]) -> str:
        """Formats alerts"""
        if not alerts:
            return "✅ Sin alertas."

        return "\n".join([f"⚠️ {alert}" for alert in alerts])

    def _format_routine(self, routine: Dict) -> str:
        """Formats routine"""
        text = f"""
🏋️‍♂️ {routine.get('name', 'Rutina Personalizada')}

Duración: {routine.get('total_duration', 'N/A')} minutos
Dificultad: {routine.get('difficulty', 'N/A')}

Ejercicios:
"""

        for i, exercise in enumerate(routine.get("exercises", [])[:5], 1):
            text += f"""
{i}. {exercise.get('name', 'Ejercicio')}
   • Duración: {exercise.get('duration', 'N/A')} min
   • Intensidad: {exercise.get('intensity', 'N/A')}
   • {exercise.get('description', 'Sin descripción')}
"""

        return text
    
    def _format_sensor_data(self, readings: List[Dict]) -> str:
        """Formats a list of sensor readings for display."""
        if not readings:
            return "No hay datos disponibles."
        
        text = ""
        for r in readings:
            date_str = r.get("fecha", "N/A")
            vals = r.get("valores", {})
            text += f"📅 {date_str}:\n"
            for k, v in vals.items():
                text += f"   • {k}: {v}\n"
            text += "\n"
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
    
    # Add Error Handler
    app.add_error_handler(error_handler)

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
