import pandas as pd
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Cargar variables de entorno (incluyendo MONGODB_URI)
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = "SmartBreathing"
COLLECTION_NAME = "Ejercicios" # Nombre de tu colección

# 1. Leer el archivo Excel
try:
    # Ruta a tu archivo Excel
    # Cambia '\' por '/'
    excel_file = "C:/Users/rober/Downloads/ejercicios_gimnasio_extendido.xlsx"
    # Lee la primera hoja del archivo en un DataFrame de pandas
    df = pd.read_excel(excel_file) 
    
    # Rellena cualquier valor NaN (nulo) si es necesario, por ejemplo, con None o un valor por defecto
    df = df.where(pd.notna(df), None) 

except FileNotFoundError:
    print(f"Error: No se encontró el archivo {excel_file}")
    exit()

# 2. Transformación: Convertir el DataFrame a una lista de diccionarios
# 'records' asegura que cada fila se convierte en un objeto JSON/Diccionario
data_to_insert = df.to_dict('records')

# 3. Carga: Conectar a MongoDB e insertar los datos
try:
    # Conexión sincrona (puedes usar 'motor' si prefieres asíncrona)
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # Insertar la lista de documentos
    result = collection.insert_many(data_to_insert)
    
    print(f"✅ Subida exitosa! Se insertaron {len(result.inserted_ids)} documentos.")
    
except Exception as e:
    print(f"❌ Error al conectar o insertar en MongoDB: {e}")

finally:
    if 'client' in locals():
        client.close()