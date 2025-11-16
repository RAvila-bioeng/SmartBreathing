import os
import asyncio
import motor.motor_asyncio
from dotenv import load_dotenv
import logging

# Configuración básica del logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Carga variables del archivo .env
load_dotenv()

# --- Configuración de la DB ---
MONGODB_URI = os.getenv("MONGODB_URI")
# Usamos el nombre de base de datos que identificamos previamente: "SmartBreathing"
DB_NAME = os.getenv("MONGODB_DB_NAME", "SmartBreathing") 
COLLECTION_NAME = "Ejercicios"

async def vaciar_coleccion_ejercicios():
    """
    Se conecta a MongoDB y elimina todos los documentos de la colección 'ejercicios'.
    """
    if not MONGODB_URI:
        logger.error("❌ MONGODB_URI no está configurada. Verifica tu archivo .env.")
        return

    client = None
    try:
        logger.info(f"Intentando conectar a MongoDB y base de datos '{DB_NAME}'...")
        client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
        
        # Prueba la conexión
        await client.admin.command('ping')
        
        db = client[DB_NAME]
        coleccion = db[COLLECTION_NAME]

        logger.info(f"Conexión exitosa. Preparando para vaciar la colección '{COLLECTION_NAME}'...")

        # --- OPERACIÓN CLAVE: ELIMINAR TODOS LOS DOCUMENTOS ---
        # El filtro vacío {} significa 'todos los documentos'
        resultado = await coleccion.delete_many({})
        
        # Muestra el resultado
        logger.info(f"✅ Éxito: Se eliminaron {resultado.deleted_count} documentos de la colección '{COLLECTION_NAME}'.")

    except Exception as e:
        logger.error(f"❌ Error durante la conexión o la operación: {e}")
        
    finally:
        if client:
            client.close()
            logger.info("Conexión cerrada.")

if __name__ == "__main__":
    asyncio.run(vaciar_coleccion_ejercicios())