import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import motor.motor_asyncio
from dotenv import load_dotenv
from telegram.ext import Application
from bson import ObjectId

import bcrypt  # de momento no lo usamos, pero lo dejamos preparado

load_dotenv()

logger = logging.getLogger(__name__)


class DBContext:
    client: motor.motor_asyncio.AsyncIOMotorClient = None
    db: motor.motor_asyncio.AsyncIOMotorDatabase = None
    is_connected: bool = False


db = DBContext()


async def connect_to_mongo(application: Application):
    """Conecta a MongoDB y actualiza el estado de la conexión."""
    mongodb_uri = os.getenv("MONGODB_URI")
    # Por defecto usamos la BD SmartBreathing
    db_name = os.getenv("MONGODB_DB_NAME", "SmartBreathing")

    if not mongodb_uri or mongodb_uri == "YOUR_MONGODB_URI":
        logger.warning("MONGODB_URI is not configured or is set to the default placeholder.")
        db.is_connected = False
        return

    try:
        db.client = motor.motor_asyncio.AsyncIOMotorClient(mongodb_uri)
        # Comprobar conexión
        await db.client.admin.command("ismaster")
        db.db = db.client[db_name]
        db.is_connected = True
        logger.info(f"Successfully connected to MongoDB and using database '{db_name}'.")
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        db.client = None
        db.db = None
        db.is_connected = False


async def close_mongo_connection(application: Application):
    """Cierra la conexión con MongoDB."""
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed.")
    db.is_connected = False


