from pymongo import MongoClient

uri ="mongodb+srv://smartindustriesibm:prototipoIBM1@SmartBreathing.udn6puq.mongodb.net/?retryWrites=true&w=majority&appName=SmartBreathing"
try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    print(client.list_database_names())
    print("✅ Conexión establecida correctamente")
except Exception as e:
    print(f"❌ Error al conectar: {e}")
