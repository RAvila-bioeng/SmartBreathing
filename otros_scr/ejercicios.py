import os
from dotenv import load_dotenv

import pandas as pd
from pymongo import MongoClient

# Cargar variables de entorno (.env en la raíz del proyecto)
load_dotenv()

# --- CONFIGURACIÓN --- #

# Ruta al Excel ACTUALIZADO (cámbiala si lo guardaste con otro nombre)
EXCEL_PATH = r"C:\Users\rober\OneDrive\Escritorio\UFV\Cuarto\Prototype\database_unificado_con_deporte.xlsx"
# Si tu archivo se llama distinto, por ejemplo:
# EXCEL_PATH = r"C:\Users\rober\OneDrive\Escritorio\UFV\Cuarto\Prototype\database_unificado_con_deporte.xlsx"

SHEET_NAME = 0  # primera hoja del Excel

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://root:example@localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "SmartBreathing")
COLLECTION_NAME = "Ejercicios"


def main():
    print(f"Usando MONGODB_URI: {MONGO_URI}")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # 1) Borrar colección de ejercicios
    print(f"Borrando todos los documentos de {DB_NAME}.{COLLECTION_NAME}...")
    result = collection.delete_many({})
    print(f"Documentos eliminados: {result.deleted_count}")

    # 2) Leer Excel
    print(f"Leyendo Excel desde: {EXCEL_PATH}")
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)

    # Opcional: eliminar filas completamente vacías
    df = df.dropna(how="all")

    # Comprobar que la columna 'deporte' existe
    if "deporte" not in df.columns:
        print("⚠️ ADVERTENCIA: la columna 'deporte' no existe en el Excel.")
        print("   El script seguirá, pero el backend no podrá filtrar bien por deporte.")
    else:
        print("✅ Columna 'deporte' encontrada en el Excel.")

    # 3) Convertir a lista de documentos
    docs = df.to_dict(orient="records")
    print(f"Número de filas a insertar: {len(docs)}")

    if not docs:
        print("❌ No hay filas en el Excel. ¿Hoja correcta? ¿Rutas bien?")
        return

    # 4) Insertar en Mongo
    result_insert = collection.insert_many(docs)
    print(f"Documentos insertados: {len(result_insert.inserted_ids)}")
    print("✅ Importación completada correctamente.")


if __name__ == "__main__":
    main()