async def update_user(user_id: int, user_data: Dict[str, Any]):
    """
    Actualiza o inserta el perfil de un usuario en la colección users
    usando su user_id de Telegram.
    """
    if not db.is_connected or db.db is None:
        logger.error("Database is not connected. Cannot update user data.")
        return

    try:
        users_collection = db.db.users
        result = await users_collection.update_one(
            {"user_id": user_id},
            {"$set": user_data},
            upsert=True,
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
    """Devuelve el estado actual de la conexión con la base de datos."""
    return db.is_connected


# -------------------------------------------------------------------
#  AUTENTICACIÓN
# -------------------------------------------------------------------
async def find_user_by_credentials(name: str, last_name: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Busca un usuario en SmartBreathing.users usando:
        - nombre
        - apellido
        - codigo (password de 4 dígitos como string)
    """
    if not db.is_connected or db.db is None:
        logger.error("Database is not connected. Cannot find user.")
        return None

    try:
        users_collection = db.db.users

        query = {
            "nombre": name,
            "apellido": last_name,
            "codigo": password,  # "0001", "1221", etc. como string
        }
        logger.info(f"Buscando usuario con query: {query}")

        user = await users_collection.find_one(query)
        logger.info(f"Resultado búsqueda usuario: {user}")
        return user

    except Exception as e:
        logger.error(f"Error finding user: {e}")
        return None


# -------------------------------------------------------------------
#  HELPERS SOBRE USUARIOS Y CONTEXTO
# -------------------------------------------------------------------
async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Devuelve un usuario por su _id de Mongo (string u ObjectId)."""
    if not db.is_connected or db.db is None:
        logger.error("Database is not connected. Cannot get user.")
        return None

    try:
        users_collection = db.db.users
        oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        return await users_collection.find_one({"_id": oid})
    except Exception as e:
        logger.error(f"Error getting user by id: {e}")
        return None


async def update_user_condition_detail(user_id: str, detail: str) -> None:
    """
    Guarda el detalle de la condición limitante en SmartBreathing.users
    campo: condicion_limitante_detalle
    """
    if not db.is_connected or db.db is None:
        logger.error("Database is not connected. Cannot update user condition.")
        return

    try:
        users_collection = db.db.users
        oid = ObjectId(user_id)
        await users_collection.update_one(
            {"_id": oid},
            {"$set": {"condicion_limitante_detalle": detail}},
        )
        logger.info(f"Updated condition detail for user {user_id}")
    except Exception as e:
        logger.error(f"Error updating user condition detail: {e}")


# -------------------------------------------------------------------
#  COLECCIÓN RegistroUsuarioEjercicio
# -------------------------------------------------------------------
async def get_latest_user_exercise_record(user_id: str) -> Optional[Dict[str, Any]]:
    """
    De la colección RegistroUsuarioEjercicio:
      - _id
      - idUsuario (ref a Users)
      - idEjercicio (ref a Ejercicios)
      - fecha_interaccion
      - resultados o métricas

    Devuelve el registro más reciente para ese usuario.
    """
    if not db.is_connected or db.db is None:
        return None

    try:
        col = db.db.RegistroUsuarioEjercicio
        oid = ObjectId(user_id)
        docs = await (
            col.find({"idUsuario": oid})
            .sort("fecha_interaccion", -1)
            .limit(1)
            .to_list(1)
        )
        return docs[0] if docs else None
    except Exception as e:
        logger.error(f"Error getting latest user exercise record: {e}")
        return None


# -------------------------------------------------------------------
#  COLECCIÓN Mediciones
# -------------------------------------------------------------------
async def get_latest_measurements_for_user(user_id: str) -> List[Dict[str, Any]]:
    """
    De la colección Mediciones:
      - _id
      - idUsuario
      - tipoDeMedicion (grasa, ECG, CO2, etc.)
      - valor
      - fecha_medicion
      - quien_realizo
      - parametros_adicionales

    Devuelve solo las mediciones de las **dos últimas fechas** distintas.
    """
    if not db.is_connected or db.db is None:
        return []

    try:
        col = db.db.Mediciones
        oid = ObjectId(user_id)

        cursor = col.find({"idUsuario": oid}).sort("fecha_medicion", -1)
        all_docs = await cursor.to_list(length=200)

        dates = []
        selected = []

        for doc in all_docs:
            fecha = doc.get("fecha_medicion")
            if isinstance(fecha, datetime):
                key = fecha.date()
            else:
                key = str(fecha)[:10]

            if key not in dates:
                dates.append(key)

            if len(dates) <= 2:
                selected.append(doc)
            else:
                break

        return selected

    except Exception as e:
        logger.error(f"Error getting latest measurements: {e}")
        return []


# -------------------------------------------------------------------
#  CONTEXTO COMPLETO DE USUARIO
# -------------------------------------------------------------------
async def get_full_user_context(user_id: str) -> Dict[str, Any]:
    """
    Devuelve un objeto con:
      - user: documento de SmartBreathing.users
      - latest_exercise_record: último RegistroUsuarioEjercicio
      - latest_measurements: Mediciones de las dos fechas más recientes
    """
    user = await get_user_by_id(user_id)
    latest_exercise = await get_latest_user_exercise_record(user_id)
    measurements = await get_latest_measurements_for_user(user_id)

    return {
        "user": user,
        "latest_exercise_record": latest_exercise,
        "latest_measurements": measurements,
    }


# -------------------------------------------------------------------
#  COLECCIÓN ejercicios_asignados
# -------------------------------------------------------------------
async def save_assigned_routine(user_id: str, routine: Dict[str, Any]) -> None:
    """
    Guarda una rutina en SmartBreathing.ejercicios_asignados.

    Estructura aproximada que guardamos:
      - idUsuario (ObjectId)
      - fecha_creacion_rutina (datetime)
      - fecha_ejercicio (datetime)  -> por ahora igual a creación
      - dias_semana (lista de str)
      - nombre, descripcion, duracion, intensidad
      - resultados: "por_hacer" / "finalizado"
    """
    if not db.is_connected or db.db is None:
        logger.error("Database is not connected. Cannot save routine.")
        return

    try:
        col = db.db.ejercicios_asignados
        oid = ObjectId(user_id)
        now = datetime.utcnow()

        dias_semana = routine.get("dias_semana", [])

        docs = []
        for ex in routine.get("exercises", []):
            docs.append(
                {
                    "idUsuario": oid,
                    "fecha_creacion_rutina": now,
                    "fecha_ejercicio": now,
                    "dias_semana": dias_semana,
                    "nombre": ex.get("name"),
                    "descripcion": ex.get("description"),
                    "duracion": ex.get("duration"),
                    "intensidad": ex.get("intensity"),
                    "resultados": "por_hacer",
                }
            )

        if docs:
            await col.insert_many(docs)
            logger.info(f"Saved {len(docs)} assigned exercises for user {user_id}")

    except Exception as e:
        logger.error(f"Error saving assigned routine: {e}")


async def get_latest_assigned_routine(user_id: str) -> List[Dict[str, Any]]:
    """
    Devuelve todos los ejercicios pertenecientes a la rutina
    con la fecha_creacion_rutina más reciente.
    """
    if not db.is_connected or db.db is None:
        return []

    try:
        col = db.db.ejercicios_asignados
        oid = ObjectId(user_id)

        latest_doc = (
            await col.find({"idUsuario": oid})
            .sort("fecha_creacion_rutina", -1)
            .limit(1)
            .to_list(1)
        )

        if not latest_doc:
            return []

        latest_date = latest_doc[0]["fecha_creacion_rutina"]

        cursor = col.find(
            {"idUsuario": oid, "fecha_creacion_rutina": latest_date}
        )
        return await cursor.to_list(length=100)

    except Exception as e:
        logger.error(f"Error getting latest assigned routine: {e}")
        return []


async def update_assigned_exercise_result(exercise_id: str, result: str) -> None:
    """
    Actualiza el campo 'resultados' de un ejercicio asignado individual.
    result -> "finalizado" o "por_hacer"
    """
    if not db.is_connected or db.db is None:
        return

    try:
        col = db.db.ejercicios_asignados
        oid = ObjectId(exercise_id)
        await col.update_one({"_id": oid}, {"$set": {"resultados": result}})
    except Exception as e:
        logger.error(f"Error updating exercise result: {e}")


async def all_exercises_done_for_routine(user_id: str, fecha_creacion_rutina: datetime) -> bool:
    """
    Comprueba si todos los ejercicios de una rutina están marcados como 'finalizado'.
    """
    if not db.is_connected or db.db is None:
        return False

    try:
        col = db.db.ejercicios_asignados
        oid = ObjectId(user_id)

        count_pending = await col.count_documents(
            {
                "idUsuario": oid,
                "fecha_creacion_rutina": fecha_creacion_rutina,
                "resultados": {"$ne": "finalizado"},
            }
        )
        return count_pending == 0

    except Exception as e:
        logger.error(f"Error checking if all exercises done: {e}")
        return False
