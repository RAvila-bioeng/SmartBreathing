import os
import math
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# ==== CARGAR .env ====
# Esto busca un archivo .env en el mismo directorio donde ejecutes el script
load_dotenv()

# Intentamos leer la URI de Mongo desde variables de entorno
MONGO_URI = (
    os.getenv("MONGO_URI") 
    or os.getenv("MONGODB_URI")
)

if not MONGO_URI:
    raise RuntimeError(
        "No se ha encontrado MONGO_URI ni MONGODB_URI en el .env.\n"
        "Añade algo como:\n\n"
        "MONGO_URI=mongodb://usuario:password@localhost:27017\n"
    )

# ==== CONFIGURACIÓN ====
DB_NAME = "SmartBreathing"
COLLECTION_NAME = "Ejercicios"  # respeta el nombre tal como está en Mongo

# Ruta ABSOLUTA a tu Excel
EXCEL_PATH = r"C:\Users\rober\OneDrive\Escritorio\UFV\Cuarto\Prototype\database_unificado_con_deporte.xlsx"
SHEET_NAME = "Sheet1"  # cámbialo si tu hoja se llama distinto

def nan_to_none(value):
    """Convierte NaN de pandas a None para que Mongo lo acepte bien."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value

def main():
    print(f"Usando MONGO_URI: {MONGO_URI}")
    # 1) Conectar a Mongo
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    col = db[COLLECTION_NAME]

    # 2) Borrar colección actual
    print(f"Borrando todos los documentos de {DB_NAME}.{COLLECTION_NAME}...")
    result = col.delete_many({})
    print(f"Documentos eliminados: {result.deleted_count}")

    # 3) Leer Excel
    print(f"Leyendo Excel desde: {EXCEL_PATH}")
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)

    # 4) Convertir filas a dict y limpiar NaN
    records = df.to_dict(orient="records")
    cleaned_records = []
    for r in records:
        cleaned = {k: nan_to_none(v) for k, v in r.items()}
        cleaned_records.append(cleaned)

    if not cleaned_records:
        print("No se han encontrado filas en el Excel. Nada que insertar.")
        return

    # 5) Insertar en Mongo
    insert_result = col.insert_many(cleaned_records)
    print(f"Documentos insertados: {len(insert_result.inserted_ids)}")

    print("✅ Importación completada correctamente.")

if __name__ == "__main__":
    main()
